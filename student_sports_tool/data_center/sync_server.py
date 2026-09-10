# -*- coding: utf-8 -*-
"""服务层：PC 端双端同步 HTTP 服务（LAN / USB 共用，标准库实现）。

与 Android 端 LanSyncManager.kt 的协议：
    POST /upload              接收手机备份 ZIP → 安全校验 → 自动合并到档案目录
    GET  /sync/students.xlsx  学员汇总 Excel（手机拉取后经 ExcelSync 导入合并）
    GET  /sync/version        数据版本号（档案目录 xlsx 最新 mtime）
    GET  /health              健康检查

复用链路：
- 校验：backup_validator.validate_backup_zip（与 auto_sync 共用）
- 合并：backup_coordinator.do_restore（默认「已存在跳过创建、合并课时」策略，
  恢复前自动备份 + 时光机快照由其内置）
- 导出：sync_exporter.build_phone_sync_excel

两种运行形态：
1. 桌面端主程序内嵌（data_center/sync_panel.py，QThread 中跑 create_server）
2. 独立控制台（android_app/desktop_sync/backup_receiver.py 薄壳 → 本模块 main()）

线程模型：ThreadingHTTPServer；合并用模块级互斥锁串行化（多线程上传安全）。
"""
import json
import logging
import os
import secrets
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_logger = logging.getLogger(__name__)

# 服务内日志级别字符串 → logging 级别（_log 的 level 参数为自定义字符串）
_LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARN': logging.WARNING,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
}

DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 8765
DEFAULT_SAVE_DIR = 'backups'
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB 上限

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

# 合并互斥锁：并发上传串行化，避免多线程同时写档案目录
_merge_lock = threading.Lock()

# 设备登记锁：/device/hello 并发写 config 串行化
_device_lock = threading.Lock()
_last_device_touch = 0.0  # v23.10：业务请求触发的设备在线刷新节流


def _to_int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def ensure_tool_paths(tool_root: str = ''):
    """确保桌面端各扁平导入路径可用（主程序已注入时幂等）。"""
    root = tool_root or _PARENT
    for p in (root,
              os.path.join(root, 'data_center'),
              os.path.join(root, 'data_center', 'backup'),
              os.path.join(root, 'student_profile')):
        if p not in sys.path:
            sys.path.insert(0, p)
    return root


class SyncRequestHandler(BaseHTTPRequestHandler):
    """双端同步 HTTP 请求处理器。"""

    # v23.6.1：升级 HTTP/1.1（默认 1.0 每响应后关连接，手机端 okhttp 连接池
    # 复用死连接导致 "unexpected end of stream"——POST /upload 后立即 GET
    # students.xlsx 的同步时序必现）。HTTP/1.1 + Content-Length 标准 keep-alive。
    protocol_version = 'HTTP/1.1'

    # 通过类属性传递启动配置
    server_token: str = ''
    save_dir: str = DEFAULT_SAVE_DIR
    archive_dir: str = ''          # 空 = 仅保存不合并（兼容模式）
    pc_name: str = ''              # PC 名称（hello 响应 / 手机端展示）
    log_cb = None                  # 可选：外部日志回调（内嵌 UI / 控制台共用）
    status_cb = None               # v23.11：同步结果回调 ('merge_ok', message)

    # === 路由 ===
    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/health':
            self._send_text(200, 'OK')
        elif path == '/sync/students.xlsx':
            self._handle_export_students()
        elif path == '/sync/packages.json':
            self._handle_export_packages()
        elif path == '/sync/pc_data.json':
            self._handle_export_pc_data()
        elif path == '/sync/version':
            self._handle_sync_version()
        else:
            self._send_json(404, {'code': 1, 'message': 'Not Found'})

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == '/upload':
            self._handle_upload()
        elif path == '/device/hello':
            self._handle_device_hello()
        else:
            self._send_json(404, {'code': 1, 'message': 'Not Found'})

    # === 鉴权（/health 豁免） ===
    def _check_token(self) -> bool:
        if not self.server_token:
            return True
        if self.headers.get('X-Sync-Token', '') == self.server_token:
            self._touch_device()
            return True
        self._send_json(401, {'code': 1, 'message': 'Unauthorized: token mismatch'})
        self._log('鉴权失败', level='ERROR')
        return False

    def _touch_device(self):
        """v23.10：业务请求即在线。USB / 蜂窝场景手机收不到心跳广播、不发 hello，
        但每次同步必然产生带 token 的业务请求——凭 X-Device-Name 头（缺省按来源
        回退）刷新 sync_devices 的 last_seen，顶栏在线指示即可覆盖 USB 场景。
        30s 模块级节流；与 hello 共用同名记录（按 name 匹配既有键，避免双条）。"""
        global _last_device_touch
        now = time.time()
        if now - _last_device_touch < 30:
            return
        device_name = (self.headers.get('X-Device-Name') or '').strip()
        if not device_name:
            src = self.client_address[0]
            device_name = '手机（USB）' if src == '127.0.0.1' else '手机（%s）' % src
        _last_device_touch = now
        with _device_lock:
            try:
                from data_center.config_manager import load_config, update_config
                cfg = load_config(self.archive_dir)
                devices = cfg.get('sync_devices') or {}
                exist_key = next(
                    (k for k, v in devices.items() if v.get('name') == device_name), None)
                key = exist_key or device_name
                dev = devices.get(key) or {}
                ts = time.strftime('%Y-%m-%d %H:%M:%S')
                # v23.10：连接即同步——设备首次出现或离线超 5 分钟后重新出现，
                # 广播一次让手机自动跟上（合并路径不广播，无死循环风险）
                reonline = False
                if dev.get('last_seen'):
                    try:
                        last = time.mktime(time.strptime(
                            dev['last_seen'], '%Y-%m-%d %H:%M:%S'))
                        reonline = (now - last) > 300
                    except (ValueError, TypeError, OSError):
                        reonline = False
                else:
                    reonline = True  # 首次接入也广播：新设备空库立即拉取灌数据
                devices[key] = {
                    'name': device_name,
                    'first_seen': dev.get('first_seen') or ts,
                    'last_seen': ts,
                    'trusted': dev.get('trusted', True),
                }
                update_config(self.archive_dir, {'sync_devices': devices})
                if reonline:
                    try:
                        from data_center.sync_beacon import notify_data_changed
                        notify_data_changed()
                        self._log('设备上线：%s → 已通知自动同步' % device_name)
                    except Exception:
                        pass
            except Exception:
                pass

    # === 上传：保存 + 校验 + 合并 ===
    def _handle_upload(self):
        if not self._check_token():
            return
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            self._send_json(400, {'code': 1, 'message': 'invalid Content-Length'})
            return
        if content_length <= 0:
            self._send_json(400, {'code': 1, 'message': 'empty body'})
            return
        if content_length > MAX_CONTENT_LENGTH:
            self._send_json(413, {'code': 1,
                                  'message': 'Payload Too Large: max %d bytes' % MAX_CONTENT_LENGTH})
            return

        # 文件名（防路径穿越：仅保留文件名部分）
        client_name = self.headers.get('X-Backup-Name', '').strip()
        safe_name = os.path.basename(client_name.replace('\\', '/')) if client_name else ''
        if not safe_name:
            safe_name = self._auto_name()

        os.makedirs(self.save_dir, exist_ok=True)
        save_path = os.path.join(self.save_dir, safe_name)
        try:
            remaining = content_length
            with open(save_path, 'wb') as f:
                while remaining > 0:
                    chunk_size = min(64 * 1024, remaining)
                    chunk = self.rfile.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            self._log('接收成功：%s (%d bytes)' % (safe_name, os.path.getsize(save_path)))
        except Exception as e:
            try:
                if os.path.exists(save_path):
                    os.remove(save_path)
            except OSError:
                pass
            self._send_json(500, {'code': 1, 'message': 'save failed: %s' % e})
            self._log('接收失败：%s' % e, level='ERROR')
            return

        # 兼容模式：未配置档案目录 → 仅保存
        if not self.archive_dir:
            self._send_json(200, {'code': 0, 'restored': 0,
                                  'message': 'saved (merge disabled)'})
            return

        # 校验 + 合并（串行化）
        with _merge_lock:
            ok, message, restored = self._merge_backup(save_path)
        if ok:
            self._send_json(200, {'code': 0, 'restored': restored, 'message': message})
        else:
            # 文件保留供人工检查，不污染档案目录
            self._send_json(422, {'code': 1, 'restored': 0, 'message': message})

    def _merge_backup(self, zip_path: str):
        """校验并把手机备份合并到档案目录。返回 (ok, message, restored_count)。"""
        ensure_tool_paths()
        try:
            from backup_validator import validate_backup_zip
            from data_center.backup_coordinator import do_restore
        except Exception as e:
            return False, '无法加载合并模块：%s' % e, 0

        ok, reason = validate_backup_zip(zip_path)
        if not ok:
            self._log('安全校验拒绝：%s（%s）' % (os.path.basename(zip_path), reason),
                      level='ERROR')
            return False, '安全校验拒绝：%s' % reason, 0

        # v23.8 安全锁：零内容备份不得合并进非空档案目录（防手机端清库后反复推空备份）
        try:
            from backup_validator import reject_wiped_backup
            ok, reason = reject_wiped_backup(zip_path, self.archive_dir)
        except Exception as e:
            ok, reason = True, ''
            self._log('安全锁检查异常（放行）：%s' % e, level='WARN')
        if not ok:
            self._log('安全锁拒绝：%s（%s）' % (os.path.basename(zip_path), reason),
                      level='ERROR')
            return False, reason, 0

        # v23.12 多租户防串库：备份 zip 的工作模式必须与 PC 当前模式一致
        # （手机在俱乐部模式备的库绝不能合并进上门体育档案目录，反之亦然）
        try:
            from data_center.mode_guard import check_backup_mode
            ok, reason = check_backup_mode(zip_path, self.archive_dir)
        except Exception as e:
            ok, reason = True, ''
            self._log('租户校验异常（放行）：%s' % e, level='WARN')
        if not ok:
            self._log('租户校验拒绝：%s（%s）' % (os.path.basename(zip_path), reason),
                      level='ERROR')
            return False, reason, 0

        def on_progress(msg: str):
            self._log('  [合并] %s' % msg)

        try:
            restored, _auto_bak = do_restore(zip_path, self.archive_dir,
                                             progress_cb=on_progress)
            message = '已合并 %d 个档案（%s）' % (restored, os.path.basename(zip_path))
            self._log('合并完成：%s' % message)
            # v23.11：通知 UI 层（顶栏点亮「同步完成」），回调异常不阻断响应
            if SyncRequestHandler.status_cb:
                try:
                    SyncRequestHandler.status_cb('merge_ok', message)
                except Exception:
                    pass
            return True, message, restored
        except Exception as e:
            self._log('合并失败：%s' % e, level='ERROR')
            return False, '合并失败：%s' % e, 0

    # === 学员 Excel 拉取（PC→手机） ===
    def _handle_export_students(self):
        if not self._check_token():
            return
        if not self.archive_dir:
            self._send_json(400, {'code': 1, 'message': 'archive-dir not configured'})
            return
        ensure_tool_paths()
        try:
            from data_center.sync_exporter import build_phone_sync_excel
        except Exception as e:
            self._send_json(500, {'code': 1, 'message': 'export module error: %s' % e})
            return

        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.xlsx', prefix='smty_sync_')
        os.close(tmp_fd)
        try:
            count = build_phone_sync_excel(self.archive_dir, tmp_path)
            if count <= 0:
                self._send_json(404, {'code': 1, 'message': 'no students to export'})
                return
            with open(tmp_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header(
                'Content-Type',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.send_header('Content-Disposition',
                             'attachment; filename="students_sync.xlsx"')
            self.send_header('Content-Length', str(len(data)))
            # v23.12：告知手机本机工作模式，手机端据此防串库
            from data_center.mode_guard import dir_mode
            self.send_header('X-Workspace-Mode', dir_mode(self.archive_dir))
            self.end_headers()
            self.wfile.write(data)
            self._log('学员同步包已下发：%d 名学员（%d bytes）' % (count, len(data)))
        except Exception as e:
            self._log('导出失败：%s' % e, level='ERROR')
            try:
                self._send_json(500, {'code': 1, 'message': 'export failed: %s' % e})
            except Exception:
                pass
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    # === 课时包 JSON 下发（PC→手机，v23.7 新增） ===
    def _handle_export_packages(self):
        """GET /sync/packages.json：课时汇总（PC 录入的课时包）下发手机。

        数据源：课时记录.xlsx 汇总（lesson_manager.get_summary）。
        返回: {"code":0, "packages":[{studentName,totalLessons,usedLessons}]}
        手机端按姓名 upsert 进本地课时包（无则建、有则更新总量与已用）。
        """
        if not self._check_token():
            return
        if not self.archive_dir:
            self._send_json(400, {'code': 1, 'message': 'archive-dir not configured'})
            return
        ensure_tool_paths()
        try:
            from lesson_manager import get_summary
            summaries = get_summary(self.archive_dir, use_phone_used=False)
        except Exception as e:
            self._log('课时包导出失败：%s' % e, level='ERROR')
            self._send_json(500, {'code': 1, 'message': 'export failed: %s' % e})
            return
        packages = [
            {
                'studentName': s['name'],
                'totalLessons': int(s.get('total') or 0),
                'usedLessons': int(s.get('attended') or 0),
            }
            for s in summaries
        ]
        self._send_json(200, {'code': 0, 'packages': packages})
        self._log('课时包已下发：%d 名学员' % len(packages))

    # === PC 数据总包下发（PC→手机，v23.8 新增） ===
    def _handle_export_pc_data(self):
        """GET /sync/pc_data.json：课时包汇总 + 课时明细 + 收费记录 一次下发。

        手机端拉取后做三件事（对账语义见 双端同步协议.md）：
        1. 课时包总量对账（单调不减，PC 空数据不动手机现值）
        2. PC 消课差值对账（PC 独录的消课折算进手机课时包已用）
        3. 收费记录镜像入库（只读展示，PC 为唯一权威源，删除不传播）
        旧端点 /sync/packages.json 保留给旧版手机。
        """
        if not self._check_token():
            return
        if not self.archive_dir:
            self._send_json(400, {'code': 1, 'message': 'archive-dir not configured'})
            return
        ensure_tool_paths()
        try:
            from lesson_manager import get_summary, get_detail, _norm_date as lm_norm_date
            from fee_manager import get_payments
            from data_center.mode_guard import dir_mode
            # 纯明细口径：手机端拉取对账只认课时明细，PC「手机已消」列不回灌
            summaries = get_summary(self.archive_dir, use_phone_used=False)
            details = get_detail(self.archive_dir)
            payments = get_payments(self.archive_dir)
            ws_mode = dir_mode(self.archive_dir)
        except Exception as e:
            self._log('PC 数据导出失败：%s' % e, level='ERROR')
            self._send_json(500, {'code': 1, 'message': 'export failed: %s' % e})
            return
        packages = [
            {
                'studentName': s['name'],
                'totalLessons': int(s.get('total') or 0),
                'usedLessons': int(s.get('attended') or 0),
            }
            for s in summaries
        ]
        # 课时明细：日期归一化为 ISO 字符串（PC 单元格可能是 datetime）
        lessons = []
        for rec in details:
            d = lm_norm_date(rec.get('date'))
            lessons.append({
                'studentName': rec.get('name'),
                'date': d.isoformat() if d else str(rec.get('date') or ''),
                'count': _to_int(rec.get('count')),
                'content': str(rec.get('content') or ''),
                'note': str(rec.get('note') or ''),
            })
        fees = [
            {
                'studentName': p['name'],
                'date': p['date'],
                'amount': float(p.get('amount') or 0),
                'hours': float(p.get('hours') or 0),
                'method': str(p.get('method') or ''),
                'note': str(p.get('note') or ''),
            }
            for p in payments
        ]
        self._send_json(200, {
            'code': 0,
            'generatedAt': int(time.time() * 1000),
            # v23.12：本机工作模式随数据下发，手机端据此防串库
            'workspaceMode': ws_mode,
            'packages': packages,
            'lessons': lessons,
            'fees': fees,
        })
        self._log('PC 数据总包已下发：%d 学员 / %d 课时明细 / %d 收费记录'
                  % (len(packages), len(lessons), len(fees)))

    # === 设备发现回执（手机 → PC：登记设备指纹，供信任管理） ===
    def _handle_device_hello(self):
        """手机收到心跳后回执设备指纹（v23.5）。

        Body: {"type":"phone_hello","device_id":"<ANDROID_ID>",
               "device_name":"<Build.MODEL>","timestamp":<ms>}
        写入 config 的 sync_devices：{device_id: {name, first_seen, last_seen, trusted}}
        信任状态由教练在数据中心面板确认；响应携带 trusted 供手机端展示。
        """
        if not self._check_token():
            return
        if not self.archive_dir:
            self._send_json(400, {'code': 1, 'message': 'archive-dir not configured'})
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
        except Exception:
            body = {}
        device_id = str(body.get('device_id', '')).strip()
        device_name = str(body.get('device_name', '')).strip() or '未知设备'
        if not device_id:
            self._send_json(400, {'code': 1, 'message': 'device_id required'})
            return

        with _device_lock:
            try:
                from data_center.config_manager import load_config, update_config
                cfg = load_config(self.archive_dir)
                devices = cfg.get('sync_devices') or {}
                dev = devices.get(device_id) or {}
                is_new = not dev  # v23.6：首次回执 → PC 端托盘提示（log_cb 链路匹配前缀）
                # v23.6.1：距上次回执超 5 分钟 = 重新上线，同样提示
                is_reonline = False
                if dev.get('last_seen'):
                    try:
                        last = time.mktime(time.strptime(
                            dev['last_seen'], '%Y-%m-%d %H:%M:%S'))
                        is_reonline = (time.time() - last) > 300
                    except (ValueError, TypeError, OSError):
                        pass
                devices[device_id] = {
                    'name': device_name,
                    'first_seen': dev.get('first_seen') or time.strftime('%Y-%m-%d %H:%M:%S'),
                    'last_seen': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'trusted': bool(dev.get('trusted')),
                }
                update_config(self.archive_dir, sync_devices=devices)
                trusted = bool(devices[device_id]['trusted'])
            except Exception as e:
                self._log('设备登记失败：%s' % e, level='ERROR')
                self._send_json(500, {'code': 1, 'message': 'register failed'})
                return
        if is_new:
            self._log('发现新设备：%s（请在数据中心「双端同步」面板确认信任）' % device_name,
                      level='WARN')
        elif is_reonline:
            self._log('设备上线：%s' % device_name)  # v23.10：降为纯日志（后台静默）
        self._log('设备回执：%s（%s）· %s'
                  % (device_name, device_id[:8], '已信任' if trusted else '待信任'))
        self._send_json(200, {'code': 0, 'trusted': trusted,
                              'pc_name': SyncRequestHandler.pc_name})

    # === 数据版本号 ===
    def _handle_sync_version(self):
        if not self._check_token():
            return
        if not self.archive_dir:
            self._send_json(400, {'code': 1, 'message': 'archive-dir not configured'})
            return
        latest = 0.0
        count = 0
        try:
            for name in os.listdir(self.archive_dir):
                if name.endswith('.xlsx') and not name.startswith('~$'):
                    count += 1
                    mtime = os.path.getmtime(os.path.join(self.archive_dir, name))
                    if mtime > latest:
                        latest = mtime
            # v23.10：PC「同步手机」按钮会 touch 信号文件计入 version——
            # 手机在线探测循环（USB/蜂窝也通）据此发现"PC 要求同步"的跳变
            signal_path = os.path.join(self.archive_dir, '.cache', '.sync_signal')
            if os.path.exists(signal_path):
                latest = max(latest, os.path.getmtime(signal_path))
        except OSError as e:
            self._send_json(500, {'code': 1, 'message': 'scan failed: %s' % e})
            return
        self._send_json(200, {'code': 0, 'version': int(latest), 'students': count})

    # === 工具 ===
    def _auto_name(self) -> str:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        return 'smty_backup_%s.smty_backup' % ts

    def _send_text(self, code: int, text: str) -> None:
        body = text.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _log(self, msg: str, level: str = 'INFO') -> None:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = '[%s] [%s] %s' % (ts, level, msg)
        if SyncRequestHandler.log_cb:
            try:
                SyncRequestHandler.log_cb(line)
                return
            except Exception:
                # 回调抛异常时回退到 logging，避免日志彻底丢失
                _logger.exception('同步日志回调失败，回退到 logging')
        # 无 UI 回调（控制台 / 服务模式）时走 logging，便于统一收集与落盘
        _logger.log(_LEVEL_MAP.get(level.upper(), logging.INFO), line)

    def log_message(self, format, *args):
        pass


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  save_dir: str = DEFAULT_SAVE_DIR, token: str = '',
                  archive_dir: str = '', log_cb=None,
                  pc_name: str = '', status_cb=None) -> ThreadingHTTPServer:
    """创建同步服务实例（serve_forever 由调用方驱动）。

    参数:
        archive_dir: 档案目录；非空启用自动合并与 Excel 拉取
        log_cb: 日志回调（内嵌 UI 传信号发射器；控制台传 None 走 print）
        pc_name: PC 名称（手机端 hello 响应展示）
        status_cb: v23.11 同步结果回调 (kind, message)，如 ('merge_ok', '已合并 9 个档案')
    """
    # P1 修复：禁止空 token 放行。
    # 原实现 token='' 时 _check_token 直接 return True，同网段任何设备都能
    # 上传/拉取全部学员数据。现改为：调用方未提供 token 时自动生成随机 token，
    # 保证鉴权始终生效；手机端需通过 hello 响应或二维码获取该 token 后同步。
    effective_token = (token or '').strip()
    if not effective_token:
        effective_token = secrets.token_urlsafe(24)
        _logger.warning('未配置同步 token，已自动生成随机 token —— 手机端需重新配对方可同步')
    SyncRequestHandler.server_token = effective_token
    SyncRequestHandler.save_dir = save_dir or DEFAULT_SAVE_DIR
    SyncRequestHandler.archive_dir = archive_dir or ''
    SyncRequestHandler.pc_name = pc_name or ''
    SyncRequestHandler.log_cb = log_cb
    SyncRequestHandler.status_cb = status_cb
    os.makedirs(SyncRequestHandler.save_dir, exist_ok=True)
    return ThreadingHTTPServer((host, port), SyncRequestHandler)


def main():
    """独立控制台入口（backup_receiver.py 薄壳调用）。"""
    import argparse
    parser = argparse.ArgumentParser(
        description='上门体育桌面端双端同步服务 v23',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python backup_receiver.py --archive-dir "G:/smty_archive"
  python backup_receiver.py --port 8765 --archive-dir "G:/smty_archive" --token secret

USB 连接:
  adb reverse tcp:8765 tcp:8765  然后手机端 syncHost 填 127.0.0.1
        """)
    parser.add_argument('--host', default=DEFAULT_HOST)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--save-dir', default=DEFAULT_SAVE_DIR)
    parser.add_argument('--archive-dir', default='',
                        help='档案目录（学员档案.xlsx 所在目录），启用自动合并与 Excel 拉取')
    parser.add_argument('--token', default='')
    args = parser.parse_args()

    ensure_tool_paths()
    if args.archive_dir:
        archive_dir = os.path.normpath(os.path.abspath(args.archive_dir))
    else:
        archive_dir = ''

    server = create_server(args.host, args.port, args.save_dir,
                           args.token, archive_dir, log_cb=None)

    # token 状态必须在 create_server 之后取：未配置时 create_server 会自动生成随机 token，
    # 提前按 args.token 判断会误报「未启用」。
    effective_token = getattr(SyncRequestHandler, 'server_token', '') or ''

    print('=' * 60, flush=True)
    print('上门体育桌面端双端同步服务 v23', flush=True)
    print('=' * 60, flush=True)
    print('监听地址: http://%s:%d' % (args.host, args.port), flush=True)
    print('保存目录: %s' % os.path.abspath(args.save_dir), flush=True)
    print('档案目录: %s' % (archive_dir or '未配置（仅保存不合并）'), flush=True)
    if effective_token:
        print('鉴权 token: 已启用', flush=True)
        if not args.token:
            print('           本次自动生成: %s' % effective_token, flush=True)
            print('           （手机端经 UDP 心跳自动获取，无需手填）', flush=True)
    else:
        print('鉴权 token: 未启用（警告：任何局域网设备均可写入）', flush=True)
    print('USB 连接: adb reverse tcp:%d tcp:%d，手机端 syncHost 填 127.0.0.1' % (args.port, args.port), flush=True)
    print('按 Ctrl+C 停止服务', flush=True)
    print('=' * 60, flush=True)
    # 控制台模式同样广播心跳（手机端「自动发现 PC」）
    beacon = None
    if archive_dir:
        try:
            from data_center.sync_beacon import SyncBeacon
            beacon = SyncBeacon(service_port=args.port)
            beacon.start()
            print('心跳广播: 已开启（UDP %d，手机端可自动发现）' % 9112, flush=True)
        except Exception as e:
            print('心跳广播: 启动失败（%s）' % e, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n正在停止服务...', flush=True)
        if beacon is not None:
            beacon.stop()
        server.shutdown()
        print('已停止', flush=True)
