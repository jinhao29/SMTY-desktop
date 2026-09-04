# -*- coding: utf-8 -*-
"""UI 图表组件层：轻量自绘柱状图、折线图、历史列表。

职责：
- BarChartWidget：垂直柱状图（带网格、圆角柱、顶部数值）
- LineChartWidget：平滑折线图（支持多条序列 + 渐变填充）
- HistoryListWidget：极简历史记录列表（Divider 分割）

单一职责：仅承担「数据序列的可视化绘制」，
不依赖业务模型，不包含卡片容器与导航逻辑。
"""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QFrame
)

from base_components import FontHelper, ColorPalette


class BarChartWidget(QWidget):
    """轻量垂直柱状图组件（金融风：带网格、圆角柱、顶部数值）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self.setMinimumHeight(180)

    def set_data(self, items):
        """设置数据。

        参数:
            items: [(label, value, color), ...]
        """
        self._data = items or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self._data:
            painter.setPen(QColor(ColorPalette.TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter, '暂无数据')
            return
        values = [v for _, v, _ in self._data]
        max_v = max(values) if values else 1
        max_v = max(max_v, 1)
        pad = 28
        bottom = self.height() - 32
        top = pad
        left = pad
        right = self.width() - pad
        chart_h = bottom - top
        n = len(self._data)
        gap = 14
        bar_w = max(10, (right - left - gap * (n - 1)) // n)
        font = FontHelper.caption()
        painter.setFont(font)
        # 网格虚线
        pen = QPen(QColor(0, 0, 0, 25))
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        for j in range(4):
            gy = bottom - chart_h * j / 3
            painter.drawLine(int(left), int(gy), int(right), int(gy))
        for i, (label, value, color) in enumerate(self._data):
            x = left + i * (bar_w + gap)
            h = (value / max_v) * chart_h * 0.82
            y = bottom - h
            rect = QRectF(x, y, bar_w, h)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(color)))
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(QColor(ColorPalette.TEXT))
            painter.drawText(QRectF(x, y - 20, bar_w, 16), Qt.AlignCenter, str(value))
            painter.setPen(QColor(ColorPalette.TEXT_SECONDARY))
            painter.drawText(QRectF(x, bottom + 6, bar_w, 20), Qt.AlignCenter | Qt.TextWordWrap, label)
        painter.end()


class LineChartWidget(QWidget):
    """轻量平滑折线图组件（支持单条或多条序列）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series = []  # [(name, [(x_label, y_value), ...], color), ...]
        self.setMinimumHeight(180)

    def set_data(self, series):
        """设置数据。

        参数:
            series: [(name, points, color), ...]，points: [(x_label, y_value), ...]
        """
        self._series = series or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self._series or all(len(s[1]) < 2 for s in self._series):
            painter.setPen(QColor(ColorPalette.TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter, '暂无趋势数据')
            return
        all_values = [v for _, pts, _ in self._series for _, v in pts]
        max_v = max(all_values) if all_values else 1
        min_v = min(all_values) if all_values else 0
        span = max(max_v - min_v, 1)
        pad = 28
        left = pad
        right = self.width() - pad
        top = pad
        bottom = self.height() - 34
        # 网格虚线
        pen = QPen(QColor(0, 0, 0, 25))
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        for j in range(4):
            gy = bottom - (bottom - top) * j / 3
            painter.drawLine(int(left), int(gy), int(right), int(gy))

        def _map(count, i, v):
            x = left + (right - left) * (i / max(count - 1, 1))
            y = bottom - (bottom - top) * ((v - min_v) / span)
            return QPointF(x, y)

        for name, points, color in self._series:
            if len(points) < 2:
                continue
            c = QColor(color)
            pts = [_map(len(points), i, v) for i, (_, v) in enumerate(points)]
            # 填充区域
            path = QPainterPath()
            path.moveTo(pts[0])
            for i in range(1, len(pts)):
                c1 = QPointF((pts[i - 1].x() + pts[i].x()) / 2, pts[i - 1].y())
                c2 = QPointF((pts[i - 1].x() + pts[i].x()) / 2, pts[i].y())
                path.cubicTo(c1, c2, pts[i])
            close = QPainterPath(path)
            close.lineTo(pts[-1].x(), bottom)
            close.lineTo(pts[0].x(), bottom)
            close.closeSubpath()
            grad = QLinearGradient(0, top, 0, bottom)
            grad.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 50))
            grad.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(grad)
            painter.drawPath(close)
            # 线条
            pen = QPen(c)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            # 数据点
            painter.setBrush(QBrush(QColor(ColorPalette.CARD)))
            painter.setPen(pen)
            for p in pts:
                painter.drawEllipse(p, 3, 3)
        # X 轴标签（只显示首尾）
        painter.setPen(QColor(ColorPalette.TEXT_SECONDARY))
        painter.setFont(FontHelper.caption())
        first_pts = next((s[1] for s in self._series if len(s[1]) >= 2), None)
        if first_pts:
            painter.drawText(QRectF(left - 20, bottom + 6, 60, 18), Qt.AlignLeft, str(first_pts[0][0]))
            painter.drawText(QRectF(right - 40, bottom + 6, 60, 18), Qt.AlignRight, str(first_pts[-1][0]))
        painter.end()


class HistoryListWidget(QWidget):
    """极简历史记录列表：轻 Divider 分割，无粗边框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._rows = []
        self._container = QWidget()
        self._container_lay = QVBoxLayout(self._container)
        self._container_lay.setContentsMargins(0, 0, 0, 0)
        self._container_lay.setSpacing(0)
        lay.addWidget(self._container)
        lay.addStretch()

    def set_items(self, items):
        """设置列表项。

        参数:
            items: [(title, subtitle, value_text, value_color), ...]
        """
        while self._container_lay.count():
            item = self._container_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._rows.clear()
        for i, (title, subtitle, value_text, value_color) in enumerate(items):
            row = self._create_row(title, subtitle, value_text, value_color, is_last=(i == len(items) - 1))
            self._container_lay.addWidget(row)
            self._rows.append(row)

    def _create_row(self, title, subtitle, value_text, value_color, is_last):
        row = QWidget()
        v = QVBoxLayout(row)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        h = QHBoxLayout()
        h.setContentsMargins(10, 12, 10, 12)
        h.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(4)
        lbl_title = QLabel(title)
        lbl_title.setFont(FontHelper.body())
        lbl_title.setStyleSheet(f'color: {ColorPalette.TEXT};')
        left.addWidget(lbl_title)
        if subtitle:
            lbl_sub = QLabel(subtitle)
            lbl_sub.setFont(FontHelper.caption())
            lbl_sub.setStyleSheet(f'color: {ColorPalette.TEXT_SECONDARY};')
            left.addWidget(lbl_sub)
        h.addLayout(left, 1)
        lbl_value = QLabel(value_text)
        lbl_value.setFont(FontHelper.body())
        lbl_value.setStyleSheet(f'color: {value_color or ColorPalette.TEXT}; font-weight: 600;')
        h.addWidget(lbl_value)
        v.addLayout(h)
        if not is_last:
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet('background: rgba(0, 0, 0, 0.06);')
            v.addWidget(line)
        return row
