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
    BaseCard, IconBox, FontHelper, ColorPalette, Shapes, Shadows, _fade_color,
    paint_card_base
)


class StatCard(BaseCard):
    """数据概览卡（参考 SaaS Dashboard 层级标准，李哥 2026-09-07 定稿）：

        小灰标签(12px)          [图标位]
        大粗数值(28px/800) +12%↗
        [内容区/留白]

    delta: 趋势文本（如 '↑12%'/'↓5%'），↑ 绿色 / ↓ 红色（KPI 口径，非股票红涨绿跌）。
    """

    _DELTA_UP = ('#1F9D55', '#E8F7EF')    # (字色, 底色)
    _DELTA_DOWN = ('#E53E3E', '#FDEEEE')

    def __init__(self, icon_type, label, value='—', color=None, parent=None, delta=None):
        """
        参数:
            icon_type: IconBox 内置图标常量（显示于右上角小图标位）
            label: 小灰标签（卡头）
            value: 主数值文本
            color: 图标主色（默认 ColorPalette.PRIMARY）
            delta: 趋势小标签文本（如 ↑5.0）
        """
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(96)
        color = color or ColorPalette.PRIMARY
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        # 第一行：小灰标签 + 右上角图标位
        top = QHBoxLayout()
        top.setSpacing(8)
        self.lbl_label = QLabel(label)
        self.lbl_label.setFont(FontHelper.caption())
        self.lbl_label.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; background: transparent;')
        top.addWidget(self.lbl_label, 1)
        self.icon = IconBox(icon_type, size=30, bg_color=_fade_color(color, 0.10),
                            fg_color=color)
        top.addWidget(self.icon, 0, Qt.AlignTop)
        v.addLayout(top)

        # 第二行：大数值 + 趋势胶囊
        row = QHBoxLayout()
        row.setSpacing(8)
        self.lbl_value = QLabel(value)
        self.lbl_value.setFont(FontHelper.stat_number())
        self.lbl_value.setStyleSheet(f'color: {ColorPalette.TEXT}; background: transparent;')
        row.addWidget(self.lbl_value, 0, Qt.AlignVCenter)
        self.lbl_delta = None
        if delta is not None:
            self.lbl_delta = QLabel(delta)
            self.lbl_delta.setFont(FontHelper.caption())
            up = str(delta).startswith('↑')
            fg, bg = self._DELTA_UP if up else self._DELTA_DOWN
            self.lbl_delta.setStyleSheet(
                f'color: {fg}; background: {bg}; border-radius: 8px;'
                'padding: 2px 7px; font-size: 11px; font-weight: 700;')
            row.addWidget(self.lbl_delta, 0, Qt.AlignVCenter)
        row.addStretch(1)
        v.addLayout(row)
        self._content.setLayout(v)

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
        radius = Shapes.CARD_RADIUS
        rect = self.rect()  # v25 去阴影：无留白，卡片铺满 widget
        # 渐变背景：珊瑚橙主色 → 深珊瑚橙（M3-S2 与 Android 端对齐）
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor('#FF6B47'))
        grad.setColorAt(1, QColor('#E04826'))
        paint_card_base(painter, rect, radius, 0, fill=QBrush(grad))
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
