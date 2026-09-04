# -*- coding: utf-8 -*-
"""UI 基础组件层：色彩 / 字体 / 阴影 / 圆角配置 + 基础卡片 + 图标盒。

职责：
- ColorPalette / Shapes / FontHelper / Shadows：全局视觉令牌
- BaseCard：通用白底大圆角柔和阴影卡片
- IconBox + _draw_icon：极细线框图标盒
- _fade_color：颜色淡化工具

单一职责：本文件仅包含「视觉令牌 + 最底层不可再分的可视化原子组件」，
不包含任何业务卡片（StatCard / GradientHeroCard）或图表/导航组件。
"""
from PySide6.QtCore import Qt, QRect, QRectF, QPointF, QPoint
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPen, QBrush
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QLayout,
    QPushButton, QTableWidgetItem, QHeaderView, QFrame
)


#==== 视觉令牌 ====

class ColorPalette:
    """全局色彩配置（浅色珊瑚橙主题，与 Android 端视觉统一）。

    主色 #FF6B47 为活力珊瑚橙，用于选中态高亮与主操作按钮。
    背景采用暖白 #F5F7FA，卡片纯白 #FFFFFF，确保双端视觉一致性。
    """
    BG = '#F5F7FA'              # 主背景：暖白
    SIDEBAR_BG = '#F5F5F5'      # 侧边栏背景（略深于主背景）
    CARD = '#FFFFFF'            # 卡片背景：纯白
    TEXT = '#1A1A1A'            # 主文字：深灰（≥12:1）
    TEXT_SECONDARY = '#6B6B6B'  # 次要文字：中灰（≥4.6:1）
    TEXT_MUTED = '#9B9B9B'      # 弱化文字：浅灰
    PRIMARY = '#FF6B47'         # 主色：活力珊瑚橙
    PRIMARY_LIGHT = '#FFEDE8'   # 主色浅化（用于 hover/选中项低饱和背景）
    PRIMARY_HOVER = '#FF8866'   # 主色 hover 加深
    PRIMARY_PRESSED = '#E55A3A'  # 主色 pressed 更深
    ACCENT_CYAN = '#06B6D4'
    ACCENT_YELLOW = '#F59E0B'
    ACCENT_GREEN = '#10B981'
    ACCENT_RED = '#FF6B6B'
    DIVIDER = '#E5E5E5'         # 分割线：浅灰
    INPUT_BORDER = '#E5E5E5'    # 输入框边框：浅灰
    INPUT_FOCUS = '#FF6B47'     # 输入框聚焦边框：珊瑚橙
    HEADER_BG = '#F8F8F8'       # 表头背景：极浅灰
    SELECTION_BG = '#FFEDE8'    # 选中项背景（珊瑚橙低饱和）
    BORDER = '#E5E5E5'          # 通用边框


class Shapes:
    """圆角配置。"""
    CARD_RADIUS = 16
    BUTTON_RADIUS = 10
    INPUT_RADIUS = 10
    ICON_RADIUS = 10
    SMALL_RADIUS = 6


class FontHelper:
    """字体配置辅助类。"""
    _FALLBACK = ['Inter', 'Roboto', 'Microsoft YaHei UI', 'Segoe UI', '微软雅黑']

    @classmethod
    def _make(cls, size, weight=QFont.Normal, bold=False):
        f = QFont(cls._FALLBACK[0])
        f.setPointSize(size)
        if bold:
            f.setBold(True)
        else:
            f.setWeight(weight)
        return f

    @classmethod
    def hero(cls):
        return cls._make(28, QFont.DemiBold, True)

    @classmethod
    def title(cls):
        return cls._make(20, QFont.DemiBold, True)

    @classmethod
    def section(cls):
        return cls._make(15, QFont.DemiBold, True)

    @classmethod
    def body(cls):
        return cls._make(13, QFont.Normal)

    @classmethod
    def caption(cls):
        return cls._make(11, QFont.Normal)

    @classmethod
    def stat_number(cls):
        return cls._make(26, QFont.Bold, True)


class Shadows:
    """阴影绘制参数（供 BaseCard 等使用）。"""
    OFFSET_Y = 4
    BLUR_STEPS = 10
    MAX_ALPHA = 22


#==== 颜色工具 ====

def _fade_color(hex_color: str, alpha_ratio: float) -> str:
    """将十六进制颜色按 alpha 比例变淡，返回 #AARRGGBB 字符串供 QColor 解析。"""
    c = QColor(hex_color)
    r, g, b = c.red(), c.green(), c.blue()
    a = int(255 * alpha_ratio)
    return f'#{a:02x}{r:02x}{g:02x}{b:02x}'


#==== 基础卡片 ====

class BaseCard(QWidget):
    """通用卡片组件：白底、大圆角、柔和弥散阴影、无实线边框。

    业务卡片（StatCard / GradientHeroCard）应继承本类或持有本类实例，
    不应在本类之上叠加图表/导航等业务逻辑。
    """

    def __init__(self, title=None, layout=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(20, 20, 20, 20)
        self._main_layout.setSpacing(12)
        self._title_label = None
        if title:
            self._title_label = QLabel(title)
            self._title_label.setFont(FontHelper.section())
            self._title_label.setStyleSheet(f'color: {ColorPalette.PRIMARY}; background: transparent;')
            self._main_layout.addWidget(self._title_label)
        self._content = QWidget()
        self._content.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._main_layout.addWidget(self._content, 1)
        if layout is not None:
            self.set_content_layout(layout)

    def set_content_layout(self, layout: QLayout):
        """设置卡片内容布局。"""
        old = self._content.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            old.deleteLater()
        self._content.setLayout(layout)

    def content_widget(self):
        return self._content

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = Shapes.CARD_RADIUS
        margin = Shadows.BLUR_STEPS // 2 + 2
        rect = self.rect().adjusted(margin, margin, -margin, -margin - Shadows.OFFSET_Y)
        # 弥散阴影：多层半透明圆角矩形，由内而外变淡
        painter.setPen(Qt.NoPen)
        for i in range(Shadows.BLUR_STEPS, 0, -1):
            alpha = int(Shadows.MAX_ALPHA * (1 - i / (Shadows.BLUR_STEPS + 1)))
            brush = QBrush(QColor(0, 0, 0, alpha))
            painter.setBrush(brush)
            shadow_rect = rect.adjusted(-i, -i + Shadows.OFFSET_Y, i, i + Shadows.OFFSET_Y)
            painter.drawRoundedRect(shadow_rect, radius, radius)
        # 白色卡片背景
        painter.setBrush(QBrush(QColor(ColorPalette.CARD)))
        painter.drawRoundedRect(rect, radius, radius)
        painter.end()


#==== 图标盒 ====

class IconBox(QWidget):
    """圆角方盒图标：细线单色图标，可配合柔和底色。"""

    HOME = 0
    CHART_BAR = 1
    CHART_LINE = 2
    LIST = 3
    FILE = 4
    USER = 5
    SETTINGS = 6
    PLUS = 7
    TREND_UP = 8
    CALENDAR = 9
    DUMBBELL = 10
    ARCHIVE = 11

    def __init__(self, icon_type, size=40, bg_color=None, fg_color=None, parent=None):
        super().__init__(parent)
        self.icon_type = icon_type
        self._size = size
        self.setFixedSize(size, size)
        self.bg_color = bg_color or ColorPalette.PRIMARY_LIGHT
        self.fg_color = fg_color or ColorPalette.PRIMARY

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(self.fg_color))
        pen.setWidth(1)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        # 底色圆角方盒
        painter.setBrush(QBrush(QColor(self.bg_color)))
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), Shapes.ICON_RADIUS, Shapes.ICON_RADIUS)
        painter.setBrush(Qt.NoBrush)
        margin = int(self._size * 0.28)
        r = self.rect().adjusted(margin, margin, -margin, -margin)
        _draw_icon(painter, self.icon_type, r)
        painter.end()


def _draw_icon(painter: QPainter, icon_type: int, rect: QRect):
    """根据类型绘制极细线框图标。"""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if icon_type == IconBox.HOME:
        painter.drawPolygon([
            QPointF(x + w * 0.5, y + h * 0.2),
            QPointF(x + w * 0.2, y + h * 0.5),
            QPointF(x + w * 0.2, y + h * 0.85),
            QPointF(x + w * 0.8, y + h * 0.85),
            QPointF(x + w * 0.8, y + h * 0.5),
        ])
        painter.drawRect(int(x + w * 0.4), int(y + h * 0.55), int(w * 0.2), int(h * 0.3))
    elif icon_type == IconBox.CHART_BAR:
        bw = w / 5
        for i, hh in enumerate((0.75, 0.5, 0.9)):
            painter.drawRect(int(x + bw * (i * 1.5 + 0.5)), int(y + h * (1 - hh)), int(bw), int(h * hh))
    elif icon_type == IconBox.CHART_LINE:
        path = QPainterPath(QPointF(x + w * 0.15, y + h * 0.75))
        path.cubicTo(x + w * 0.35, y + h * 0.75, x + w * 0.45, y + h * 0.35, x + w * 0.6, y + h * 0.55)
        path.cubicTo(x + w * 0.75, y + h * 0.75, x + w * 0.85, y + h * 0.25, x + w * 0.9, y + h * 0.3)
        painter.drawPath(path)
    elif icon_type == IconBox.LIST:
        for i in range(3):
            yy = y + h * (0.25 + i * 0.25)
            painter.drawEllipse(int(x + w * 0.1), int(yy - w * 0.04), int(w * 0.08), int(w * 0.08))
            painter.drawLine(int(x + w * 0.25), int(yy), int(x + w * 0.9), int(yy))
    elif icon_type == IconBox.FILE:
        painter.drawRect(int(x + w * 0.2), int(y + h * 0.15), int(w * 0.6), int(h * 0.7))
        painter.drawLine(int(x + w * 0.35), int(y + h * 0.4), int(x + w * 0.65), int(y + h * 0.4))
        painter.drawLine(int(x + w * 0.35), int(y + h * 0.6), int(x + w * 0.55), int(y + h * 0.6))
    elif icon_type == IconBox.USER:
        painter.drawEllipse(int(x + w * 0.35), int(y + h * 0.22), int(w * 0.3), int(h * 0.3))
        path = QPainterPath()
        path.moveTo(x + w * 0.2, y + h * 0.85)
        path.cubicTo(x + w * 0.2, y + h * 0.65, x + w * 0.8, y + h * 0.65, x + w * 0.8, y + h * 0.85)
        painter.drawPath(path)
    elif icon_type == IconBox.SETTINGS:
        import math
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) * 0.18
        painter.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        for angle in (0, 45, 90, 135, 180, 225, 270, 315):
            rad = math.radians(angle)
            ox = cx + math.cos(rad) * r * 1.45
            oy = cy + math.sin(rad) * r * 1.45
            painter.drawEllipse(int(ox - 2.5), int(oy - 2.5), 5, 5)
    elif icon_type == IconBox.PLUS:
        painter.drawLine(int(x + w * 0.5), int(y + h * 0.2), int(x + w * 0.5), int(y + h * 0.8))
        painter.drawLine(int(x + w * 0.2), int(y + h * 0.5), int(x + w * 0.8), int(y + h * 0.5))
    elif icon_type == IconBox.TREND_UP:
        path = QPainterPath(QPointF(x + w * 0.15, y + h * 0.75))
        path.lineTo(x + w * 0.45, y + h * 0.45)
        path.lineTo(x + w * 0.65, y + h * 0.65)
        path.lineTo(x + w * 0.9, y + h * 0.2)
        painter.drawPath(path)
        painter.drawLine(int(x + w * 0.75), int(y + h * 0.2), int(x + w * 0.9), int(y + h * 0.2))
        painter.drawLine(int(x + w * 0.9), int(y + h * 0.2), int(x + w * 0.9), int(y + h * 0.4))
    elif icon_type == IconBox.CALENDAR:
        painter.drawRect(int(x + w * 0.15), int(y + h * 0.25), int(w * 0.7), int(h * 0.6))
        painter.drawLine(int(x + w * 0.25), int(y + h * 0.25), int(x + w * 0.25), int(y + h * 0.1))
        painter.drawLine(int(x + w * 0.75), int(y + h * 0.25), int(x + w * 0.75), int(y + h * 0.1))
        painter.drawLine(int(x + w * 0.15), int(y + h * 0.4), int(x + w * 0.85), int(y + h * 0.4))
    elif icon_type == IconBox.DUMBBELL:
        painter.drawLine(int(x + w * 0.2), int(y + h * 0.5), int(x + w * 0.8), int(y + h * 0.5))
        painter.drawRect(int(x + w * 0.15), int(y + h * 0.35), int(w * 0.12), int(h * 0.3))
        painter.drawRect(int(x + w * 0.73), int(y + h * 0.35), int(w * 0.12), int(h * 0.3))
    elif icon_type == IconBox.ARCHIVE:
        painter.drawRect(int(x + w * 0.2), int(y + h * 0.25), int(w * 0.6), int(h * 0.6))
        painter.drawLine(int(x + w * 0.4), int(y + h * 0.35), int(x + w * 0.6), int(y + h * 0.35))
        painter.drawLine(int(x + w * 0.35), int(y + h * 0.55), int(x + w * 0.65), int(y + h * 0.55))


class StatCell(QFrame):
    """极简量级单元：小标签 + 大数字（无边框，用于一行多列的概览条）。

    accent: 强调色（如 #F87171 红色），传入时数值非 0 才显色；为 0 时回退到中性 TEXT 色，
    避免「需续费 0」用红色吓到用户。
    """

    def __init__(self, label: str, accent: str = None, parent=None):
        super().__init__(parent)
        self._accent = accent
        self.setStyleSheet('background: transparent; border: none;')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)
        cap = QLabel(label)
        cap.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; font-size: 12px;'
            'background: transparent; border: none;'
        )
        lay.addWidget(cap)
        self._value = QLabel('—')
        self._value.setStyleSheet(
            f'color: {accent or ColorPalette.TEXT}; font-size: 24px;'
            'font-weight: 800; background: transparent; border: none;'
        )
        lay.addWidget(self._value)

    def set_value(self, value):
        """设置数值（int 或 str）。accent 模式下非 0 才高亮。"""
        self._value.setText(str(value))
        if self._accent:
            active = bool(value)
            self._value.setStyleSheet(
                f'color: {self._accent if active else ColorPalette.TEXT};'
                'font-size: 24px; font-weight: 800; background: transparent; border: none;'
            )


def compute_overview(students: list) -> dict:
    """从学员列表计算概览统计（纯函数，便于测试）。

    参数:
        students: profile_manager.list_students 返回的字典列表，含 warn_level 与 remaining
    返回:
        {total, red, yellow, remaining}
    """
    total = len(students)
    red = sum(1 for s in students if s.get('warn_level') == 'red')
    yellow = sum(1 for s in students if s.get('warn_level') == 'yellow')
    remaining = sum(int(s.get('remaining') or 0) for s in students)
    return {'total': total, 'red': red, 'yellow': yellow, 'remaining': remaining}


#==== 表格行操作按钮 ====

_ROW_ACTIONS_KEY = '_row_actions'


def install_row_actions(table, actions, header='操作'):
    """为 QTableWidget 追加最后一列「操作」，每行渲染一组小按钮。

    参数:
        actions: [(按钮文本, 回调)], 回调签名 cb(table, row)，row 为点击时的
                 视觉行号（排序后仍正确，勿在填表循环中捕获行号）
        header: 操作列列头文本

    说明: 表格每次重新填充数据后需调用 refresh_row_actions(table) 重建按钮。
    """
    table.setProperty(_ROW_ACTIONS_KEY, actions)
    table.setColumnCount(table.columnCount() + 1)
    table.setHorizontalHeaderItem(table.columnCount() - 1, QTableWidgetItem(header))
    table.horizontalHeader().setSectionResizeMode(
        table.columnCount() - 1, QHeaderView.ResizeToContents
    )
    refresh_row_actions(table)


def refresh_row_actions(table):
    """按当前行数重建「操作」列按钮（排序/增删行后调用）。"""
    actions = table.property(_ROW_ACTIONS_KEY) or []
    col = table.columnCount() - 1
    if col < 0:
        return
    for row in range(table.rowCount()):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)
        for label, cb in actions:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f'''
                QPushButton {{
                    background: #FFF7F5;
                    color: {ColorPalette.PRIMARY};
                    border: 1px solid #FFD5C8;
                    border-radius: 8px;
                    padding: 3px 10px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{ background: {ColorPalette.PRIMARY}; color: #FFFFFF; }}
            ''')
            btn.clicked.connect(lambda _=False, c=cb, b=btn: c(table, _visual_row(table, b)))
            lay.addWidget(btn)
        lay.addStretch()
        table.setCellWidget(row, col, box)


def _visual_row(table, btn) -> int:
    """按钮所在单元格的当前视觉行号（随排序实时变化）。"""
    pos = btn.mapTo(table.viewport(), QPoint(0, 0))
    return table.indexAt(pos).row()

