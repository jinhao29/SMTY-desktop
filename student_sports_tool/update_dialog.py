# -*- coding: utf-8 -*-
"""UI 层：自动更新对话框 + 启动时后台检查。

职责：
- UpdateDialog：显示版本信息、下载进度，提供"立即更新/稍后"按钮
- check_update_on_startup：启动时静默检查（后台线程，发现新版本才弹窗）

设计说明：
- 启动检查延迟 5 秒执行，避免与初始化竞争
- 仅通过 GitHub API 查询版本号，不下载任何文件
- 用户确认后再启动 UpdateWorker 下载并应用
"""
import modern_dialog as dialog
import os
import sys
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QMessageBox, QCheckBox, QTextEdit
)

import updater
from update_worker import UpdateWorker


# 默认 GitHub 仓库（留空则跳过更新检查，开发者发版时请修改为实际仓库地址）
DEFAULT_REPO = ''


class UpdateDialog(QDialog):
    """更新检查与下载对话框。"""

    def __init__(self, parent=None, repo: str = DEFAULT_REPO, info: dict = None):
        super().__init__(parent)
        self.setWindowTitle('检查更新')
        self.resize(480, 360)
        self._repo = repo
        self._info = info
        self._worker = None
        self._init_ui()
        if info:
            self._render_info(info)

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(22, 22, 22, 22)

        # 标题
        self.lbl_title = QLabel('正在检查更新...')
        self.lbl_title.setStyleSheet('font-size:16px; font-weight:bold; color:#1A1A1A;')
        lay.addWidget(self.lbl_title)

        # 版本信息
        self.lbl_version = QLabel('')
        self.lbl_version.setStyleSheet('color:#6B7280; font-size:13px;')
        self.lbl_version.setWordWrap(True)
        lay.addWidget(self.lbl_version)

        # Release notes
        lay.addWidget(QLabel('更新说明：'))
        self.te_notes = QTextEdit()
        self.te_notes.setReadOnly(True)
        self.te_notes.setStyleSheet('background:#F9FAFB; border:1px solid #E5E7EB; border-radius:8px;')
        lay.addWidget(self.te_notes, 1)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.progress)

        # 底部按钮
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        self.btn_check = QPushButton('检查更新', objectName='secondary')
        self.btn_check.clicked.connect(self._on_check)
        self.btn_update = QPushButton('立即更新', objectName='primary')
        self.btn_update.clicked.connect(self._on_update)
        self.btn_update.setEnabled(False)
        self.btn_close = QPushButton('关闭', objectName='secondary')
        self.btn_close.clicked.connect(self.reject)
        btn_lay.addWidget(self.btn_check)
        btn_lay.addWidget(self.btn_update)
        btn_lay.addWidget(self.btn_close)
        lay.addLayout(btn_lay)

    def _render_info(self, info: dict):
        """渲染版本信息到 UI。"""
        if not info:
            self.lbl_title.setText('检查失败')
            self.lbl_version.setText('无法获取版本信息，请检查网络或仓库配置。')
            self.btn_update.setEnabled(False)
            return
        cur = info.get('current_version', '?')
        latest = info.get('latest_version', '?')
        has_update = info.get('has_update', False)
        self.lbl_title.setText(
            f'发现新版本：{latest}' if has_update else '已是最新版本'
        )
        self.lbl_version.setText(f'当前版本：{cur}    最新版本：{latest}')
        release = info.get('release') or {}
        notes = release.get('body', '') or '（无更新说明）'
        self.te_notes.setPlainText(notes)
        self.btn_update.setEnabled(has_update and bool(info.get('asset')))

    def _on_check(self):
        """手动触发检查（前台阻塞，建议仅在用户主动点击时使用）。"""
        self.lbl_title.setText('正在检查更新...')
        self.btn_check.setEnabled(False)
        QApplication_proxy = None
        try:
            from PySide6.QtWidgets import QApplication as QApplication_proxy
        except ImportError:
            pass
        if QApplication_proxy:
            QApplication_proxy.processEvents()
        info = updater.check_for_update(self._repo)
        self.btn_check.setEnabled(True)
        self._info = info
        self._render_info(info or {})

    def _on_update(self):
        """启动后台下载并应用更新。"""
        if self._worker is not None and self._worker.isRunning():
            return
        self.btn_update.setEnabled(False)
        self.btn_check.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat('准备下载...')

        self._worker = UpdateWorker(self._repo, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_sig.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, downloaded: int, total: int, message: str):
        """更新进度条。"""
        if total > 0:
            pct = int(downloaded * 100 / total)
            self.progress.setValue(pct)
            self.progress.setFormat(f'{pct}% - {message}')
        else:
            self.progress.setRange(0, 0)  # 不确定进度
            self.progress.setFormat(message)

    def _on_finished(self, success: bool, message: str):
        """更新流程结束。"""
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.btn_check.setEnabled(True)
        if success:
            dialog.info(self, '更新完成', message + '\n\n应用将重启以完成安装。')
            # 通知主窗口退出（让 bat 脚本接管）
            self.accept()
            # 触发主窗口关闭
            try:
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    app.quit()
            except Exception:
                logging.exception('更新完成触发退出失败')
        else:
            dialog.info(self, '提示', message)
            self.btn_update.setEnabled(
                self._info is not None and self._info.get('has_update', False)
            )


def check_update_on_startup(parent_window, repo: str = DEFAULT_REPO, delay_ms: int = 5000):
    """启动时静默检查更新（延迟执行，发现新版本才弹窗）。

    参数:
        parent_window: 主窗口（用于弹窗父对象）
        repo: GitHub 仓库全名
        delay_ms: 启动后延迟检查的毫秒数
    """
    if not repo:
        return  # 仓库地址未配置，跳过更新检查

    def _do_check():
        try:
            info = updater.check_for_update(repo)
            if not info:
                return
            if not info.get('has_update'):
                return
            # 发现新版本，弹窗提示
            dlg = UpdateDialog(parent=parent_window, repo=repo, info=info)
            dlg.exec()
        except Exception:
            logging.exception('启动更新检查失败')

    timer = QTimer(parent_window)
    timer.setSingleShot(True)
    timer.timeout.connect(_do_check)
    timer.start(delay_ms)
    # 持有引用避免被 GC
    if not hasattr(parent_window, '_update_check_timers'):
        parent_window._update_check_timers = []
    parent_window._update_check_timers.append(timer)
