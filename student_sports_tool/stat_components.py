# -*- coding: utf-8 -*-
"""UI 业务卡片层：数据概览卡片与渐变 Hero 卡片。

职责：
- StatCard：图标 + 大数字 + 描述 + 趋势小标签
- GradientHeroCard：珊瑚橙渐变重点卡片（总资产 / 核心数据）

单一职责：仅承载「单一数据点的可视化呈现」，
不包含图表、导航、列表等复杂组合组件。
依赖 base_components 中的视觉令牌与 BaseCard 基类。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy
)

from base_components import (
    BaseCard, IconBox, FontHelper, ColorPalette, Shapes, Shadows, _fade_color
)


class StatCard(BaseCard):
    """数据概览小卡片：图标 + 大数字 + 描述。"""

    def __init__(self, icon_type, label, value='—', color=None, parent=None, delta=None):
        """
        参数:
            icon_type: IconBox 内置图标常量
            label: 描述文字
            value: 主数值文本
            color: 图标主色（默认 ColorPalette.PRIMARY）
            delta: 趋势小标签文本（如 ↑5.0），以 ↑ 开头显示为绿色
        """
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(100)
        color = color or ColorPalette.PRIMARY
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(14)
        self.icon = IconBox(icon_type, size=44, bg_color=_fade_color(color, 0.10), fg_color=color)
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.lbl_value = QLabel(value)
        self.lbl_value.setFont(FontHelper.stat_number())
        self.lbl_value.setStyleSheet(f'color: {ColorPalette.TEXT}; background: transparent;')
        self.lbl_label = QLabel(label)
        self.lbl_label.setFont(FontHelper.caption())
        self.lbl_label.setStyleSheet(f'color: {ColorPalette.TEXT_SECONDARY}; background: transparent;')
        v.addWidget(self.lbl_value)
        if delta is not None:
            self.lbl_delta = QLabel(delta)
            self.lbl_delta.setFont(FontHelper.caption())
            delta_color = ColorPalette.ACCENT_GREEN if str(delta).startswith('↑') else ColorPalette.TEXT_MUTED
            self.lbl_delta.setStyleSheet(f'color: {delta_color}; background: transparent;')
            v.addWidget(self.lbl_delta)
        v.addWidget(self.lbl_label)
        h.addWidget(self.icon)
        h.addLayout(v, 1)
        self._content.setLayout(h)

    def set_value(self, value):
        """更新主数值文本。"""
        self.lbl_value.setText(str(value))


class GradientHeroCard(BaseCard):
    """带珊瑚橙渐变的重点卡片（总资产 / 核心数据）。"""

    def __init__(self, title, value, subtitle=None, parent=None):
        """
        参数:
            title: 顶部小标题（白色淡显）
            value: 中央大数值
            subtitle: 底部副标题（可选，白色半透明）
        """
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(140)
        self._title = title
        self._value = value
        self._subtitle = subtitle

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = Shapes.CARD_RADIUS
        margin = Shadows.BLUR_STEPS // 2 + 2
        rect = self.rect().adjusted(margin, margin, -margin, -margin - Shadows.OFFSET_Y)
        # 弥散阴影
        painter.setPen(Qt.NoPen)
        for i in range(Shadows.BLUR_STEPS, 0, -1):
            alpha = int(Shadows.MAX_ALPHA * (1 - i / (Shadows.BLUR_STEPS + 1)))
            painter.setBrush(QBrush(QColor(0, 0, 0, alpha)))
            shadow_rect = rect.adjusted(-i, -i + Shadows.OFFSET_Y, i, i + Shadows.OFFSET_Y)
            painter.drawRoundedRect(shadow_rect, radius, radius)
        # 渐变背景：珊瑚橙主色 → 深珊瑚橙（M3-S2 与 Android 端对齐）
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor('#FF6B47'))
        grad.setColorAt(1, QColor('#E04826'))
        painter.setBrush(grad)
        painter.drawRoundedRect(rect, radius, radius)
        # 文字
        painter.setPen(QColor('#FFFFFF'))
        painter.setFont(FontHelper.caption())
        painter.drawText(rect.adjusted(20, 20, -20, 0), Qt.AlignTop | Qt.AlignLeft, self._title)
        painter.setFont(FontHelper.hero())
        painter.drawText(rect.adjusted(20, 44, -20, -20), Qt.AlignLeft | Qt.AlignVCenter, str(self._value))
        if self._subtitle:
            painter.setPen(QColor(255, 255, 255, 200))
            painter.setFont(FontHelper.caption())
            painter.drawText(rect.adjusted(20, 0, -20, -20), Qt.AlignBottom | Qt.AlignLeft, self._subtitle)
        painter.end()
