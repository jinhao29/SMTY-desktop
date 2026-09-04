# -*- coding: utf-8 -*-
"""UI 层：学员档案管理界面（深色磨砂玻璃风格）。

功能：
1. 学员列表表格：姓名/年龄/身高/体重/BMI/体型/年级/总课时/已上/剩余/状态
2. 顶部预警栏：红色（剩余≤3）/黄色（剩余≤6）
3. 新增/编辑/删除学员
4. 实时 BMI 计算预览
5. 搜索过滤
6. 课时剩余联动展示

拆分说明（P2 超大文件拆分）：
- 对话框 → profile_dialogs.py / profile_lesson_dialog.py
- 事件处理 → profile_handlers.py（mixin 混入）
- 本文件仅保留主界面组装与数据渲染
"""
import modern_dialog as dialog
import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableView, QHeaderView, QFrame, QCheckBox, QAbstractItemView
)

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import profile_manager as pm
# 优化5新增：表格模型视图架构（QAbstractTableModel + QSortFilterProxyModel）
from student_table_model import StudentTableModel, StudentSortFilterProxyModel
from profile_handlers import ProfileHandlersMixin
from base_components import ColorPalette, StatCell, compute_overview


class ProfileScreen(ProfileHandlersMixin, QWidget):
    """学员档案管理主界面。"""

    # 表格列（保持兼容性，仅用于表头长度参考；实际表头由 StudentTableModel 提供）
    COLUMNS = ['姓名', '年龄', '身高', '体重', 'BMI', '体型', '年级',
               '总课时', '已上', '剩余', '状态']

    def __init__(self, archive_dir_getter=None, parent=None):
        """
        参数:
            archive_dir_getter: 返回当前档案目录路径的可调用对象
        """
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        # 优化5新增：表格数据模型 + 排序过滤代理模型
        self._source_model = StudentTableModel(parent=self)
        self._proxy_model = StudentSortFilterProxyModel(parent=self)
        self._proxy_model.setSourceModel(self._source_model)
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)

        # 顶部标题 + 操作栏
        top = QHBoxLayout()
        title = QLabel('学员档案管理')
        title.setObjectName('title')
        _f = QFont('微软雅黑'); _f.setPointSize(18); _f.setBold(True)
        title.setFont(_f)
        top.addWidget(title)
        top.addStretch()

        self.btn_add = QPushButton('+ 新增学员')
        self.btn_add.setObjectName('primary')
        self.btn_add.clicked.connect(self.on_add)
        top.addWidget(self.btn_add)

        self.btn_edit = QPushButton('编辑')
        self.btn_edit.setObjectName('secondary')
        self.btn_edit.clicked.connect(self.on_edit)
        top.addWidget(self.btn_edit)

        self.btn_edit_lesson = QPushButton('修改课时')
        self.btn_edit_lesson.setObjectName('secondary')
        self.btn_edit_lesson.clicked.connect(self.on_edit_lesson)
        top.addWidget(self.btn_edit_lesson)

        self.btn_growth = QPushButton('成长工具')
        self.btn_growth.setObjectName('secondary')
        self.btn_growth.setToolTip('身高预测 / 营养方案（TDEE·膳食） / 体型历史')
        self.btn_growth.clicked.connect(self.on_growth_tools)
        top.addWidget(self.btn_growth)

        self.btn_del = QPushButton('删除')
        self.btn_del.setObjectName('danger')
        self.btn_del.clicked.connect(self.on_del)
        top.addWidget(self.btn_del)

        self.btn_refresh = QPushButton('刷新')
        self.btn_refresh.setObjectName('secondary')
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)
        lay.addLayout(top)

        # === 学员概览条（真数据：学员总数/正常/需续费/课时关注）===
        strip = QFrame()
        strip.setObjectName('statStrip')
        strip.setStyleSheet(f'''
            QFrame#statStrip {{
                background: {ColorPalette.CARD};
                border: 1px solid #E5E5E5;
                border-radius: 16px;
            }}
        ''')
        sl = QHBoxLayout(strip)
        sl.setContentsMargins(20, 14, 20, 14)
        sl.setSpacing(0)
        self.cell_total = StatCell('学员总数')
        self.cell_normal = StatCell('正常')
        self.cell_red = StatCell('需续费（≤3课时）', accent='#F87171')
        self.cell_yellow = StatCell('课时关注（≤6课时）', accent='#F59E0B')
        cells = [self.cell_total, self.cell_normal, self.cell_red, self.cell_yellow]
        for i, cell in enumerate(cells):
            if i:
                line = QLabel()
                line.setFixedSize(1, 36)
                line.setStyleSheet('background: #E5E5E5; border: none;')
                sl.addWidget(line)
            sl.addWidget(cell, 1)
        lay.addWidget(strip)

        # 预警栏
        self.warn_bar = QFrame()
        self.warn_bar.setObjectName('card')
        wl = QHBoxLayout(self.warn_bar)
        wl.setContentsMargins(14, 10, 14, 10)
        self.lbl_warn = QLabel('暂无预警')
        self.lbl_warn.setStyleSheet('color:#6B6B6B; font-size:13px;')
        wl.addWidget(self.lbl_warn)
        wl.addStretch()
        lay.addWidget(self.warn_bar)

        # 搜索栏
        search_lay = QHBoxLayout()
        search_lay.addWidget(QLabel('搜索：'))
        self.le_search = QLineEdit(placeholderText='按姓名或年级搜索...')
        self.le_search.textChanged.connect(self._on_search)
        search_lay.addWidget(self.le_search, 1)
        # 显示已停用学员开关（软删除配套）
        self.cb_show_inactive = QCheckBox('显示已停用学员')
        self.cb_show_inactive.setToolTip('勾选后将显示已停用的学员，可在右键菜单中恢复')
        self.cb_show_inactive.stateChanged.connect(self.refresh)
        search_lay.addWidget(self.cb_show_inactive)
        lay.addLayout(search_lay)

        # 学员表格（优化5：QTableView + QAbstractTableModel + QSortFilterProxyModel）
        self.table = QTableView()
        self.table.setModel(self._proxy_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        # 启用点击列头排序
        self.table.setSortingEnabled(True)
        # 默认按姓名列升序
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(1, len(self.COLUMNS) - 1):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(len(self.COLUMNS) - 1, QHeaderView.Stretch)
        # 垂直表头（行号）隐藏，更贴近原 QTableWidget 视觉
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(400)
        self.table.doubleClicked.connect(self.on_edit)
        lay.addWidget(self.table, 1)

    def refresh(self):
        """从存储刷新表格数据。

        根据「显示已停用学员」开关决定是否包含 is_active=False 的学员。
        """
        archive_dir = self._get_dir()
        if not archive_dir:
            self._source_model.set_students([])
            return
        include_inactive = self.cb_show_inactive.isChecked()
        try:
            students = pm.list_students(archive_dir, include_inactive=include_inactive)
        except Exception as e:
            dialog.error(self, '加载失败', str(e))
            return
        self._render_table(students)
        self._refresh_stat_cells(students)
        self._render_warn_bar(students)

    def _refresh_stat_cells(self, students: list):
        """按当前学员列表刷新顶部概览条四个统计单元。"""
        o = compute_overview(students or [])
        self.cell_total.set_value(o['total'])
        self.cell_normal.set_value(max(o['total'] - o['red'] - o['yellow'], 0))
        self.cell_red.set_value(o['red'])
        self.cell_yellow.set_value(o['yellow'])

    def _render_table(self, students: list):
        """优化5：通过模型批量更新数据，避免逐行 QTableWidgetItem 创建。"""
        # 搜索关键字透传给代理模型（兼容 _on_search 不调用 refresh 的场景）
        self._proxy_model.set_keyword(self.le_search.text())
        self._source_model.set_students(students or [])

    def _warn_label(self, s: dict) -> str:
        level = s.get('warn_level', 'normal')
        if level == 'red':
            return f'需续费（剩 {s["remaining"]} 课时）'
        if level == 'yellow':
            return f'关注（剩 {s["remaining"]} 课时）'
        if level == 'unknown':
            return '未设总课时'
        return '正常'

    def _render_warn_bar(self, students: list):
        red = [s for s in students if s['warn_level'] == 'red']
        yellow = [s for s in students if s['warn_level'] == 'yellow']
        if not red and not yellow:
            self.lbl_warn.setText(f'共 {len(students)} 名学员，无续费预警')
            self.lbl_warn.setStyleSheet('color:#34D399; font-size:13px;')
            return
        parts = []
        if red:
            names = '、'.join(s['name'] for s in red)
            parts.append(f'<span style="color:#F87171;">需续费({len(red)})：{names}</span>')
        if yellow:
            names = '、'.join(s['name'] for s in yellow)
            parts.append(f'<span style="color:#FBBF24;">关注({len(yellow)})：{names}</span>')
        self.lbl_warn.setText('  |  '.join(parts))
        self.lbl_warn.setTextFormat(Qt.RichText)
        self.lbl_warn.setStyleSheet('font-size:13px;')
