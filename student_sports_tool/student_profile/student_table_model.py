# -*- coding: utf-8 -*-
"""数据层：学员列表表格模型（QAbstractTableModel + QSortFilterProxyModel）。

职责：
- StudentTableModel：以 list[dict] 为数据源的表格模型，支持显示与排序
- StudentSortFilterProxyModel：在源模型之上提供搜索过滤与列排序

设计说明：
- 仅处理数据/视图契约，不涉及业务逻辑与 UI 控件
- 数值列（年龄/身高/体重/BMI/总课时/已上/剩余）按数值大小排序
- 文本列按本地化字符串排序
- 通过 set_students 重置数据，调用 beginResetModel/endResetModel 保证视图同步
- is_active=False 的学员在 data() 中以灰色前景显示，与原 QTableWidget 行为一致
"""
from typing import List, Dict, Any

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
)
from PySide6.QtGui import QColor, QFont


# 列定义：(显示名, 数据键, 是否数值列)
COLUMNS = [
    ('姓名', 'name', False),
    ('年龄', 'age', True),
    ('身高', 'height', True),
    ('体重', 'weight', True),
    ('BMI', 'bmi', True),
    ('体型', 'body_type', False),
    ('年级', 'grade_display', False),
    ('总课时', 'total', True),
    ('已上', 'attended', True),
    ('剩余', 'remaining', True),
    ('状态', 'status_label', False),
]

# 数值列索引集合（用于排序时区分数值/文本）
NUMERIC_COLS = {i for i, (_, _, is_num) in enumerate(COLUMNS) if is_num}

# 默认列数与表头
COLUMN_COUNT = len(COLUMNS)
HEADER_LABELS = [c[0] for c in COLUMNS]


def _to_float(value: Any) -> float:
    """安全转换为 float，失败返回 0.0。"""
    try:
        if value is None or value == '':
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_value(key: str, s: Dict[str, Any]) -> str:
    """根据字段键格式化显示文本，与原 _render_table 保持一致。"""
    if key == 'height':
        v = s.get('height')
        return f"{v:g}" if v not in (None, '', 0) else ''
    if key == 'weight':
        v = s.get('weight')
        return f"{v:g}" if v not in (None, '', 0) else ''
    if key == 'bmi':
        v = s.get('bmi')
        return f"{v:g}" if v else '—'
    if key == 'body_type':
        return s.get('body_type', '') or '—'
    if key == 'grade_display':
        return s.get('grade_display') or ''
    if key == 'status_label':
        # 已在 set_students 中预计算
        return s.get('status_label', '正常')
    if key in ('age', 'total', 'attended', 'remaining'):
        return str(s.get(key, 0) or 0)
    # 默认：name 等
    return str(s.get(key, '') or '')


def _compute_status_label(s: Dict[str, Any]) -> str:
    """根据学员状态计算状态列文本（与原 _warn_label 对齐）。"""
    if not s.get('is_active', True):
        return '已停用'
    level = s.get('warn_level', 'normal')
    if level == 'red':
        return f'需续费（剩 {s.get("remaining", 0)} 课时）'
    if level == 'yellow':
        return f'关注（剩 {s.get("remaining", 0)} 课时）'
    if level == 'unknown':
        return '未设总课时'
    return '正常'


class StudentTableModel(QAbstractTableModel):
    """学员数据表格模型：以 list[dict] 为数据源。"""

    def __init__(self, students: List[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self._students: List[Dict[str, Any]] = []
        if students:
            self.set_students(students)

    def set_students(self, students: List[Dict[str, Any]]):
        """重置数据源（预计算 status_label 等显示字段）。"""
        self.beginResetModel()
        # 预计算显示字段，避免 data() 频繁调用
        prepared = []
        for s in students or []:
            row = dict(s)
            row['status_label'] = _compute_status_label(s)
            prepared.append(row)
        self._students = prepared
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent is None or parent.isValid():
            return 0
        return len(self._students)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent is None or parent.isValid():
            return 0
        return COLUMN_COUNT

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < COLUMN_COUNT:
            return HEADER_LABELS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._students):
            return None
        if col < 0 or col >= COLUMN_COUNT:
            return None
        s = self._students[row]
        key = COLUMNS[col][1]
        is_active = s.get('is_active', True)

        if role == Qt.DisplayRole:
            return _format_value(key, s)

        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter

        if role == Qt.ForegroundRole:
            # 已停用：整行灰色
            if not is_active:
                return QColor('#9B9B9B')
            # 剩余列：根据 warn_level 着色
            if col == 9:  # 剩余
                level = s.get('warn_level', 'normal')
                if level == 'red':
                    return QColor('#F87171')
                if level == 'yellow':
                    return QColor('#FBBF24')
            # 状态列：根据 warn_level 着色
            if col == 10:  # 状态
                level = s.get('warn_level', 'normal')
                if level == 'red':
                    return QColor('#F87171')
                if level == 'yellow':
                    return QColor('#FBBF24')
                return QColor('#34D399')
            # BMI 列：根据 body_type 着色
            if col == 4 and s.get('bmi'):
                try:
                    from bmi_processor import body_type_color
                    return QColor(body_type_color(s.get('body_type', '')))
                except Exception:
                    return None
            return None

        if role == Qt.FontRole:
            # 已停用学员姓名列：斜体（替代删除线效果）
            if not is_active and col == 0:
                font = QFont()
                font.setItalic(True)
                return font
            return None

        return None

    def get_student_at(self, row: int) -> Dict[str, Any]:
        """返回指定行（源模型行）的学员 dict，越界返回空 dict。"""
        if 0 <= row < len(self._students):
            return self._students[row]
        return {}

    def get_student_name_at(self, row: int) -> str:
        """返回指定行的学员姓名（用于双击编辑等）。"""
        s = self.get_student_at(row)
        return s.get('name', '')

    def all_students(self) -> List[Dict[str, Any]]:
        """返回当前模型持有的全部学员列表（只读引用）。"""
        return self._students


class StudentSortFilterProxyModel(QSortFilterProxyModel):
    """学员表格排序 + 搜索过滤代理模型。

    - 搜索关键字匹配姓名或年级（不区分大小写）
    - 排序：数值列按 float 比较，文本列按本地化字符串比较
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keyword: str = ''

    def set_keyword(self, keyword: str):
        """设置搜索关键字（空串表示无过滤）。"""
        kw = (keyword or '').strip().lower()
        if kw == self._keyword:
            return
        self._keyword = kw
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._keyword:
            return True
        sm = self.sourceModel()
        if not isinstance(sm, StudentTableModel):
            return True
        s = sm.get_student_at(source_row)
        if not s:
            return False
        name = (s.get('name', '') or '').lower()
        grade = (s.get('grade', '') or '').lower()
        return self._keyword in name or self._keyword in grade

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """排序比较：数值列按数值，文本列按字符串。"""
        col = left.column()
        if col in NUMERIC_COLS:
            lv = _to_float(left.data(Qt.DisplayRole))
            rv = _to_float(right.data(Qt.DisplayRole))
            return lv < rv
        # 文本列：本地化字符串比较
        lv = left.data(Qt.DisplayRole) or ''
        rv = right.data(Qt.DisplayRole) or ''
        return lv < rv

    def get_student_name_at_proxy(self, proxy_row: int) -> str:
        """通过代理模型行号获取学员姓名（自动映射到源模型）。"""
        proxy_idx = self.index(proxy_row, 0)
        source_idx = self.mapToSource(proxy_idx)
        sm = self.sourceModel()
        if not isinstance(sm, StudentTableModel):
            return ''
        return sm.get_student_name_at(source_idx.row())

    def get_student_at_proxy(self, proxy_row: int) -> Dict[str, Any]:
        """通过代理模型行号获取学员 dict（自动映射到源模型）。"""
        proxy_idx = self.index(proxy_row, 0)
        source_idx = self.mapToSource(proxy_idx)
        sm = self.sourceModel()
        if not isinstance(sm, StudentTableModel):
            return {}
        return sm.get_student_at(source_idx.row())
