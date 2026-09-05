# -*- coding: utf-8 -*-
"""管理层：手机备份目录自动同步。

职责：
- QTimer 每分钟扫描 config_manager 中设定的「手机备份同步目录」
- 检测到新的 .zip 备份文件时，自动调用 backup_coordinator.do_restore
- 完成后在 Windows 托盘区弹出通知（委托 tray_notifier）
- 已处理的 zip 文件名记入 synced_zip_history，避免重复恢复
- 同步在后台 QThread 执行，避免阻塞 UI

使用方式（app.py 启动时）：
    from auto_sync import AutoSyncManager
    sync_mgr = AutoSyncManager(parent=main_window, archive_dir_getter=lambda: archive_dir)
    sync_mgr.start()  # 启动每分钟定时扫描
    # 用户修改同步目录时：
    sync_mgr.reload_config()
"""
import os
import time
import logging
from PySide6.QtCore import QObject, QTimer, QThread, Signal, Slot, Qt

# 引入父目录模块
_HERE = os.path.dirname(os.path.abspath(__file__))
import sys
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import tray_notifier


# ===== 备份内容安全校验 =====
# 实现 已下沉至 backup_validator.py（无 GUI 依赖，供主程序与 sync_server 共用）；
# 此处 re-export 保持既有 import 路径兼容
from backup_validator import BLOCKED_EXTS as _BLOCKED_EXTS, validate_backup_zip  # noqa: F401


# ===== 同步工作线程 =====

class SyncWorker(QThread):
    """后台执行 do_restore 的工作线程。

    信号:
        progress(str): 进度消息
        finished_ok(str): 成功消息（含恢复文件数）
        failed(str): 失败原因
    """
    progress = Signal(str)
    finished_ok = Signal(str, int)  # (消息, 恢复文件数)
    failed = Signal(str)

    def __init__(self, zip_path: str, target_dir: str, parent=None):
        super().__init__(parent)
        self._zip_path = zip_path
        self._target_dir = target_dir

    def run(self):
        try:
            # P0 修复：恢复前内容安全校验，默认拒绝路径穿越 / 可执行文件等可疑备份
            ok, reason = validate_backup_zip(self._zip_path)
            if not ok:
                self.failed.emit(f'自动同步已拒绝：{reason}')
                return

            # v23.8 安全锁：零内容备份不得合并进非空档案目录（防清空）
            from backup_validator import reject_wiped_backup
            ok, reason = reject_wiped_backup(self._zip_path, self._target_dir)
            if not ok:
                self.failed.emit(reason)
                return

            # 延迟导入避免循环
            from data_center import backup_coordinator as bc
            count = 0
            messages = []

            def on_progress(msg: str):
                messages.append(msg)
                self.progress.emit(msg)

            count, _auto_bak = bc.do_restore(
                self._zip_path, self._target_dir,
                progress_cb=on_progress,
            )
            self.finished_ok.emit(
                f'自动同步完成：共恢复 {count} 个档案\n来源：{os.path.basename(self._zip_path)}',
                count,
            )
        except Exception as e:
            logging.exception('自动同步恢复失败')
            self.failed.emit(f'自动同步失败：{e}')


# ===== 自动同步管理器 =====

class AutoSyncManager(QObject):
    """自动同步管理器：QTimer 定时扫描 + 后台 do_restore + 托盘通知。

    信号:
        syncState(str): 同步状态变化，取值 idle / syncing / ok / error，
                        供主窗口顶部状态指示器展示

    生命周期由父 QObject 管理（通常传入 main_window 作为 parent）。
    """
    syncState = Signal(str)

    def __init__(self, parent=None, archive_dir_getter=None,
                 sync_dir_getter=None, interval_ms: int = 60_000):
        """
        参数:
            parent: 父 QObject（通常为 MainWindow）
            archive_dir_getter: 返回当前档案目录的可调用对象
            sync_dir_getter: 可选，返回手机备份同步目录的可调用对象；
                             若为 None 则从 config_manager 读取
            interval_ms: 扫描间隔，默认 60000ms（1 分钟）
        """
        super().__init__(parent)
        self._parent = parent
        self._get_archive_dir = archive_dir_getter or (lambda: '')
        self._get_sync_dir = sync_dir_getter
        self._interval_ms = interval_ms

        # 当前活跃的 worker（同一时间只允许一个恢复任务）
        self._worker: SyncWorker = None

        # QTimer 定时扫描
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_timeout)
        # 跟踪上次扫描时目录下的 zip 文件名集合，用于检测「新增」文件
        self._last_seen_files: set = set()
        # 首次扫描标记：首次扫描不触发通知，只记录基线
        self._first_scan = True

    # ===== 生命周期 =====

    def start(self):
        """启动定时扫描。"""
        if not self._timer.isActive():
            self._timer.start(self._interval_ms)
        # 启动后立即执行一次基线扫描，避免应用启动时已存在的 zip 被误触发
        self._scan_once(is_initial=True)
        self.syncState.emit('idle')

    def stop(self):
        """停止定时扫描。"""
        if self._timer.isActive():
            self._timer.stop()

    def reload_config(self):
        """用户修改同步目录后调用，立即重新扫描。"""
        self._first_scan = True
        self._last_seen_files.clear()
        self._scan_once(is_initial=True)

    def set_interval(self, interval_ms: int):
        """调整扫描间隔。"""
        self._interval_ms = max(10_000, interval_ms)  # 最低 10 秒
        if self._timer.isActive():
            self._timer.start(self._interval_ms)

    # ===== 内部逻辑 =====

    def _resolve_sync_dir(self) -> str:
        """解析当前应监听的手机备份同步目录。"""
        if self._get_sync_dir:
            return self._get_sync_dir() or ''
        # 从 config_manager 读取
        try:
            from data_center import config_manager as cm
            archive_dir = self._get_archive_dir() or ''
            cfg = cm.load_config(archive_dir)
            return cfg.get('phone_backup_sync_dir', '') or ''
        except Exception:
            logging.exception('解析同步目录失败')
            return ''

    def _load_synced_history(self) -> set:
        """从 config_manager 加载已处理的 zip 文件名集合。"""
        try:
            from data_center import config_manager as cm
            archive_dir = self._get_archive_dir() or ''
            cfg = cm.load_config(archive_dir)
            history = cfg.get('synced_zip_history', [])
            if isinstance(history, list):
                return set(str(x) for x in history)
        except Exception:
            logging.exception('加载已处理 zip 历史失败')
        return set()

    def _save_synced_history(self, history: set):
        """持久化已处理的 zip 文件名集合（超过 100 条自动清理旧记录）。"""
        try:
            from data_center import config_manager as cm
            archive_dir = self._get_archive_dir() or ''
            # 限制历史记录长度
            history_list = list(history)
            if len(history_list) > 100:
                history_list = history_list[-100:]
            cm.update_config(archive_dir, synced_zip_history=history_list)
        except Exception:
            logging.exception('保存已处理 zip 历史失败')

    def _on_timeout(self):
        """QTimer 触发：执行一次目录扫描。"""
        self._scan_once(is_initial=False)

    def _scan_once(self, is_initial: bool = False):
        """扫描同步目录，检测新增 zip 并触发恢复。

        参数:
            is_initial: True 表示首次扫描，仅建立基线，不触发恢复
        """
        sync_dir = self._resolve_sync_dir()
        if not sync_dir or not os.path.isdir(sync_dir):
            # 同步目录未配置或不存在：静默跳过
            return

        # 列出当前所有 .zip 文件
        try:
            current_files = {
                f for f in os.listdir(sync_dir)
                if f.lower().endswith('.zip') and not f.startswith('~$')
            }
        except OSError:
            return

        # 加载已处理历史
        synced_history = self._load_synced_history()

        # 计算本次需要处理的新 zip：当前存在 + 未在历史记录中
        new_zips = current_files - synced_history

        if is_initial:
            # 首次扫描：把当前所有 zip 记入基线，不触发恢复
            # 但允许用户手动把已处理 zip 删掉重新触发同步
            self._last_seen_files = current_files
            # 将已存在的 zip 加入历史，避免应用启动时把陈旧备份全部恢复一遍
            if new_zips:
                self._save_synced_history(synced_history | new_zips)
            return

        # 非首次扫描：只处理真正「新增」的 zip
        # 新增 = 当前存在 + 不在 last_seen_files + 不在 synced_history
        truly_new = new_zips - self._last_seen_files
        self._last_seen_files = current_files

        if not truly_new:
            return

        # 同一时间只允许一个恢复任务
        if self._worker is not None and self._worker.isRunning():
            tray_notifier.notify(
                '自动同步跳过',
                f'检测到 {len(truly_new)} 个新备份，但当前已有同步任务在执行，已跳过',
                severity='warning',
            )
            return

        # 取最早新增的一个 zip 处理（避免一次性恢复多个造成混乱）
        # 按 mtime 排序，最早的最优先
        def _zip_mtime(name):
            try:
                return os.path.getmtime(os.path.join(sync_dir, name))
            except OSError:
                return time.time()

        zip_name = sorted(truly_new, key=_zip_mtime)[0]
        zip_path = os.path.join(sync_dir, zip_name)
        archive_dir = self._get_archive_dir() or ''
        if not archive_dir:
            tray_notifier.notify(
                '自动同步失败',
                f'档案目录未设置，无法恢复 {zip_name}',
                severity='warning',
            )
            return

        # 启动后台 worker
        tray_notifier.notify(
            '检测到新备份',
            f'正在自动同步：{zip_name}',
            severity='info',
        )
        self._worker = SyncWorker(zip_path, archive_dir, parent=self)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished_ok.connect(self._on_worker_ok)
        self._worker.failed.connect(self._on_worker_failed)
        self.syncState.emit('syncing')
        # 标记为已处理（即使后续失败也不重试，避免死循环）
        synced_history.add(zip_name)
        self._save_synced_history(synced_history)
        self._worker.start()

    @Slot(str)
    def _on_worker_progress(self, msg: str):
        """worker 进度消息（静默记录，不打扰用户）。"""
        # 可在此扩展为日志写入
        pass

    @Slot(str, int)
    def _on_worker_ok(self, msg: str, count: int):
        """worker 成功完成：托盘通知。"""
        tray_notifier.notify('自动同步完成', msg, severity='info')
        # 通知父窗口刷新学员列表（若实现了 refresh_all 方法）
        if self._parent is not None and hasattr(self._parent, 'refresh_after_sync'):
            try:
                self._parent.refresh_after_sync()
            except Exception:
                logging.exception('同步完成后刷新父窗口失败')
        self._worker = None
        self.syncState.emit('ok')

    @Slot(str)
    def _on_worker_failed(self, reason: str):
        """worker 失败：托盘警告。"""
        tray_notifier.notify('自动同步失败', reason, severity='warning')
        self._worker = None
        self.syncState.emit('error')
