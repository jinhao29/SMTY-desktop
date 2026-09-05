# -*- coding: utf-8 -*-
"""UI 层：阶段总结子页（灰白简约 · 蓝紫强调，对齐图2）。

功能流程：
  选择学员 + 时间段 → 点击「生成阶段总结」→ 展示课时/反馈/成绩数据 → 导出 Word

界面布局：
  ┌─ 左侧主区域 ─────────────┬─ 右侧辅助区 ───────┐
  │ 查询条件卡片              │ 蓝紫渐变概览卡片    │
  │ 阶段概述卡片              │ 数据概览 2x2       │
  │ 成绩进步对比表            │ 导出操作卡片        │
  │ 阶段内课后反馈表          │                    │
  └──────────────────────────┴────────────────────┘

设计要点：
- 不持有业务状态，所有数据每次生成时现取
- 通过 archive_dir_getter 回调获取档案目录，避免与主窗口耦合
- 导出 Word 时使用 python-docx，A4 纵向
- 顶部导航由 main.py 统一提供，本页不重复渲染
- #training_root 作用域 QSS 由外层根 widget 向下级联，本页无需自带样式表
"""
import modern_dialog as dialog
import os
from datetime import datetime
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog, QFrame, QTextEdit, QScrollArea
)

import summary_processor

# 新设计语言令牌与组件
from styles import Palette, Type, Spacing, Shadow, Radius
from cards import Card
# StatCard / IconBox / BarChartWidget 接受 color 参数，传入新令牌色即可统一
from ui_components import StatCard, IconBox, BarChartWidget, GradientHeroCard
from base_components import Shapes, Shadows, _fade_color, paint_card_base, FormSheet


class HeroCard(GradientHeroCard):
    """蓝紫渐变重点卡片（覆盖 GradientHeroCard 的珊瑚橙渐变）。

    复用 GradientHeroCard 的 _title/_value/_subtitle 属性与 update() 接口，
    仅替换 paintEvent 的渐变色为蓝紫强调，与训练编排主界面统一。
    """

    def paintEvent(self, event):
        painter = QPainter(self)
        radius = Shapes.CARD_RADIUS
        rect = self.rect()  # v25 去阴影：无留白，卡片铺满 widget
        # 蓝紫渐变：强调色 → 深强调
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor(Palette.ACCENT))
        grad.setColorAt(1, QColor(Palette.ACCENT_PRESSED))
        paint_card_base(painter, rect, radius, 0, fill=QBrush(grad))
        # 文字
        painter.setPen(QColor('#FFFFFF'))
        painter.setFont(Type.caption())
        painter.drawText(rect.adjusted(20, 20, -20, 0), Qt.AlignTop | Qt.AlignLeft, self._title)
        painter.setFont(Type.hero())
        painter.drawText(rect.adjusted(20, 44, -20, -20), Qt.AlignLeft | Qt.AlignVCenter, str(self._value))
        if self._subtitle:
            painter.setPen(QColor(255, 255, 255, 200))
            painter.setFont(Type.caption())
            painter.drawText(rect.adjusted(20, 0, -20, -20), Qt.AlignBottom | Qt.AlignLeft, self._subtitle)
        painter.end()


class StageSummaryScreen(QWidget):
    """阶段总结子页。"""

    def __init__(self, archive_dir_getter=None, parent=None):
        """
        参数:
            archive_dir_getter: 返回档案目录路径的可调用对象
        """
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        self._summary = None  # 当前展示的总结数据
        self._init_ui()

    def _init_ui(self):
        main_lay = QHBoxLayout(self)
        main_lay.setSpacing(Spacing.CARD)
        main_lay.setContentsMargins(0, 0, 0, 0)

        # ===== 左侧：可滚动主内容区 =====
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        left_content = QWidget()  # 透明背景由 TRAINING_QSS 全局规则提供（裸声明会压掉按钮背景）
        left_lay = QVBoxLayout(left_content)
        left_lay.setSpacing(Spacing.CARD)
        left_lay.setContentsMargins(0, 0, 0, 0)

        # --- 连续版面（v25：单张白纸分节，替代多卡框套框） ---
        sheet = FormSheet()
        cl = QVBoxLayout()
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(Spacing.SM)

        field_row = QHBoxLayout()
        field_row.setSpacing(Spacing.MD)
        lbl_student = self._mk_sub_label('学员')
        field_row.addWidget(lbl_student)
        self.cb_student = QComboBox()
        self.cb_student.setMinimumWidth(160)
        field_row.addWidget(self.cb_student, 1)

        lbl_start = self._mk_sub_label('起始')
        field_row.addWidget(lbl_start)
        self.dte_start = QDateEdit()
        self.dte_start.setCalendarPopup(True)
        self.dte_start.setDisplayFormat('yyyy-MM-dd')
        # 默认最近 3 个月
        s, e = summary_processor.default_stage_range(3)
        self.dte_start.setDate(QDate.fromString(s, 'yyyy-MM-dd'))
        field_row.addWidget(self.dte_start)

        lbl_end = self._mk_sub_label('结束')
        field_row.addWidget(lbl_end)
        self.dte_end = QDateEdit()
        self.dte_end.setCalendarPopup(True)
        self.dte_end.setDisplayFormat('yyyy-MM-dd')
        self.dte_end.setDate(QDate.fromString(e, 'yyyy-MM-dd'))
        field_row.addWidget(self.dte_end)
        cl.addLayout(field_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(Spacing.SM)
        btn_row.addStretch()
        self.btn_refresh = QPushButton('刷新学员', objectName='secondary')
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_students)
        btn_row.addWidget(self.btn_refresh)

        self.btn_gen = QPushButton('生成阶段总结', objectName='primary')
        self.btn_gen.setCursor(Qt.PointingHandCursor)
        self.btn_gen.setMinimumWidth(140)
        self.btn_gen.clicked.connect(self.on_generate)
        btn_row.addWidget(self.btn_gen)
        cl.addLayout(btn_row)
        sheet.add_section('查询条件', cl)

        # --- 阶段概述节 ---
        ol = QVBoxLayout()
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(Spacing.SM)
        self.te_overview = QTextEdit()
        self.te_overview.setReadOnly(True)
        self.te_overview.setPlaceholderText('点击「生成阶段总结」后，此处显示概述文字。')
        self.te_overview.setFixedHeight(90)
        ol.addWidget(self.te_overview)
        sheet.add_section('阶段概述', ol)

        # --- 成绩进步对比节 ---
        sl = QVBoxLayout()
        sl.setContentsMargins(0, 0, 0, 0)
        self.table_score = QTableWidget()
        self.table_score.setColumnCount(6)
        self.table_score.setHorizontalHeaderLabels(
            ['项目', '首次成绩', '首次得分', '末次成绩', '末次得分', '得分变化']
        )
        self.table_score.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            self.table_score.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table_score.setMinimumHeight(180)
        self.table_score.setAlternatingRowColors(True)
        sl.addWidget(self.table_score)
        sheet.add_section('成绩进步对比', sl)

        # --- 阶段内课后反馈节 ---
        fl = QVBoxLayout()
        fl.setContentsMargins(0, 0, 0, 0)
        self.table_fb = QTableWidget()
        self.table_fb.setColumnCount(6)
        self.table_fb.setHorizontalHeaderLabels(
            ['日期', '训练内容', '完成度', '学员状态', '教练评语', '下次建议']
        )
        self.table_fb.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_fb.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table_fb.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        for c in range(0, 6):
            if c not in (1, 4, 5):
                self.table_fb.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table_fb.setMinimumHeight(220)
        self.table_fb.setAlternatingRowColors(True)
        fl.addWidget(self.table_fb)
        sheet.add_section('阶段内课后反馈', fl, stretch=1)
        left_lay.addWidget(sheet, 1)  # 版面必须挂入布局，否则 _init_ui 返回即被 GC（use-after-free 崩溃）

        left_scroll.setWidget(left_content)
        main_lay.addWidget(left_scroll, 3)

        # ===== 右侧：辅助区 =====
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        right_content = QWidget()  # 透明背景由 TRAINING_QSS 全局规则提供
        right_lay = QVBoxLayout(right_content)
        right_lay.setSpacing(Spacing.CARD)
        right_lay.setContentsMargins(0, 0, 0, 0)

        self.hero_card = HeroCard('阶段概览', '—', '选择学员并生成总结')
        right_lay.addWidget(self.hero_card)

        # 统计卡竖排（v24：2x2 在 ~240px 窄栏里每张不足百像素太挤，1x4 全宽更从容）
        self.stat_lessons = StatCard(IconBox.CALENDAR, '阶段消课', '—', Palette.ACCENT)
        self.stat_feedback = StatCard(IconBox.CHART_BAR, '反馈条数', '—', Palette.ACCENT_BLUE)
        self.stat_score = StatCard(IconBox.CHART_LINE, '成绩变化', '—', Palette.GREEN)
        self.stat_remaining = StatCard(IconBox.ARCHIVE, '剩余课时', '—', Palette.ACCENT)
        for _stat in (self.stat_lessons, self.stat_feedback,
                      self.stat_score, self.stat_remaining):
            right_lay.addWidget(_stat)

        # 成绩变化分布柱状图
        chart_card = Card('项目得分变化')
        chart_lay = QVBoxLayout()
        chart_lay.setContentsMargins(0, 0, 0, 0)
        chart_lay.setSpacing(Spacing.SM)
        self.score_chart = BarChartWidget()
        chart_lay.addWidget(self.score_chart)
        chart_card.set_content_layout(chart_lay)
        right_lay.addWidget(chart_card)

        # 导出操作卡片
        export_card = Card('导出')
        el = QVBoxLayout()
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(Spacing.SM)
        export_hint = QLabel('生成阶段总结后，可导出为 Word 文档。')
        export_hint.setFont(Type.caption())
        export_hint.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        export_hint.setWordWrap(True)
        el.addWidget(export_hint)
        self.btn_export_word = QPushButton('导出 Word 总结', objectName='primary')
        self.btn_export_word.setCursor(Qt.PointingHandCursor)
        self.btn_export_word.setMinimumWidth(160)
        self.btn_export_word.clicked.connect(self.on_export_word)
        self.btn_export_word.setEnabled(False)
        el.addWidget(self.btn_export_word)
        export_card.set_content_layout(el)
        right_lay.addWidget(export_card)
        right_lay.addStretch()

        right_scroll.setWidget(right_content)
        right_scroll.setMaximumWidth(260)  # 大屏下右栏不过分拉宽，剩余宽度留给左内容
        main_lay.addWidget(right_scroll, 1)

    @staticmethod
    def _mk_sub_label(text: str) -> QLabel:
        """统一次文字标签样式。"""
        lbl = QLabel(text)
        lbl.setFont(Type.caption())
        lbl.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        return lbl

    def refresh_students(self):
        """刷新学员下拉列表。"""
        d = self._get_dir() or ''
        self.cb_student.clear()
        if not d or not os.path.isdir(d):
            return
        students = summary_processor.list_students_with_files(d)
        for s in students:
            self.cb_student.addItem(s['name'])

    def on_generate(self):
        """生成阶段总结。"""
        name = self.cb_student.currentText().strip()
        if not name:
            dialog.info(self, '提示', '请先选择学员')
            return
        d = self._get_dir() or ''
        if not d:
            dialog.warn(self, '提示', '档案目录未设置')
            return
        start = self.dte_start.date().toString('yyyy-MM-dd')
        end = self.dte_end.date().toString('yyyy-MM-dd')

        try:
            summary = summary_processor.build_stage_summary(d, name, start, end)
        except Exception as e:
            dialog.error(self, '生成失败', f'聚合数据出错：\n{e}')
            return

        self._summary = summary
        self._render_overview(summary)
        self._render_score(summary)
        self._render_feedback(summary)
        self._render_right_panel(summary)
        self.btn_export_word.setEnabled(True)

    def _render_overview(self, summary: dict):
        """渲染阶段概述文字。"""
        self.te_overview.setPlainText(summary_processor.suggest_summary(summary))

    def _render_score(self, summary: dict):
        """渲染成绩进步表。"""
        score = summary.get('score', {})
        self.table_score.setRowCount(0)
        if not score.get('has_score'):
            self.table_score.setRowCount(1)
            it = QTableWidgetItem('阶段内无成绩型测评记录')
            it.setTextAlignment(Qt.AlignCenter)
            it.setFlags(Qt.ItemIsEnabled)
            it.setForeground(QColor(Palette.TEXT_SUB))
            self.table_score.setSpan(0, 0, 1, 6)
            self.table_score.setItem(0, 0, it)
            return
        progress = score.get('progress', {})
        if not progress:
            self.table_score.setRowCount(1)
            it = QTableWidgetItem('阶段内成绩记录不足')
            it.setTextAlignment(Qt.AlignCenter)
            it.setFlags(Qt.ItemIsEnabled)
            it.setForeground(QColor(Palette.TEXT_SUB))
            self.table_score.setSpan(0, 0, 1, 6)
            self.table_score.setItem(0, 0, it)
            return
        items = sorted(progress.keys())
        self.table_score.setRowCount(len(items))
        for i, item in enumerate(items):
            p = progress[item]
            diff = p.get('score_diff')
            diff_text = ''
            diff_color = QColor(Palette.MUTED)
            if diff is not None:
                arrow = '↑' if diff > 0 else ('↓' if diff < 0 else '→')
                diff_text = f"{arrow} {abs(diff):.1f}"
                diff_color = QColor(Palette.GREEN) if diff > 0 else (
                    QColor(Palette.RED) if diff < 0 else QColor(Palette.MUTED))
            cells = [
                item,
                str(p.get('first_value', '')),
                str(p.get('first_score', '')),
                str(p.get('last_value', '')),
                str(p.get('last_score', '')),
                diff_text,
            ]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                if c == 5:
                    it.setForeground(diff_color)
                self.table_score.setItem(i, c, it)
        self.table_score.resizeRowsToContents()

    def _render_feedback(self, summary: dict):
        """渲染反馈历史表。"""
        feedback = summary.get('feedback', {})
        recent = feedback.get('recent', [])
        self.table_fb.setRowCount(0)
        if not recent:
            self.table_fb.setRowCount(1)
            it = QTableWidgetItem('阶段内暂无课后反馈记录')
            it.setTextAlignment(Qt.AlignCenter)
            it.setFlags(Qt.ItemIsEnabled)
            it.setForeground(QColor(Palette.TEXT_SUB))
            self.table_fb.setSpan(0, 0, 1, 6)
            self.table_fb.setItem(0, 0, it)
            return
        self.table_fb.setRowCount(len(recent))
        for i, h in enumerate(recent):
            cells = [
                str(h.get('date', '')),
                str(h.get('content', '')),
                f"{h.get('completion', 0)}%",
                str(h.get('state', '')),
                str(h.get('comment', '')),
                str(h.get('next', '')),
            ]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if c in (1, 4, 5):
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    it.setTextAlignment(Qt.AlignCenter)
                self.table_fb.setItem(i, c, it)
        self.table_fb.resizeRowsToContents()

    def _render_right_panel(self, summary: dict):
        """渲染右侧辅助区：概览卡片与图表。"""
        lessons = summary.get('lessons', {})
        feedback = summary.get('feedback', {})
        score = summary.get('score', {})
        name = summary.get('student_name', '')

        stage_count = lessons.get('stage_count', 0)
        remaining = lessons.get('remaining', 0)
        self.stat_lessons.set_value(f'{stage_count}')
        self.stat_lessons.setToolTip(f'阶段内消课 {stage_count} 课时')

        fb_count = feedback.get('count', 0)
        self.stat_feedback.set_value(f'{fb_count}')
        self.stat_feedback.setToolTip(f'阶段内反馈 {fb_count} 条')

        self.stat_remaining.set_value(f'{remaining}')
        self.stat_remaining.setToolTip(f'剩余 {remaining} 课时')

        # 成绩变化
        if score.get('has_score') and score.get('total_diff') is not None:
            diff = score['total_diff']
            arrow = '↑' if diff > 0 else ('↓' if diff < 0 else '→')
            self.stat_score.set_value(f'{arrow} {abs(diff):.1f}')
            diff_color = (Palette.GREEN if diff > 0 else
                          (Palette.RED if diff < 0 else Palette.MUTED))
            self.stat_score.icon.fg_color = diff_color
            self.stat_score.icon.bg_color = _fade_color(diff_color, 0.10)
            self.stat_score.icon.update()
            self.stat_score.setToolTip(f'总分变化 {arrow} {abs(diff):.1f}')
        else:
            self.stat_score.set_value('—')
            self.stat_score.setToolTip('无成绩数据')

        # Hero 卡片
        self.hero_card._value = f'{stage_count} 课时'
        self.hero_card._subtitle = name if name else '选择学员并生成总结'
        self.hero_card.update()

        # 项目得分变化柱状图（柱色用新令牌）
        chart_items = []
        if score.get('has_score') and score.get('progress'):
            for item, p in sorted(score['progress'].items()):
                diff = p.get('score_diff')
                if diff is None:
                    continue
                color = (Palette.GREEN if diff > 0 else
                         (Palette.RED if diff < 0 else Palette.MUTED))
                chart_items.append((item, abs(diff), color))
        self.score_chart.set_data(chart_items)

    def on_export_word(self):
        """导出阶段总结到 Word。"""
        if not self._summary:
            dialog.info(self, '提示', '请先生成阶段总结')
            return
        summary = self._summary
        name = summary.get('student_name', '学员')
        start = summary.get('start_date', '')
        end = summary.get('end_date', '')
        default_name = f"{name}_{start}_{end}_阶段总结.docx"
        default_dir = os.path.join(os.path.expanduser('~'), 'Desktop')
        path, _ = QFileDialog.getSaveFileName(
            self, '保存阶段总结', os.path.join(default_dir, default_name),
            'Word 文件 (*.docx)'
        )
        if not path:
            return
        if not path.lower().endswith('.docx'):
            path += '.docx'
        try:
            _export_summary_word(summary, path)
            dialog.info(self, '导出成功', f'已保存到：\n{path}')
        except Exception as e:
            dialog.error(self, '导出失败', f'{e}')

    def refresh(self):
        """外部切换到此 Tab 时调用，刷新学员列表。"""
        self.refresh_students()


def _fade_color(hex_color: str, alpha_ratio: float) -> str:
    """将十六进制颜色按 alpha 比例变淡，返回 #AARRGGBB 字符串。"""
    c = QColor(hex_color)
    r, g, b = c.red(), c.green(), c.blue()
    a = int(255 * alpha_ratio)
    return f'#{a:02x}{r:02x}{g:02x}{b:02x}'


# =============================================================================
# Word 导出（管理层职责，但因依赖 python-docx 且仅此一处使用，就近放置）
# =============================================================================
def _export_summary_word(summary: dict, path: str):
    """将阶段总结数据导出为 Word 文档。"""
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn

    doc = Document()
    # 页面设置
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)

    # 默认字体
    style = doc.styles['Normal']
    style.font.name = '微软雅黑'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    style.font.size = Pt(10.5)

    name = summary.get('student_name', '学员')
    start = summary.get('start_date', '')
    end = summary.get('end_date', '')
    generated = summary.get('generated_at', '')

    # 标题
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"{name}  阶段训练总结")
    run.font.name = '微软雅黑'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(18)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    # 基本信息
    p = doc.add_paragraph()
    p.add_run(f'阶段范围：').bold = True
    p.add_run(f'{start} ~ {end}')
    p = doc.add_paragraph()
    p.add_run(f'生成时间：').bold = True
    p.add_run(generated)

    # 概述
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run('阶段概述：').bold = True
    p.add_run(summary_processor.suggest_summary(summary))

    # 课时统计
    doc.add_paragraph()
    h = doc.add_paragraph()
    hr = h.add_run('一、课时统计')
    hr.font.bold = True
    hr.font.size = Pt(13)
    hr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    lessons = summary.get('lessons', {})
    lesson_data = [
        ('总课时', str(lessons.get('total', 0))),
        ('累计已上', str(lessons.get('attended_total', 0))),
        ('剩余课时', str(lessons.get('remaining', 0))),
        ('本阶段消课', f"{lessons.get('stage_count', 0)} 课时"),
        ('最近上课', str(lessons.get('last_date', '—'))),
    ]
    t = doc.add_table(rows=len(lesson_data), cols=2)
    t.style = 'Light Grid Accent 1'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(lesson_data):
        c1 = t.cell(i, 0); c1.text = k
        c2 = t.cell(i, 1); c2.text = v
        for cell in (c1, c2):
            for para in cell.paragraphs:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in para.runs:
                    r.font.name = '微软雅黑'
                    r.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
                    r.font.size = Pt(10.5)
        for r in c1.paragraphs[0].runs:
            r.font.bold = True

    # 训练反馈
    doc.add_paragraph()
    h = doc.add_paragraph()
    hr = h.add_run('二、训练反馈')
    hr.font.bold = True
    hr.font.size = Pt(13)
    hr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    feedback = summary.get('feedback', {})
    p = doc.add_paragraph()
    p.add_run(f'阶段内反馈条数：').bold = True
    p.add_run(f"{feedback.get('count', 0)} 条")
    p = doc.add_paragraph()
    p.add_run(f'平均完成度：').bold = True
    p.add_run(f"{feedback.get('avg_completion', 0)}%")

    comments = feedback.get('comments', [])
    if comments:
        p = doc.add_paragraph()
        p.add_run('教练评语节选：').bold = True
        for c in comments[:5]:
            doc.add_paragraph(c, style='List Bullet')

    # 成绩进步
    doc.add_paragraph()
    h = doc.add_paragraph()
    hr = h.add_run('三、成绩进步对比')
    hr.font.bold = True
    hr.font.size = Pt(13)
    hr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    score = summary.get('score', {})
    if not score.get('has_score'):
        doc.add_paragraph('（阶段内无成绩型测评记录）')
    elif not score.get('progress'):
        doc.add_paragraph('（阶段内成绩记录不足，无法对比）')
    else:
        progress = score.get('progress', {})
        # 总分变化
        if score.get('total_diff') is not None:
            diff = score['total_diff']
            arrow = '提升' if diff > 0 else ('下降' if diff < 0 else '持平')
            p = doc.add_paragraph()
            p.add_run(f'总分变化：').bold = True
            p.add_run(f"{arrow} {abs(diff):.1f} 分"
                      f"（{score.get('total_first')} → {score.get('total_last')}）")
        # 明细表
        items = sorted(progress.keys())
        t = doc.add_table(rows=len(items) + 1, cols=6)
        t.style = 'Light Grid Accent 1'
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ['项目', '首次成绩', '首次得分', '末次成绩', '末次得分', '得分变化']
        for ci, h in enumerate(headers):
            cell = t.cell(0, ci)
            cell.text = h
            for para in cell.paragraphs:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in para.runs:
                    r.font.name = '微软雅黑'
                    r.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
                    r.font.size = Pt(10.5)
                    r.font.bold = True
        for ri, item in enumerate(items, 1):
            p = progress[item]
            diff = p.get('score_diff')
            if diff is None:
                diff_text = '—'
            else:
                arrow = '↑' if diff > 0 else ('↓' if diff < 0 else '→')
                diff_text = f"{arrow} {abs(diff):.1f}"
            cells = [
                item,
                str(p.get('first_value', '')),
                str(p.get('first_score', '')),
                str(p.get('last_value', '')),
                str(p.get('last_score', '')),
                diff_text,
            ]
            for ci, v in enumerate(cells):
                cell = t.cell(ri, ci)
                cell.text = v
                for para in cell.paragraphs:
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for r in para.runs:
                        r.font.name = '微软雅黑'
                        r.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
                        r.font.size = Pt(10.5)

    # 反馈明细表
    doc.add_paragraph()
    h = doc.add_paragraph()
    hr = h.add_run('四、阶段内课后反馈明细')
    hr.font.bold = True
    hr.font.size = Pt(13)
    hr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)
    recent = feedback.get('recent', [])
    if not recent:
        doc.add_paragraph('（暂无反馈记录）')
    else:
        headers = ['日期', '训练内容', '完成度', '学员状态', '教练评语', '下次建议']
        t = doc.add_table(rows=len(recent) + 1, cols=6)
        t.style = 'Light Grid Accent 1'
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for ci, h in enumerate(headers):
            cell = t.cell(0, ci)
            cell.text = h
            for para in cell.paragraphs:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in para.runs:
                    r.font.name = '微软雅黑'
                    r.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
                    r.font.size = Pt(10.5)
                    r.font.bold = True
        for ri, h in enumerate(recent, 1):
            cells = [
                str(h.get('date', '')),
                str(h.get('content', '')),
                f"{h.get('completion', 0)}%",
                str(h.get('state', '')),
                str(h.get('comment', '')),
                str(h.get('next', '')),
            ]
            for ci, v in enumerate(cells):
                cell = t.cell(ri, ci)
                cell.text = v
                for para in cell.paragraphs:
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER if ci != 4 else WD_ALIGN_PARAGRAPH.LEFT
                    for r in para.runs:
                        r.font.name = '微软雅黑'
                        r.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
                        r.font.size = Pt(10)

    # 落款
    doc.add_paragraph()
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.add_run(f'教练签字：________________     日期：{generated[:10]}')

    doc.save(path)
