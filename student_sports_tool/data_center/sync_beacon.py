# -*- coding: utf-8 -*-
"""服务层：桌面端在线心跳 UDP 广播器（自动发现链路的 PC 端）。

协议（与 Android UdpDesktopDiscoveryService.kt 严格对齐）：
    目标：255.255.255.255:9112（受限广播，SO_BROADCAST）
    报文：JSON {"type":"desktop_online", "host":"<本机局域网IP>",
                "port":<同步服务端口>, "timestamp":<毫秒>}

Android 端 UdpDesktopDiscoveryService 常驻监听 9112，收到后写入
SharedPreferences（host/port/last_seen_at），设置页「自动发现 PC」据此一键填址。

无 GUI 依赖（纯 socket + json），供内嵌面板与控制台脚本共用。
"""
import json
import logging
import socket
import threading
import time

# Android UdpDesktopDiscoveryService.UDP_PORT（勿单端改动）
UDP_PORT = 9112

# 广播间隔（秒）：3 秒一次，保证手机端"最后在线时间"始终新鲜
DEFAULT_INTERVAL = 3.0


def local_ip() -> str:
    """探测本机局域网 IP（UDP connect trick，不实际发包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()


class SyncBeacon:
    """心跳广播器：后台线程周期广播桌面在线状态。"""

    def __init__(self, service_port: int, interval: float = DEFAULT_INTERVAL,
                 target_host: str = '255.255.255.255',
                 token: str = '', pc_name: str = ''):
        """
        参数:
            service_port: 同步服务端口（写入报文 port 字段，手机端据此填 syncPort）
            interval: 广播间隔秒数
            target_host: 广播目标（默认受限广播 255.255.255.255；
                         测试或单播探测时可指定具体地址）
            token: PC 端同步 token（v23.5 零配置：手机端收到后自动填充）
            pc_name: PC 名称（手机端展示"已连接：XXX"）
        """
        self._service_port = int(service_port)
        self._interval = max(1.0, interval)
        self._target = (target_host, UDP_PORT)
        self._token = token or ''
        self._pc_name = pc_name or ''
        self._stop_event = threading.Event()
        self._thread: threading.Thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name='SyncBeacon')
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1)
            self._thread = None

    def _run(self):
        local = local_ip()
        payload = json.dumps({
            'type': 'desktop_online',
            'host': local,
            'port': self._service_port,
            'timestamp': int(time.time() * 1000),
            # v23.5 零配置配对：手机端收到后自动填充 syncToken 与展示 PC 名称
            'token': self._token,
            'name': self._pc_name,
        }).encode('utf-8')

        # v23.6.1：广播目标全集 —— 受限广播 + 本机各网卡子网定向广播。
        # 部分路由器（AP 隔离/跨网段策略）会丢弃 255.255.255.255 受限广播，
        # 子网定向广播（如 192.168.1.255）穿透率高得多；多目标并发的冗余无害。
        targets = [self._target]
        if self._target[0] == '255.255.255.255':
            for ip in self._subnet_broadcasts(local):
                if (ip, UDP_PORT) not in targets:
                    targets.append((ip, UDP_PORT))

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            while not self._stop_event.is_set():
                for target in targets:
                    try:
                        sock.sendto(payload, target)
                    except OSError as e:
                        # 广播被路由器/防火墙拦截时仅记录，不退出
                        logging.debug('心跳广播失败（%s）：%s', target[0], e)
                self._stop_event.wait(self._interval)
        finally:
            sock.close()

    @staticmethod
    def _subnet_broadcasts(local_ip_str: str):
        """从本机 IP 推导各可能的子网定向广播地址（前两段 + 常见子网掩码展开）。"""
        parts = local_ip_str.split('.')
        if len(parts) != 4:
            return []
        a, b, c, _ = parts
        # 常见家庭/办公网段掩码：/24 为主，附带 /16 与最近邻子网覆盖
        candidates = {f'{a}.{b}.{c}.255', f'{a}.{b}.255.255', f'{a}.{b}.{int(c) + 1}.255'}
        return sorted(candidates)
