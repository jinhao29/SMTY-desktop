# -*- coding: utf-8 -*-
"""UI 层：数据库时光机回滚对话框（v5 优化6 新增）。

职责：
- 显示所有可用数据库快照列表
- 提供时间滑条快速选择回滚点
- 展示快照详情（时间戳、文件大小、触发原因）
- 二次确认 + 回滚后引导重启应用

设计原则：
- 对话框模态显示，避免回滚过程中其他线程读写数据库
- 回滚前再生成保护快照（防撤回），在对话框中明确提示
- 失败时弹出 QMessageBox 详细说明原因
- 整体风格与 DataCenterWindow 的深色主题保持一致
"""
import modern_dialog as dialog
import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox, QSizePolicy
)

import db_snapshot_manager as dsm


class DbSnapshotDialog(QDialog):
    """数据库时光机回滚对话框。

    用法：
        dlg = DbSnapshotDialog(parent)
        if dlg.exec() == QDialog.Accepted:
            # 回滚成功，应用需重启
            ...
    """

    def __init__(self, parent=None, dir_path: str = ''):
        super().__init__(parent)
        self.setWindowTitle('数据库时光机')
        self.setModal(True)
        self.resize(620, 480)
        # 快照/回滚必须作用于当前档案目录的 per-directory 索引库，
        # 否则会操作主程序根目录的孤儿库，导致快照静默失效
        self._dir_path = dir_path or ''
        self._snapshots = []  # [(name, full_path, size)]
        self._current_idx = -1
        self._init_ui()
        self._load_snapshots()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel('时光机快照回滚')
        title.setObjectName('title')
        f = QFont('微软雅黑'); f.setPointSize(16); f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)

        # 说明文字
        desc = QLabel(
            '每次恢复数据前会自动生成一份 SQLite 数据库快照。\n'
            '拖动下方滑条或选择列表项，即可回滚到任意历史状态。\n'
            '回滚前会自动生成一份"保护快照"，可随时撤回。'
        )
        desc.setStyleSheet('color:#6B6B6B; font-size:12px;')
        desc.setWordWrap(True)
        lay.addWidget(desc)

        # 时间滑条
        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)
        slider_row.addWidget(QLabel('回滚点：'))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.slider, 1)
        self.lbl_slider_pos = QLabel('—')
        self.lbl_slider_pos.setMinimumWidth(160)
        self.lbl_slider_pos.setStyleSheet('color:#6B6B6B; font-size:12px;')
        slider_row.addWidget(self.lbl_slider_pos)
        lay.addLayout(slider_row)

        # 快照列表
        list_label = QLabel('可用快照（按时间倒序）：')
        list_label.setStyleSheet('color:#6B6B6B; font-size:12px;')
        lay.addWidget(list_label)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: #FFFFFF;
                color: #1A1A1A;
                border: 1px solid #E5E5E5;
                border-radius: 10px;
                padding: 6px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: #FFEDE8;
                color: #FF6B47;
            }
            QListWidget::item:hover {
                background: #F8F8F8;
            }
        """)
        self.list_widget.currentRowChanged.connect(self._on_list_changed)
        lay.addWidget(self.list_widget, 1)

        # 详情区
        self.lbl_detail = QLabel('')
        self.lbl_detail.setStyleSheet(
            'color:#6B6B6B; font-size:11px; padding:8px 10px;'
            'background:#F5F7FA; border:1px solid #E5E5E5; border-radius:8px;'
        )
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self.lbl_detail)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.btn_refresh = QPushButton('刷新', objectName='secondary')
        self.btn_refresh.clicked.connect(self._load_snapshots)
        btn_row.addWidget(self.btn_refresh)

        self.btn_rollback = QPushButton('回滚到此快照', objectName='primary')
        self.btn_rollback.clicked.connect(self._on_rollback)
        self.btn_rollback.setEnabled(False)
        btn_row.addWidget(self.btn_rollback)

        self.btn_close = QPushButton('关闭', objectName='secondary')
        self.btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_close)

        lay.addLayout(btn_row)

    def _load_snapshots(self):
        """加载快照列表。"""
        self.list_widget.clear()
        try:
            self._snapshots = dsm.list_snapshots(self._dir_path)
        except Exception as e:
            dialog.warn(self, '加载失败', f'读取快照列表失败：{e}')
            self._snapshots = []

        if not self._snapshots:
            empty = QListWidgetItem('（暂无快照 — 执行恢复数据后将自动生成）')
            empty.setFlags(empty.flags() & ~Qt.ItemIsSelectable)
            self.list_widget.addItem(empty)
            self.slider.setMaximum(0)
            self.slider.setEnabled(False)
            self.btn_rollback.setEnabled(False)
            self.lbl_slider_pos.setText('—')
            self.lbl_detail.setText('尚未生成任何快照。')
            return

        # 填充列表
        for name, full, size in self._snapshots:
            ts = dsm.parse_snapshot_timestamp(name)
            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else '未知时间'
            size_str = self._format_size(size)
            reason = self._extract_reason(name)
            display = f'{ts_str}  |  {reason}  |  {size_str}'
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, full)
            self.list_widget.addItem(item)

        # 同步滑条范围
        self.slider.setEnabled(True)
        self.slider.setMaximum(len(self._snapshots) - 1)
        self.slider.setValue(0)
        self.list_widget.setCurrentRow(0)

    def _on_slider_changed(self, value: int):
        """滑条值变化时同步列表选中。"""
        if not self._snapshots:
            return
        if 0 <= value < len(self._snapshots):
            self.list_widget.setCurrentRow(value)
            self._update_detail(value)

    def _on_list_changed(self, row: int):
        """列表选中变化时同步滑条。"""
        if not self._snapshots:
            return
        if 0 <= row < len(self._snapshots):
            self.slider.setValue(row)
            self._update_detail(row)
            self.btn_rollback.setEnabled(True)
            self._current_idx = row
        else:
            self.btn_rollback.setEnabled(False)
            self._current_idx = -1

    def _update_detail(self, idx: int):
        """更新详情区显示。"""
        if idx < 0 or idx >= len(self._snapshots):
            self.lbl_detail.setText('')
            return
        name, full, size = self._snapshots[idx]
        ts = dsm.parse_snapshot_timestamp(name)
        ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else '未知'
        reason = self._extract_reason(name)
        size_str = self._format_size(size)

        # 计算距今天数
        ago_text = ''
        if ts:
            delta = datetime.now() - ts
            if delta.days == 0:
                hours = delta.seconds // 3600
                if hours == 0:
                    mins = delta.seconds // 60
                    ago_text = f'（{mins if mins > 0 else 0} 分钟前）'
                else:
                    ago_text = f'（{hours} 小时前）'
            else:
                ago_text = f'（{delta.days} 天前）'

        self.lbl_detail.setText(
            f'<b>快照时间：</b>{ts_str} {ago_text}<br>'
            f'<b>触发原因：</b>{reason}<br>'
            f'<b>文件大小：</b>{size_str}<br>'
            f'<b>文件名：</b>{name}'
        )

    def _on_rollback(self):
        """执行回滚。"""
        if self._current_idx < 0 or self._current_idx >= len(self._snapshots):
            dialog.warn(self, '无效操作', '请先选择一个快照')
            return

        name, full, size = self._snapshots[self._current_idx]
        ts = dsm.parse_snapshot_timestamp(name)
        ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else '未知时间'

        # 二次确认
        ret = dialog.confirm(
            self, '确认回滚',
            f'确定要将数据库回滚到以下时间点吗？\n\n'
            f'快照时间：{ts_str}\n'
            f'文件大小：{self._format_size(size)}\n\n'
            f'⚠️ 注意：\n'
            f'1. 回滚后当前数据库状态将被覆盖\n'
            f'2. 系统会自动生成一份"保护快照"用于撤回\n'
            f'3. 回滚成功后建议重启应用以刷新所有缓存',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if not ret:
            return

        # 执行回滚
        self.btn_rollback.setEnabled(False)
        self.btn_rollback.setText('正在回滚...')

        progress_log = []

        def cb(msg: str):
            progress_log.append(msg)
            self.lbl_detail.setText('<br>'.join(progress_log[-6:]))
            QApplication.processEvents()

        try:
            ok, msg = dsm.rollback_to_snapshot(full, dir_path=self._dir_path, progress_cb=cb)
        except Exception as e:
            ok, msg = False, f'回滚异常：{e}'

        self.btn_rollback.setEnabled(True)
        self.btn_rollback.setText('回滚到此快照')

        if ok:
            dialog.info(
                self, '回滚成功',
                f'数据库已成功回滚到 {ts_str}\n\n'
                f'建议关闭并重启应用以刷新所有缓存。\n'
                f'（已自动生成保护快照，可再次打开时光机撤回）'
            )
            self.accept()
        else:
            dialog.warn(self, '回滚失败', msg)
            self._load_snapshots()

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小。"""
        if size < 1024:
            return f'{size} B'
        elif size < 1024 * 1024:
            return f'{size / 1024:.1f} KB'
        else:
            return f'{size / 1024 / 1024:.2f} MB'

    @staticmethod
    def _extract_reason(snap_name: str) -> str:
        """从快照文件名提取触发原因。"""
        # meta_index.db.old_YYYYMMDD_HHMMSS_{reason}.db
        try:
            body = snap_name[len(dsm.SNAPSHOT_PREFIX):]
            if body.endswith('.db'):
                body = body[:-3]
            parts = body.split('_', 3)
            if len(parts) >= 4:
                return parts[3]
        except Exception:
            pass
        return '未知'
