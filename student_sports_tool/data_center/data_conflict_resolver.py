# -*- coding: utf-8 -*-
"""UI 层：数据冲突可视化解决弹窗（v5 优化4 新增）。

职责：
- 用 QTableWidget 列出所有冲突项（学员名/类型/本地状态/远端状态/解决策略）
- 每行最后一列为下拉框，让教练选择：合并/覆盖/重命名/跳过
- 重命名策略支持就地编辑新名称（默认 xxx_2）
- 二次确认后输出解决结果列表，供 do_restore 应用

设计原则：
- 模态对话框，强制教练逐条确认
- 默认勾选 conflict_detector 给出的建议策略
- 冲突为空时直接返回 Accepted，不弹窗（由调用方判断）
- 整体风格与 DbSnapshotDialog 一致（深色主题）
"""
import modern_dialog as dialog
from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QComboBox, QHeaderView, QMessageBox, QAbstractItemView
)

import conflict_detector as cd


# 表格列索引
COL_NAME = 0
COL_TYPE = 1
COL_LOCAL = 2
COL_REMOTE = 3
COL_ACTION = 4
COL_NEW_NAME = 5

# 冲突类型中文映射
TYPE_LABELS = {
    cd.CONFLICT_NAME_DUPLICATE: '同名学员',
    cd.CONFLICT_LESSON_DATE_OVERLAP: '课时日期重叠',
    cd.CONFLICT_PACKAGE_MISMATCH: '课时包不一致',
}

# 解决策略中文映射
ACTION_LABELS = {
    cd.RESOLVE_MERGE: '合并历史记录',
    cd.RESOLVE_OVERWRITE: '覆盖现有数据',
    cd.RESOLVE_RENAME: '重命名为副本',
    cd.RESOLVE_SKIP: '跳过此条',
}


class DataConflictResolver(QDialog):
    """数据冲突可视化解决弹窗。

    用法：
        conflicts = conflict_detector.detect_conflicts_from_zip(...)
        if not conflicts:
            # 无冲突，直接继续
        else:
            dlg = DataConflictResolver(conflicts, parent)
            if dlg.exec() == QDialog.Accepted:
                resolutions = dlg.get_resolutions()
                # 传给 do_restore
    """

    def __init__(self, conflicts: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle('数据冲突解决')
        self.setModal(True)
        self.resize(900, 520)
        self._conflicts = conflicts
        self._resolutions: List[Dict[str, Any]] = []
        self._init_ui()
        self._load_conflicts()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel('检测到数据冲突')
        title.setObjectName('title')
        f = QFont('微软雅黑'); f.setPointSize(16); f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)

        # 说明
        desc = QLabel(
            f'共检测到 {len(self._conflicts)} 项数据冲突。\n'
            f'请逐条选择处理方式后点击"应用并继续"，系统将按你的选择恢复数据。\n'
            f'⚠️ 覆盖现有数据会删除本地档案后重新导入，请谨慎选择。'
        )
        desc.setStyleSheet('color:#9B9B9B; font-size:12px;')
        desc.setWordWrap(True)
        lay.addWidget(desc)

        # 表格
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ['学员名', '冲突类型', '本地状态', '远端状态', '处理方式', '新名称（仅重命名）']
        )
        self.table.setStyleSheet("""
            QTableWidget {
                background: #FFFFFF;
                color: #1A1A1A;
                border: 1px solid #E5E5E5;
                border-radius: 8px;
                gridline-color: #F0F0F0;
                font-size: 12px;
            }
            QHeaderView::section {
                background: #F8F8F8;
                color: #6B6B6B;
                padding: 8px 6px;
                border: none;
                border-right: 1px solid #E5E5E5;
                font-weight: 600;
            }
            QTableWidget::item {
                padding: 6px 8px;
            }
            QTableWidget::item:selected {
                background: #FFEDE8;
                color: #FF6B47;
            }
            QComboBox {
                background: #FFFFFF;
                color: #1A1A1A;
                border: 1px solid #E5E5E5;
                padding: 4px 8px;
                border-radius: 8px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: #FFFFFF;
                color: #1A1A1A;
                selection-background-color: #FFEDE8;
                selection-color: #FF6B47;
            }
        """)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_LOCAL, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_REMOTE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_ACTION, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_NEW_NAME, QHeaderView.ResizeToContents)
        lay.addWidget(self.table, 1)

        # 全部应用快捷按钮
        bulk_row = QHBoxLayout()
        bulk_row.setSpacing(8)
        lbl_bulk = QLabel('批量操作：')
        lbl_bulk.setStyleSheet('color:#9B9B9B; font-size:12px;')
        bulk_row.addWidget(lbl_bulk)
        btn_all_merge = QPushButton('全部合并', objectName='secondary')
        btn_all_merge.clicked.connect(lambda: self._apply_bulk(cd.RESOLVE_MERGE))
        bulk_row.addWidget(btn_all_merge)
        btn_all_overwrite = QPushButton('全部覆盖', objectName='secondary')
        btn_all_overwrite.clicked.connect(lambda: self._apply_bulk(cd.RESOLVE_OVERWRITE))
        bulk_row.addWidget(btn_all_overwrite)
        btn_all_skip = QPushButton('全部跳过', objectName='secondary')
        btn_all_skip.clicked.connect(lambda: self._apply_bulk(cd.RESOLVE_SKIP))
        bulk_row.addWidget(btn_all_skip)
        bulk_row.addStretch(1)
        lay.addLayout(bulk_row)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton('取消恢复', objectName='secondary')
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        self.btn_apply = QPushButton('应用并继续', objectName='primary')
        self.btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self.btn_apply)
        lay.addLayout(btn_row)

    def _load_conflicts(self):
        """加载冲突列表到表格。"""
        self.table.setRowCount(len(self._conflicts))
        for row, c in enumerate(self._conflicts):
            # 学员名
            name_item = QTableWidgetItem(c.get('student_name', ''))
            name_item.setToolTip(c.get('student_name', ''))
            self.table.setItem(row, COL_NAME, name_item)

            # 冲突类型
            type_key = c.get('type', '')
            type_label = TYPE_LABELS.get(type_key, type_key)
            type_item = QTableWidgetItem(type_label)
            self.table.setItem(row, COL_TYPE, type_item)

            # 本地状态
            local_item = QTableWidgetItem(c.get('local_info', ''))
            local_item.setToolTip(c.get('local_info', ''))
            self.table.setItem(row, COL_LOCAL, local_item)

            # 远端状态
            remote_item = QTableWidgetItem(c.get('remote_info', ''))
            remote_item.setToolTip(c.get('remote_info', ''))
            self.table.setItem(row, COL_REMOTE, remote_item)

            # 处理方式下拉框
            combo = QComboBox()
            for action_key, action_label in ACTION_LABELS.items():
                combo.addItem(action_label, action_key)
            # 默认选中建议策略
            suggested = c.get('suggested_resolution', cd.RESOLVE_MERGE)
            idx = combo.findData(suggested)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self.table.setCellWidget(row, COL_ACTION, combo)

            # 新名称（仅重命名时启用）
            default_new_name = f"{c.get('student_name', '')}_2"
            new_name_item = QTableWidgetItem(default_new_name)
            new_name_item.setFlags(new_name_item.flags() | Qt.ItemIsEditable)
            new_name_item.setToolTip('选择"重命名为副本"时可编辑新名称')
            self.table.setItem(row, COL_NEW_NAME, new_name_item)

        # 初始禁用所有新名称列（因为默认策略不是 rename）
        self._refresh_new_name_editability()

        # 监听 combo 变化以动态启禁新名称列
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, COL_ACTION)
            if combo:
                combo.currentIndexChanged.connect(self._refresh_new_name_editability)

    def _refresh_new_name_editability(self):
        """根据处理方式动态启禁新名称列。"""
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, COL_ACTION)
            if not combo:
                continue
            action = combo.currentData()
            new_name_item = self.table.item(row, COL_NEW_NAME)
            if not new_name_item:
                continue
            if action == cd.RESOLVE_RENAME:
                new_name_item.setFlags(
                    new_name_item.flags() | Qt.ItemIsEditable
                )
                new_name_item.setBackground(Qt.darkGreen)
                # 提示文字
                if not new_name_item.text() or new_name_item.text() == '':
                    new_name_item.setText(f"{self.table.item(row, COL_NAME).text()}_2")
            else:
                new_name_item.setFlags(
                    new_name_item.flags() & ~Qt.ItemIsEditable
                )
                new_name_item.setBackground(Qt.gray)

    def _apply_bulk(self, action: str):
        """批量设置所有行的处理方式。"""
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, COL_ACTION)
            if combo:
                idx = combo.findData(action)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        self._refresh_new_name_editability()

    def _on_apply(self):
        """应用按钮：收集所有解决策略并关闭对话框。"""
        self._resolutions = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, COL_NAME)
            combo = self.table.cellWidget(row, COL_ACTION)
            new_name_item = self.table.item(row, COL_NEW_NAME)
            if not name_item or not combo:
                continue

            name = name_item.text().strip()
            action = combo.currentData()
            new_name = new_name_item.text().strip() if new_name_item else ''

            # 重命名时校验新名称
            if action == cd.RESOLVE_RENAME:
                if not new_name or new_name == name:
                    dialog.warn(
                        self, '新名称无效',
                        f'学员 {name} 选择"重命名为副本"，但新名称为空或与原名相同。\n'
                        f'请修改新名称或选择其他处理方式。'
                    )
                    return

            self._resolutions.append({
                'student_name': name,
                'action': action,
                'new_name': new_name if action == cd.RESOLVE_RENAME else None,
                'original_conflict': self._conflicts[row],
            })

        # 二次确认
        merge_count = sum(1 for r in self._resolutions if r['action'] == cd.RESOLVE_MERGE)
        overwrite_count = sum(1 for r in self._resolutions if r['action'] == cd.RESOLVE_OVERWRITE)
        rename_count = sum(1 for r in self._resolutions if r['action'] == cd.RESOLVE_RENAME)
        skip_count = sum(1 for r in self._resolutions if r['action'] == cd.RESOLVE_SKIP)

        ret = dialog.confirm(
            self, '确认应用冲突解决方案',
            f'即将按以下方案恢复数据：\n\n'
            f'  合并历史记录：{merge_count} 项\n'
            f'  覆盖现有数据：{overwrite_count} 项\n'
            f'  重命名为副本：{rename_count} 项\n'
            f'  跳过此条：{skip_count} 项\n\n'
            f'确认继续？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ret :
            self.accept()

    def get_resolutions(self) -> List[Dict[str, Any]]:
        """返回教练选择的解决策略列表。"""
        return self._resolutions
