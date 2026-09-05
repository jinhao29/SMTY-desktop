# -*- coding: utf-8 -*-
"""UI 层：教练管理页面（参考管理后台布局语言，浅色珊瑚橙主题）。

布局结构（与学员管理页统一）：
1. 页头：大标题 + 计数徽章 + 副标题
2. 工具栏：搜索框 | 刷新 | + 新增教练（主按钮）
3. 筛选 chips：全部(n) / 在职(n) / 离职(n)，单选互斥
4. 表格：头像姓名 | 电话 | 角色 | 专长 | 入职日期 | 状态徽章 | 行内操作
5. 底部计数栏

数据层：coach_manager（教练档案.xlsx，软删除离职/恢复）。
"""
import os
import sys

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableView, QHeaderView, QFrame, QDialog, QFormLayout, QComboBox,
    QAbstractItemView, QMenu
)

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import coach_manager as cm
import modern_dialog as dialog
from base_components import ColorPalette
from manage_components import (
    PageHeader, FilterChipBar, AvatarNameDelegate, StatusBadgeDelegate,
    RowActionsDelegate,
)

# 列定义：(显示名, 数据键, 是否数值列)
COLUMNS = [
    ('姓名', 'name', False),
    ('电话', 'phone', False),
    ('角色', 'role', False),
    ('专长', 'specialty', False),
    ('入职日期', 'join_date', False),
    ('状态', 'status_label', False),
    ('操作', '_actions', False),
]
COLUMN_COUNT = len(COLUMNS)
HEADER_LABELS = [c[0] for c in COLUMNS]


def _status_label(is_active: bool) -> str:
    """在职状态 → 状态徽章文本。"""
    return '在职' if is_active else '离职'


class CoachTableModel(QAbstractTableModel):
    """教练数据表格模型：以 list[dict] 为数据源（同学员表模型模式）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._coaches = []

    def set_coaches(self, coaches: list):
        """重置数据源（预计算 status_label）。"""
        self.beginResetModel()
        prepared = []
        for c in coaches or []:
            row = dict(c)
            row['status_label'] = _status_label(c.get('is_active', True))
            prepared.append(row)
        self._coaches = prepared
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._coaches)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent is not None and parent.isValid():
            return 0
        return COLUMN_COUNT

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < COLUMN_COUNT:
            return HEADER_LABELS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._coaches) or col < 0 or col >= COLUMN_COUNT:
            return None
        c = self._coaches[row]
        key = COLUMNS[col][1]
        is_active = c.get('is_active', True)

        if role == Qt.DisplayRole:
            if key == '_actions':
                return ''
            if key == 'status_label':
                return c.get('status_label', '在职')
            return str(c.get(key, '') or '')

        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        if role == Qt.ForegroundRole:
            if not is_active:
                return QColor('#9B9B9B')
            return None

        if role == Qt.FontRole:
            # 离职教练姓名列斜体（与学员停用行视觉一致）
            if not is_active and col == 0:
                f = QFont()
                f.setItalic(True)
                return f
            return None

        if role == Qt.UserRole + 1:
            # AvatarNameDelegate / RowActionsDelegate 的 muted 标记
            return is_active

        if role == Qt.UserRole + 2:
            # RowActionsDelegate 按钮组 key
            return 'active' if is_active else 'inactive'

        return None

    def get_coach_at(self, row: int) -> dict:
        """返回指定行（源模型行）的教练 dict，越界返回空 dict。"""
        if 0 <= row < len(self._coaches):
            return self._coaches[row]
        return {}

    def all_coaches(self) -> list:
        """返回当前模型持有的全部教练列表。"""
        return self._coaches


class CoachSortFilterProxyModel(QSortFilterProxyModel):
    """教练表搜索 + 状态过滤代理模型。

    - 关键字匹配姓名/电话/角色/专长（不区分大小写）
    - status_filter: 'all' 仅在职 | 'inactive' 仅离职
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keyword = ''
        self._status_filter = 'all'

    def set_keyword(self, keyword: str):
        kw = (keyword or '').strip().lower()
        if kw == self._keyword:
            return
        self._keyword = kw
        self.invalidateFilter()

    def set_status_filter(self, key: str):
        key = key or 'all'
        if key == self._status_filter:
            return
        self._status_filter = key
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        sm = self.sourceModel()
        if not isinstance(sm, CoachTableModel):
            return True
        c = sm.get_coach_at(source_row)
        if not c:
            return False
        active = c.get('is_active', True)
        if self._status_filter == 'all' and not active:
            return False
        if self._status_filter == 'inactive' and active:
            return False
        if not self._keyword:
            return True
        haystack = ' '.join(str(c.get(k, '') or '') for k in ('name', 'phone', 'role', 'specialty')).lower()
        return self._keyword in haystack

    def get_coach_at_proxy(self, proxy_row: int) -> dict:
        """通过代理行号取教练 dict（自动映射源模型）。"""
        proxy_idx = self.index(proxy_row, 0)
        src = self.mapToSource(proxy_idx)
        sm = self.sourceModel()
        if isinstance(sm, CoachTableModel):
            return sm.get_coach_at(src.row())
        return {}


class CoachEditDialog(QDialog):
    """教练新增/编辑对话框：姓名/电话/角色/专长/入职日期/备注。"""

    def __init__(self, parent=None, coach: dict = None):
        super().__init__(parent)
        coach = coach or {}
        self.setWindowTitle('编辑教练' if coach.get('name') else '新增教练')
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)
        self.le_name = QLineEdit(coach.get('name', ''))
        self.le_name.setPlaceholderText('教练姓名（必填）')
        self.le_phone = QLineEdit(coach.get('phone', ''))
        self.le_phone.setPlaceholderText('联系电话')
        self.cb_role = QComboBox()
        self.cb_role.setEditable(True)
        self.cb_role.addItems(cm.ROLE_OPTIONS)
        if coach.get('role'):
            self.cb_role.setCurrentText(coach['role'])
        else:
            self.cb_role.setCurrentText('')
        self.cb_role.lineEdit().setPlaceholderText('如 主教练 / 助理教练 / 体能教练')
        self.le_specialty = QLineEdit(coach.get('specialty', ''))
        self.le_specialty.setPlaceholderText('如 青少年体能 / 篮球 / 田径')
        self.le_join = QLineEdit(coach.get('join_date', ''))
        self.le_join.setPlaceholderText('如 2025-09-01')
        self.le_note = QLineEdit(coach.get('note', ''))
        self.le_note.setPlaceholderText('备注')
        form.addRow('姓名', self.le_name)
        form.addRow('电话', self.le_phone)
        form.addRow('角色', self.cb_role)
        form.addRow('专长', self.le_specialty)
        form.addRow('入职日期', self.le_join)
        form.addRow('备注', self.le_note)
        lay.addLayout(form)

        self.lbl_err = QLabel('')
        self.lbl_err.setStyleSheet('color: #EF4444; font-size: 12px; background: transparent;')
        self.lbl_err.hide()
        lay.addWidget(self.lbl_err)

        btns = QHBoxLayout()
        btns.addStretch()
        self.btn_cancel = QPushButton('取消')
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton('保存')
        self.btn_ok.setObjectName('primary')
        self.btn_ok.clicked.connect(self._on_save)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

    def _on_save(self):
        name = self.le_name.text().strip()
        if not name:
            self.lbl_err.setText('请填写教练姓名')
            self.lbl_err.show()
            return
        self.accept()

    def get_coach(self) -> dict:
        """收集表单为教练 dict（确认对话框后调用）。"""
        return {
            'name': self.le_name.text().strip(),
            'phone': self.le_phone.text().strip(),
            'role': self.cb_role.currentText().strip(),
            'specialty': self.le_specialty.text().strip(),
            'join_date': self.le_join.text().strip(),
            'note': self.le_note.text().strip(),
        }


class CoachScreen(QWidget):
    """教练管理主界面。"""

    COLUMNS = HEADER_LABELS

    def __init__(self, archive_dir_getter=None, parent=None):
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        self._source_model = CoachTableModel(parent=self)
        self._proxy_model = CoachSortFilterProxyModel(parent=self)
        self._proxy_model.setSourceModel(self._source_model)
        self._init_ui()

    #==== UI 组装 ====

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(12)

        # 1. 页头：标题 + 计数徽章 + 副标题
        self.header = PageHeader('教练管理', subtitle='管理教练团队、联系方式与在职状态')
        lay.addWidget(self.header)

        # 2. 工具栏：搜索 | 刷新 | + 新增教练
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.le_search = QLineEdit(placeholderText='搜索姓名、电话、角色或专长...')
        self.le_search.setClearButtonEnabled(True)
        self.le_search.textChanged.connect(self._on_search)
        toolbar.addWidget(self.le_search, 1)

        self.btn_refresh = QPushButton('刷新')
        self.btn_refresh.setObjectName('secondary')
        self.btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(self.btn_refresh)

        self.btn_add = QPushButton('+ 新增教练')
        self.btn_add.setObjectName('primary')
        self.btn_add.clicked.connect(self.on_add)
        toolbar.addWidget(self.btn_add)
        lay.addLayout(toolbar)

        # 3. 筛选 chips（单选互斥）
        self.chip_bar = FilterChipBar()
        self.chip_bar.add_chip('all', '全部')
        self.chip_bar.add_chip('active', '在职', accent='#10B981')
        self.chip_bar.add_chip('inactive', '离职', accent='#9B9B9B')
        self.chip_bar.filterChanged.connect(self._on_filter_changed)
        lay.addWidget(self.chip_bar)

        # 4. 表格：头像姓名 | 电话 | 角色 | 专长 | 入职日期 | 状态 | 操作
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
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # 姓名
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # 电话
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)   # 角色
        header.setSectionResizeMode(3, QHeaderView.Stretch)            # 专长（吸收剩余宽度）
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)   # 入职日期
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)   # 状态
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)   # 操作
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setFixedHeight(44)
        self.table.setMinimumHeight(400)
        self.table.doubleClicked.connect(self.on_edit)

        # delegates：姓名头像 / 状态徽章 / 行内操作
        self.table.setItemDelegateForColumn(0, AvatarNameDelegate(self.table))
        self.table.setItemDelegateForColumn(5, StatusBadgeDelegate(self.table))
        self.table.setItemDelegateForColumn(6, RowActionsDelegate({
            'active': [
                ('编辑', self._on_action_edit),
                ('离职', self._on_action_deactivate),
            ],
            'inactive': [
                ('恢复', self._on_action_reactivate),
            ],
        }, self.table))
        lay.addWidget(self.table, 1)

        # 5. 底部计数栏
        footer = QFrame()
        footer.setObjectName('footerBar')
        footer.setStyleSheet(f'''
            QFrame#footerBar {{
                background: {ColorPalette.CARD};
                border: 1px solid #E5E5E5; border-radius: 12px;
            }}
        ''')
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        self.lbl_footer = QLabel('共 0 名教练')
        self.lbl_footer.setStyleSheet('color: #6B6B6B; font-size: 13px; background: transparent; border: none;')
        fl.addWidget(self.lbl_footer)
        fl.addStretch()
        self.lbl_hint = QLabel('双击行编辑 · 右键恢复离职教练')
        self.lbl_hint.setStyleSheet('color: #9B9B9B; font-size: 12px; background: transparent; border: none;')
        fl.addWidget(self.lbl_hint)
        lay.addWidget(footer)

    #==== 数据刷新 ====

    def refresh(self):
        """从存储刷新全量教练（含离职），显示层由 chips 过滤。"""
        archive_dir = self._get_dir()
        if not archive_dir:
            self._source_model.set_coaches([])
            self._update_chips([])
            self._update_header_and_footer([])
            return
        try:
            coaches = cm.list_coaches(archive_dir, include_inactive=True)
        except Exception as e:
            dialog.error(self, '加载失败', str(e))
            return
        self._source_model.set_coaches(coaches)
        self._update_chips(coaches)
        self._update_header_and_footer(coaches)

    def _update_chips(self, coaches: list):
        """按全量列表刷新 chips 计数。"""
        total = len(coaches)
        active = sum(1 for c in coaches if c.get('is_active', True))
        self.chip_bar.set_chip_count('all', total)
        self.chip_bar.set_chip_count('active', active)
        self.chip_bar.set_chip_count('inactive', total - active)

    def _update_header_and_footer(self, coaches: list):
        """更新页头计数与底部统计。"""
        self.header.set_count(len(coaches))
        active = sum(1 for c in coaches if c.get('is_active', True))
        self.lbl_footer.setText(f'共 {len(coaches)} 名教练 · 在职 {active} · 离职 {len(coaches) - active}')

    #==== 事件 ====

    def _on_search(self, text: str):
        """搜索过滤由代理模型负责。"""
        self._proxy_model.set_keyword(text)

    def _on_filter_changed(self, key: str):
        """chips 切换：更新代理模型状态过滤。"""
        self._proxy_model.set_status_filter(key)

    def _selected_coach(self) -> dict:
        """当前选中行的教练 dict（未选中返回空 dict）。"""
        row = self.table.currentIndex().row()
        if row < 0:
            return {}
        return self._proxy_model.get_coach_at_proxy(row)

    def on_add(self):
        archive_dir = self._get_dir()
        if not archive_dir:
            dialog.warn(self, '提示', '请先在「体测档案」页设置档案目录')
            return
        dlg = CoachEditDialog(self)
        if dlg.exec() == QDialog.Accepted:
            try:
                cm.save_coach(archive_dir, dlg.get_coach())
                self.refresh()
            except Exception as e:
                dialog.error(self, '保存失败', str(e))

    def on_edit(self):
        archive_dir = self._get_dir()
        if not archive_dir:
            return
        coach = self._selected_coach()
        if not coach:
            dialog.info(self, '提示', '请先选中要编辑的教练')
            return
        dlg = CoachEditDialog(self, coach=coach)
        if dlg.exec() == QDialog.Accepted:
            try:
                cm.save_coach(archive_dir, dlg.get_coach())
                self.refresh()
            except Exception as e:
                dialog.error(self, '保存失败', str(e))

    def _on_action_edit(self, index):
        """操作列「编辑」按钮：定位选中该行后走编辑流程。"""
        self.table.selectRow(self._proxy_model.mapFromSource(index).row())
        self.on_edit()

    def _on_action_deactivate(self, index):
        """操作列「离职」按钮：软删除确认后停用。"""
        if index is None or not index.isValid():
            return
        coach = self._source_model.get_coach_at(index.row())
        name = coach.get('name', '')
        if not name:
            return
        reply = dialog.confirm(
            self, '确认离职',
            f'确定将教练 [{name}] 标记为离职吗？\n（软删除：档案保留，可随时恢复）',
        )
        if not reply:
            return
        try:
            cm.set_coach_active(self._get_dir(), name, False)
            self.refresh()
        except Exception as e:
            dialog.error(self, '操作失败', str(e))

    def _on_action_reactivate(self, index):
        """操作列「恢复」按钮：离职教练恢复在职。"""
        if index is None or not index.isValid():
            return
        coach = self._source_model.get_coach_at(index.row())
        name = coach.get('name', '')
        if not name:
            return
        try:
            cm.set_coach_active(self._get_dir(), name, True)
            self.refresh()
            dialog.info(self, '已恢复', f'教练 [{name}] 已恢复在职')
        except Exception as e:
            dialog.error(self, '恢复失败', str(e))

    def _coach_source_index(self, name: str):
        """按姓名定位源模型 index（找不到返回 None）。"""
        for i, c in enumerate(self._source_model.all_coaches()):
            if c.get('name') == name:
                return self._source_model.index(i, 0)
        return None

    def _on_table_context_menu(self, pos):
        """右键菜单：离职教练恢复 / 在职教练编辑与离职。"""
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        coach = self._proxy_model.get_coach_at_proxy(row)
        if not coach:
            return
        name = coach.get('name', '')
        menu = QMenu(self)
        if not coach.get('is_active', True):
            act = menu.addAction('恢复在职')
            act.triggered.connect(lambda: self._on_action_reactivate(
                self._coach_source_index(name)))
        else:
            act_edit = menu.addAction('编辑')
            act_edit.triggered.connect(self.on_edit)
            act_leave = menu.addAction('标记离职')
            act_leave.triggered.connect(lambda: self._on_action_deactivate(
                self._coach_source_index(name)))
        menu.exec(self.table.viewport().mapToGlobal(pos))
