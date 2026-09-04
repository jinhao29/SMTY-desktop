# -*- coding: utf-8 -*-
"""UI 导航组件层：图标按钮与左侧窄垂直导航栏。

职责：
- IconButton：48x48 图标按钮（用于左侧窄导航栏）
- NavBar：左侧窄垂直导航栏（仅图标 + 底部圆角加号按钮）

单一职责：仅承担「应用级导航交互」，
不包含业务卡片、图表、数据列表等组件。
依赖 base_components 中的 IconBox 与视觉令牌。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QSizePolicy
)

from base_components import (
    IconBox, ColorPalette, Shapes
)


class IconButton(QPushButton):
    """图标按钮（用于左侧窄导航栏）。"""

    def __init__(self, icon_type, tooltip='', color=None, parent=None):
        """
        参数:
            icon_type: IconBox 内置图标常量
            tooltip: 悬停提示文本
            color: 图标前景色（默认 ColorPalette.PRIMARY）
        """
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f'''
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {Shapes.SMALL_RADIUS}px;
            }}
            QPushButton:hover {{ background: {ColorPalette.PRIMARY_LIGHT}; }}
            QPushButton:pressed {{ background: #FFE2D8; }}
        ''')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.icon = IconBox(icon_type, size=36, fg_color=color)
        lay.addWidget(self.icon, alignment=Qt.AlignCenter)


class NavBar(QWidget):
    """左侧窄垂直导航栏：仅图标，底部圆角加号按钮。"""

    def __init__(self, parent=None, items=None, plus_callback=None):
        """
        参数:
            items: [(icon_type, tooltip), ...]
            plus_callback: 底部 + 按钮的点击回调
        """
        super().__init__(parent)
        self.setFixedWidth(72)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 20, 10, 20)
        lay.setSpacing(12)
        top = QVBoxLayout()
        top.setSpacing(12)
        for icon, tip in (items or []):
            top.addWidget(IconButton(icon, tip), alignment=Qt.AlignHCenter)
        lay.addLayout(top)
        lay.addStretch()
        self.btn_plus = QPushButton('+')
        self.btn_plus.setFixedSize(44, 44)
        self.btn_plus.setToolTip('新增')
        self.btn_plus.setCursor(Qt.PointingHandCursor)
        self.btn_plus.setStyleSheet(f'''
            QPushButton {{
                background: {ColorPalette.PRIMARY};
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 22px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {ColorPalette.PRIMARY_HOVER}; }}
        ''')
        if plus_callback:
            self.btn_plus.clicked.connect(plus_callback)
        lay.addWidget(self.btn_plus, alignment=Qt.AlignHCenter)
