# -*- coding: utf-8 -*-
"""UI 层：自动更新对话框 + 启动时后台检查。

职责：
- UpdateDialog：显示版本信息、下载进度，提供"立即更新/跳过此版本/稍后"按钮
- check_update_on_startup：启动时静默检查（后台线程，发现新版本才弹窗）

设计说明：
- 启动检查延迟 5 秒执行，检查请求在 CheckWorker 后台线程执行（2026-09-09 修复：
  原实现直接在主线程调 updater.check_for_update，网络超时会卡死 UI 最长 45s）
- 仅通过 GitHub API 查询版本号，不下载任何文件
- 用户确认后再启动 UpdateWorker 下载并应用
- "跳过此版本"持久化到 _update_config.json（updater.PROTECTED_CONFIG_FILES 保护，
  更新覆盖时不会丢失），同版本启动检查不再弹窗，手动检查不受限
"""
import modern_dialog as dialog
import json
import os
import sys
import logging

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit
)

import updater
from update_worker import UpdateWorker


# GitHub 仓库全名（app.py.UPDATE_REPO 传入；此处仅作独立调用时的默认值）
DEFAULT_REPO = 'jinhao29/SMTY-desktop'


# ============================================================
# "跳过此版本"持久化（_update_config.json）
# ============================================================

def _update_config_path() -> str:
    """返回更新配置文件路径（应用根目录，打包/源码模式均适配）。"""
    if getattr(sys, 'frozen', False):
        here = os.path.dirname(sys.executable)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, '_update_config.json')


def load_skip_version(path: str = None) -> str:
    """读取用户跳过的版本号。无记录/文件损坏返回 ''。"""
    p = path or _update_config_path()
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return str(data.get('skip_version', '') or '')
    except (OSError, ValueError):
        return ''


def save_skip_version(version: str, path: str = None) -> bool:
    """记录用户跳过的版本号。传空字符串等于清除记录。"""
    p = path or _update_config_path()
    try:
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'skip_version': version}, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


# ============================================================
# 后台检查线程（2026-09-09 新增：所有检查请求不再占用主线程）
# ============================================================

class CheckWorker(QThread):
    """仅检查版本的后台线程（不做下载）。

    finished_sig 参数：updater.check_for_update 的返回 dict；None 表示检查失败。
    """

    finished_sig = Signal(object)

    def __init__(self, repo: str, parent=None):
        super().__init__(parent)
        self._repo = repo

    def run(self):
        try:
            self.finished_sig.emit(updater.check_for_update(self._repo))
        except Exception as e:
            logging.exception('后台检查更新失败')
            self.finished_sig.emit(None)


# ============================================================
# 更新对话框
# ============================================================

class UpdateDialog(QDialog):
    """更新检查与下载对话框。"""

    def __init__(self, parent=None, repo: str = DEFAULT_REPO, info: dict = None):
        super().__init__(parent)
        self.setWindowTitle('检查更新')
        self.resize(480, 360)
        self._repo = repo
        self._info = info
        self._worker = None
        self._check_worker = None
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
        self.btn_skip = QPushButton('跳过此版本', objectName='secondary')
        self.btn_skip.clicked.connect(self._on_skip)
        self.btn_skip.setEnabled(False)
        self.btn_close = QPushButton('关闭', objectName='secondary')
        self.btn_close.clicked.connect(self.reject)
        btn_lay.addWidget(self.btn_check)
        btn_lay.addWidget(self.btn_update)
        btn_lay.addWidget(self.btn_skip)
        btn_lay.addWidget(self.btn_close)
        lay.addLayout(btn_lay)

    def _render_info(self, info: dict):
        """渲染版本信息到 UI。"""
        self.btn_check.setEnabled(True)
        if not info:
            self.lbl_title.setText('检查失败')
            self.lbl_version.setText('无法获取版本信息，请检查网络或仓库配置。')
            self.btn_update.setEnabled(False)
            self.btn_skip.setEnabled(False)
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
        # 已跳过该版本则提示（手动查看时仍可"立即更新"，只标记状态）
        if has_update and load_skip_version() == latest:
            self.lbl_version.setText(
                self.lbl_version.text() + '    （你已跳过此版本）'
            )
        self.btn_skip.setEnabled(has_update)

    def _on_check(self):
        """后台线程检查版本（2026-09-09 修复：不再阻塞主线程）。"""
        self.lbl_title.setText('正在检查更新...')
        self.btn_check.setEnabled(False)
        self.btn_update.setEnabled(False)
        self.btn_skip.setEnabled(False)
        self._check_worker = CheckWorker(self._repo, parent=self)
        self._check_worker.finished_sig.connect(self._on_check_finished)
        self._check_worker.start()

    def _on_check_finished(self, info):
        """检查线程结束回调（主线程执行）。"""
        self._info = info
        self._render_info(info or {})

    def _on_update(self):
        """启动后台下载并应用更新。"""
        if self._worker is not None and self._worker.isRunning():
            return
        self.btn_update.setEnabled(False)
        self.btn_check.setEnabled(False)
        self.btn_skip.setEnabled(False)
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

    def _on_skip(self):
        """记录"跳过此版本"，同版本启动检查不再弹窗（手动检查仍可见）。"""
        latest = (self._info or {}).get('latest_version', '')
        if latest and save_skip_version(latest):
            self.btn_skip.setEnabled(False)
            self.btn_update.setEnabled(False)
            self.lbl_title.setText(f'已跳过版本 {latest}')
            self.lbl_version.setText(
                self.lbl_version.text() + '    （已记录跳过，新版本发布后会再次提醒）'
            )
        else:
            dialog.warn(self, '提示', '记录跳过版本失败（配置文件写入受阻）。')


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
        # 后台线程执行检查（2026-09-09 修复：原实现直接在主线程发网络请求）
        worker = CheckWorker(repo, parent=parent_window)

        def _on_result(info):
            try:
                if not info:
                    return
                if not info.get('has_update'):
                    return
                latest = info.get('latest_version', '')
                # 用户跳过的版本不再打扰（手动"检查更新"不受限）
                if latest and load_skip_version() == latest:
                    return
                dlg = UpdateDialog(parent=parent_window, repo=repo, info=info)
                dlg.exec()
            except Exception:
                logging.exception('启动更新检查弹窗失败')

        worker.finished_sig.connect(_on_result)
        worker.start()
        # 持有引用避免被 GC（QThread 坑：无引用即销毁，running 中销毁直接崩）
        if not hasattr(parent_window, '_update_check_workers'):
            parent_window._update_check_workers = []
        parent_window._update_check_workers.append(worker)

    timer = QTimer(parent_window)
    timer.setSingleShot(True)
    timer.timeout.connect(_do_check)
    timer.start(delay_ms)
    # 持有引用避免被 GC
    if not hasattr(parent_window, '_update_check_timers'):
        parent_window._update_check_timers = []
    parent_window._update_check_timers.append(timer)
