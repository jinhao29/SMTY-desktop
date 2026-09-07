# -*- coding: utf-8 -*-
"""UI 层：学员 / 教练个人详情页（Dashboard 风格，参考图1 布局语言）。

从「学员档案 / 教练管理」表格点击行进入，聚合该人全部数据：
- 头部：返回按钮 + 大头像 + 姓名 + 状态徽章 + 基本信息行
- 统计条：课时与费用关键数字（StatCell 复用）
- 左列：近 6 月上课柱状图 + 上课记录列表
- 右列：收入构成分段条（实收/待收）+ 财务指标 + 收费记录列表

数据来源（只读，不做任何写操作）：
- profile_manager.list_students / lesson_manager.get_detail / fee_manager
- coach_manager.list_coaches

信号:
    backRequested(): 「返回」被点击，由 App 切回来源页面
"""
import logging
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QScrollArea, QApplication
)

from base_components import (
    ColorPalette, Shapes, IconBox, StatCell, _fade_color
)
from home_page import _BarChart, _Pill, _Avatar, _parse_date, compute_monthly_stats


def _fmt_money(v):
    try:
        return f'¥{float(v or 0):,.2f}'
    except (TypeError, ValueError):
        return '¥0.00'


#==== 收入构成分段条（参考图2 lightcap Cap table 风格）====

class FinanceBar(QWidget):
    """横向分段构成条 + 图例：实收（珊瑚橙） / 待收（琥珀）。

    set_data(paid, due) 后重绘；总额为 0 时画灰色空轨道。
    """

    PAID_COLOR = '#FF6B47'
    DUE_COLOR = '#F5B04C'
    TRACK_COLOR = '#EFEFEF'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paid = 0.0
        self._due = 0.0
        self.setMinimumHeight(88)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_data(self, paid: float, due: float):
        self._paid = max(0.0, float(paid or 0))
        self._due = max(0.0, float(due or 0))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        bar_h = 18
        bar_y = 6
        radius = bar_h / 2
        total = self._paid + self._due

        # 空轨道
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.TRACK_COLOR))
        painter.drawRoundedRect(QRectF(0, bar_y, w, bar_h), radius, radius)

        if total > 0:
            paid_w = max(bar_h, w * self._paid / total) if self._paid > 0 else 0
            if self._paid > 0:
                painter.setBrush(QColor(self.PAID_COLOR))
                painter.drawRoundedRect(QRectF(0, bar_y, paid_w, bar_h), radius, radius)
            if self._due > 0:
                # 待收段紧贴实收段（留 2px 白缝），右端圆角
                seg_x = paid_w + 3 if self._paid > 0 else 0
                seg_w = max(bar_h, w - seg_x)
                painter.setBrush(QColor(self.DUE_COLOR))
                painter.drawRoundedRect(QRectF(seg_x, bar_y, seg_w, bar_h), radius, radius)

        # 图例
        ly = bar_y + bar_h + 12
        painter.setFont(self._legend_font(bold=True))
        total_txt = _fmt_money(total)
        painter.setPen(QColor(ColorPalette.TEXT))
        painter.drawText(QRectF(0, ly, w * 0.4, 22), Qt.AlignLeft, total_txt)
        painter.setFont(self._legend_font())
        painter.setPen(QColor(ColorPalette.TEXT_MUTED))
        painter.drawText(QRectF(w * 0.42, ly + 2, w * 0.3, 20), Qt.AlignLeft,
                         '实收 + 待收')
        painter.end()

    @staticmethod
    def _legend_font(bold=False):
        from PySide6.QtGui import QFont
        f = QFont('Inter')
        f.setPixelSize(13)
        f.setBold(bold)
        return f


class FinanceLegendRow(QFrame):
    """图例行：色点 + 名称 + 金额 + 百分比（参考图2 图例排版）。"""

    def __init__(self, label: str, amount: str, percent: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName('legendRow')
        self.setStyleSheet('QFrame#legendRow { background: transparent; border: none; }')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(10)
        dot = QLabel()
        dot.setFixedSize(12, 12)
        dot.setStyleSheet(
            f'background: {color}; border-radius: 3px; border: none;'
        )
        lay.addWidget(dot)
        self.lbl_name = QLabel(label)
        self.lbl_name.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 13px; font-weight: 700;'
            'background: transparent; border: none;'
        )
        lay.addWidget(self.lbl_name)
        lay.addStretch()
        self.lbl_amount = QLabel(amount)
        self.lbl_amount.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 13px; font-weight: 700;'
            'background: transparent; border: none;'
        )
        lay.addWidget(self.lbl_amount)
        self.lbl_pct = QLabel(percent)
        self.lbl_pct.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; font-size: 12px;'
            'background: transparent; border: none;'
        )
        self.lbl_pct.setFixedWidth(52)
        self.lbl_pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.lbl_pct)

    def set_data(self, label: str, amount: float, total: float):
        """更新图例数值（amount/total 为原始金额）。"""
        pct = f'{(amount / total * 100):.0f}%' if total > 0 else '0%'
        self.lbl_name.setText(label)
        self.lbl_amount.setText(_fmt_money(amount))
        self.lbl_pct.setText(pct)


#==== 白底描边卡片（与首页 _SectionCard 同款，避免循环 import 直接复制视觉参数）====

class _Card(QFrame):
    def __init__(self, title: str, scroll: bool = False, min_height: int = 160, parent=None):
        super().__init__(parent)
        self.setObjectName('DetailCard')
        self.setStyleSheet(f'''
            QFrame#DetailCard {{
                background: {ColorPalette.CARD};
                border: 1px solid {ColorPalette.BORDER};
                border-radius: {Shapes.CARD_RADIUS}px;
            }}
        ''')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        t = QLabel(title)
        t.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 14px; font-weight: 700;'
            'background: transparent; border: none;'
        )
        lay.addWidget(t)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(4)
        if scroll:
            # 列表行后续动态添加：先占位滚动区，body 已移交给内容 widget
            content = QWidget()
            content.setObjectName('ScrollBody')
            content.setLayout(self.body)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(content)
            area.setFrameShape(QFrame.NoFrame)
            area.setMinimumHeight(min_height)
            area.setStyleSheet('''
                QScrollArea { background: transparent; border: none; }
                QWidget#ScrollBody { background: transparent; }
                QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }
                QScrollBar::handle:vertical { background: #DADADA; border-radius: 2px; min-height: 24px; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            ''')
            lay.addWidget(area)
        else:
            lay.addLayout(self.body)


#==== 信息行 ====

def _plain_row() -> QWidget:
    """透明容器行（objectName 限定裸声明，防止 QSS 下压覆盖后代按钮边框）。"""
    row = QWidget()
    row.setObjectName('plainRow')
    row.setStyleSheet(
        'QWidget#plainRow { background: transparent; border: none; }'
    )
    return row


def _info_row(label: str, value: str, value_color: str = None) -> QWidget:
    """标签左 / 值右的单行信息。"""
    row = _plain_row()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(2, 5, 2, 5)
    lay.setSpacing(8)
    lbl = QLabel(label)
    lbl.setStyleSheet(
        f'color: {ColorPalette.TEXT_MUTED}; font-size: 13px;'
        'background: transparent; border: none;'
    )
    lay.addWidget(lbl)
    lay.addStretch()
    val = QLabel(value or '—')
    val.setStyleSheet(
        f'color: {value_color or ColorPalette.TEXT}; font-size: 13px; font-weight: 600;'
        'background: transparent; border: none;'
    )
    lay.addWidget(val)
    return row


def _clear_layout(lay):
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.deleteLater()


#==== 学员详情页 ====

class StudentDetailPage(QWidget):
    """单个学员的课时 / 财务 / 档案聚合详情页。"""

    backRequested = Signal()

    def __init__(self, archive_dir_getter=None, parent=None):
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        self._student_name = ''
        self.setObjectName('StudentDetailPage')
        self.setStyleSheet(
            f'QWidget#StudentDetailPage {{ background-color: {ColorPalette.BG}; }}'
        )
        self._build_ui()

    #---- UI ----

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)

        # 顶部：返回
        top = QHBoxLayout()
        self.btn_back = QPushButton('‹  返回列表')
        self.btn_back.setObjectName('secondary')
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.backRequested.emit)
        top.addWidget(self.btn_back)
        top.addStretch()
        root.addLayout(top)

        # 头部卡：头像 + 姓名 + 状态 + 信息 chips
        head = QFrame()
        head.setObjectName('DetailCard')
        head.setStyleSheet(f'''
            QFrame#DetailCard {{
                background: {ColorPalette.CARD};
                border: 1px solid {ColorPalette.BORDER};
                border-radius: {Shapes.CARD_RADIUS}px;
            }}
        ''')
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(16)
        self.avatar = _Avatar('?', 56)
        hl.addWidget(self.avatar)
        info = QVBoxLayout()
        info.setSpacing(4)
        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        self.lbl_name = QLabel('—')
        self.lbl_name.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 24px; font-weight: 800;'
            'background: transparent; border: none;'
        )
        name_row.addWidget(self.lbl_name)
        self.pill_status = _Pill('正常', '#E8F7EF', '#1E8A5A')
        name_row.addWidget(self.pill_status)
        name_row.addStretch()
        info.addLayout(name_row)
        self.lbl_meta = QLabel('—')
        self.lbl_meta.setStyleSheet(
            f'color: {ColorPalette.TEXT_SECONDARY}; font-size: 13px;'
            'background: transparent; border: none;'
        )
        info.addWidget(self.lbl_meta)
        hl.addLayout(info, 1)
        # 右上角：最近上课
        recent_col = QVBoxLayout()
        recent_col.setSpacing(2)
        cap = QLabel('最近上课')
        cap.setAlignment(Qt.AlignRight)
        cap.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; font-size: 12px;'
            'background: transparent; border: none;'
        )
        recent_col.addWidget(cap)
        self.lbl_last = QLabel('—')
        self.lbl_last.setAlignment(Qt.AlignRight)
        self.lbl_last.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 16px; font-weight: 700;'
            'background: transparent; border: none;'
        )
        recent_col.addWidget(self.lbl_last)
        hl.addLayout(recent_col)
        root.addWidget(head)

        # 统计条：总课时 / 已上 / 剩余 / 已消课费用
        strip = QFrame()
        strip.setObjectName('statStrip')
        strip.setStyleSheet(f'''
            QFrame#statStrip {{
                background: {ColorPalette.CARD};
                border: 1px solid {ColorPalette.BORDER};
                border-radius: {Shapes.CARD_RADIUS}px;
            }}
        ''')
        sl = QHBoxLayout(strip)
        sl.setContentsMargins(20, 14, 20, 14)
        sl.setSpacing(0)
        self.cell_total = StatCell('总课时')
        self.cell_attended = StatCell('已上')
        self.cell_remaining = StatCell('剩余课时')
        self.cell_consumed = StatCell('已消课费用')
        for i, cell in enumerate((self.cell_total, self.cell_attended,
                                  self.cell_remaining, self.cell_consumed)):
            if i:
                line = QLabel()
                line.setFixedSize(1, 36)
                line.setStyleSheet(f'background: {ColorPalette.DIVIDER}; border: none;')
                sl.addWidget(line)
            sl.addWidget(cell, 1)
        root.addWidget(strip)

        # 主体两列
        body = QHBoxLayout()
        body.setSpacing(14)

        # -- 左列：柱状图 + 上课记录 --
        left = QVBoxLayout()
        left.setSpacing(14)
        card_chart = _Card('上课统计 · 近 6 个月')
        self.chart = _BarChart()
        card_chart.body.addWidget(self.chart)
        left.addWidget(card_chart, 5)

        card_records = _Card('上课记录', scroll=True, min_height=150)
        self.records_lay = card_records.body
        left.addWidget(card_records, 4)
        body.addLayout(left, 3)

        # -- 右列：财务 + 收费记录 --
        right = QVBoxLayout()
        right.setSpacing(14)
        card_finance = _Card('财务概览')
        self.finance_bar = FinanceBar()
        card_finance.body.addWidget(self.finance_bar)
        self.legend_paid = FinanceLegendRow('实收', '¥0.00', '0%', FinanceBar.PAID_COLOR)
        self.legend_due = FinanceLegendRow('待收', '¥0.00', '0%', FinanceBar.DUE_COLOR)
        card_finance.body.addWidget(self.legend_paid)
        card_finance.body.addWidget(self.legend_due)
        card_finance.body.addSpacing(6)
        # 指标行独立子布局：刷新时只清这里，不动柱条与图例
        self.metrics_lay = QVBoxLayout()
        self.metrics_lay.setContentsMargins(0, 0, 0, 0)
        self.metrics_lay.setSpacing(0)
        card_finance.body.addLayout(self.metrics_lay)
        self.finance_rows_lay = self.metrics_lay  # 兼容旧引用
        right.addWidget(card_finance, 5)

        card_pay = _Card('收费记录', scroll=True, min_height=150)
        self.payments_lay = card_pay.body
        right.addWidget(card_pay, 4)
        body.addLayout(right, 2)

        root.addLayout(body, 1)

    #---- 数据 ----

    def load_student(self, name: str):
        """按姓名加载学员详情（数据读取失败静默降级为空态）。"""
        self._student_name = name or ''
        d = self._get_dir()
        student = {}
        finance = None
        details = []
        payments = []
        try:
            import profile_manager as pm
            import lesson_manager as lm
            import fee_manager as fm
            students = pm.list_students(d, include_inactive=True)
            student = next((s for s in students if s.get('name') == name), {})
            details = lm.get_detail(d, name)
            if student:
                finance = fm.compute_finance(
                    d, lesson_summaries=[student], fee_records=fm.get_payments(d, name))
                payments = fm.get_payments(d, name)
        except Exception:
            logging.exception('学员详情加载失败：%s', name)

        self._fill_head(student)
        self._fill_stats(student)
        self.chart.set_data(compute_monthly_stats(details))
        self._fill_records(details)
        self._fill_finance(finance, payments, student)

    #---- 填充 ----

    def _fill_head(self, s: dict):
        name = s.get('name') or self._student_name or '—'
        self.lbl_name.setText(name)
        self.avatar.setText(name[0] if name and name != '—' else '?')
        if not s:
            self.lbl_meta.setText('未找到该学员档案')
            self.lbl_last.setText('—')
            self.pill_status.setText('未知')
            return
        meta_parts = []
        if s.get('gender'):
            meta_parts.append(str(s['gender']))
        if s.get('age'):
            meta_parts.append(f"{s['age']} 岁")
        if s.get('grade'):
            meta_parts.append(str(s.get('grade_display') or s['grade']))
        if s.get('school'):
            meta_parts.append(str(s['school']))
        if s.get('phone'):
            meta_parts.append(str(s['phone']))
        self.lbl_meta.setText('  ·  '.join(meta_parts) if meta_parts else '暂无档案信息')
        self.lbl_last.setText(s.get('last_date') or '—')
        level = s.get('warn_level', 'unknown')
        if not s.get('is_active', True):
            self.pill_status.setText('已停用')
            self.pill_status.setStyleSheet(
                'background: #EFEFEF; color: #6B6B6B; border-radius: 9px;'
                'padding: 2px 9px; font-size: 11px; font-weight: 600;')
        elif level == 'red':
            self.pill_status.setText('需续费')
            self.pill_status.setStyleSheet(
                'background: #FEE2E2; color: #DC2626; border-radius: 9px;'
                'padding: 2px 9px; font-size: 11px; font-weight: 600;')
        elif level == 'yellow':
            self.pill_status.setText('课时关注')
            self.pill_status.setStyleSheet(
                'background: #FEF3C7; color: #B45309; border-radius: 9px;'
                'padding: 2px 9px; font-size: 11px; font-weight: 600;')
        else:
            self.pill_status.setText('正常')
            self.pill_status.setStyleSheet(
                'background: #E8F7EF; color: #1E8A5A; border-radius: 9px;'
                'padding: 2px 9px; font-size: 11px; font-weight: 600;')

    def _fill_stats(self, s: dict):
        total = int(s.get('total') or 0)
        attended = int(s.get('attended') or 0)
        self.cell_total.set_value(total)
        self.cell_attended.set_value(attended)
        self.cell_remaining.set_value(int(s.get('remaining') or 0))
        # 已消课费用由财务计算填充；无财务数据时显示 0
        self.cell_consumed.set_value('¥0.00')

    def _fill_records(self, details: list):
        _clear_layout(self.records_lay)
        details = sorted(
            (r for r in details or [] if _parse_date(r.get('date'))),
            key=lambda r: _parse_date(r.get('date')), reverse=True)
        if not details:
            self.records_lay.addWidget(_EmptyHint('暂无上课记录'))
            return
        for rec in details[:20]:
            d = _parse_date(rec.get('date'))
            content = str(rec.get('content') or '').strip()
            try:
                cnt = int(rec.get('count') or 0)
            except (TypeError, ValueError):
                cnt = 0
            row = _plain_row()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(4, 5, 4, 5)
            lay.setSpacing(10)
            dt = QLabel(d.strftime('%Y-%m-%d') if d else '—')
            dt.setFixedWidth(88)
            dt.setStyleSheet(
                f'color: {ColorPalette.TEXT_SECONDARY}; font-size: 12px;'
                'background: transparent; border: none;')
            lay.addWidget(dt)
            desc = QLabel(content or '课时消耗')
            desc.setStyleSheet(
                f'color: {ColorPalette.TEXT}; font-size: 13px;'
                'background: transparent; border: none;')
            desc.setMaximumWidth(220)
            lay.addWidget(desc)
            lay.addStretch()
            lay.addWidget(_Pill(f'+{cnt} 节', ColorPalette.PRIMARY_LIGHT, ColorPalette.PRIMARY))
            self.records_lay.addWidget(row)
        self.records_lay.addStretch()

    def _fill_finance(self, finance: list, payments: list, student: dict):
        row = finance[0] if finance else None
        paid = float(row.get('paid') or 0) if row else 0.0
        due = max(0.0, float(row.get('due') or 0)) if row else 0.0
        receivable = float(row.get('receivable') or 0) if row else 0.0
        consumed = float(row.get('consumed') or 0) if row else 0.0
        price = row.get('unit_price') or 0 if row else 0

        self.finance_bar.set_data(paid, due)
        total = paid + due
        self.legend_paid.set_data('实收', paid, total)
        self.legend_due.set_data('待收', due, total)

        # 更新统计条「已消课费用」
        self.cell_consumed.set_value(_fmt_money(consumed))

        # 指标行（重建：只清独立子布局）
        _clear_layout(self.metrics_lay)
        status = (row or {}).get('status') or (
            '未收费' if paid <= 0 else '已结清')
        status_color = {'已结清': '#1F9D55', '待收款': '#E55A3A',
                        '未收费': '#9B9B9B'}.get(status, ColorPalette.TEXT)
        for label, value, color in (
                ('课时单价', _fmt_money(price) if price else '—', None),
                ('应收总额', _fmt_money(receivable), None),
                ('待收金额', _fmt_money(due) if due > 0 else '—', '#E55A3A' if due > 0 else None),
                ('状态', status, status_color)):
            self.finance_rows_lay.addWidget(_info_row(label, value, color))

        # 收费记录
        _clear_layout(self.payments_lay)
        payments = payments or []
        if not payments:
            self.payments_lay.addWidget(_EmptyHint('暂无收费记录'))
            return
        for p in payments[:20]:
            row_w = _plain_row()
            lay = QHBoxLayout(row_w)
            lay.setContentsMargins(4, 5, 4, 5)
            lay.setSpacing(10)
            dt = QLabel(str(p.get('date') or '—'))
            dt.setFixedWidth(88)
            dt.setStyleSheet(
                f'color: {ColorPalette.TEXT_SECONDARY}; font-size: 12px;'
                'background: transparent; border: none;')
            lay.addWidget(dt)
            method = QLabel(str(p.get('method') or '—'))
            method.setStyleSheet(
                f'color: {ColorPalette.TEXT}; font-size: 13px;'
                'background: transparent; border: none;')
            lay.addWidget(method)
            lay.addStretch()
            lay.addWidget(_Pill(_fmt_money(p.get('amount')), '#E8F7EF', '#1F9D55'))
            self.payments_lay.addWidget(row_w)
        self.payments_lay.addStretch()

    @staticmethod
    def _refresh_legend(old: 'FinanceLegendRow', label, amount, total) -> 'FinanceLegendRow':
        """兼容占位：图例行已改为原地 set_data 更新。"""
        old.set_data(label, amount, total)
        return old


class _EmptyHint(QWidget):
    """空态提示。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 14, 0, 14)
        tip = QLabel(text)
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; font-size: 12px;'
            'background: transparent; border: none;'
        )
        lay.addWidget(tip)


#==== 教练详情页 ====

class CoachDetailPage(QWidget):
    """单个教练的个人详情页（档案信息 + 联系方式）。"""

    backRequested = Signal()

    def __init__(self, archive_dir_getter=None, parent=None):
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        self._phone = ''
        self.setObjectName('CoachDetailPage')
        self.setStyleSheet(
            f'QWidget#CoachDetailPage {{ background-color: {ColorPalette.BG}; }}'
        )
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)

        top = QHBoxLayout()
        btn_back = QPushButton('‹  返回列表')
        btn_back.setObjectName('secondary')
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.clicked.connect(self.backRequested.emit)
        top.addWidget(btn_back)
        top.addStretch()
        root.addLayout(top)

        # 头部卡
        head = QFrame()
        head.setObjectName('DetailCard')
        head.setStyleSheet(f'''
            QFrame#DetailCard {{
                background: {ColorPalette.CARD};
                border: 1px solid {ColorPalette.BORDER};
                border-radius: {Shapes.CARD_RADIUS}px;
            }}
        ''')
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(16)
        self.avatar = _Avatar('?', 56)
        hl.addWidget(self.avatar)
        info = QVBoxLayout()
        info.setSpacing(4)
        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        self.lbl_name = QLabel('—')
        self.lbl_name.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 24px; font-weight: 800;'
            'background: transparent; border: none;'
        )
        name_row.addWidget(self.lbl_name)
        self.pill_status = _Pill('在职', '#E8F7EF', '#1E8A5A')
        name_row.addWidget(self.pill_status)
        name_row.addStretch()
        info.addLayout(name_row)
        self.lbl_role = QLabel('—')
        self.lbl_role.setStyleSheet(
            f'color: {ColorPalette.TEXT_SECONDARY}; font-size: 13px;'
            'background: transparent; border: none;'
        )
        info.addWidget(self.lbl_role)
        hl.addLayout(info, 1)
        root.addWidget(head)

        # 信息卡
        card = _Card('教练信息')
        self.info_lay = card.body
        root.addWidget(card)
        root.addStretch()

    def load_coach(self, name: str):
        """按姓名加载教练详情。"""
        coach = {}
        try:
            import coach_manager as cm
            coaches = cm.list_coaches(self._get_dir(), include_inactive=True)
            coach = next((c for c in coaches if c.get('name') == name), {})
        except Exception:
            logging.exception('教练详情加载失败：%s', name)

        display = coach.get('name') or name or '—'
        self.lbl_name.setText(display)
        self.avatar.setText(display[0] if display and display != '—' else '?')
        active = coach.get('is_active', True)
        self.pill_status.setText('在职' if active else '离职')
        self.pill_status.setStyleSheet(
            ('background: #E8F7EF; color: #1E8A5A;' if active
             else 'background: #EFEFEF; color: #6B6B6B;')
            + 'border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 600;')
        role = coach.get('role') or '—'
        specialty = coach.get('specialty') or ''
        self.lbl_role.setText(
            role + (f'  ·  {specialty}' if specialty else ''))

        # 信息行重建
        while self.info_lay.count():
            it = self.info_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._phone = coach.get('phone') or ''
        for label, value in (
                ('电话', self._phone or '未填写'),
                ('入职日期', coach.get('join_date') or '—'),
                ('专长', coach.get('specialty') or '—'),
                ('备注', coach.get('note') or '—')):
            self.info_lay.addWidget(_info_row(label, value))
        btn_copy = None
        if self._phone:
            btn_copy = QPushButton('复制电话')
            btn_copy.setObjectName('secondary')
            btn_copy.setCursor(Qt.PointingHandCursor)
            btn_copy.setFixedWidth(96)
            btn_copy.clicked.connect(self._copy_phone)
        row = _plain_row()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(2, 8, 2, 2)
        lay.addStretch()
        if btn_copy is not None:
            lay.addWidget(btn_copy)
        self.info_lay.addWidget(row)

    def _copy_phone(self):
        if self._phone:
            QApplication.clipboard().setText(self._phone)
