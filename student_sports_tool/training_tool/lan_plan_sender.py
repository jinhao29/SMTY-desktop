# -*- coding: utf-8 -*-
"""协调层：局域网训练计划截图发送器（纯离线跨端方案）。

职责：
- 截图当前窗口（PySide6 QApplication.primaryScreen().grabWindow()）
- 按 {学员姓名}_{YYYYMMDD}_plan.png 命名保存到本地缓存目录
- 启动极简 HTTP 服务（http.server.ThreadingHTTPServer）供手机端下载
- 通过 UDP 局域网广播（255.255.255.255:9111）通知手机端有新截图

设计原则：
- 纯局域网，完全不依赖外网
- 截图在 Qt 主线程同步执行（按钮点击时调用，耗时仅几十毫秒）
- HTTP 服务 + UDP 广播在后台线程执行，避免阻塞 Qt UI
- HTTP 服务在截图后启动，闲置 60 秒后自动关闭，避免长期占用端口
- 同一时刻仅允许一个 HTTP 服务实例，新截图会复用或重启服务
- 广播内容为 JSON：{host, port, filename, student_name, date, timestamp}

与 Android 端配合：
- Android 端 UdpPlanListenerService 监听 9111 端口接收广播
- 收到广播后弹出 Notification 提示用户
- 用户在设置页点击"同步电脑端截图"按钮，触发 LanImageReceiver 下载
"""
import os
import json
import logging
import socket
import threading
import time
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget


# ===== 协议常量 =====

# UDP 广播端口（Android 端 UdpPlanListenerService 监听同一端口）
UDP_PORT = 9111

# HTTP 服务端口（供手机端下载图片）
HTTP_PORT = 8080

# HTTP 服务闲置超时秒数（无新请求 60 秒后自动关闭）
HTTP_IDLE_TIMEOUT = 60.0

# UDP 广播重复次数（提高到达率）
UDP_BROADCAST_REPEAT = 3

# UDP 广播间隔（秒）
UDP_BROADCAST_INTERVAL = 0.2


class _PlanImageHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器：GET /<filename> 下载截图，POST /upload_moment 上传精彩瞬间。

    安全性：
    - 仅允许下载 CACHE_DIR 目录下的文件，禁止路径穿越（../）
    - 不响应目录列举请求
    - POST 上传限制文件大小（10MB）和扩展名（jpg/png）
    """

    # === v5 新增：POST 上传精彩瞬间照片相关配置 ===
    MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_UPLOAD_EXTS = ('.jpg', '.jpeg', '.png')

    def do_GET(self):
        # 健康检查端点
        if self.path in ('/', '/health'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'lan-plan-sender-ok')
            return

        # 解析请求文件名（去掉前导 / 和查询参数）
        filename = self.path.split('?')[0].lstrip('/')
        if not filename or '..' in filename or '/' in filename or '\\' in filename:
            self.send_error(403, 'Forbidden')
            return

        # 从 handler 持有的 cache_dir 读取文件
        cache_dir = self.server.cache_dir  # type: ignore[attr-defined]
        file_path = os.path.join(cache_dir, filename)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.send_error(404, 'Not Found')
            return

        try:
            file_size = os.path.getsize(file_path)
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(file_size))
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            # 标记最近访问时间（用于闲置超时判断）
            self.server.last_request_time = time.time()  # type: ignore[attr-defined]
        except Exception as e:
            self.send_error(500, f'Internal Server Error: {e}')

    # ============================================================
    # === v5 新增：POST /upload_moment 接收 Android 端精彩瞬间 ===
    # ============================================================

    def do_POST(self):
        """接收 Android 端推送的精彩瞬间照片。

        协议：
        - URL: POST /upload_moment?student={name}&date={YYYYMMDD}
        - Body: 原始二进制图片数据（Content-Type: image/jpeg 或 image/png）
        - 限制：单文件 ≤ 10MB，扩展名 jpg/jpeg/png

        保存位置：
        - data_center/MomentsPhotos/{学员姓名}_{YYYYMMDD}_moment_{HHMMSS}.jpg
        """
        path = self.path.split('?')[0]
        if path != '/upload_moment':
            self.send_error(404, 'Not Found')
            return

        # 从 query 解析学员姓名和日期
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        student_name = (params.get('student', [''])[0] or '').strip()
        date_str = (params.get('date', [''])[0] or '').strip()

        if not student_name:
            self._json_response(400, {'code': 1, 'msg': '缺少 student 参数'})
            return

        # 清理文件名非法字符
        safe_name = ''.join(
            c for c in student_name if c not in r'\/:*?"<>|'
        ) or 'student'
        if not date_str:
            date_str = datetime.now().strftime('%Y%m%d')

        # 检查 Content-Type 决定扩展名
        content_type = self.headers.get('Content-Type', 'image/jpeg').lower()
        if 'png' in content_type:
            ext = '.png'
        else:
            ext = '.jpg'

        # 检查 Content-Length
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            self._json_response(400, {'code': 1, 'msg': '请求体为空'})
            return
        if content_length > self.MAX_UPLOAD_SIZE:
            self._json_response(413, {'code': 1, 'msg': f'文件过大（>{self.MAX_UPLOAD_SIZE//1024//1024}MB）'})
            return

        # 准备保存目录：data_center/MomentsPhotos/
        moments_dir = self._get_moments_dir()
        os.makedirs(moments_dir, exist_ok=True)

        # 生成文件名：{学员}_{日期}_moment_{时分秒}.jpg
        time_str = datetime.now().strftime('%H%M%S')
        filename = f'{safe_name}_{date_str}_moment_{time_str}{ext}'
        save_path = os.path.join(moments_dir, filename)

        # 读取 body 并保存
        try:
            remaining = content_length
            with open(save_path, 'wb') as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            file_size = os.path.getsize(save_path)
        except Exception as e:
            # 清理半成品
            try:
                if os.path.exists(save_path):
                    os.remove(save_path)
            except Exception:
                pass
            self._json_response(500, {'code': 1, 'msg': f'保存失败：{e}'})
            return

        # 触发 UI 通知信号（如已注册）
        server = self.server
        if hasattr(server, 'on_moment_received') and callable(server.on_moment_received):
            try:
                server.on_moment_received(student_name, save_path, file_size)
            except Exception:
                logging.exception('精彩瞬间上传回调异常')

        # 标记最近访问时间
        server.last_request_time = time.time()  # type: ignore[attr-defined]

        self._json_response(200, {
            'code': 0,
            'msg': '上传成功',
            'data': {
                'filename': filename,
                'path': save_path,
                'size': file_size,
                'student': student_name,
                'date': date_str
            }
        })

    def _json_response(self, status: int, payload: dict) -> None:
        """统一 JSON 响应。"""
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _get_moments_dir() -> str:
        """返回精彩瞬间照片保存目录（桌面端主程序目录下的 MomentsPhotos/）。

        优先使用 data_center 目录，找不到则使用主程序目录。
        """
        # 与桌面端主程序同级的 data_center 目录
        # lan_plan_sender 位于 training_tool/，主程序在 student_sports_tool/
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 优先 data_center 子目录（若存在）
        data_center = os.path.join(base, 'data_center')
        if os.path.isdir(data_center):
            return os.path.join(data_center, 'MomentsPhotos')
        # 回退到主程序根目录
        return os.path.join(base, 'MomentsPhotos')

    def log_message(self, format, *args):
        # 静默日志输出（避免污染控制台）
        pass


class LanPlanSender(QObject):
    """局域网训练计划截图发送器（单例）。

    信号：
    - success(message)：截图 + 广播成功
    - failed(message)：截图或广播失败
    - momentReceived(student_name, save_path, file_size)：
        收到 Android 端推送的精彩瞬间照片（v5 新增，用于双向传输）
    """

    # UI 反馈信号（Qt 主线程连接）
    success = Signal(str)
    failed = Signal(str)
    # === v5 新增：精彩瞬间接收信号 ===
    # 参数：(student_name:str, save_path:str, file_size:int)
    momentReceived = Signal(str, str, int)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._cache_dir = os.path.join(
            os.path.expanduser('~'), '.shangmentiyu', 'lan_plan_cache'
        )
        os.makedirs(self._cache_dir, exist_ok=True)

        # HTTP 服务实例（同一时刻仅一个）
        self._http_server: Optional[ThreadingHTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        # 闲置关闭计时线程
        self._idle_watch_thread: Optional[threading.Thread] = None
        self._stop_idle_watch = threading.Event()

        # 最后一次广播的元数据（供 UI 调试查看）
        self._last_broadcast: Optional[dict] = None

    # ===== 公开 API =====

    def capture_and_broadcast(
        self,
        window: QWidget,
        student_name: str,
        date_str: Optional[str] = None
    ) -> None:
        """截图当前窗口 → 保存 → 启动 HTTP → UDP 广播。

        参数：
        - window：要截图的 QWidget（通常为 training_tool 主窗口）
        - student_name：学员姓名（用于文件名前缀）
        - date_str：可选日期字符串 YYYYMMDD，默认今天

        流程：
        1. 在 Qt 主线程同步执行截图（按钮点击时本就在主线程，耗时几十毫秒）
        2. 截图成功后，启动后台线程执行 HTTP + UDP 广播
        3. 后台线程通过 success/failed 信号反馈结果
        """
        if not student_name or not student_name.strip():
            self.failed.emit('学员姓名为空，无法生成截图文件名')
            return

        # 清理文件名中的非法字符
        safe_name = ''.join(
            c for c in student_name.strip() if c not in r'\/:*?"<>|'
        ) or '学员'
        date_str = date_str or datetime.now().strftime('%Y%m%d')
        filename = f'{safe_name}_{date_str}_plan.png'
        file_path = os.path.join(self._cache_dir, filename)

        # 1. 主线程同步截图（调用方在 Qt 主线程，可直接执行 GUI 操作）
        try:
            self._capture_direct(window, file_path)
        except Exception as e:
            self.failed.emit(f'截图失败：{e}')
            return

        if not os.path.exists(file_path):
            self.failed.emit('截图失败：文件未生成')
            return

        # 2. 后台线程执行 HTTP + UDP（避免阻塞 UI）
        threading.Thread(
            target=self._run_network_pipeline,
            args=(file_path, filename, safe_name, date_str),
            daemon=True
        ).start()

    def get_last_broadcast(self) -> Optional[dict]:
        """返回最后一次广播的元数据（供 UI 显示已发送信息）。"""
        return self._last_broadcast

    def shutdown(self) -> None:
        """关闭 HTTP 服务（App 退出时调用）。"""
        self._stop_http_server()

    # ============================================================
    # === v5 新增：精彩瞬间接收回调（HTTP 线程 → Qt 主线程） ===
    # ============================================================

    def _on_moment_received(self, student_name: str, save_path: str, file_size: int) -> None:
        """HTTP 服务线程收到精彩瞬间照片时的回调。

        注意：
        - 此方法在 HTTP 服务线程被调用，禁止直接操作 UI 控件
        - 通过 Qt Signal 投递到主线程，由连接到 [momentReceived] 的槽处理
        - 信号本身是线程安全的，会自动跨线程投递
        """
        try:
            self.momentReceived.emit(student_name, save_path, int(file_size))
        except Exception:
            # 信号发射失败不影响 HTTP 响应
            pass

    # ===== 内部实现 =====

    @staticmethod
    def _capture_direct(window: QWidget, file_path: str) -> None:
        """直接执行截图（仅可在 Qt 主线程调用）。

        截图策略：
        - 优先使用 QApplication.primaryScreen().grabWindow(window.winId())
          （含标题栏，更接近用户视觉感知）
        - 若失败，回退到 QWidget.grab()（仅截取 Widget 内容区域）
        """
        screen = QApplication.primaryScreen()
        if screen is not None:
            try:
                pixmap = screen.grabWindow(int(window.winId()))
                pixmap.save(file_path, 'PNG')
                return
            except Exception:
                pass
        # 回退方案
        pixmap = window.grab()
        pixmap.save(file_path, 'PNG')

    def _run_network_pipeline(
        self,
        file_path: str,
        filename: str,
        student_name: str,
        date_str: str
    ) -> None:
        """后台线程主流程：启动 HTTP → 广播 UDP。"""
        try:
            # 1. 获取局域网 IP
            host_ip = self._get_lan_ip()
            if not host_ip:
                self.failed.emit('未找到局域网 IP，请检查 Wi-Fi 连接')
                return

            # 2. 启动 / 复用 HTTP 服务
            self._ensure_http_server()

            # 3. UDP 广播通知手机端
            broadcast_payload = {
                'host': host_ip,
                'port': HTTP_PORT,
                'filename': filename,
                'student_name': student_name,
                'date': date_str,
                'timestamp': int(time.time()),
                'source': 'shangmentiyu_desktop'
            }
            self._udp_broadcast(broadcast_payload)
            self._last_broadcast = broadcast_payload

            url = f'http://{host_ip}:{HTTP_PORT}/{filename}'
            self.success.emit(
                f'截图已发送：{filename}\n'
                f'手机端访问：{url}\n'
                f'已通过 UDP 广播通知手机端（端口 {UDP_PORT}）'
            )

        except Exception as e:
            self.failed.emit(f'截图发送失败：{e}')

    # ===== HTTP 服务管理 =====

    def _ensure_http_server(self) -> None:
        """确保 HTTP 服务已启动（若已存在则复用，否则新建）。"""
        if self._http_server is not None:
            # 已有服务，更新最近访问时间
            self._http_server.last_request_time = time.time()  # type: ignore[attr-defined]
            return

        try:
            self._create_http_server()
        except OSError:
            # 端口被占用，尝试关闭后重试一次
            try:
                self._stop_http_server()
                self._create_http_server()
            except Exception as retry_e:
                raise RuntimeError(f'HTTP 服务启动失败：{retry_e}')

    def _create_http_server(self) -> None:
        """创建并启动 HTTP 服务实例。"""
        server = ThreadingHTTPServer(
            ('0.0.0.0', HTTP_PORT),
            _PlanImageHTTPHandler
        )
        server.cache_dir = self._cache_dir  # type: ignore[attr-defined]
        server.last_request_time = time.time()  # type: ignore[attr-defined]
        # === v5 新增：注册精彩瞬间接收回调，转发到 Qt 信号 ===
        # 注意：HTTP 处理线程非 Qt 主线程，必须通过 Signal 投递到主线程
        server.on_moment_received = self._on_moment_received  # type: ignore[attr-defined]
        self._http_server = server

        self._http_thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name='LanPlanHTTP'
        )
        self._http_thread.start()

        # 启动闲置监视线程
        self._stop_idle_watch.clear()
        self._idle_watch_thread = threading.Thread(
            target=self._idle_watch_loop,
            daemon=True,
            name='LanPlanIdleWatch'
        )
        self._idle_watch_thread.start()

    def _idle_watch_loop(self) -> None:
        """闲置监视循环：超过 HTTP_IDLE_TIMEOUT 秒无请求则关闭服务。"""
        while not self._stop_idle_watch.is_set():
            self._stop_idle_watch.wait(HTTP_IDLE_TIMEOUT / 2)
            if self._stop_idle_watch.is_set():
                break
            server = self._http_server
            if server is None:
                break
            idle = time.time() - getattr(server, 'last_request_time', time.time())
            if idle >= HTTP_IDLE_TIMEOUT:
                self._stop_http_server()
                break

    def _stop_http_server(self) -> None:
        """关闭 HTTP 服务。"""
        self._stop_idle_watch.set()
        server = self._http_server
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
            self._http_server = None
        self._http_thread = None
        self._idle_watch_thread = None

    # ===== UDP 广播 =====

    def _udp_broadcast(self, payload: dict) -> None:
        """向局域网广播 UDP 数据包（255.255.255.255:UDP_PORT）。

        重复发送 UDP_BROADCAST_REPEAT 次以提高到达率。
        """
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            for _ in range(UDP_BROADCAST_REPEAT):
                try:
                    sock.sendto(data, ('255.255.255.255', UDP_PORT))
                except Exception:
                    pass
                time.sleep(UDP_BROADCAST_INTERVAL)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    @staticmethod
    def _get_lan_ip() -> Optional[str]:
        """获取本机局域网 IP（通过创建临时 UDP socket 探测）。

        原理：连接一个外部地址时，操作系统会自动选择出口网卡对应的本机 IP。
        此处连接 8.8.8.8 仅为获取本机 IP，不会真正发送数据包。
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect(('8.8.8.8', 80))
                ip = sock.getsockname()[0]
                if ip and not ip.startswith('127.'):
                    return ip
            finally:
                sock.close()
        except Exception:
            pass
        # 回退：遍历网卡
        try:
            hostname = socket.gethostname()
            ip_list = socket.getaddrinfo(hostname, None, socket.AF_INET)
            for item in ip_list:
                ip = item[4][0]
                if ip and not ip.startswith('127.') and not ip.startswith('169.254'):
                    return ip
        except Exception:
            pass
        return None


# ===== 单例 =====

_single_instance: Optional[LanPlanSender] = None
_single_lock = threading.Lock()


def get_sender() -> LanPlanSender:
    """获取 LanPlanSender 单例（线程安全）。"""
    global _single_instance
    if _single_instance is None:
        with _single_lock:
            if _single_instance is None:
                _single_instance = LanPlanSender()
    return _single_instance
