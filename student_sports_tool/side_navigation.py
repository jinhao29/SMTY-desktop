# -*- coding: utf-8 -*-
"""UI 层：左侧固定导航栏组件（浅色珊瑚橙主题，参考 SaaS 后台导航风格）。

职责：
- NavItem：可点击的导航菜单项按钮（checkable，带图标与可选数字徽标）
- SideNav：左侧固定宽度垂直导航栏，顶部品牌块 + 搜索框 + 中部菜单 + 底部辅助项

单一职责：仅承担「应用级导航交互 + 全局搜索入口」，
- 通过 QButtonGroup 保证菜单项单选
- 点击菜单项时发射 navChanged(index) 信号，由主窗口切换 QStackedWidget
- 搜索框回车时发射 searchSubmitted(text)，由主窗口路由到学员档案页过滤
- set_badge(index, count) 供主窗口更新菜单项数字徽标（如续费预警人数）
- 不包含业务卡片、表单、表格等业务组件

依赖：base_components.ColorPalette / IconBox / _draw_icon
"""
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QButtonGroup, QLabel,
    QLineEdit, QSizePolicy
)

from base_components import ColorPalette, IconBox, _draw_icon


def _nav_pixmap(icon_type: int, color: str, size: int = 18) -> QPixmap:
    """以指定颜色渲染单色导航图标（透明底，无 IconBox 底盒）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    m = 2
    _draw_icon(painter, icon_type, QRect(m, m, size - m * 2, size - m * 2))
    painter.end()
    return pm


class NavItem(QPushButton):
    """导航菜单项按钮（checkable，单选，含图标与可选红色数字徽标）。

    视觉三态（统一由 _refresh_state 在 enter/leave/toggled 时调用，避免样式残留）：
    - 选中：主色浅底 + 主色文字 + 主色图标（柔和胶囊）
    - 仅 hover：中性浅灰底 + 深色文字（与选中可区分）
    - 普通：透明底 + 中灰文字

    ponytail：早期版本只把 setStyleSheet 串写在 enter/leave，导致点击切换时
    旧菜单项的样式停在「选中」态无法清除（QButtonGroup 自动 uncheck 不会触发
    enter/leave）。修复：toggled 信号也走 _refresh_state，背景从 isChecked +
    underMouse 重新计算。
    """

    def __init__(self, text: str, index: int, icon_type: int = None, parent=None):
        """
        参数:
            text: 菜单项显示文本
            index: 对应 QStackedWidget 的页面索引
            icon_type: IconBox 图标类型（None 则不显示图标）
        """
        super().__init__(parent)
        self._index = index
        self._icon_type = icon_type
        self._pm_normal = None
        self._pm_checked = None
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName('NavItem')
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(10)
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(18, 18)
        self._icon_label.setStyleSheet('background: transparent;')
        lay.addWidget(self._icon_label)
        self._text_label = QLabel(text)
        self._text_label.setStyleSheet('background: transparent; font-size: 14px;')
        lay.addWidget(self._text_label, 1)
        self._badge = QLabel()
        self._badge.setStyleSheet(
            'background: #F87171; color: #FFFFFF; border: none;'
            'border-radius: 9px; padding: 1px 7px; font-size: 11px; font-weight: 700;'
        )
        self._badge.hide()
        lay.addWidget(self._badge)

        if icon_type is not None:
            self._render_icons()
        # 关键：toggled 信号也走刷新，否则 auto-uncheck 后的菜单项不会清背景
        self.toggled.connect(self._refresh_state)
        self._refresh_state()

    @property
    def index(self) -> int:
        """对应 QStackedWidget 的页面索引。"""
        return self._index

    def set_badge(self, count: int):
        """设置数字徽标（<=0 时隐藏）。"""
        count = int(count or 0)
        if count > 0:
            self._badge.setText(str(count) if count < 99 else '99+')
            self._badge.show()
        else:
            self._badge.hide()

    def _render_icons(self):
        """预渲染未选中 / 选中两态图标。"""
        self._pm_normal = _nav_pixmap(self._icon_type, ColorPalette.TEXT_SECONDARY)
        self._pm_checked = _nav_pixmap(self._icon_type, ColorPalette.PRIMARY)
        self._icon_label.setPixmap(self._pm_normal)
        self._icon_label.show()

    def _refresh_state(self):
        """按当前 isChecked + underMouse 三态统一刷新背景 + 文字色 + 图标。

        是 enterEvent / leaveEvent / toggled 的唯一渲染入口，
        确保 QSS 字符串与真实状态始终一致（修复旧的「点击切换后背景残留」bug）。
        """
        checked = self.isChecked()
        hover = self.underMouse()
        if checked:
            bg = ColorPalette.PRIMARY_LIGHT
            text_color = ColorPalette.PRIMARY
            text_weight = 700
            icon_pm = self._pm_checked
        elif hover:
            bg = '#ECECEE'
            text_color = ColorPalette.TEXT
            text_weight = 500
            icon_pm = self._pm_normal
        else:
            bg = 'transparent'
            text_color = ColorPalette.TEXT_SECONDARY
            text_weight = 500
            icon_pm = self._pm_normal
        if icon_pm is not None:
            self._icon_label.setPixmap(icon_pm)
        self._text_label.setStyleSheet(
            f'background: transparent; font-size: 14px;'
            f'color: {text_color}; font-weight: {text_weight};'
        )
        self.setStyleSheet(f'''
            QPushButton#NavItem {{
                background: {bg};
                border: none;
                border-radius: 12px;
                padding: 9px 4px;
                text-align: left;
            }}
        ''')

    def enterEvent(self, event):
        self._refresh_state()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._refresh_state()
        super().leaveEvent(event)


class SideNav(QWidget):
    """左侧固定宽度垂直导航栏。

    结构：
        ┌──────────────────┐
        │ [logo] 上门体育   │  品牌块（logo 方块 + 名称 + 副标题）
        │        教学管理   │
        │ 🔍 搜索学员...    │  全局搜索（回车提交）
        ├──────────────────┤
        │  菜单项 1        │  中部（主菜单，QButtonGroup 单选）
        │  菜单项 N        │
        ├──────────────────┤
        │  帮助 / 退出登录  │  底部（辅助菜单）
        └──────────────────┘

    信号:
        navChanged(int): 主菜单项被点击时发射，参数为对应页面索引
        searchSubmitted(str): 搜索框回车提交
        helpRequested(): 底部"帮助"被点击时发射
        logoutRequested(): 底部"退出登录"被点击时发射
    """

    navChanged = Signal(int)
    searchSubmitted = Signal(str)
    helpRequested = Signal()
    logoutRequested = Signal()

    NAV_WIDTH = 232  # 侧边栏固定宽度

    def __init__(self, menu_items, parent=None, title: str = '上门体育'):
        """
        参数:
            menu_items: [(text, index) 或 (text, index, icon_type), ...]
            title: 顶部标题文本
        """
        super().__init__(parent)
        self.setFixedWidth(self.NAV_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setStyleSheet(f'''
            SideNav {{
                background-color: {ColorPalette.SIDEBAR_BG};
                border: none;
                border-right: 1px solid {ColorPalette.DIVIDER};
            }}
        ''')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 20, 14, 16)
        lay.setSpacing(6)

        # === 品牌块：logo 方块 + 名称 + 副标题 ===
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo_box = QLabel('上')
        logo_box.setFixedSize(38, 38)
        logo_box.setAlignment(Qt.AlignCenter)
        logo_box.setStyleSheet(
            f'background: {ColorPalette.PRIMARY}; color: #FFFFFF; border: none;'
            f'border-radius: 12px; font-size: 17px; font-weight: 800;'
        )
        brand.addWidget(logo_box)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        t = QLabel(title)
        t.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 15px; font-weight: 800;'
            'background: transparent;'
        )
        sub = QLabel('教学管理平台')
        sub.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; font-size: 11px; background: transparent;'
        )
        brand_text.addWidget(t)
        brand_text.addWidget(sub)
        brand.addLayout(brand_text)
        brand.addStretch()
        lay.addLayout(brand)

        lay.addSpacing(10)

        # === 全局搜索框（回车提交，由主窗口路由） ===
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText('搜索学员 / 课程...')
        self.le_search.setClearButtonEnabled(True)
        self.le_search.returnPressed.connect(
            lambda: self.searchSubmitted.emit(self.le_search.text().strip())
        )
        lay.addWidget(self.le_search)

        lay.addSpacing(8)

        # === 中部主菜单 ===
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for item in menu_items:
            text, idx = item[0], item[1]
            icon_type = item[2] if len(item) > 2 else None
            nav = NavItem(text, idx, icon_type)
            self._group.addButton(nav, idx)
            lay.addWidget(nav)
        self._group.idClicked.connect(self.navChanged.emit)

        lay.addStretch()

        # === 底部辅助菜单（与主菜单隔离） ===
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f'background-color: {ColorPalette.DIVIDER}; border: none;')
        lay.addWidget(sep)

        self._btn_help = NavItem('帮助', -1)
        self._btn_help.clicked.connect(self.helpRequested.emit)
        lay.addWidget(self._btn_help)

        self._btn_logout = NavItem('退出登录', -2)
        self._btn_logout.clicked.connect(self.logoutRequested.emit)
        lay.addWidget(self._btn_logout)

    def select(self, index: int):
        """程序化选中指定索引的菜单项。"""
        btn = self._group.button(index)
        if btn is not None:
            btn.setChecked(True)

    def set_badge(self, index: int, count: int):
        """更新指定页面菜单项的数字徽标（如续费预警人数）。"""
        btn = self._group.button(index)
        if btn is not None and isinstance(btn, NavItem):
            btn.set_badge(count)
