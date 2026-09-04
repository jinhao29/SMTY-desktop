# -*- coding: utf-8 -*-
"""UI 层：周训练计划编辑（灰白简约 · 蓝紫强调，对齐图2）。

职责：
- 周计划表界面交互
- 每日训练明细编辑（准备/教学/结束）
- 智能推荐：委托 plan_coordinator 完成一周教案填充

布局：Card 组织表单与表格，主区域可滚动占满中列。
顶部导航由 main.py 统一提供，本页不重复渲染。
#training_root 作用域 QSS 由外层根 widget 向下级联，本页无需自带样式表。
"""
import modern_dialog as dialog
import os
import logging
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
    QMessageBox, QDateEdit, QFrame, QScrollArea, QGridLayout, QSpinBox
)
from task_model import WeeklyPlan
import summary_processor
import plan_coordinator

# 新设计语言令牌与组件
from styles import Palette, Type, Spacing, Radius
from cards import Card, Tag


class WeeklyTab(QWidget):
    """周计划编辑（灰白卡片式）。"""

    AGE_GROUPS = ['4-6岁', '7-9岁', '10-12岁', '13-15岁', '中考']

    def __init__(self, archive_dir_getter=None, parent=None):
        super().__init__(parent)
        # 档案目录回调（用于读取学员列表填充下拉框）
        self._get_dir = archive_dir_getter or (lambda: '')
        self._days = plan_coordinator.make_default_week_days()
        self._loading_detail = False  # 防止明细编辑区反向触发死循环
        self._init_ui()
        # 初始化时填充本周日期
        self._on_start_date_changed(self.dte_start.date())
        self._refresh_table()
        # 默认选中第一行加载明细
        if self.table.rowCount() > 0:
            self.table.setCurrentCell(0, 0)
            self._load_detail_to_editor(0)

    def _init_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setSpacing(Spacing.CARD)
        main_lay.setContentsMargins(0, 0, 0, 0)

        mid_scroll = QScrollArea()
        mid_scroll.setWidgetResizable(True)
        mid_scroll.setFrameShape(QFrame.NoFrame)
        mid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        mid_scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        mid_content = QWidget()
        mid_content.setStyleSheet('background: transparent;')
        mid_lay = QVBoxLayout(mid_content)
        mid_lay.setSpacing(Spacing.CARD)
        mid_lay.setContentsMargins(0, 0, 0, 0)

        # ---------- 基本信息卡 ----------
        info_card = Card('基本信息')
        gl = QGridLayout()
        gl.setHorizontalSpacing(20)
        gl.setVerticalSpacing(12)
        gl.setContentsMargins(0, 0, 0, 0)
        self.cb_name = QComboBox()
        self.cb_name.setEditable(True)
        self.cb_name.setPlaceholderText('学员姓名（可下拉选择或手动输入）')
        self.le_coach = QLineEdit(placeholderText='教练姓名')
        self.dte_start = QDateEdit(QDate.currentDate())
        self.dte_start.setCalendarPopup(True)
        self.dte_start.setDisplayFormat('yyyy-MM-dd')
        # 日期变化时自动生成一周日期
        self.dte_start.dateChanged.connect(self._on_start_date_changed)
        self.le_goal = QLineEdit(placeholderText='如 提升耐力与速度')
        # 年龄段下拉框（分龄教案核心字段）
        self.cb_age = QComboBox()
        self.cb_age.addItems([''] + self.AGE_GROUPS)
        self.cb_age.setCurrentIndex(0)
        gl.addWidget(self._mk_sub_label('姓名'), 0, 0)
        gl.addWidget(self.cb_name, 0, 1)
        gl.addWidget(self._mk_sub_label('教练'), 0, 2)
        gl.addWidget(self.le_coach, 0, 3)
        gl.addWidget(self._mk_sub_label('年龄段'), 1, 0)
        gl.addWidget(self.cb_age, 1, 1)
        gl.addWidget(self._mk_sub_label('本周起始(周一)'), 1, 2)
        gl.addWidget(self.dte_start, 1, 3)
        gl.addWidget(self._mk_sub_label('本周目标'), 2, 0)
        gl.addWidget(self.le_goal, 2, 1, 1, 2)
        # 智能推荐按钮
        self.btn_recommend = QPushButton('智能推荐', objectName='recommend')
        self.btn_recommend.setToolTip('根据学员年龄自动匹配对应年龄段教案，推荐一周训练计划（可在此基础上自定义）')
        self.btn_recommend.setMinimumWidth(120)
        self.btn_recommend.setCursor(Qt.PointingHandCursor)
        self.btn_recommend.clicked.connect(self.on_recommend_weekly)
        gl.addWidget(self.btn_recommend, 2, 3)
        gl.setColumnStretch(1, 1); gl.setColumnStretch(3, 2)
        info_card.set_content_layout(gl)
        mid_lay.addWidget(info_card)

        # ---------- 周计划概览表卡 ----------
        week_card = Card('周训练计划')
        tl = QVBoxLayout()
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(Spacing.SM)
        hint = QLabel('双击单元格编辑 · 日期根据起始自动生成')
        hint.setFont(Type.caption())
        hint.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        tl.addWidget(hint)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ['星期', '日期', '训练主题', '核心内容', '强度', '时长(min)', '备注']
        )
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(240)
        self.table.setAlternatingRowColors(True)
        # 选中行变化时加载明细到编辑区
        self.table.itemSelectionChanged.connect(self._on_row_changed)
        tl.addWidget(self.table)
        week_card.set_content_layout(tl)
        mid_lay.addWidget(week_card)

        # ---------- 每日训练明细编辑卡 ----------
        detail_card = Card('每日训练明细（准备 / 教学 / 结束）')
        dl = QGridLayout()
        dl.setHorizontalSpacing(20)
        dl.setVerticalSpacing(10)
        dl.setContentsMargins(0, 0, 0, 0)
        self.lbl_detail_title = QLabel('请选择上方表格中的某一天')
        self.lbl_detail_title.setFont(Type.card_title())
        self.lbl_detail_title.setStyleSheet(
            f'color: {Palette.ACCENT}; background: {Palette.ACCENT_LIGHT}; '
            f'padding: 8px 12px; border-radius: {Radius.TAG}px;'
        )
        dl.addWidget(self.lbl_detail_title, 0, 0, 1, 4)
        # 当日训练目标
        self.le_daily_goal = QLineEdit(placeholderText='当日核心内容/训练目标（如 下肢力量+核心力量+协调能力）')
        self.le_daily_goal.textChanged.connect(self._on_detail_changed)
        dl.addWidget(self._mk_sub_label('核心内容'), 1, 0)
        dl.addWidget(self.le_daily_goal, 1, 1, 1, 3)
        # 时长 + 器材
        self.spn_duration = QSpinBox()
        self.spn_duration.setRange(0, 240)
        self.spn_duration.setValue(60)
        self.spn_duration.setSuffix(' 分钟')
        self.spn_duration.valueChanged.connect(self._on_detail_changed)
        self.le_equipment = QLineEdit(placeholderText='当日器材（如 绳梯1个、垫子1个、标志桶2个）')
        self.le_equipment.textChanged.connect(self._on_detail_changed)
        dl.addWidget(self._mk_sub_label('训练时长'), 2, 0)
        dl.addWidget(self.spn_duration, 2, 1)
        dl.addWidget(self._mk_sub_label('器材'), 2, 2)
        dl.addWidget(self.le_equipment, 2, 3)
        # 准备部分
        dl.addWidget(self._mk_sub_label('准备部分'), 3, 0, 1, 4)
        self.te_warmup = QTextEdit(placeholderText='热身+拉伸动作（如 1.娃娃蹲 2.提踵走 3.双腿轻跳 4.体前屈 5.蝴蝶飞）')
        self.te_warmup.setMaximumHeight(80)
        self.te_warmup.textChanged.connect(self._on_detail_changed)
        dl.addWidget(self.te_warmup, 4, 0, 1, 4)
        # 教学部分
        dl.addWidget(self._mk_sub_label('教学部分（每行一个类别，如 绳梯类/垫上类/敏捷圈类）'), 5, 0, 1, 4)
        self.te_main = QTextEdit(placeholderText='绳梯类 目的:协调能力+节奏感\n1.双腿开合跳 2.双腿连续跳 3.双腿左右跳\n各2-4组\n---\n垫上类 目的:核心力量+支撑能力\n1.直臂支撑 2.卷腹 3.摇篮滚\n各2-4组')
        self.te_main.setMaximumHeight(140)
        self.te_main.textChanged.connect(self._on_detail_changed)
        dl.addWidget(self.te_main, 6, 0, 1, 4)
        # 结束部分
        dl.addWidget(self._mk_sub_label('结束部分'), 7, 0, 1, 4)
        self.te_cooldown = QTextEdit(placeholderText='结束拉伸动作（如 1.体前屈 2.蛙式 3.侧压腿 4.小海豹）')
        self.te_cooldown.setMaximumHeight(80)
        self.te_cooldown.textChanged.connect(self._on_detail_changed)
        dl.addWidget(self.te_cooldown, 8, 0, 1, 4)
        dl.setColumnStretch(1, 2); dl.setColumnStretch(3, 2)
        detail_card.set_content_layout(dl)
        mid_lay.addWidget(detail_card, 1)

        # ---------- 教练寄语卡 ----------
        note_card = Card('教练寄语')
        nl = QVBoxLayout()
        nl.setContentsMargins(0, 0, 0, 0)
        self.te_coach_note = QTextEdit(placeholderText='给家长的寄语（如 请家长督促学员按时完成训练，注意训练安全）')
        self.te_coach_note.setMaximumHeight(80)
        nl.addWidget(self.te_coach_note)
        note_card.set_content_layout(nl)
        mid_lay.addWidget(note_card)

        mid_scroll.setWidget(mid_content)
        main_lay.addWidget(mid_scroll, 1)

    @staticmethod
    def _mk_sub_label(text: str) -> QLabel:
        """统一次文字标签样式（灰底无）。"""
        lbl = QLabel(text)
        lbl.setFont(Type.caption())
        lbl.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        return lbl

    def _update_right_panel(self):
        """刷新右侧概览卡片与图表数据（右侧辅助区已移除，保留空实现以兼容现有调用）。"""
        pass

    def _on_start_date_changed(self, new_date):
        """起始日期变化时，自动定位到当周周一并填充 7 天日期。"""
        if not new_date or not new_date.isValid():
            return
        day_of_week = new_date.dayOfWeek()  # 1=Mon, 7=Sun
        monday = new_date.addDays(-(day_of_week - 1))
        if day_of_week != 1:
            self.dte_start.blockSignals(True)
            self.dte_start.setDate(monday)
            self.dte_start.blockSignals(False)
        for i, day in enumerate(self._days):
            d = monday.addDays(i)
            day.date = d.toString('yyyy-MM-dd')
        if hasattr(self, 'table') and self.table.rowCount() > 0:
            self._sync_table_to_days()
            for i, day in enumerate(self._days):
                if i < self.table.rowCount():
                    item = self.table.item(i, 1)
                    if item:
                        item.setText(day.date)
                    else:
                        new_item = QTableWidgetItem(day.date)
                        new_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        self.table.setItem(i, 1, new_item)
        self._update_right_panel()

    def _sync_table_to_days(self):
        """将当前表格编辑内容同步回 _days。"""
        for i, day in enumerate(self._days):
            if i >= self.table.rowCount():
                break
            item_theme = self.table.item(i, 2)
            item_goal = self.table.item(i, 3)
            item_intensity = self.table.item(i, 4)
            item_duration = self.table.item(i, 5)
            item_note = self.table.item(i, 6)
            if item_theme:
                day.theme = item_theme.text()
            if item_goal:
                day.key_tasks = item_goal.text()
            if item_intensity:
                day.intensity = item_intensity.text()
            if item_duration:
                try:
                    day.duration_min = int(item_duration.text()) if item_duration.text() else 0
                except ValueError:
                    pass
            if item_note:
                day.note = item_note.text()
        self._update_right_panel()

    def _refresh_table(self):
        self.table.setRowCount(len(self._days))
        for i, day in enumerate(self._days):
            items = [
                QTableWidgetItem(day.weekday),
                QTableWidgetItem(day.date),
                QTableWidgetItem(day.theme),
                QTableWidgetItem(day.key_tasks),
                QTableWidgetItem(day.intensity),
                QTableWidgetItem(str(day.duration_min) if day.duration_min else ''),
                QTableWidgetItem(day.note),
            ]
            for j, it in enumerate(items):
                if j != 0:
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    it.setTextAlignment(Qt.AlignCenter)
                    it.setFlags(Qt.ItemIsEnabled)
                    # 星期列用强调色
                    it.setForeground(QColor(Palette.ACCENT))
                self.table.setItem(i, j, it)
        self.table.resizeRowsToContents()
        self._update_right_panel()

    def _on_row_changed(self):
        """表格选中行变化时，加载该日的明细到编辑区。"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self._days):
            return
        self._load_detail_to_editor(row)

    def _load_detail_to_editor(self, row: int):
        """加载指定行的明细到编辑区。"""
        if row < 0 or row >= len(self._days):
            return
        self._loading_detail = True
        try:
            day = self._days[row]
            self.lbl_detail_title.setText(f'当前编辑：{day.weekday} {day.date}  -  {day.theme or "训练课"}')
            self.le_daily_goal.setText(day.daily_goal)
            self.spn_duration.setValue(day.duration_min if day.duration_min else 0)
            self.le_equipment.setText(day.equipment)
            self.te_warmup.setPlainText(day.warmup)
            self.te_main.setPlainText(day.main_content)
            self.te_cooldown.setPlainText(day.cooldown)
        finally:
            self._loading_detail = False

    def _on_detail_changed(self):
        """明细编辑区内容变化时，同步回当前选中行的 _days。"""
        if self._loading_detail:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self._days):
            return
        day = self._days[row]
        day.daily_goal = self.le_daily_goal.text().strip()
        day.duration_min = self.spn_duration.value()
        day.equipment = self.le_equipment.text().strip()
        day.warmup = self.te_warmup.toPlainText().strip()
        day.main_content = self.te_main.toPlainText().strip()
        day.cooldown = self.te_cooldown.toPlainText().strip()
        # 同步时长到表格
        dur_item = self.table.item(row, 5)
        if dur_item:
            dur_item.setText(str(day.duration_min) if day.duration_min else '')
        self._update_right_panel()

    def collect_plan(self):
        self._sync_table_to_days()
        # 日期列由起始日期统一生成
        monday = self.dte_start.date()
        for i, day in enumerate(self._days):
            day.date = monday.addDays(i).toString('yyyy-MM-dd')
        # 年龄段
        age_group = self.cb_age.currentText().strip()
        # 教练寄语
        coach_note = self.te_coach_note.toPlainText().strip()
        return WeeklyPlan(
            student_name=self.cb_name.currentText().strip(),
            coach=self.le_coach.text().strip(),
            week_start=monday.toString('yyyy-MM-dd'),
            goal=self.le_goal.text().strip(),
            days=self._days,
            age_group=age_group,
            coach_note=coach_note,
        )

    def refresh_students(self):
        """从档案目录刷新学员下拉列表（保留当前输入文本）。"""
        if not hasattr(self, 'cb_name'):
            return
        cur = self.cb_name.currentText()
        self.cb_name.blockSignals(True)
        self.cb_name.clear()
        d = self._get_dir() or ''
        if d and os.path.isdir(d):
            try:
                students = summary_processor.list_students_with_files(d)
                for s in students:
                    self.cb_name.addItem(s['name'])
            except Exception:
                logging.exception('加载学员列表失败')
        if cur:
            self.cb_name.setEditText(cur)
        self.cb_name.blockSignals(False)

    def on_recommend_weekly(self):
        """智能推荐：根据学员年龄自动匹配教案并填充一周训练计划（委托 plan_coordinator）。"""
        name = self.cb_name.currentText().strip()
        archive_dir = self._get_dir() or ''
        result = plan_coordinator.recommend_weekly_plan(name, archive_dir, days=7)
        if not result.get('ok'):
            dialog.warn(self, '提示', result.get('reason', '推荐失败'))
            return

        age = result['age']
        age_group = result['age_group']
        week_lessons = result['week_lessons']

        # 同步年龄段下拉框
        ag_idx = self.cb_age.findText(age_group)
        if ag_idx >= 0:
            self.cb_age.setCurrentIndex(ag_idx)

        # 先同步当前表格编辑到 _days，避免丢失用户已编辑的内容
        self._sync_table_to_days()
        # 委托 plan_coordinator 填充一周
        plan_coordinator.apply_weekly_lessons_to_days(self._days, week_lessons)

        # 6. 刷新表格与明细编辑区
        self._refresh_table()
        if self.table.rowCount() > 0:
            self.table.setCurrentCell(0, 0)
            self._load_detail_to_editor(0)
        dialog.info(
            self, '推荐成功',
            f'已为学员「{name}」（{age}岁 / {age_group}）填充一周训练计划：\n'
            f'共 {len(week_lessons)} 节教案循环填充 7 天\n'
            f'周日默认设为休息日\n\n'
            f'可在此基础上自由修改每日训练内容。'
        )
