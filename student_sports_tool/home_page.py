# -*- coding: utf-8 -*-
"""UI 层：首页（应用打开时的默认页面，Dashboard 概览）。

布局（参考浅色 SaaS Dashboard 语言：白卡描边 + 小灰标签 + 大数字 + 胶囊徽章）：
- 头部：欢迎语 + 日期 + 「+ 新增学员」主操作
- 统计条：学员总数 / 需续费（≤3）/ 课时关注（≤6）/ 剩余课时合计
- 快捷入口行：5 个页面直达迷你卡（索引与 PAGE_* 常量一致）
- 主体两列：
    左列：近 6 个月上课统计柱状图（课时明细按月聚合）
          续费预警列表（红/黄学员 + 课时进度条，点击跳学员档案）
    右列：今日日程（当日课时明细，空态友好提示）
          最近上课（按日期倒序前 5 条）

单一职责：仅承担「首页展示与快捷跳转」，
- 通过 quickNav(index) / addStudentRequested() 信号通知主窗口
- 数据只读（profile_manager / lesson_manager），不在首页做任何写操作
"""
import logging
from datetime import date, datetime

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QSizePolicy, QScrollArea
)

from base_components import ColorPalette, Shapes, IconBox, StatCell, compute_overview


# Re-export 保持向后兼容（test_tool.py 仍从此处导入）
__all__ = ['compute_overview', 'StatCell', 'HomePage']


#==== 纯函数（便于测试）====

def _parse_date(v):
    """课时明细日期解析：兼容 datetime / date / 字符串（2026-09-04、2026/09/04）。"""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()[:10].replace('/', '-')
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    return None


def compute_monthly_stats(records, months=6, today=None):
    """近 N 个月上课节数统计（含本月，纯函数）。

    参数:
        records: lesson_manager.get_detail 返回的明细列表（含 date/count）
        months: 统计月数
        today: 基准日期（默认今天）
    返回:
        [{'label': '4月', 'count': 12, 'year': 2026, 'month': 4}, ...] 按时间正序
    """
    today = today or date.today()
    keys = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()
    counts = {k: 0 for k in keys}
    for rec in records or []:
        d = _parse_date(rec.get('date'))
        if d and (d.year, d.month) in counts:
            try:
                counts[(d.year, d.month)] += int(rec.get('count') or 0)
            except (TypeError, ValueError):
                pass
    return [{'label': f'{mm}月', 'count': counts[(y, mm)], 'year': y, 'month': mm}
            for y, mm in keys]


def filter_today(records, today=None):
    """筛出指定日期（默认今天）的课时明细记录。"""
    today = today or date.today()
    out = []
    for rec in records or []:
        if _parse_date(rec.get('date')) == today:
            out.append(rec)
    return out


def recent_lessons(records, limit=5):
    """按上课日期倒序取前 limit 条明细记录（无日期的记录跳过）。"""
    items = []
    for rec in records or []:
        d = _parse_date(rec.get('date'))
        if d:
            items.append((d, rec))
    items.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in items[:limit]]


#==== 视觉辅助 ====

_AVATAR_COLORS = [
    ('#FFE4D6', '#C2410C'), ('#E0F2FE', '#0369A1'), ('#DCFCE7', '#15803D'),
    ('#FCE7F3', '#BE185D'), ('#EDE9FE', '#6D28D9'), ('#FEF9C3', '#A16207'),
]


def _avatar_colors(name: str):
    """按姓名散列取一组（浅底, 深字）配色，同一学员颜色稳定。"""
    h = 0
    for ch in name or '?':
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _AVATAR_COLORS[h % len(_AVATAR_COLORS)]


def _emit_nav(widget: QWidget, page: int):
    """沿父链找到 HomePage 并发射 quickNav(page)。"""
    parent = widget.parent()
    while parent is not None:
        if isinstance(parent, HomePage):
            parent.quickNav.emit(page)
            return
        parent = parent.parent()


def _clear_layout(lay):
    """清空布局内所有 widget（用于列表刷新重建）。

    hide() 必须立即调用：deleteLater 在同嵌套级别的 processEvents 中不会被处理，
    旧 widget 会冻结在旧几何位置继续渲染，与新行叠画。
    """
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.deleteLater()


class _Pill(QLabel):
    """浅底色胶囊徽章（如「剩 2 节」「+2 节」）。"""

    def __init__(self, text: str, bg: str, fg: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f'''
            background: {bg}; color: {fg};
            border-radius: 9px; padding: 2px 9px;
            font-size: 11px; font-weight: 600;
        ''')


class _Avatar(QLabel):
    """圆形首字头像（浅底深字，按姓名散列配色）。"""

    def __init__(self, name: str, size: int = 26, parent=None):
        super().__init__(parent)
        bg, fg = _avatar_colors(name)
        self.setText((name or '?')[0])
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(size, size)
        self.setStyleSheet(f'''
            background: {bg}; color: {fg};
            border-radius: {size // 2}px;
            font-size: {max(10, size // 2 - 3)}px; font-weight: 700;
        ''')


class _SlimProgress(QWidget):
    """细圆角进度条（已上/总课时）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ratio = 0.0
        self._color = ColorPalette.PRIMARY
        self.setFixedSize(90, 6)

    def set_ratio(self, ratio: float, color: str):
        self._ratio = max(0.0, min(1.0, ratio))
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor('#EFEFEF')))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()),
                                self.height() / 2, self.height() / 2)
        if self._ratio > 0:
            w = max(self.height(), self.width() * self._ratio)
            painter.setBrush(QBrush(QColor(self._color)))
            painter.drawRoundedRect(QRectF(0, 0, w, self.height()),
                                    self.height() / 2, self.height() / 2)
        painter.end()


class _BarChart(QWidget):
    """近 N 月上课柱状图（纯 QPainter 绘制，本月高亮主色）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []          # [{'label','count','year','month'}]
        self._current = (0, 0)   # (year, month) 高亮
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, data, today=None):
        today = today or date.today()
        self._data = data or []
        self._current = (today.year, today.month)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 10, 10, 20, 22
        chart_w, chart_h = w - pad_l - pad_r, h - pad_t - pad_b
        base_y = pad_t + chart_h

        # 基线
        painter.setPen(QPen(QColor(ColorPalette.DIVIDER), 1))
        painter.drawLine(pad_l, base_y, w - pad_r, base_y)

        n = len(self._data)
        if n == 0:
            painter.end()
            return
        slot = chart_w / n
        bar_w = min(30.0, slot * 0.42)
        max_v = max((d['count'] for d in self._data), default=0) or 1

        for i, d in enumerate(self._data):
            cx = pad_l + slot * i + slot / 2
            count = d['count']
            is_current = (d['year'], d['month']) == self._current
            # 柱体
            bar_h = chart_h * (count / max_v)
            if count > 0:
                rect = QRectF(cx - bar_w / 2, base_y - bar_h, bar_w, bar_h)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(
                    ColorPalette.PRIMARY if is_current else '#FFD6C9')))
                painter.drawRoundedRect(rect, 5, 5)
            else:
                # 零值：底部小圆点占位
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor('#EADDD7')))
                painter.drawEllipse(QRectF(cx - 2.5, base_y - 5, 5, 5))
            # 数值
            painter.setPen(QPen(QColor(
                ColorPalette.TEXT if is_current else ColorPalette.TEXT_SECONDARY)))
            font = painter.font()
            font.setPointSize(8)
            font.setBold(is_current)
            painter.setFont(font)
            painter.drawText(QRectF(cx - slot / 2, base_y - bar_h - 18,
                                    slot, 14), Qt.AlignCenter, str(count))
            # 月份标签
            painter.setPen(QPen(QColor(
                ColorPalette.TEXT if is_current else ColorPalette.TEXT_MUTED)))
            font.setBold(is_current)
            painter.setFont(font)
            painter.drawText(QRectF(cx - slot / 2, base_y + 6, slot, 14),
                             Qt.AlignCenter, d['label'])
        painter.end()


#==== 卡片容器 ====

class _SectionCard(QFrame):
    """白底描边圆角卡片：标题行（标题 + 可选「查看全部 ›」链接）+ 内容布局。

    scroll=True 时内容包在无边框内滚动区里——窗口过矮时列表滚动而非互相叠压。
    """

    def __init__(self, title: str, link_text: str = '', link_page: int = None,
                 scroll: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName('SectionCard')
        self.setStyleSheet(f'''
            QFrame#SectionCard {{
                background: {ColorPalette.CARD};
                border: 1px solid {ColorPalette.BORDER};
                border-radius: {Shapes.CARD_RADIUS}px;
            }}
        ''')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        t = QLabel(title)
        t.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 14px; font-weight: 700;'
            'background: transparent; border: none;'
        )
        head.addWidget(t)
        head.addStretch()
        if link_text and link_page is not None:
            btn = QPushButton(link_text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f'''
                QPushButton {{
                    background: transparent; border: none;
                    color: {ColorPalette.TEXT_MUTED};
                    font-size: 12px; padding: 0px;
                }}
                QPushButton:hover {{ color: {ColorPalette.PRIMARY}; }}
            ''')
            btn.clicked.connect(lambda _=False, w=btn, p=link_page: _emit_nav(w, p))
            head.addWidget(btn)
        lay.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(4)
        if scroll:
            content = QWidget()
            content.setObjectName('ScrollBody')
            content.setLayout(self.body)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(content)
            area.setFrameShape(QFrame.NoFrame)
            area.setStyleSheet('''
                QScrollArea { background: transparent; border: none; }
                QWidget#ScrollBody { background: transparent; }
                QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }
                QScrollBar::handle:vertical {
                    background: #DADADA; border-radius: 2px; min-height: 24px;
                }
                QScrollBar::handle:vertical:hover { background: #C4C4C4; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            ''')
            lay.addWidget(area)
        else:
            lay.addLayout(self.body)


#==== 列表行 ====

class _HoverRow(QFrame):
    """可点击列表行基类：悬浮浅橙背景，点击跳转目标页。"""

    def __init__(self, target_page: int = None, parent=None):
        super().__init__(parent)
        self._target = target_page
        self.setObjectName('HoverRow')
        self.setMinimumHeight(38)  # 防止布局压缩导致行内容叠画
        self.setCursor(Qt.PointingHandCursor if target_page is not None
                       else Qt.ArrowCursor)
        self._apply_style(False)

    def _apply_style(self, hover: bool):
        if self._target is None:
            bg = 'transparent'
        else:
            bg = '#FFF7F4' if hover else 'transparent'
        self.setStyleSheet(f'''
            QFrame#HoverRow {{
                background: {bg};
                border: none; border-radius: 10px;
            }}
        ''')

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self._target is not None and event.button() == Qt.LeftButton:
            _emit_nav(self, self._target)
            return
        super().mousePressEvent(event)


class _AlertRow(_HoverRow):
    """续费预警行：头像 + 姓名 + 课时进度条 + 剩余胶囊，点击跳学员档案。"""

    def __init__(self, name: str, remaining, total, level: str, parent=None):
        super().__init__(target_page=1, parent=parent)  # PAGE_PROFILE
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)
        lay.addWidget(_Avatar(name, 28))
        nm = QLabel(name)
        nm.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 13px; font-weight: 600;'
            'background: transparent;'
        )
        lay.addWidget(nm)
        lay.addStretch()
        try:
            total_i = int(total or 0)
            remain_i = int(remaining or 0)
        except (TypeError, ValueError):
            total_i, remain_i = 0, 0
        attended = max(0, total_i - remain_i)
        ratio = (attended / total_i) if total_i > 0 else 0.0
        prog = _SlimProgress()
        prog.set_ratio(ratio, '#F87171' if level == 'red' else '#F59E0B')
        lay.addWidget(prog)
        if level == 'red':
            pill = _Pill(f'剩 {remain_i} 节', '#FEE2E2', '#DC2626')
        else:
            pill = _Pill(f'剩 {remain_i} 节', '#FEF3C7', '#B45309')
        lay.addWidget(pill)


class _LessonRow(_HoverRow):
    """上课记录行：头像 + 姓名 + 描述/日期 + 「+N 节」胶囊，点击跳体测课时页。"""

    def __init__(self, name: str, tail_text: str, count, show_tail_right: bool = True,
                 parent=None):
        super().__init__(target_page=3, parent=parent)  # PAGE_ARCHIVE
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)
        lay.addWidget(_Avatar(name, 28))
        nm = QLabel(name)
        nm.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 13px; font-weight: 600;'
            'background: transparent;'
        )
        lay.addWidget(nm)
        try:
            cnt = int(count or 0)
        except (TypeError, ValueError):
            cnt = 0
        if show_tail_right:
            lay.addStretch()
            tail = QLabel(tail_text)
            tail.setStyleSheet(
                f'color: {ColorPalette.TEXT_MUTED}; font-size: 12px;'
                'background: transparent;'
            )
            lay.addWidget(tail)
        else:
            desc = QLabel(tail_text)
            desc.setStyleSheet(
                f'color: {ColorPalette.TEXT_MUTED}; font-size: 12px;'
                'background: transparent;'
            )
            # 截断过长训练内容
            desc.setMaximumWidth(180)
            lay.addWidget(desc, 1)
            lay.addStretch()
        lay.addWidget(_Pill(f'+{cnt} 节', ColorPalette.PRIMARY_LIGHT,
                            ColorPalette.PRIMARY))


class _EmptyState(QWidget):
    """空态占位：图标 + 灰字提示。"""

    def __init__(self, text: str, icon_type: int = IconBox.CALENDAR, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(8)
        lay.addStretch()
        wrap = QHBoxLayout()
        wrap.addStretch()
        wrap.addWidget(IconBox(icon_type, size=44))
        wrap.addStretch()
        lay.addLayout(wrap)
        tip = QLabel(text)
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; font-size: 12px;'
            'background: transparent;'
        )
        lay.addWidget(tip)
        lay.addStretch()


#==== 快捷入口迷你卡 ====

class _QuickCard(QFrame):
    """快捷入口迷你卡：图标 + 名称，横向紧凑，悬浮橙描边。"""

    def __init__(self, title: str, icon_type: int, target_index: int, parent=None):
        super().__init__(parent)
        self._target = target_index
        self.setObjectName('QuickCard')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._apply_style(False)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)
        lay.addWidget(IconBox(icon_type, size=32))
        t = QLabel(title)
        t.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 13px; font-weight: 600;'
            'background: transparent;'
        )
        lay.addWidget(t, 1)

    def _apply_style(self, hover: bool):
        self.setStyleSheet(f'''
            QFrame#QuickCard {{
                background-color: {ColorPalette.PRIMARY_LIGHT if hover else ColorPalette.CARD};
                border: 1px solid {ColorPalette.PRIMARY if hover else ColorPalette.BORDER};
                border-radius: {Shapes.BUTTON_RADIUS + 2}px;
            }}
        ''')

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            _emit_nav(self, self._target)
            return
        super().mousePressEvent(event)


#==== 首页主体 ====

_WEEKDAY_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


class HomePage(QWidget):
    """首页 Dashboard：欢迎区 + 统计条 + 快捷入口行 + 数据两列（图表/预警/日程/最近）。

    信号:
        quickNav(int): 快捷卡片/预警横幅被点击时发射，参数为目标页面索引
        addStudentRequested(): 「+ 新增学员」被点击时发射
    """

    quickNav = Signal(int)
    addStudentRequested = Signal()

    def __init__(self, parent=None, coach_name: str = '教练', archive_dir_getter=None):
        """
        参数:
            coach_name: 当前登录教练名（用于欢迎语）
            archive_dir_getter: 返回当前档案目录的可调用对象（概览数据来源）
        """
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        # 背景规则必须限定在本控件（无选择器会下压覆盖所有后代的 QSS，如主按钮橙底）
        self.setObjectName('HomePage')
        self.setStyleSheet(
            f'QWidget#HomePage {{ background-color: {ColorPalette.BG}; }}'
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(14)

        # === 头部行：欢迎语 + 主操作 ===
        head = QHBoxLayout()
        head.setSpacing(12)
        head_col = QVBoxLayout()
        head_col.setSpacing(2)
        welcome = QLabel(f'你好，{coach_name}')
        welcome.setStyleSheet(f'''
            color: {ColorPalette.TEXT};
            font-size: 26px;
            font-weight: 800;
            background: transparent;
        ''')
        head_col.addWidget(welcome)
        now = datetime.now()
        self.subtitle = QLabel(
            f'欢迎回来，今天是{now.month}月{now.day}日 {_WEEKDAY_CN[now.weekday()]}'
        )
        self.subtitle.setStyleSheet(f'''
            color: {ColorPalette.TEXT_SECONDARY};
            font-size: 13px;
            background: transparent;
        ''')
        head_col.addWidget(self.subtitle)
        head.addLayout(head_col, 1)

        self.btn_add_student = QPushButton('+ 新增学员')
        self.btn_add_student.setObjectName('primary')
        self.btn_add_student.setCursor(Qt.PointingHandCursor)
        self.btn_add_student.clicked.connect(self.addStudentRequested.emit)
        head.addWidget(self.btn_add_student)
        root.addLayout(head)

        # === 真数据统计条（小灰标签 + 大数字，一行四格竖线分隔） ===
        strip = QFrame()
        strip.setObjectName('statStrip')
        strip.setStyleSheet(f'''
            QFrame#statStrip {{
                background: {ColorPalette.CARD};
                border: 1px solid {ColorPalette.BORDER};
                border-radius: {Shapes.CARD_RADIUS}px;
            }}
        ''')
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(20, 14, 20, 14)
        strip_lay.setSpacing(0)
        self.cell_total = StatCell('学员总数')
        self.cell_red = StatCell('需续费（≤3课时）', accent='#F87171')
        self.cell_yellow = StatCell('课时关注（≤6课时）', accent='#F59E0B')
        self.cell_remaining = StatCell('剩余课时合计')
        cells = [self.cell_total, self.cell_red, self.cell_yellow, self.cell_remaining]
        for i, cell in enumerate(cells):
            if i:
                line = QLabel()
                line.setFixedSize(1, 36)
                line.setStyleSheet(
                    f'background: {ColorPalette.DIVIDER}; border: none;'
                )
                strip_lay.addWidget(line)
            strip_lay.addWidget(cell, 1)
        root.addWidget(strip)

        # === 快捷入口行（5 项，索引与 app.py PAGE_* 常量一致） ===
        quick_row = QHBoxLayout()
        quick_row.setSpacing(12)
        quicks = [
            ('学员档案', IconBox.USER, 1),
            ('教练管理', IconBox.WHISTLE, 2),
            ('体测档案与课时', IconBox.CHART_BAR, 3),
            ('训练任务编排', IconBox.DUMBBELL, 4),
            ('数据中心', IconBox.ARCHIVE, 5),
        ]
        for title, icon, page in quicks:
            quick_row.addWidget(_QuickCard(title, icon, page), 1)
        root.addLayout(quick_row)

        # === 主体两列 ===
        body = QHBoxLayout()
        body.setSpacing(14)

        # -- 左列：上课统计 + 续费预警 --
        left = QVBoxLayout()
        left.setSpacing(14)

        self.card_chart = _SectionCard('上课统计 · 近 6 个月',
                                       link_text='课时明细 ›', link_page=3)
        self.chart = _BarChart()
        self.card_chart.body.addWidget(self.chart)
        left.addWidget(self.card_chart, 5)

        self.card_alert = _SectionCard('续费预警',
                                       link_text='学员档案 ›', link_page=1, scroll=True)
        self.alert_list_lay = self.card_alert.body
        left.addWidget(self.card_alert, 4)

        body.addLayout(left, 3)

        # -- 右列：今日日程 + 最近上课 --
        right = QVBoxLayout()
        right.setSpacing(14)

        self.card_today = _SectionCard('今日日程',
                                       link_text='课时管理 ›', link_page=3, scroll=True)
        self.today_list_lay = self.card_today.body
        right.addWidget(self.card_today, 5)

        self.card_recent = _SectionCard('最近上课',
                                        link_text='全部记录 ›', link_page=3, scroll=True)
        self.recent_list_lay = self.card_recent.body
        right.addWidget(self.card_recent, 4)

        body.addLayout(right, 2)

        root.addLayout(body, 1)

    #---- 数据刷新 ----

    def showEvent(self, event):
        """每次切到首页都刷新概览（轻量 xlsx 读取，失败静默降级为 —）。"""
        self.refresh_overview()
        super().showEvent(event)

    def refresh_overview(self):
        """读取学员与课时数据，刷新统计条 / 柱状图 / 今日日程 / 最近上课 / 预警列表。"""
        overview = {'total': 0, 'red': 0, 'yellow': 0, 'remaining': 0}
        students = []
        details = []
        summary_map = {}
        try:
            # 延迟导入：模块加载路径由 app.py 注入，纯函数测试时无需 Qt 外依赖
            import profile_manager as pm
            import lesson_manager as lm
            d = self._get_dir()
            students = pm.list_students(d)
            details = lm.get_detail(d)
            summary_map = {s['name']: s for s in lm.get_summary(d)}
            overview = compute_overview(students)
        except Exception:
            logging.exception('首页概览数据加载失败')

        # 统计条
        self.cell_total.set_value(overview['total'])
        self.cell_red.set_value(overview['red'])
        self.cell_yellow.set_value(overview['yellow'])
        self.cell_remaining.set_value(overview['remaining'])

        # 近 6 月柱状图（课时明细按月聚合）
        self.chart.set_data(compute_monthly_stats(details))

        # 今日日程
        _clear_layout(self.today_list_lay)
        today_items = filter_today(details)
        if today_items:
            for rec in today_items[:4]:
                content = str(rec.get('content') or '').strip()
                self.today_list_lay.addWidget(
                    _LessonRow(rec['name'], content, rec.get('count'),
                               show_tail_right=bool(content))
                )
            if len(today_items) > 4:
                self.today_list_lay.addWidget(self._more_hint(f'还有 {len(today_items) - 4} 条今日记录'))
        else:
            self.today_list_lay.addWidget(_EmptyState('今天没有课程安排'))

        # 最近上课（按日期倒序前 5）
        _clear_layout(self.recent_list_lay)
        recent = recent_lessons(details, limit=5)
        if recent:
            for rec in recent:
                d = _parse_date(rec.get('date'))
                tail = d.strftime('%m-%d') if d else ''
                self.recent_list_lay.addWidget(
                    _LessonRow(rec['name'], tail, rec.get('count'))
                )
        else:
            self.recent_list_lay.addWidget(_EmptyState('暂无上课记录', IconBox.CHART_LINE))

        # 续费预警（红/黄学员，进度条 + 剩余胶囊）
        _clear_layout(self.alert_list_lay)
        warn_students = [s for s in students if s.get('warn_level') in ('red', 'yellow')]
        warn_students.sort(key=lambda s: (s.get('warn_level') != 'red',
                                          int(s.get('remaining') or 0)))
        if warn_students:
            for s in warn_students[:4]:
                sm = summary_map.get(s['name'], {})
                self.alert_list_lay.addWidget(_AlertRow(
                    s['name'], s.get('remaining'), sm.get('total'),
                    s.get('warn_level'),
                ))
            if len(warn_students) > 4:
                self.alert_list_lay.addWidget(
                    self._more_hint(f'还有 {len(warn_students) - 4} 名学员需要关注'))
        else:
            self.alert_list_lay.addWidget(_EmptyState('暂无续费预警，课时充足', IconBox.TREND_UP))

    @staticmethod
    def _more_hint(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; font-size: 11px;'
            'background: transparent; padding: 2px;'
        )
        return lbl
