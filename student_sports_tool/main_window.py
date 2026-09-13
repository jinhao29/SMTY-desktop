# -*- coding: utf-8 -*-
"""UI 层：学员体测档案管理主窗口（UI 外壳）。

职责：
- 构建 UI 控件、布局、信号槽连接
- 路由用户交互到 archive_controller
- 维护 UI 状态（评分中标志、加载中标志、当前目录）

M3-S4 拆分后业务逻辑迁移至 archive_controller.py，
本文件仅保留 UI 创建与事件路由。
"""
import modern_dialog as dialog
import os
import logging
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor, QIntValidator
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QRadioButton, QButtonGroup,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
    QMessageBox, QFileDialog, QDateEdit, QFrame, QScrollArea, QSizePolicy,
    QDialog, QFormLayout, QSpinBox
)

from standards import (get_primary_standards, get_zhongkao_standards,
                       get_standards_by_grade, SCORE_TYPES)
from scorer import calc_score, format_value
from ui_components import (
    ColorPalette, FontHelper, FormSheet, StatCard, IconBox
)
import archive_controller as ac
import lesson_manager as lm
from lesson_window import LessonWindow

DEFAULT_DIR = os.path.join(os.path.expanduser('~'), 'Desktop', '学员档案')

_feedback_storage_cache = None


def feedback_storage():
    """按需加载 training_tool/feedback_storage（该模块按顶层名导入，需先补 path）。

    批 1 接线：feedback_storage 此前从未被 UI 调用过。
    """
    global _feedback_storage_cache
    if _feedback_storage_cache is None:
        import sys
        _tt = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'training_tool')
        if _tt not in sys.path:
            sys.path.insert(0, _tt)
        import feedback_storage as _mod
        _feedback_storage_cache = _mod
    return _feedback_storage_cache


class LessonFeedbackDialog(QDialog):
    """课后反馈录入（7 字段）。

    批 1 接线：把 training_tool/feedback_storage 接到 UI —— 该模块此前只有定义与导出，
    全项目没有任何 UI 调用。落盘到档案目录下「课堂反馈.xlsx」，与「课时记录.xlsx」
    各自成文件、互不干扰（已由 _verify_b1_wiring.py 验证）。

    字段映射（D3：只做映射，不统一字段）；文档见
    docs/reports/feedback_field_mapping.md（本地文档，未入库）：

        PC「课堂反馈.xlsx」    Android Lesson
        ------------------    ------------------
        日期                  date
        学员                  studentName
        训练内容              content（PC 纯文本 / Android 结构化 JSON）
        完成度(%)             无直映（Android 用 performance 1-10 + summary）
        学员状态              attitude（两端预设项一致）
        教练评语              coachComment
        下次课建议            nextGoal
    """

    #: 与 Android 端「训练态度」快捷项对齐（LessonScreen.kt quickAttitudes）
    STATES = ['认真', '专注', '积极', '一般', '需努力', '散漫', '分心', '懒散']

    def __init__(self, dir_path, students, default_name='', parent=None):
        super().__init__(parent)
        self.setWindowTitle('课后反馈')
        self.resize(600, 680)
        self._dir_path = dir_path
        self._init_ui(students, default_name)
        self._reload_history()

    def _init_ui(self, students, default_name):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(18, 18, 18, 18)

        form = QFormLayout()
        form.setSpacing(10)

        self.cb_name = QComboBox()
        self.cb_name.addItems(students)
        if default_name and default_name in students:
            self.cb_name.setCurrentText(default_name)
        self.cb_name.currentIndexChanged.connect(self._reload_history)

        self.dte = QDateEdit(QDate.currentDate())
        self.dte.setCalendarPopup(True)
        self.dte.setDisplayFormat('yyyy-MM-dd')

        self.le_content = QLineEdit(placeholderText='如：体能训练、跳绳强化...')

        self.sb_completion = QSpinBox()
        self.sb_completion.setRange(0, 100)
        self.sb_completion.setValue(100)
        self.sb_completion.setSuffix(' %')

        self.cb_state = QComboBox()
        self.cb_state.setEditable(True)          # 允许自由输入，不锁死枚举
        self.cb_state.addItems(self.STATES)
        self.cb_state.setCurrentText('认真')

        self.te_comment = QTextEdit()
        self.te_comment.setPlaceholderText('教练评语（写给家长，可多行）')
        self.te_comment.setFixedHeight(90)

        self.te_next = QTextEdit()
        self.te_next.setPlaceholderText('下次课建议')
        self.te_next.setFixedHeight(70)

        form.addRow('学员：', self.cb_name)
        form.addRow('日期：', self.dte)
        form.addRow('训练内容：', self.le_content)
        form.addRow('完成度：', self.sb_completion)
        form.addRow('学员状态：', self.cb_state)
        form.addRow('教练评语：', self.te_comment)
        form.addRow('下次课建议：', self.te_next)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        btn_close = QPushButton('关闭', objectName='secondary')
        btn_close.clicked.connect(self.reject)
        self.btn_save = QPushButton('保存反馈', objectName='primary')
        self.btn_save.clicked.connect(self.on_save)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        btn_row.addWidget(self.btn_save)
        lay.addLayout(btn_row)

        lay.addWidget(QLabel('最近反馈（回读自「课堂反馈.xlsx」）'))
        self.te_history = QTextEdit()
        self.te_history.setReadOnly(True)
        self.te_history.setFixedHeight(160)
        lay.addWidget(self.te_history)

    def _reload_history(self):
        """按当前学员回读最近反馈，验证「保存 → 回读」闭环。"""
        name = self.cb_name.currentText().strip()
        if not name:
            self.te_history.setPlainText('')
            return
        try:
            rows = feedback_storage().get_feedback_history(self._dir_path, name, limit=8)
        except Exception as e:                    # 文件损坏/被占用不应打断录入
            self.te_history.setPlainText(f'读取失败：{e}')
            return
        if not rows:
            self.te_history.setPlainText('（暂无反馈记录）')
            return
        blocks = [
            f"{r['date']}  完成度 {r['completion']}%  {r['state']}\n"
            f"  内容：{r['content']}\n"
            f"  评语：{r['comment']}\n"
            f"  下次：{r['next']}"
            for r in rows
        ]
        self.te_history.setPlainText('\n\n'.join(blocks))

    def on_save(self):
        """保存反馈（调用既有 feedback_storage.save_feedback，不新写存储逻辑）。"""
        name = self.cb_name.currentText().strip()
        if not name:
            dialog.warn(self, '提示', '请选择学员')
            return
        try:
            ok = feedback_storage().save_feedback(
                self._dir_path, name,
                self.le_content.text().strip(),
                self.sb_completion.value(),
                self.cb_state.currentText().strip(),
                self.te_comment.toPlainText().strip(),
                self.te_next.toPlainText().strip(),
                self.dte.date().toString('yyyy-MM-dd'),
            )
        except Exception as e:
            dialog.error(self, '保存失败', str(e))
            return
        if ok:
            dialog.info(self, '保存成功', f'已写入 {name} 的课后反馈')
            self.te_comment.clear()
            self.te_next.clear()
            self._reload_history()
        else:
            dialog.warn(self, '保存失败', '反馈未写入')


class MainWindow(QMainWindow):
    """学员体测档案管理主窗口。"""

    def __init__(self, initial_dir: str = None):
        super().__init__()
        self.setWindowTitle('学员体测档案管理工具')
        self.resize(1100, 820)
        self._cur_stds = []          # 当前标准列表
        self._scoring = False        # 评分中标志，防止递归
        # v23.12：支持启动模式指定档案目录（俱乐部模式 = 独立目录，物理隔离）
        self._dir_path = initial_dir or DEFAULT_DIR  # 档案目录
        self._loading_meta = False    # 加载已有学员信息时屏蔽响应
        self._init_ui()
        self.on_type_changed(0)
        self.refresh_students()

    def get_current_directory(self):
        """公开 getter：返回当前档案目录，替代外部直接访问 _dir_path。"""
        return self._dir_path

    #==== UI 构建 ====

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QHBoxLayout(central)
        main_lay.setSpacing(22)
        main_lay.setContentsMargins(20, 20, 20, 20)

        mid_scroll = QScrollArea()
        mid_scroll.setWidgetResizable(True)
        mid_scroll.setFrameShape(QFrame.NoFrame)
        mid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        mid_content = QWidget()
        mid_lay = QVBoxLayout(mid_content)
        mid_lay.setSpacing(22)
        mid_lay.setContentsMargins(0, 0, 0, 0)

        # 顶部标题栏 + Mini Stats 胶囊状态栏（替代原 2x2 统计方块）
        header_row = QHBoxLayout()
        header_row.setSpacing(14)
        header_row.setContentsMargins(0, 0, 0, 0)
        header = QLabel('学员体测档案管理')
        header.setFont(FontHelper.title())
        header.setStyleSheet(f'color: {ColorPalette.TEXT}; background: transparent;')
        header_row.addWidget(header)
        header_row.addStretch()
        # Mini Stats 胶囊：低调小字，放在标题右侧
        _pill_qss = (f'background: {ColorPalette.CARD}; color: {ColorPalette.TEXT_SECONDARY};'
                     f'border: 1px solid {ColorPalette.BORDER}; border-radius: 12px;'
                     f'padding: 4px 12px; font-size: 12px;')
        self.stat_count = QLabel('测评次数 —')
        self.stat_count.setStyleSheet(_pill_qss)
        self.stat_total = QLabel('最新综合分 —')
        self.stat_total.setStyleSheet(_pill_qss)
        self.stat_avg = QLabel('平均分 —')
        self.stat_avg.setStyleSheet(_pill_qss)
        self.stat_lesson = QLabel('剩余课时 —')
        self.stat_lesson.setStyleSheet(_pill_qss)
        for _pill in (self.stat_count, self.stat_total, self.stat_avg, self.stat_lesson):
            header_row.addWidget(_pill)
        mid_lay.addLayout(header_row)

        # 连续版面（v25：单张白纸，区块用小节标题+分隔线分节，替代多卡框套框）
        sheet = FormSheet()

        # --- 学员与目录 ---
        info_lay = QVBoxLayout()
        info_lay.setSpacing(10)
        info_lay.setContentsMargins(0, 0, 0, 0)
        # 第一行：档案目录
        dir_row = QHBoxLayout()
        dir_row.setSpacing(10)
        dir_row.addWidget(QLabel('目录'))
        self.le_dir = QLineEdit(self._dir_path)
        dir_row.addWidget(self.le_dir, 1)
        self.btn_dir_browse = QPushButton('浏览', objectName='secondary')
        self.btn_dir_browse.clicked.connect(self.on_dir_browse)
        dir_row.addWidget(self.btn_dir_browse)
        self.btn_refresh = QPushButton('刷新学员', objectName='secondary')
        self.btn_refresh.clicked.connect(lambda: self.refresh_students())
        dir_row.addWidget(self.btn_refresh)
        info_lay.addLayout(dir_row)
        # 第二行：学员选择
        stu_row = QHBoxLayout()
        stu_row.setSpacing(10)
        stu_row.addWidget(QLabel('学员'))
        self.cb_student = QComboBox()
        self.cb_student.currentIndexChanged.connect(self.on_student_selected)
        stu_row.addWidget(self.cb_student, 1)
        self.lbl_history = QLabel('（请选择或新建学员）')
        self.lbl_history.setStyleSheet(f'color: {ColorPalette.TEXT_SECONDARY};')
        stu_row.addWidget(self.lbl_history, 2)
        info_lay.addLayout(stu_row)
        sheet.add_section('学员与目录', info_lay)

        # 基本信息卡（v24：双列网格，10 字段 5 行放下，避免单列过长滚动疲劳）
        form = QGridLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        form.setContentsMargins(0, 0, 0, 0)
        self.le_name = QLineEdit(placeholderText='学员姓名')
        self.le_age = QLineEdit(placeholderText='如 7（7岁以下不显示年级）')
        self.le_age.setValidator(QIntValidator(1, 99))
        self.le_school = QLineEdit(placeholderText='学校（选填）')
        self.le_phone = QLineEdit(placeholderText='联系电话（选填）')
        self.le_total_lessons = QLineEdit(placeholderText='如 20（留空=不修改）')
        self.dte_date = QDateEdit(QDate.currentDate())
        self.dte_date.setCalendarPopup(True)
        self.dte_date.setDisplayFormat('yyyy-MM-dd')
        # 批 1（操作摩擦修复）：原「本次课时数 / 本次训练内容」两个 inline 输入框已移除。
        # 改为接线既有实现：LessonWindow（5 字段上课记录）+ feedback_storage（7 字段课后反馈）。
        # 职责分离——保存测评（on_save）不再顺带记课时，上课记录走独立入口。
        self.btn_record_lesson = QPushButton('记录一次上课', objectName='secondary')
        self.btn_record_lesson.clicked.connect(self.on_record_lesson)
        self.btn_record_feedback = QPushButton('填写课后反馈', objectName='secondary')
        self.btn_record_feedback.clicked.connect(self.on_record_feedback)
        self.rb_boy = QRadioButton('男')
        self.rb_girl = QRadioButton('女')
        self.rb_boy.setChecked(True)
        bg_sex = QButtonGroup(self)
        bg_sex.addButton(self.rb_boy)
        bg_sex.addButton(self.rb_girl)
        sex_w = QWidget()
        sex_w.setObjectName('sexRow')  # 全局 QWidget 有灰底，白版面上需透明（裸声明会下压后代，必须限定）
        sex_w.setStyleSheet('QWidget#sexRow { background: transparent; }')
        sex_lay = QHBoxLayout(sex_w)
        sex_lay.setContentsMargins(0, 0, 0, 0)
        sex_lay.setSpacing(14)
        sex_lay.addWidget(self.rb_boy)
        sex_lay.addWidget(self.rb_girl)
        self.cb_type = QComboBox()
        for name, *_ in ac.TYPE_OPTIONS:
            self.cb_type.addItem(name)
        self.cb_type.currentIndexChanged.connect(self.on_type_changed)
        # 左列 label 列 0/2，字段列 1/3；短字段配对成 5 行
        _rows = [
            ('姓名', self.le_name, '年龄', self.le_age),
            ('性别', sex_w, '档案类型', self.cb_type),
            ('学校', self.le_school, '联系电话', self.le_phone),
            ('总课时', self.le_total_lessons, '测评日期', self.dte_date),
            ('课时记录', self.btn_record_lesson, '课后反馈', self.btn_record_feedback),
        ]
        for r, (lab1, w1, lab2, w2) in enumerate(_rows):
            form.addWidget(QLabel(lab1), r, 0)
            form.addWidget(w1, r, 1)
            form.addWidget(QLabel(lab2), r, 2)
            form.addWidget(w2, r, 3)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)
        sheet.add_section('基本信息', form)

        # 成绩录入
        tlay = QVBoxLayout()
        tlay.setSpacing(12)
        tlay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self.on_item_changed)
        tlay.addWidget(self.table)
        self.table.setMinimumHeight(260)
        sheet.add_section('成绩录入（实测成绩填写后自动评分）', tlay, stretch=1)

        # 综合评价
        elay = QVBoxLayout()
        elay.setSpacing(12)
        elay.setContentsMargins(0, 0, 0, 0)
        self.te_eval = QTextEdit(placeholderText='填写综合评价、优势项目、提分建议等...')
        self.te_eval.setFixedHeight(100)
        elay.addWidget(self.te_eval)
        sheet.add_section('综合评价与提升建议（选填）', elay)
        mid_lay.addWidget(sheet, 1)

        # 底部按钮
        btn_w = QWidget()
        btn_w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        blay = QHBoxLayout(btn_w)
        blay.setContentsMargins(0, 0, 0, 0)
        blay.setSpacing(14)
        self.btn_lesson = QPushButton('课时管理', objectName='tertiary')
        self.btn_lesson.clicked.connect(self.on_open_lesson)
        self.btn_save = QPushButton('保存本次测评（追加到档案）', objectName='primary')
        self.btn_save.clicked.connect(self.on_save)
        self.btn_open = QPushButton('打开档案目录', objectName='tertiary')
        self.btn_open.clicked.connect(self.on_open)
        self.btn_clear = QPushButton('清空录入', objectName='secondary')
        self.btn_clear.clicked.connect(self.on_clear)
        blay.addWidget(self.btn_lesson)
        blay.addStretch(1)
        blay.addWidget(self.btn_save)
        blay.addWidget(self.btn_clear)
        blay.addWidget(self.btn_open)
        mid_lay.addWidget(btn_w)

        mid_scroll.setWidget(mid_content)
        main_lay.addWidget(mid_scroll, 1)

    #==== UI 辅助 ====

    def _gender(self):
        return '男' if self.rb_boy.isChecked() else '女'

    def on_type_changed(self, idx):
        """档案类型切换：重建录入表格。"""
        self._scoring = True
        name, ttype, grade, tag, zk = ac.TYPE_OPTIONS[idx]
        self.table.clear()
        self.table.setRowCount(0)
        self.table.blockSignals(True)
        if ttype in SCORE_TYPES:
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderLabels(
                ['测试项目', '单位', '满分标准', '及格标准', '实测成绩', '得分', '等级']
            )
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            if ttype == 'primary':
                stds = get_primary_standards(grade)
            elif ttype in ('junior', 'senior'):
                stds = get_standards_by_grade(grade)
            else:
                stds = get_zhongkao_standards()
            self._cur_stds = stds
            self._fill_score_rows(stds, ttype, zk)
        elif ttype in ('posture', 'weight'):
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels(['项目', '内容'])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            blocks = ac.POSTURE_BLOCKS if ttype == 'posture' else ac.WEIGHT_BLOCKS
            self._cur_stds = []
            self._fill_eval_rows(blocks)
        self.table.blockSignals(False)
        self._scoring = False

    def _fill_score_rows(self, stds, ttype, zk):
        """填充成绩录入行。"""
        gender = self._gender()
        self.table.setRowCount(len(stds))
        for i, std in enumerate(stds):
            full = std.boys_full if gender == '男' else std.girls_full
            pass_ = std.boys_pass if gender == '男' else std.girls_pass
            items = [
                std.name, std.unit, format_value(full, std.unit),
                format_value(pass_, std.unit), '', '', ''
            ]
            for j, txt in enumerate(items):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                if j in (0, 1, 2, 3, 5, 6):
                    it.setFlags(Qt.ItemIsEnabled)
                    if j == 0:
                        it.setForeground(QColor('#FF6B47'))
                elif j == 4:
                    it.setBackground(QColor('#FFFFFF'))
                    it.setForeground(QColor('#1A1A1A'))
                self.table.setItem(i, j, it)
        if ttype == 'zhongkao_old':
            tip = QTableWidgetItem('提示：2025旧方案暂不支持自动评分，请参考满分标准手动评估')
            tip.setFlags(Qt.ItemIsEnabled)
            tip.setForeground(QColor('#B45309'))
            self.table.insertRow(self.table.rowCount())
            self.table.setSpan(self.table.rowCount() - 1, 0, 1, 7)
            self.table.setItem(self.table.rowCount() - 1, 0, tip)

    def _fill_eval_rows(self, blocks):
        """填充评估表分组行。"""
        row = 0
        for title, rows in blocks:
            self.table.insertRow(row)
            it = QTableWidgetItem(title)
            it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it.setFlags(Qt.ItemIsEnabled)
            it.setForeground(QColor('#1F4E78'))
            it.setBackground(QColor('#EAF2FC'))
            self.table.setSpan(row, 0, 1, 2)
            self.table.setItem(row, 0, it)
            row += 1
            for label, _ in rows:
                self.table.insertRow(row)
                la = QTableWidgetItem(label)
                la.setFlags(Qt.ItemIsEnabled)
                la.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 0, la)
                self.table.setItem(row, 1, QTableWidgetItem(''))
                row += 1
        self.table.setRowCount(row)

    def on_item_changed(self, item):
        """实测成绩变化时自动评分。"""
        if self._scoring:
            return
        if item.column() != 4:
            return
        col0 = self.table.item(item.row(), 0)
        if not col0:
            return
        self._scoring = True
        proj = col0.text()
        std = next((s for s in self._cur_stds if s.name == proj), None)
        if std is None:
            self._scoring = False
            return
        raw = item.text().strip()
        if not raw:
            self.table.setItem(item.row(), 5, QTableWidgetItem(''))
            self.table.setItem(item.row(), 6, QTableWidgetItem(''))
            self._scoring = False
            return
        res = calc_score(std, self._gender(), raw)
        if res['ok']:
            sc_item = QTableWidgetItem(f"{res['score']:.1f}")
            gr_item = QTableWidgetItem(res['grade'])
        else:
            sc_item = QTableWidgetItem('—')
            gr_item = QTableWidgetItem('格式错误')
        sc_item.setTextAlignment(Qt.AlignCenter)
        sc_item.setFlags(Qt.ItemIsEnabled)
        sc_item.setBackground(QColor('#4338ca'))
        sc_item.setForeground(QColor('#ffffff'))
        gr_item.setTextAlignment(Qt.AlignCenter)
        gr_item.setFlags(Qt.ItemIsEnabled)
        gr_item.setBackground(QColor('#4338ca'))
        gr_item.setForeground(QColor('#ffffff' if res['ok'] else '#ff8a8a'))
        self.table.setItem(item.row(), 5, sc_item)
        self.table.setItem(item.row(), 6, gr_item)
        self._scoring = False

    #==== 业务路由（调用 archive_controller）====

    def on_dir_browse(self):
        """选择档案目录。"""
        path = QFileDialog.getExistingDirectory(self, '选择档案目录', self.le_dir.text() or DEFAULT_DIR)
        if path:
            self.le_dir.setText(path)
            self._dir_path = path
            self.refresh_students()

    def refresh_students(self):
        """刷新学员下拉列表。"""
        dir_path = self.le_dir.text().strip()
        self._dir_path = dir_path
        self.cb_student.blockSignals(True)
        self.cb_student.clear()
        self.cb_student.addItem('＋ 新建学员')
        for name in ac.scan_students(dir_path):
            self.cb_student.addItem(name)
        self.cb_student.blockSignals(False)
        self.on_student_selected(self.cb_student.currentIndex())

    def on_student_selected(self, idx):
        """选择学员：新建则解锁姓名输入，已有则加载基本信息。"""
        if self._loading_meta:
            return
        if idx <= 0:
            self.le_name.setReadOnly(False)
            self.le_name.clear()
            self.le_age.clear()
            self.le_school.clear()
            self.le_phone.clear()
            self.le_total_lessons.clear()
            self.rb_boy.setChecked(True)
            self.rb_girl.setChecked(False)
            self.lbl_history.setText('（新建学员，输入姓名后录入成绩）')
            return
        name = self.cb_student.itemText(idx)
        meta = ac.load_student_meta(name, self._dir_path)
        if not meta:
            self.lbl_history.setText('（档案读取失败）')
            return
        self._loading_meta = True
        info = meta.get('info', {})
        records = meta.get('records', [])
        self.le_name.setText(info.get('name', name))
        self.le_name.setReadOnly(True)
        age_val = info.get('age')
        self.le_age.setText(str(age_val) if age_val else '')
        self.le_school.setText(info.get('school', ''))
        self.le_phone.setText(info.get('phone', ''))
        total = ac.get_lesson_total_for(name, self._dir_path)
        self.le_total_lessons.setText(str(total) if total > 0 else '')
        gender = info.get('gender', '男')
        self.rb_boy.setChecked(gender == '男')
        self.rb_girl.setChecked(gender == '女')
        if records:
            last = records[-1]
            self.lbl_history.setText(
                f"已完成 {len(records)} 次测评，最近：{last.get('date', '')} {last.get('tag', '')}")
        else:
            self.lbl_history.setText('（暂无测评记录）')
        self._loading_meta = False

    def on_clear(self):
        """清空成绩录入表格与评价（保留基本信息）。"""
        self.te_eval.clear()
        self.le_age.clear()
        self.on_type_changed(self.cb_type.currentIndex())

    def on_open_lesson(self):
        """打开课时记录 Excel 文件。"""
        ok, msg = ac.open_lesson_file(self.le_dir.text().strip())
        if not ok:
            dialog.warn(self, '提示', msg)

    def _sync_and_list_students(self, dir_path):
        """返回课时汇总里的学员名单（先同步一次）。

        ⚠️ 学员名单不来自档案目录扫描，而来自「课时记录.xlsx」的汇总表：
        新目录下拉本来为空、要手动点一次「同步学员名单」。
        这里顺手同步，省掉那一步（同步是幂等的，已有学员不受影响）。
        """
        lm.sync_students(dir_path)
        return [d['name'] for d in lm.get_summary(dir_path)]

    def on_record_lesson(self):
        """记录一次上课 —— 打开课时记录窗口。

        批 1 接线：LessonWindow（5 字段：学员/日期/课时数/训练内容/备注）此前从未被实例化。
        同时含汇总表、明细表、编辑/删除与课时回退，全部复用其既有实现，未改其内部逻辑。
        """
        dir_path = self.le_dir.text().strip()
        if not dir_path:
            dialog.warn(self, '提示', '请先选择档案目录')
            return
        if not os.path.isdir(dir_path):
            dialog.warn(self, '提示', '档案目录不存在，请先选择')
            return
        self._sync_and_list_students(dir_path)

        dlg = QDialog(self)
        dlg.setWindowTitle('课时记录')
        dlg.resize(1000, 780)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(LessonWindow(dir_path, parent=dlg))
        dlg.exec()
        self.refresh_students()

    def on_record_feedback(self):
        """填写课后反馈 —— 打开 7 字段反馈对话框。

        批 1 接线：feedback_storage 此前从未被任何 UI 调用。
        """
        dir_path = self.le_dir.text().strip()
        if not dir_path:
            dialog.warn(self, '提示', '请先选择档案目录')
            return
        if not os.path.isdir(dir_path):
            dialog.warn(self, '提示', '档案目录不存在，请先选择')
            return
        students = self._sync_and_list_students(dir_path)
        if not students:
            dialog.warn(self, '提示', '该档案目录下暂无学员，请先在「学员档案」新增')
            return
        default_name = self.le_name.text().strip() or self.cb_student.currentText()
        LessonFeedbackDialog(dir_path, students, default_name, self).exec()

    def on_save(self):
        """保存本次测评（委托 archive_controller）。"""
        name = self.le_name.text().strip()
        if not name:
            dialog.warn(self, '提示', '请输入学员姓名')
            return
        idx = self.cb_type.currentIndex()
        _, ttype, grade, tag, zk = ac.TYPE_OPTIONS[idx]
        dir_path = self.le_dir.text().strip()
        if not dir_path:
            dialog.warn(self, '提示', '请选择档案目录')
            return
        # 解析年龄
        age_text = self.le_age.text().strip()
        try:
            age = int(age_text) if age_text else None
            if age is not None and age <= 0:
                age = None
        except ValueError:
            age = None
        # 收集数据
        if ttype in SCORE_TYPES:
            records = ac.collect_records_from_table(self.table)
            blocks = None
        else:
            records = None
            blocks = ac.collect_blocks_from_table(self.table)
        student = ac.build_student_payload(
            name=name, age=age, gender=self._gender(),
            school=self.le_school.text().strip(),
            phone=self.le_phone.text().strip(),
            date_str=self.dte_date.date().toString('yyyy-MM-dd'),
            ttype=ttype, grade=grade, sheet_tag=tag, zk_plan=zk,
            evaluation=self.te_eval.toPlainText().strip(),
            records=records, blocks=blocks,
        )
        try:
            sheet, fpath, lesson_msg = ac.save_assessment(
                student, dir_path,
                total_lessons_input=self.le_total_lessons.text().strip(),
                # 批 1：测评保存不再顺带记课时（原 inline 两字段已移除），
                # 上课记录走「记录一次上课」入口（LessonWindow，5 字段）。
                lesson_count_input='',
                lesson_content_input='',
            )
            dialog.info(
                self, '保存成功',
                f'已追加 [{name}] 第 {sheet.split("_")[0]} 次测评到档案\n'
                f'文件：{fpath}{lesson_msg}'
            )
            self.refresh_students()
            target_idx = self.cb_student.findText(name)
            if target_idx > 0:
                self.cb_student.setCurrentIndex(target_idx)
        except PermissionError as e:
            dialog.error(
                self, '保存失败',
                f'{e}\n\n请先关闭 Excel 后重试。'
            )
        except Exception as e:
            logging.exception('保存测评数据失败')
            dialog.error(
                self, '保存失败',
                f'{e}\n\n请确认文件未被其他程序占用。'
            )

    def on_open(self):
        """打开档案目录。"""
        ok, msg = ac.open_archive_dir(self.le_dir.text().strip())
        if not ok:
            dialog.info(self, '提示', msg)
