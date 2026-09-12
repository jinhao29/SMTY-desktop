# -*- coding: utf-8 -*-
"""UI 层：学员管理界面（灰白简约 · 珊瑚橙强调，卡片式布局）。

布局结构（复用 training_tool 设计令牌，#profile_root 作用域 QSS 级联子树）：
1. 页头：大标题 + 计数徽章 + 副标题
2. 操作卡：搜索框 | 成长工具 | 刷新 | + 新增学员（主按钮）| 筛选 chips
3. 表格卡：头像姓名 | 年龄 | 身高 | 体重 | BMI | 体型 | 年级 | 总课时 | 已上 | 剩余 | 状态徽章 | 行内操作
4. 状态卡：显示数量 + 续费预警名单

拆分说明（P2 超大文件拆分）：
- 对话框 → profile_dialogs.py / profile_lesson_dialog.py
- 事件处理 → profile_handlers.py（mixin 混入）
- 本文件仅保留主界面组装与数据渲染
"""
import modern_dialog as dialog
import os
import sys
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableView, QHeaderView, QAbstractItemView
)

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
# training_tool 共享设计资产（styles/cards 为包内 path-insert 式顶层模块，app.py 启动时同样插入）
_TRAINING = os.path.join(_PARENT, 'training_tool')
if _TRAINING not in sys.path:
    sys.path.insert(0, _TRAINING)

import profile_manager as pm
from student_table_model import StudentTableModel, StudentSortFilterProxyModel
from profile_handlers import ProfileHandlersMixin
from manage_components import (
    PageHeader, FilterChipBar, AvatarNameDelegate, StatusBadgeDelegate,
    RowActionsDelegate,
)

# 新设计语言令牌与组件（灰白简约 · 珊瑚橙强调）
from styles import scoped_qss, Spacing
from cards import Card


class ProfileScreen(ProfileHandlersMixin, QWidget):
    """学员管理主界面。"""

    # 表格列（含操作列，仅用于表头长度参考；实际表头由 StudentTableModel 提供）
    COLUMNS = ['姓名', '年龄', '身高', '体重', 'BMI', '体型', '年级',
               '总课时', '已上', '剩余', '状态', '操作']

    # 双击行 / 操作列「详情」时发射（App 据此打开学员详情页）
    studentActivated = Signal(str)

    def __init__(self, archive_dir_getter=None, parent=None):
        """
        参数:
            archive_dir_getter: 返回当前档案目录路径的可调用对象
        """
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        # 表格数据模型 + 排序/搜索/状态过滤代理模型
        self._source_model = StudentTableModel(parent=self)
        self._proxy_model = StudentSortFilterProxyModel(parent=self)
        self._proxy_model.setSourceModel(self._source_model)
        self._all_students = []  # 最近一次全量列表（含停用，用于 chips 计数与底部栏）
        self._init_ui()

    def _init_ui(self):
        # 作用域 QSS：#profile_root 子树统一灰白卡片风格（复用 training_tool 同一套 QSS）
        self.setObjectName('profile_root')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(scoped_qss('profile_root'))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(Spacing.CARD)

        # 1. 页头：标题 + 计数徽章 + 副标题
        self.header = PageHeader('学员管理', subtitle='管理学员档案、课时与续费状态')
        lay.addWidget(self.header)

        # 2. 操作卡：搜索 + 成长工具 / 刷新 / + 新增学员 + 筛选 chips
        card_actions = Card()
        actions_lay = QVBoxLayout()
        actions_lay.setContentsMargins(0, 0, 0, 0)
        actions_lay.setSpacing(Spacing.MD)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.le_search = QLineEdit(placeholderText='搜索姓名或年级...')
        self.le_search.setClearButtonEnabled(True)
        self.le_search.textChanged.connect(self._on_search)
        toolbar.addWidget(self.le_search, 1)

        self.btn_growth = QPushButton('成长工具')
        self.btn_growth.setObjectName('secondary')
        self.btn_growth.setToolTip('身高预测 / 营养方案（TDEE·膳食） / 体型历史')
        self.btn_growth.clicked.connect(self.on_growth_tools)
        toolbar.addWidget(self.btn_growth)

        self.btn_refresh = QPushButton('刷新')
        self.btn_refresh.setObjectName('secondary')
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        toolbar.addWidget(self.btn_refresh)

        self.btn_add = QPushButton('+ 新增学员')
        self.btn_add.setObjectName('primary')
        self.btn_add.clicked.connect(self.on_add)
        toolbar.addWidget(self.btn_add)
        actions_lay.addLayout(toolbar)

        # 筛选 chips（单选互斥，带状态计数）
        self.chip_bar = FilterChipBar()
        self.chip_bar.add_chip('all', '全部')
        self.chip_bar.add_chip('normal', '正常', accent='#10B981')
        self.chip_bar.add_chip('red', '需续费', accent='#EF4444')
        self.chip_bar.add_chip('yellow', '课时关注', accent='#F59E0B')
        self.chip_bar.add_chip('inactive', '已停用', accent='#9B9B9B')
        self.chip_bar.filterChanged.connect(self._on_filter_changed)
        actions_lay.addWidget(self.chip_bar)
        card_actions.set_content_layout(actions_lay)
        lay.addWidget(card_actions)

        # 3. 表格卡：QTableView + 模型/代理 + delegates（背景/表头交给作用域 QSS）
        self.table = QTableView()
        self.table.setModel(self._proxy_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setFixedHeight(44)
        # 列宽策略：文本列按内容，体型列固定宽（长文本截断），年级列拉伸吸收剩余宽度
        for i in (1, 2, 3, 4, 7, 8, 9):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # 姓名（头像+名字）
        header.setSectionResizeMode(5, QHeaderView.Interactive)        # 体型（长文本）
        self.table.setColumnWidth(5, 105)
        header.setSectionResizeMode(6, QHeaderView.Stretch)            # 年级
        header.setSectionResizeMode(10, QHeaderView.Stretch)           # 状态徽章（随窗口尺寸自适应）
        header.setSectionResizeMode(11, QHeaderView.ResizeToContents)  # 操作
        header.setStretchLastSection(False)
        self.table.setMinimumHeight(400)
        # 双击行 → 学员详情页（编辑走操作列「编辑」按钮 / 右键菜单）
        self.table.doubleClicked.connect(self._on_open_detail)

        # delegates：姓名头像 / 状态徽章 / 行内操作（在职行与停用行按钮组不同）
        self.table.setItemDelegateForColumn(0, AvatarNameDelegate(self.table))
        self.table.setItemDelegateForColumn(10, StatusBadgeDelegate(self.table))
        self.table.setItemDelegateForColumn(11, RowActionsDelegate({
            'active': [
                ('详情', self._on_open_detail_index),
                ('编辑', self._on_action_edit),
                ('课时', self._on_action_lesson),
                ('停用', self._on_action_deactivate),
                ('删除', self._on_action_delete),
            ],
            'inactive': [
                ('详情', self._on_open_detail_index),
                ('恢复', self._on_action_reactivate),
                ('删除', self._on_action_delete),
            ],
        }, self.table))
        card_table = Card()
        table_lay = QVBoxLayout()
        table_lay.setContentsMargins(0, 0, 0, 0)
        table_lay.addWidget(self.table)
        card_table.set_content_layout(table_lay)
        lay.addWidget(card_table, 1)

        # 4. 状态卡：显示数量 + 续费预警名单
        card_footer = Card()
        fl = QHBoxLayout()
        fl.setContentsMargins(0, 0, 0, 0)
        self.lbl_footer = QLabel('共 0 名学员')
        self.lbl_footer.setTextFormat(Qt.RichText)
        fl.addWidget(self.lbl_footer)
        fl.addStretch()
        self.lbl_hint = QLabel('双击行查看详情 · 编辑走操作列「编辑」')
        self.lbl_hint.setObjectName('hint')
        fl.addWidget(self.lbl_hint)
        card_footer.set_content_layout(fl)
        lay.addWidget(card_footer)

    #==== 数据刷新 ====

    def _on_refresh_clicked(self):
        """刷新按钮：带加载反馈（禁用 + 文案变化），顺带执行明细去重修复。"""
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText('刷新中…')
        try:
            try:
                import lesson_manager as lm
                lm.dedup_details(self._get_dir())
            except Exception:
                pass  # 去重失败不阻塞刷新
            self.refresh()
        finally:
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText('刷新')

    def refresh(self):
        """从存储刷新表格数据（全量含停用，显示层由 chips 过滤）。"""
        archive_dir = self._get_dir()
        if not archive_dir:
            self._all_students = []
            self._source_model.set_students([])
            self._update_chips([])
            self._update_header_and_footer([])
            return
        try:
            students = pm.list_students(archive_dir, include_inactive=True)
        except Exception as e:
            dialog.error(self, '加载失败', str(e))
            return
        self._all_students = students or []
        self._render_table(self._all_students)
        self._update_chips(self._all_students)
        self._update_header_and_footer(self._all_students)

    def _render_table(self, students: list):
        """通过模型批量更新数据，并同步搜索关键字过滤。"""
        self._proxy_model.set_keyword(self.le_search.text())
        self._source_model.set_students(students or [])

    def _update_chips(self, students: list):
        """按全量列表刷新 chips 计数（已停用单独计数）。"""
        active = [s for s in students if s.get('is_active', True)]
        self.chip_bar.set_chip_count('all', len(active))
        self.chip_bar.set_chip_count('normal',
                                     sum(1 for s in active if s.get('warn_level') in ('normal', 'unknown')))
        self.chip_bar.set_chip_count('red', sum(1 for s in active if s.get('warn_level') == 'red'))
        self.chip_bar.set_chip_count('yellow', sum(1 for s in active if s.get('warn_level') == 'yellow'))
        self.chip_bar.set_chip_count('inactive', len(students) - len(active))

    def _update_header_and_footer(self, students: list):
        """更新页头计数徽章与底部统计 + 预警名单。"""
        self.header.set_count(len(students))
        active = [s for s in students if s.get('is_active', True)]
        visible = self._proxy_model.rowCount()
        parts = [f'共 {len(students)} 名学员 · 在档 {len(active)}']
        if visible != len(students):
            parts.append(f'当前显示 {visible} 名')
        red = [s for s in active if s.get('warn_level') == 'red']
        yellow = [s for s in active if s.get('warn_level') == 'yellow']
        if red:
            names = '、'.join(s['name'] for s in red)
            parts.append(f'<span style="color:#EF4444;">需续费({len(red)})：{names}</span>')
        if yellow:
            names = '、'.join(s['name'] for s in yellow)
            parts.append(f'<span style="color:#F59E0B;">关注({len(yellow)})：{names}</span>')
        if not red and not yellow:
            parts.append('<span style="color:#10B981;">无续费预警</span>')
        self.lbl_footer.setText(' &nbsp;·&nbsp; '.join(parts))

    #==== chips / 行内操作事件 ====

    def _row_student_name(self, index) -> str:
        """源模型 index → 学员名（越界返回空串）。"""
        return self._source_model.get_student_name_at(index.row()) or ''

    def _on_open_detail_index(self, index):
        """操作列「详情」按钮：按源行精确定位学员并打开详情页。"""
        name = self._row_student_name(index)
        if name:
            self.studentActivated.emit(name)

    def _on_open_detail(self, proxy_index):
        """双击行：打开学员详情页（替代原双击编辑）。"""
        src = self._proxy_model.mapToSource(proxy_index)
        name = self._source_model.get_student_name_at(src.row())
        if name:
            self.studentActivated.emit(name)

    def _on_filter_changed(self, key: str):
        """chips 切换：更新代理模型状态过滤并同步底部栏显示数量。"""
        self._proxy_model.set_status_filter(key)
        self._update_header_and_footer(self._all_students)

    def _proxy_source_index(self, proxy_row: int):
        """代理行号 → 源模型 index（行内操作回调用）。"""
        proxy_idx = self._proxy_model.index(proxy_row, 0)
        return self._proxy_model.mapToSource(proxy_idx)

    def _select_proxy_row(self, src_index):
        """按源模型 index 选中对应代理行（用于操作列按钮触发的流程）。"""
        proxy_idx = self._proxy_model.mapFromSource(src_index)
        if proxy_idx.isValid():
            self.table.selectRow(proxy_idx.row())

    def _on_action_edit(self, index):
        """操作列「编辑」按钮。"""
        self._select_proxy_row(index)
        self.on_edit()

    def _on_action_lesson(self, index):
        """操作列「课时」按钮：修改选中学员课时。"""
        self._select_proxy_row(index)
        self.on_edit_lesson()

    def _on_action_deactivate(self, index):
        """操作列「停用」按钮：按源行精确定位学员（不依赖表格当前选中）。"""
        name = self._source_model.get_student_name_at(index.row())
        if not name:
            return
        reply = dialog.confirm(
            self, '确认停用',
            f'确定停用学员 [{name}] 吗？\n（软删除：所有数据保留，可随时恢复）',
        )
        if not reply:
            return
        try:
            pm.delete_student(self._get_dir(), name)
            self.refresh()
        except Exception as e:
            dialog.error(self, '停用失败', str(e))

    def _on_action_delete(self, index):
        """操作列「删除」按钮：硬删除学员（花名册/档案/课时/收费一并移除，档案隔离可找回）。"""
        name = self._source_model.get_student_name_at(index.row())
        if not name:
            return
        reply = dialog.confirm(
            self, '确认删除',
            f'确定永久删除学员 [{name}] 吗？\n'
            '将同时删除其课时记录、收费记录与档案，删除后不可在软件内恢复！',
        )
        if not reply:
            return
        try:
            pm.delete_student_permanently(self._get_dir(), name)
            self.refresh()
        except Exception as e:
            dialog.error(self, '删除失败', str(e))

    def _on_action_reactivate(self, index):
        """操作列「恢复」按钮：恢复已停用学员。"""
        name = self._source_model.get_student_name_at(index.row())
        if not name:
            return
        reply = dialog.confirm(
            self, '确认恢复',
            f'确定恢复学员 [{name}] 为启用状态吗？\n恢复后将重新出现在正常学员列表中。',
        )
        if not reply:
            return
        try:
            pm.reactivate_student(self._get_dir(), name)
            self.refresh()
            dialog.info(self, '已恢复', f'学员 [{name}] 已恢复启用')
        except Exception as e:
            dialog.error(self, '恢复失败', str(e))

    def _warn_label(self, s: dict) -> str:
        level = s.get('warn_level', 'normal')
        if level == 'red':
            return f'需续费（剩 {s["remaining"]} 课时）'
        if level == 'yellow':
            return f'关注（剩 {s["remaining"]} 课时）'
        if level == 'unknown':
            return '未设总课时'
        return '正常'
