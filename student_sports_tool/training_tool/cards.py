# -*- coding: utf-8 -*-
"""训练任务编排模块卡片组件（灰白简约 · 蓝紫强调）。

复用 base_components 卡片绘制的平铺模式（v25 起彻底去阴影：卡片平铺、
1px 描边出轮廓，不引入 QGraphicsDropShadowEffect 以避免子控件渲染异常）。

组件：
- Card：白底圆角卡片，可选标题 + 内容布局
- Tag：灰底圆角只读标签
- TagInput：可编辑标签输入（时长 / 器材等）
- SectionTitle：区块小标题（加粗 + 可选图标前缀）
- TaskListItem：左列任务项（日期 + 标题，选中态左侧 3px 竖条，右侧编辑按钮）
- IconButton：极简图标按钮（Unicode 字形，无图标文件依赖）
"""
from PySide6.QtCore import Qt, Signal, QRect, QRectF
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSizePolicy, QLayout
)
from styles import Palette, Radius, Spacing, Type


# ==================== 通用卡片 ====================

class Card(QFrame):
    """白底圆角卡片：12px 圆角 + 1px 浅灰边框 + 轻微弥散阴影。

    用 paintEvent 绘制阴影（复用 base_components.BaseCard 已验证模式，
    alpha 量级对齐规格 0 2px 8px rgba(0,0,0,0.06)）。
    """

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._main = QVBoxLayout(self)
        self._main.setContentsMargins(
            Spacing.CARD_PAD, Spacing.CARD_PAD, Spacing.CARD_PAD, Spacing.CARD_PAD
        )
        self._main.setSpacing(Spacing.MD)
        self._title_label = None
        if title:
            self._title_label = QLabel(title)
            self._title_label.setObjectName('cardTitle')
            self._title_label.setFont(Type.card_title())
            self._main.addWidget(self._title_label)
        self._body = QWidget()
        self._main.addWidget(self._body, 1)

    def set_content_layout(self, layout: QLayout):
        old = self._body.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            old.deleteLater()
        self._body.setLayout(layout)

    def content_widget(self):
        return self._body

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # v25 去阴影：卡片平铺，轮廓交给 1px 描边（李哥反馈不要叠加阴影方框）
        rect = self.rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(Palette.CARD)))
        painter.drawRoundedRect(rect, Radius.CARD, Radius.CARD)
        painter.setPen(QPen(QColor(Palette.DIVIDER), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), Radius.CARD, Radius.CARD)
        painter.end()


# ==================== 标签 ====================

class Tag(QLabel):
    """灰底圆角只读标签（#F3F4F6 / #374151）。"""

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setObjectName('tag')
        self.setFont(Type.caption())
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)


class TagInput(QLineEdit):
    """可编辑标签输入：无边框灰底圆角，用于时长 / 器材等紧凑元信息。"""

    def __init__(self, text='', placeholder='', parent=None):
        super().__init__(text, parent)
        self.setObjectName('tagInput')
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setFont(Type.caption())
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # 宽度自适应内容
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)


# ==================== 区块标题 ====================

class SectionTitle(QLabel):
    """区块小标题：加粗 16px，可带前缀图标字形。"""

    def __init__(self, text='', icon='', parent=None):
        full = f'{icon}  {text}' if icon else text
        super().__init__(full, parent)
        self.setObjectName('cardTitle')
        self.setFont(Type.card_title())


# ==================== 任务列表项 ====================

class TaskListItem(QFrame):
    """左列任务项：日期 + 标题，选中态左侧 3px 强调竖条 + 浅蓝背景，右侧编辑按钮。

    信号：
        clicked(index)：整项被点击
        edit_clicked(index)：编辑图标被点击
    """
    clicked = Signal(int)
    edit_clicked = Signal(int)

    def __init__(self, index, date_str='', title='', selected=False, parent=None):
        super().__init__(parent)
        self._index = index
        self.setObjectName('taskItem')
        self.setCursor(Qt.PointingHandCursor)
        self._selected = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 8, 10)
        lay.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        self._lbl_date = QLabel(date_str or '—')
        self._lbl_date.setFont(Type.caption())
        self._lbl_date.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        self._lbl_title = QLabel(title)
        self._lbl_title.setFont(Type.body())
        self._lbl_title.setStyleSheet(f'color: {Palette.TEXT}; background: transparent;')
        col.addWidget(self._lbl_date)
        col.addWidget(self._lbl_title)
        lay.addLayout(col, 1)
        self._btn_edit = QPushButton('✎')
        self._btn_edit.setObjectName('ghost')
        self._btn_edit.setCursor(Qt.PointingHandCursor)
        self._btn_edit.setFixedSize(30, 30)
        self._btn_edit.setToolTip('编辑')
        self._btn_edit.clicked.connect(lambda: self.edit_clicked.emit(self._index))
        lay.addWidget(self._btn_edit)
        self.set_selected(selected)

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.setStyleSheet(
                f'QFrame#taskItem {{ background: {Palette.ACCENT_LIGHT}; '
                f'border-left: 3px solid {Palette.ACCENT}; border-radius: {Radius.SMALL}px; }}'
            )
            self._lbl_title.setStyleSheet(f'color: {Palette.ACCENT}; background: transparent;')
        else:
            self.setStyleSheet(
                f'QFrame#taskItem {{ background: transparent; border: none; '
                f'border-radius: {Radius.SMALL}px; }}'
            )
            self._lbl_title.setStyleSheet(f'color: {Palette.TEXT}; background: transparent;')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(event)


# ==================== 图标按钮 ====================

class IconButton(QPushButton):
    """极简图标按钮：Unicode 字形 + 可选文字，无边框透明底，hover 强调浅底。

    避免图标文件依赖，字形在 Windows Segoe UI Emoji / YaHei UI 均可渲染。
    """
    def __init__(self, icon='', text='', tooltip='', parent=None):
        label = f'{icon} {text}' if text else icon
        super().__init__(label, parent)
        self.setObjectName('ghost')
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
