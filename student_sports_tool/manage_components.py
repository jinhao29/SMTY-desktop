# -*- coding: utf-8 -*-
"""UI 层：管理页共享组件（学员管理 / 教练管理复用）。

布局语言参考现代管理后台（浅色珊瑚橙主题）：
- PageHeader：大标题 + 计数徽章 + 副标题描述
- FilterChip / FilterChipBar：可单选的筛选 chips（状态色圆点 + 文字 + 计数胶囊）
- AvatarNameDelegate：姓名列 delegate（圆形首字头像 + 姓名）
- StatusBadgeDelegate：状态列 delegate（色点 + 浅色胶囊徽章）
- RowActionsDelegate：操作列 delegate（文字幽灵按钮组，免 widget、排序安全）

单一职责：仅提供上述原子组件，不包含业务数据逻辑。
"""
import hashlib

from PySide6.QtCore import Qt, QRect, Signal, Property, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QButtonGroup,
    QSizePolicy, QStyledItemDelegate, QStyle, QApplication, QTabBar
)
from PySide6.QtCore import QPropertyAnimation, QRectF

from base_components import ColorPalette, _fade_color


#==== 页头：标题 + 计数徽章 + 副标题 ====

class PageHeader(QWidget):
    """管理页头部：左侧大标题 + 计数小胶囊 + 下方副标题描述。"""

    def __init__(self, title: str, subtitle: str = '', parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet('background: transparent;')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 22px; font-weight: 800;'
            'background: transparent;'
        )
        row.addWidget(self.lbl_title)

        # 计数徽章（灰底圆角胶囊，参考管理后台标题旁的数字）
        self.lbl_count = QLabel('0')
        self.lbl_count.setStyleSheet('''
            color: #6B6B6B; background: #EFEFEF; border-radius: 10px;
            padding: 2px 10px; font-size: 13px; font-weight: 700;
        ''')
        row.addWidget(self.lbl_count)
        row.addStretch()
        lay.addLayout(row)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet(
            f'color: {ColorPalette.TEXT_SECONDARY}; font-size: 13px;'
            'background: transparent;'
        )
        self.lbl_sub.setVisible(bool(subtitle))
        lay.addWidget(self.lbl_sub)

    def set_count(self, count: int):
        """更新标题旁的计数徽章。"""
        self.lbl_count.setText(str(int(count or 0)))


#==== 筛选 chips ====

class FilterChip(QPushButton):
    """可选中筛选 chip：状态色圆点 + 文字 + 计数（checkable 单选，纯文本配色）。"""

    def __init__(self, text: str, key: str, accent: str = None, parent=None):
        super().__init__(parent)
        self._key = key
        self._text = text
        self._accent = accent
        self._count = 0
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(30)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    @property
    def key(self) -> str:
        """筛选键（如 all/normal/red/yellow/inactive）。"""
        return self._key

    def set_count(self, count: int):
        """更新计数并按选中态刷新样式。"""
        self._count = int(count or 0)
        self._refresh_style()

    def _refresh_style(self):
        accent = self._accent or ColorPalette.PRIMARY
        # QPushButton 不支持富文本：圆点/文字/计数统一由 QSS color 控制
        dot = '● ' if self._accent else ''
        self.setText(f'{dot}{self._text}\u2002{self._count}')
        if self.isChecked():
            self.setStyleSheet(f'''
                QPushButton {{
                    background: {_fade_color(accent, 0.10)};
                    color: {accent}; border: 1px solid {_fade_color(accent, 0.45)};
                    border-radius: 15px; padding: 4px 14px;
                    font-size: 13px; font-weight: 700;
                }}
            ''')
        else:
            self.setStyleSheet('''
                QPushButton {
                    background: #FFFFFF; color: #6B6B6B;
                    border: 1px solid #E5E5E5; border-radius: 15px;
                    padding: 4px 14px; font-size: 13px; font-weight: 500;
                }
                QPushButton:hover { border: 1px solid #CFCFCF; color: #1A1A1A; }
            ''')


class FilterChipBar(QWidget):
    """筛选 chip 行：内部 QButtonGroup 保证单选互斥，切换时发射 filterChanged(key)。"""

    filterChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._chips = {}
        self._group.buttonToggled.connect(self._on_toggled)

    def add_chip(self, key: str, text: str, accent: str = None) -> FilterChip:
        """添加 chip；首枚默认选中。"""
        chip = FilterChip(text, key, accent=accent)
        self._group.addButton(chip)
        # 尾部 stretch 固定后重排：保证 chips 紧凑左对齐
        if self._lay.count() and self._lay.itemAt(self._lay.count() - 1).spacerItem():
            self._lay.takeAt(self._lay.count() - 1)
        self._lay.addWidget(chip)
        self._lay.addStretch()
        self._chips[key] = chip
        if len(self._chips) == 1:
            chip.setChecked(True)
        chip._refresh_style()
        return chip

    def _on_toggled(self, button, checked: bool):
        """任一 chip 切换：刷新全部 chips 样式并广播当前选中 key。"""
        for chip in self._chips.values():
            chip._refresh_style()
        if checked:
            self.filterChanged.emit(button.key)

    def current_key(self) -> str:
        """当前选中的筛选 key。"""
        for key, chip in self._chips.items():
            if chip.isChecked():
                return key
        return ''

    def set_chip_count(self, key: str, count: int):
        """更新指定 chip 的计数。"""
        chip = self._chips.get(key)
        if chip is not None:
            chip.set_count(count)


#==== 头像配色（按姓名 hash 稳定取色，浅底深字的柔和色组） ====

_AVATAR_PALETTES = [
    ('#FFE4DC', '#C2492C'),  # 珊瑚
    ('#DBEEFF', '#1D6FB8'),  # 蓝
    ('#DDF5E7', '#1E8A5A'),  # 绿
    ('#FDEFD3', '#A66A12'),  # 黄
    ('#EEE7FB', '#6D4FC2'),  # 紫
    ('#FBE3EF', '#B0447A'),  # 粉
]
_AVATAR_GRAY = ('#EFEFEF', '#9B9B9B')


def _avatar_colors(name: str, muted: bool = False):
    """按姓名 hash 稳定返回 (底色, 文字色)；muted 时返回灰色组。"""
    if muted:
        return _AVATAR_GRAY
    digest = hashlib.md5(name.encode('utf-8')).digest()
    return _AVATAR_PALETTES[digest[0] % len(_AVATAR_PALETTES)]


#==== 姓名列 delegate：圆形首字头像 + 姓名 ====

class AvatarNameDelegate(QStyledItemDelegate):
    """姓名列：左侧圆形首字头像 + 右侧姓名文字。

    停用行（UserRole=Qt.UserRole+1 传 bool 或 model FontRole 斜体）仅灰显：
    头像灰底灰字，文字颜色交由 model 的 ForegroundRole 控制。
    """

    AVATAR_SIZE = 26
    GAP = 10

    def paint(self, painter, option, index):
        # 先让 view 画选中/hover 背景
        opt = option
        self.initStyleOption(opt, index)
        opt.text = ''
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        name = index.data(Qt.DisplayRole) or ''
        if not name:
            return
        muted = index.data(Qt.UserRole + 1) is False
        bg, fg = _avatar_colors(name, muted=muted)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cell = option.rect
        cy = cell.center().y()
        ax = cell.x() + 10
        ay = cy - self.AVATAR_SIZE // 2

        # 圆形头像
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawEllipse(ax, ay, self.AVATAR_SIZE, self.AVATAR_SIZE)
        # 首字
        painter.setPen(QColor(fg))
        f = QFont(option.font)
        f.setPointSizeF(max(f.pointSizeF() - 1.0, 9.0))
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(
            QRect(ax, ay, self.AVATAR_SIZE, self.AVATAR_SIZE),
            Qt.AlignCenter, name[0]
        )

        # 姓名文字（颜色遵循 ForegroundRole，停用行为灰色）
        fg_color = QColor('#1A1A1A')
        role_color = index.data(Qt.ForegroundRole)
        if role_color is not None:
            fg_color = QColor(role_color)
        painter.setPen(fg_color)
        painter.setFont(option.font)
        tx = ax + self.AVATAR_SIZE + self.GAP
        text_rect = QRect(tx, cell.y(), cell.right() - tx, cell.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, name)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        name = index.data(Qt.DisplayRole) or ''
        fm = QFontMetrics(option.font)
        need = 10 + self.AVATAR_SIZE + self.GAP + fm.horizontalAdvance(name) + 14
        return _size(base, need, base.height())


def _size(base, w, h):
    """构造不小于 (w, h) 的 QSize（辅助函数）。"""
    from PySide6.QtCore import QSize
    s = QSize(base)
    s.setWidth(max(s.width(), w))
    s.setHeight(max(s.height(), h))
    return s


#==== 状态列 delegate：色点 + 浅色胶囊徽章 ====

def _status_style(text: str):
    """状态文本 → (圆点色, 胶囊底色, 文字色)。未知状态回退灰色。"""
    t = (text or '').strip()
    if t.startswith('正常'):
        return '#10B981', _fade_color('#10B981', 0.10), '#1E8A5A'
    if t.startswith('需续费'):
        return '#EF4444', _fade_color('#EF4444', 0.10), '#C53030'
    if t.startswith('关注'):
        return '#F59E0B', _fade_color('#F59E0B', 0.12), '#A66A12'
    if t.startswith('在职'):
        return '#10B981', _fade_color('#10B981', 0.10), '#1E8A5A'
    return '#9B9B9B', '#F0F0F0', '#6B6B6B'


class StatusBadgeDelegate(QStyledItemDelegate):
    """状态列：左侧小圆点 + 浅色胶囊底 + 深色语义文字（参考管理后台 Status 列）。"""

    PAD_H = 12
    DOT_GAP = 7
    DOT_SIZE = 7

    def paint(self, painter, option, index):
        opt = option
        self.initStyleOption(opt, index)
        opt.text = ''
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        text = index.data(Qt.DisplayRole) or ''
        if not text:
            return
        dot, pill_bg, fg = _status_style(text)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fm = QFontMetrics(option.font)
        text_w = fm.horizontalAdvance(text)
        pill_w = self.PAD_H * 2 + self.DOT_SIZE + self.DOT_GAP + text_w
        pill_h = min(option.rect.height() - 10, 26)
        px = option.rect.x() + (option.rect.width() - pill_w) // 2
        py = option.rect.center().y() - pill_h // 2

        # 胶囊底
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(pill_bg))
        painter.drawRoundedRect(px, py, pill_w, pill_h, pill_h // 2, pill_h // 2)
        # 圆点
        cy = option.rect.center().y()
        painter.setBrush(QColor(dot))
        painter.drawEllipse(px + self.PAD_H, cy - self.DOT_SIZE // 2, self.DOT_SIZE, self.DOT_SIZE)
        # 文字
        painter.setPen(QColor(fg))
        painter.setFont(option.font)
        tx = px + self.PAD_H + self.DOT_SIZE + self.DOT_GAP
        painter.drawText(QRect(tx, option.rect.y(), text_w + 2, option.rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        text = index.data(Qt.DisplayRole) or ''
        fm = QFontMetrics(option.font)
        w = self.PAD_H * 2 + self.DOT_SIZE + self.DOT_GAP + fm.horizontalAdvance(text) + 8
        return _size(base, w, 30)


#==== 操作列 delegate：文字幽灵按钮组 ====

class RowActionsDelegate(QStyledItemDelegate):
    """操作列：一组文字幽灵按钮（无 widget，排序/过滤安全）。

    actions_map: {key: [(label, callback(index)), ...]}
    按钮组按 index 的 UserRole+2 取 key（默认 'default'），
    学员/教练表用它区分在职行（编辑/课时/停用）与停用行（恢复）。
    """

    PAD_H = 10
    PAD_V = 4
    BTN_GAP = 6

    def __init__(self, actions_map: dict, parent=None):
        super().__init__(parent)
        self._actions_map = actions_map

    def _actions_for(self, index):
        key = index.data(Qt.UserRole + 2) or 'default'
        return self._actions_map.get(key, [])

    def _button_rects(self, option, index):
        """返回 [(label, QRect), ...] 按钮矩形列表（垂直居中排布）。"""
        actions = self._actions_for(index)
        fm = QFontMetrics(option.font)
        rects = []
        x = option.rect.x() + self.PAD_H
        cy = option.rect.center().y()
        btn_h = min(option.rect.height() - 8, 26)
        for label, _cb in actions:
            w = self.PAD_H * 2 + fm.horizontalAdvance(label)
            y = cy - btn_h // 2
            rects.append((label, QRect(x, y, w, btn_h)))
            x += w + self.BTN_GAP
        return rects

    def paint(self, painter, option, index):
        opt = option
        self.initStyleOption(opt, index)
        opt.text = ''
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        actions = self._actions_for(index)
        if not actions:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = QFont(option.font)
        f.setPointSizeF(max(f.pointSizeF() - 0.5, 9.0))
        painter.setFont(f)
        fm = QFontMetrics(f)
        muted = index.data(Qt.UserRole + 1) is False
        for label, rect in self._button_rects(option, index):
            if muted:
                # 停用行：恢复按钮用绿色系
                bg, border, fg = _fade_color('#10B981', 0.08), _fade_color('#10B981', 0.30), '#1E8A5A'
            else:
                bg, border, fg = '#F5F5F5', '#E3E3E3', '#6B6B6B'
            painter.setPen(QPen(QColor(border), 1))
            painter.setBrush(QColor(bg))
            # 胶囊描边（参考李哥 Click 按钮图）：圆角取高度一半
            painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
            painter.setPen(QColor(fg))
            painter.drawText(rect, Qt.AlignCenter, label)
            painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        actions = self._actions_for(index)
        fm = QFontMetrics(option.font)
        w = self.PAD_H + sum(self.PAD_H * 2 + fm.horizontalAdvance(label) + self.BTN_GAP for label, _ in actions)
        return _size(base, w, 30)

    def editorEvent(self, event, model, option, index):
        """点击命中检测：映射到对应按钮回调（传源模型 index）。"""
        from PySide6.QtCore import QEvent
        if event.type() != QEvent.MouseButtonRelease:
            return False
        pos = event.pos()
        for label, rect in self._button_rects(option, index):
            if rect.adjusted(-3, -3, 3, 3).contains(pos):
                actions = self._actions_for(index)
                for lbl, cb in actions:
                    if lbl == label:
                        cb(index)
                        return True
        return False


#==== Tab 栏：滑动下划线过渡动画（参考李哥 2026-09-07 导航样式图） ====

class AnimatedTabBar(QTabBar):
    """带滑动指示条动画的 Tab 栏。

    - 文字颜色由外部 QSS 控制（选中橙色 / hover 过渡）
    - 选中下划线由本类绘制：切换 Tab 时以 180ms OutCubic 动画滑到新位置
    - resizeEvent 时指示条立即吸附到当前 Tab（避免错位）
    """

    _INDICATOR_H = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._indicator_x = 0.0
        self._indicator_w = 0.0
        self._anim = QPropertyAnimation(self, b'indicatorX', self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.currentChanged.connect(self._on_current_changed)

    # QPropertyAnimation 使用的属性（float，px）
    def _get_indicator_x(self) -> float:
        return self._indicator_x

    def _set_indicator_x(self, v: float):
        self._indicator_x = float(v)
        self.update()

    indicatorX = Property(float, _get_indicator_x, _set_indicator_x)

    def _target_geometry(self, index: int):
        """返回当前 index 指示条的 (x, width)（居中缩窄版，参考图7 文字宽度感）。"""
        r = self.tabRect(index)
        w = max(28.0, min(float(r.width()) - 24.0, 72.0))
        x = r.x() + (r.width() - w) / 2.0
        return x, w

    def _snap(self, index: int):
        x, w = self._target_geometry(index)
        self._indicator_x = x
        self._indicator_w = w
        self.update()

    def _on_current_changed(self, index: int):
        self._indicator_w = self._target_geometry(index)[1]
        self._anim.stop()
        self._anim.setStartValue(self._indicator_x)
        self._anim.setEndValue(self._target_geometry(index)[0])
        self._anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.count():
            self._snap(self.currentIndex())

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() <= 0 or self.currentIndex() < 0:
            return
        if self._indicator_w <= 0:
            self._snap(self.currentIndex())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        y = self.height() - self._INDICATOR_H - 1
        rect = QRectF(self._indicator_x, y, self._indicator_w, self._INDICATOR_H)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#FF6B47'))
        painter.drawRoundedRect(rect, self._INDICATOR_H / 2, self._INDICATOR_H / 2)
        painter.end()
