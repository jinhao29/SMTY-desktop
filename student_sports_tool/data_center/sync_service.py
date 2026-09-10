# -*- coding: utf-8 -*-
"""服务层：双端同步全局服务管理器（单例，纯 threading，无 Qt 依赖）。

职责（v23.5 设备自动发现与信任）：
- 主程序启动即自动开启同步服务（HTTP + 心跳广播 + USB 自动 reverse），
  不再需要教练手动到数据中心点"启动"
- 心跳报文携带 token 与 PC 名称，手机端零配置自动填充
- 周期检测 adb 设备并对每台在线手机执行 adb reverse（USB 通道自动化）
- 数据中心面板与本管理器共享同一单例（get_service），按钮只做启停切换

线程模型：
- serve / beacon / usb-watch 均为 daemon 线程；stop() 逐一收尾
- 日志通过回调分发（UI 线程安全由调用方保证，如 Qt 用信号转发）
"""
import os
import secrets
import threading
import time
import logging

from data_center.sync_server import create_server

# USB 自动 reverse 轮询间隔（秒）
USB_WATCH_INTERVAL = 15.0

# 心跳广播间隔（秒），与 sync_beacon 默认一致
BEACON_INTERVAL = 3.0


class SyncServiceManager:
    """双端同步服务全局管理器（进程内单例）。"""

    def __init__(self):
        self._server = None
        self._serve_thread: threading.Thread = None
        self._beacon = None
        self._usb_thread: threading.Thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._log_cbs = []
        self._status_cbs = []     # v23.11：手机备份合并成功等同步结果回调
        self.config = {}          # 当前生效配置 {port, token, archive_dir, save_dir}

    # ---------- 日志 ----------
    def add_log_callback(self, cb):
        """注册日志回调（收到行文本）。重复注册由调用方自行去重。"""
        if cb and cb not in self._log_cbs:
            self._log_cbs.append(cb)

    def add_status_callback(self, cb):
        """v23.11：注册同步结果回调（收到 ('merge_ok', message) 元组）。

        手机推送合并成功时触发；UI 层借此把顶栏点亮为「同步完成」。
        回调在 HTTP 工作线程执行，UI 层自行做线程切换。
        """
        if cb and cb not in self._status_cbs:
            self._status_cbs.append(cb)

    def remove_status_callback(self, cb):
        if cb in self._status_cbs:
            self._status_cbs.remove(cb)

    def _emit_status(self, kind: str, message: str):
        for cb in list(self._status_cbs):
            try:
                cb(kind, message)
            except Exception:
                pass

    def remove_log_callback(self, cb):
        if cb in self._log_cbs:
            self._log_cbs.remove(cb)

    def _log(self, msg: str):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = '[%s] [同步] %s' % (ts, msg)
        for cb in list(self._log_cbs):
            try:
                cb(line)
            except Exception:
                pass
        logging.info(msg)

    # ---------- 生命周期 ----------
    def is_running(self) -> bool:
        return self._serve_thread is not None and self._serve_thread.is_alive()

    def start(self, port: int, token: str, archive_dir: str,
              save_dir: str = None, usb_watch: bool = True) -> bool:
        """启动服务（已运行时幂等返回 True）。

        参数:
            archive_dir: 档案目录（合并与导出目标）
            usb_watch: 是否开启 USB 自动 reverse 轮询
        """
        with self._lock:
            if self.is_running():
                return True
            self._stop_event.clear()
            # P1 修复：禁止空 token。原实现空 token 时服务端不鉴权，
            # 同网段任何设备可上传/拉取全部学员数据。
            # 此处集中生成随机 token 并回写 config，保证 server 与 beacon 携带同一值
            # （若只在 create_server 内生成，beacon 仍会广播空 token，手机端无法配对）。
            effective_token = (token or '').strip()
            if not effective_token:
                effective_token = secrets.token_urlsafe(24)
                self._log('未配置同步 token，已自动生成随机 token（手机端将通过 UDP 发现自动获取）')
            self.config = {
                'port': int(port),
                'token': effective_token,
                'archive_dir': archive_dir or '',
                'save_dir': save_dir or os.path.join(archive_dir or '.', '.sync_backups'),
            }
            try:
                self._server = create_server(
                    host='0.0.0.0', port=self.config['port'],
                    save_dir=self.config['save_dir'],
                    token=self.config['token'],
                    archive_dir=self.config['archive_dir'],
                    log_cb=self._log,
                    pc_name=self._pc_name(),
                    status_cb=self._emit_status)
            except OSError as e:
                # 端口被占用等启动失败：不抛出，由调用方提示
                self._log('服务启动失败：%s' % e)
                self._server = None
                return False

            self._serve_thread = threading.Thread(
                target=self._serve_loop, daemon=True, name='SyncService')
            self._serve_thread.start()

            # 心跳广播（携带 token + PC 名称，手机端零配置填充）
            try:
                from data_center.sync_beacon import SyncBeacon
                self._beacon = SyncBeacon(
                    service_port=self.config['port'],
                    interval=BEACON_INTERVAL,
                    token=self.config['token'],
                    pc_name=self._pc_name())
                self._beacon.start()
            except Exception as e:
                logging.exception('心跳广播启动失败')
                self._beacon = None

            # USB 自动 reverse 轮询
            if usb_watch:
                self._usb_thread = threading.Thread(
                    target=self._usb_watch_loop, daemon=True, name='SyncUsbWatch')
                self._usb_thread.start()

            self._log('服务已启动：端口 %d（档案目录 %s）'
                      % (self.config['port'], self.config['archive_dir'] or '未设置'))
            return True

    def stop(self):
        with self._lock:
            self._stop_event.set()
            if self._server is not None:
                try:
                    self._server.shutdown()
                except Exception:
                    pass
                self._server = None
            if self._beacon is not None:
                try:
                    self._beacon.stop()
                except Exception:
                    pass
                self._beacon = None
            self._serve_thread = None
            self._usb_thread = None
            self._log('服务已停止')

    # ---------- 内部 ----------
    def _serve_loop(self):
        try:
            self._server.serve_forever()
        except Exception as e:
            if not self._stop_event.is_set():
                self._log('服务异常退出：%s' % e)
                logging.exception('同步服务异常')

    def _usb_watch_loop(self):
        """周期核验 adb reverse 映射（v23.11 验证式）。

        旧实现「成功一次记 serial 永不重做」：拔插 USB / 手机重连 / adb 重启
        会清空设备侧 reverse 表，之后映射永远缺失、USB 同步通道静默失效
        （2026-09-07 李哥实机踩坑）。改为每轮核验 `reverse --list`，缺了就重建。
        """
        last_logged = set()
        while not self._stop_event.is_set():
            try:
                from data_center.usb_helper import ensure_reverse
                serials = ensure_reverse(self.config.get('port', 8765))
                for s in serials:
                    if s not in last_logged:
                        self._log('USB 设备已自动连接（adb reverse）：%s' % s)
                # 状态变化才打日志：本轮重建过的记下，下一轮核验通过即静默
                if serials:
                    last_logged = set(serials)
                elif last_logged:
                    last_logged = set()
            except Exception as e:
                logging.debug('USB 轮询异常：%s', e)
            self._stop_event.wait(USB_WATCH_INTERVAL)

    @staticmethod
    def _pc_name() -> str:
        try:
            import socket
            return socket.gethostname()
        except Exception:
            return 'PC'


# ---------- 模块级单例 ----------
_service: SyncServiceManager = None
_service_lock = threading.Lock()


def get_service() -> SyncServiceManager:
    global _service
    with _service_lock:
        if _service is None:
            _service = SyncServiceManager()
        return _service
