# -*- coding: utf-8 -*-
"""协调层：GitHub 自动更新 QThread Worker。

职责：
- 在后台线程执行 updater.perform_update 完整流程
- 通过信号向 UI 层报告进度和最终结果
- 避免网络调用阻塞 Qt 主线程

信号：
- progress(downloaded, total, message)：进度更新
- finished(success, message)：流程结束
"""
from PySide6.QtCore import QThread, Signal

import updater


class UpdateWorker(QThread):
    """后台更新执行线程。"""

    # 信号：(已下载字节数, 总字节数, 消息文本)
    progress = Signal(int, int, str)
    # 信号：(是否成功, 消息文本)
    finished_sig = Signal(bool, str)

    def __init__(self, repo: str, parent=None):
        super().__init__(parent)
        self._repo = repo

    def run(self):
        """线程入口：执行完整更新流程。"""
        try:
            success, msg = updater.perform_update(
                self._repo,
                progress_cb=self._on_progress,
            )
            self.finished_sig.emit(success, msg)
        except Exception as e:
            self.finished_sig.emit(False, f'更新失败：{e}')

    def _on_progress(self, downloaded: int, total: int, message: str):
        """将 updater 的进度回调转发为 Qt 信号。"""
        self.progress.emit(downloaded, total, message)
