# -*- coding: utf-8 -*-
"""UI 层：教练管理页面（**只读镜像**，数据来自手机端备份）。

v67（李哥拍板 D2）：教练数据的重心在 Android —— 薪资结算 / 排课 / 团队管理都在手机，
PC 只有 6 个基础字段且不参与同步 → 同一份数据两端各存一份早晚对不上。
本页因此改为**只读**：数据由备份恢复流程把 Android 备份里的 `coaches[]`
灌进本地档案（`coach_manager.replace_mirror`，整体替换、以手机为真源），
PC 不再提供新增 / 编辑 / 离职 / 删除 / 恢复入口。

布局结构（与学员管理页统一）：
1. 页头：大标题 + 计数徽章 + 副标题（标注数据来源为手机备份）
2. 工具栏：搜索框 | 刷新
3. 筛选 chips：全部(n) / 在职(n) / 离职(n)，单选互斥
4. 表格：头像姓名 | 电话 | 专长 | 状态徽章 | 操作(详情)
5. 底部计数栏

数据层：coach_manager（教练档案.xlsx，由备份镜像整体替换）。
说明：Android 备份只导出 name / phone / specialty / status 四个字段（不动同步协议），
故「角色」「入职日期」「备注」三列不在此页展示。
"""
import os
import sys

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableView, QHeaderView, QFrame, QAbstractItemView
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
# 只读镜像：仅展示 Android 备份导出的字段 + 状态徽章 + 操作列
COLUMNS = [
    ('姓名', 'name', False),
    ('电话', 'phone', False),
    ('专长', 'specialty', False),
    ('状态', 'status_label', False),
    ('操作', '_actions', False),
]
COLUMN_COUNT = len(COLUMNS)
HEADER_LABELS = [c[0] for c in COLUMNS]

# 只读页唯一行内操作
ROW_ACTIONS = [('详情', '_on_open_detail_index')]


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
            # RowActionsDelegate 按钮组 key（只读页两组同款：仅「详情」）
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

    - 关键字匹配姓名 / 电话 / 专长（不区分大小写）
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
        haystack = ' '.join(str(c.get(k, '') or '') for k in ('name', 'phone', 'specialty')).lower()
        return self._keyword in haystack

    def get_coach_at_proxy(self, proxy_row: int) -> dict:
        """通过代理行号取教练 dict（自动映射源模型）。"""
        proxy_idx = self.index(proxy_row, 0)
        src = self.mapToSource(proxy_idx)
        sm = self.sourceModel()
        if isinstance(sm, CoachTableModel):
            return sm.get_coach_at(src.row())
        return {}


class CoachScreen(QWidget):
    """教练管理主界面（只读镜像）。"""

    COLUMNS = HEADER_LABELS

    # 双击行 / 操作列「详情」时发射（App 据此打开教练详情页）
    coachActivated = Signal(str)

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

        # 1. 页头：标题 + 计数徽章 + 副标题（点明数据来源，避免误以为能在 PC 改）
        self.header = PageHeader(
            '教练管理',
            subtitle='数据来自手机端备份，本页只读（新增/编辑请在手机端操作）',
        )
        lay.addWidget(self.header)

        # 2. 工具栏：搜索 | 刷新（只读页不提供新增入口）
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.le_search = QLineEdit(placeholderText='搜索姓名、电话或专长...')
        self.le_search.setClearButtonEnabled(True)
        self.le_search.textChanged.connect(self._on_search)
        toolbar.addWidget(self.le_search, 1)

        self.btn_refresh = QPushButton('刷新')
        self.btn_refresh.setObjectName('secondary')
        self.btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(self.btn_refresh)
        lay.addLayout(toolbar)

        # 3. 筛选 chips（单选互斥）
        self.chip_bar = FilterChipBar()
        self.chip_bar.add_chip('all', '全部')
        self.chip_bar.add_chip('active', '在职', accent='#10B981')
        self.chip_bar.add_chip('inactive', '离职', accent='#9B9B9B')
        self.chip_bar.filterChanged.connect(self._on_filter_changed)
        lay.addWidget(self.chip_bar)

        # 4. 表格：头像姓名 | 电话 | 专长 | 状态 | 操作
        self.table = QTableView()
        self.table.setModel(self._proxy_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # 姓名
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # 电话
        header.setSectionResizeMode(2, QHeaderView.Stretch)            # 专长（吸收剩余宽度）
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)   # 状态
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)   # 操作
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setFixedHeight(44)
        self.table.setMinimumHeight(400)
        # 双击行 → 教练详情页（只读页无编辑入口）
        self.table.doubleClicked.connect(self._on_open_detail)

        # delegates：姓名头像 / 状态徽章 / 行内操作（仅「详情」）
        self.table.setItemDelegateForColumn(0, AvatarNameDelegate(self.table))
        self.table.setItemDelegateForColumn(3, StatusBadgeDelegate(self.table))
        self.table.setItemDelegateForColumn(
            4, RowActionsDelegate({'active': ROW_ACTIONS, 'inactive': ROW_ACTIONS}, self.table)
        )
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
        self.lbl_hint = QLabel('双击行查看详情 · 编辑请在手机端操作')
        self.lbl_hint.setStyleSheet('color: #9B9B9B; font-size: 12px; background: transparent; border: none;')
        fl.addWidget(self.lbl_hint)
        lay.addWidget(footer)

    #==== 数据刷新 ====

    def refresh(self):
        """从本地镜像文件刷新全量教练（含离职），显示层由 chips 过滤。

        数据由备份恢复流程写入（coach_manager.replace_mirror），本页不产生写入。
        """
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

    def _on_open_detail_index(self, index):
        """操作列「详情」按钮：按源行定位教练并打开详情页。"""
        if index is None or not index.isValid():
            return
        coach = self._source_model.get_coach_at(index.row())
        if coach.get('name'):
            self.coachActivated.emit(coach['name'])

    def _on_open_detail(self, proxy_index):
        """双击行：打开教练详情页。"""
        coach = self._proxy_model.get_coach_at_proxy(proxy_index.row())
        if coach.get('name'):
            self.coachActivated.emit(coach['name'])

    def _on_filter_changed(self, key: str):
        """chips 切换：更新代理模型状态过滤。"""
        self._proxy_model.set_status_filter(key)
