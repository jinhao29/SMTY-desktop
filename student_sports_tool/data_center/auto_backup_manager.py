# -*- coding: utf-8 -*-
"""管理层：自动无感备份调度器（QThread + QTimer）。

职责：
- 每日凌晨 4:00 触发一次自动备份（QTimer 定时）
- 提供 trigger_now() 供外部主动触发（如 do_restore 成功后）
- 调用 backup_coordinator.do_auto_backup 执行实际打包与清理
- 通过信号通知 UI 更新状态栏（"上次自动备份：YYYY-MM-DD HH:MM"）
- 读取 config_manager.auto_backup_enabled 决定是否执行

设计原则：
- 后台线程：所有 IO 在 worker 线程执行，不阻塞 UI 主线程
- 静默执行：失败仅记录日志，不弹窗
- 可配置：用户可在配置文件或 UI 中开启/关闭

与 Android 端 AutoBackupScheduler 的区别：
- Android 端基于数据变更 + 10 分钟防抖触发（签退后 10 分钟静默备份）
- 桌面端基于每日凌晨 4:00 定时触发 + 恢复后立即触发
"""
import logging
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

import config_manager
import backup_coordinator

logger = logging.getLogger(__name__)


class AutoBackupWorker(QObject):
    """自动备份工作线程（在 QThread 中运行）。

    通过 QTimer 在 worker 线程内定时触发，避免占用主线程。
    """

    # 备份完成信号：参数为 (success: bool, message: str, timestamp: str)
    backup_finished = Signal(bool, str, str)

    def __init__(self, get_dir_cb, parent=None):
        """
        参数:
            get_dir_cb: 无参回调，返回当前档案目录路径（主线程安全读取）
        """
        super().__init__(parent)
        self._get_dir_cb = get_dir_cb
        self._timer = None

    def start(self):
        """启动定时器：每分钟检查一次是否到达凌晨 4:00。"""
        # QTimer 必须在所属线程的事件循环中创建
        self._timer = QTimer(self)
        self._timer.setInterval(60 * 1000)  # 1 分钟检查一次
        self._timer.timeout.connect(self._check_and_run)
        self._timer.start()
        logger.info('自动备份调度器已启动，每日凌晨 4:00 触发')

    @Slot()
    def stop(self):
        """停止定时器。"""
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

    @Slot()
    def trigger_now(self):
        """立即触发一次自动备份（外部主动调用，如恢复后）。

        通过 QTimer.singleShot 投递到 worker 线程的事件循环执行，
        保证线程安全。
        """
        QTimer.singleShot(0, self._do_backup)

    def _check_and_run(self):
        """每分钟检查：按配置频率触发自动备份。

        - daily：每日凌晨 4:00 触发
        - weekly：每周一凌晨 4:00 触发
        - manual：不自动触发，仅外部调用 trigger_now()
        """
        now = datetime.now()
        if now.minute != 0 or now.hour != 4:
            return
        freq = self._get_frequency()
        if freq == 'manual':
            return
        if freq == 'weekly' and now.weekday() != 0:
            return
        self._do_backup()

    def _get_frequency(self):
        """读取备份频率配置（daily/weekly/manual）。"""
        try:
            cfg = config_manager.load_config('')
            return cfg.get('auto_backup_frequency', 'daily')
        except Exception:
            return 'daily'

    def _do_backup(self):
        """执行一次自动备份（在 worker 线程中运行）。"""
        try:
            dir_path = self._get_dir_cb() if self._get_dir_cb else ''
            if not dir_path:
                logger.info('档案目录未设置，跳过自动备份')
                return

            # 调用 backup_coordinator.do_auto_backup
            success, zip_path, message = backup_coordinator.do_auto_backup(
                dir_path, progress_cb=None
            )

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            self.backup_finished.emit(success, message, timestamp)

            if success:
                logger.info(f'自动备份成功：{zip_path}')
            else:
                logger.warning(f'自动备份未执行或失败：{message}')
        except Exception as e:
            logger.error(f'自动备份异常：{e}', exc_info=True)
            self.backup_finished.emit(False, f'自动备份异常：{e}',
                                      datetime.now().strftime('%Y-%m-%d %H:%M'))


class AutoBackupManager(QObject):
    """自动备份管理器（协调层）：管理 worker 线程生命周期。

    使用方式：
        manager = AutoBackupManager(get_dir_cb)
        manager.start()  # 启动定时备份
        manager.trigger_now()  # 立即触发一次
        manager.stop()  # 停止（应用退出时）

    信号：
        backup_finished：备份完成，UI 据此更新状态栏
    """

    backup_finished = Signal(bool, str, str)

    def __init__(self, get_dir_cb, parent=None):
        super().__init__(parent)
        self._thread = QThread()
        self._worker = AutoBackupWorker(get_dir_cb)
        self._worker.moveToThread(self._thread)
        self._worker.backup_finished.connect(self._on_backup_finished)
        # 线程启动后调用 worker.start 初始化 QTimer
        self._thread.started.connect(self._worker.start)
        self._thread.finished.connect(self._worker.deleteLater)

    def start(self):
        """启动自动备份调度（应用启动后调用）。"""
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self):
        """停止自动备份调度（应用退出时调用）。"""
        if self._thread.isRunning():
            # 通过 invokeMethod 在 worker 线程停止 QTimer
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self._worker, 'stop', Qt.QueuedConnection)
            self._thread.quit()
            self._thread.wait(3000)

    def trigger_now(self):
        """立即触发一次自动备份（恢复后等场景）。"""
        from PySide6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(self._worker, 'trigger_now', Qt.QueuedConnection)

    def _on_backup_finished(self, success, message, timestamp):
        """备份完成回调：转发信号给 UI。"""
        self.backup_finished.emit(success, message, timestamp)

    def get_last_backup_time(self):
        """读取上次自动备份时间戳（用于 UI 初始化展示）。"""
        try:
            cfg = config_manager.load_config('')
            return cfg.get('last_auto_backup_at', '')
        except Exception:
            return ''

    def is_enabled(self):
        """读取自动备份开关状态。"""
        try:
            cfg = config_manager.load_config('')
            return cfg.get('auto_backup_enabled', True)
        except Exception:
            return True

    def set_enabled(self, enabled):
        """开启/关闭自动备份。"""
        try:
            config_manager.update_config('', auto_backup_enabled=enabled)
            logger.info(f'自动备份已{"开启" if enabled else "关闭"}')
        except Exception as e:
            logger.error(f'更新自动备份开关失败：{e}')
