# -*- coding: utf-8 -*-
"""学员档案对话框：新增/编辑学员 + 单条上课记录编辑。

拆分自 profile_screen.py（P2 超大文件拆分）。
"""
import modern_dialog as dialog
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFrame, QSpinBox, QDoubleSpinBox, QTextEdit, QCheckBox,
)

import profile_manager as pm
from bmi_processor import calc_bmi, classify_body_type, body_type_color, get_bmi_advice


class StudentEditDialog(QDialog):
    """学员信息编辑弹窗（新增/编辑共用）。"""

    def __init__(self, parent=None, student: dict = None, archive_dir: str = ''):
        super().__init__(parent)
        self.setWindowTitle('编辑学员' if student else '新增学员')
        self.resize(520, 700)
        self._archive_dir = archive_dir
        self._student = student
        self._init_ui()
        if student:
            self._fill_form(student)

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(22, 22, 22, 22)

        # 基本信息区
        gl = QGridLayout()
        gl.setHorizontalSpacing(14)
        gl.setVerticalSpacing(10)

        self.le_name = QLineEdit(placeholderText='必填')
        self.le_name.setEnabled(self._student is None)  # 编辑时禁用改名
        self.cb_gender = QComboBox()
        self.cb_gender.addItems(['男', '女'])
        self.sb_age = QSpinBox()
        self.sb_age.setRange(3, 30)
        self.sb_age.setValue(12)
        self.cb_grade = QComboBox()
        self.cb_grade.addItems(pm.get_grades())

        # 身高体重可选：复选框控制是否录入
        self.cb_height_weight = QCheckBox('录入身高体重')
        self.cb_height_weight.setChecked(True)
        self.cb_height_weight.toggled.connect(self._on_toggle_hw)
        self.sb_height = QDoubleSpinBox()
        self.sb_height.setRange(50.0, 220.0)
        self.sb_height.setSuffix(' cm')
        self.sb_height.setDecimals(1)
        self.sb_height.setValue(150.0)
        self.sb_weight = QDoubleSpinBox()
        self.sb_weight.setRange(10.0, 150.0)
        self.sb_weight.setSuffix(' kg')
        self.sb_weight.setDecimals(1)
        self.sb_weight.setValue(40.0)

        # 联系方式（对齐 Android 端 school/phone 字段）
        self.le_school = QLineEdit(placeholderText='就读学校（选填）')
        self.le_phone = QLineEdit(placeholderText='家长电话（选填）')

        gl.addWidget(QLabel('姓名 *'), 0, 0)
        gl.addWidget(self.le_name, 0, 1, 1, 3)
        gl.addWidget(QLabel('年龄'), 1, 0)
        gl.addWidget(self.sb_age, 1, 1)
        gl.addWidget(QLabel('年级'), 1, 2)
        gl.addWidget(self.cb_grade, 1, 3)
        gl.addWidget(QLabel('性别'), 2, 0)
        gl.addWidget(self.cb_gender, 2, 1)
        gl.addWidget(QLabel('学校'), 2, 2)
        gl.addWidget(self.le_school, 2, 3)
        gl.addWidget(QLabel('电话'), 3, 0)
        gl.addWidget(self.le_phone, 3, 1)
        gl.addWidget(self.cb_height_weight, 4, 0, 1, 4)
        gl.addWidget(QLabel('身高'), 5, 0)
        gl.addWidget(self.sb_height, 5, 1)
        gl.addWidget(QLabel('体重'), 5, 2)
        gl.addWidget(self.sb_weight, 5, 3)
        lay.addLayout(gl)

        # 遗传与生活习惯区（身高预测用，对齐 Android 端 v17 字段）
        gen_title = QLabel('遗传与生活习惯（身高预测用，选填）')
        gen_title.setStyleSheet('color:#6B6B6B; font-weight:bold;')
        lay.addWidget(gen_title)
        gl2 = QGridLayout()
        gl2.setHorizontalSpacing(14)
        gl2.setVerticalSpacing(10)
        self.sb_father_h = QDoubleSpinBox()
        self.sb_father_h.setRange(0.0, 250.0)
        self.sb_father_h.setSuffix(' cm')
        self.sb_father_h.setDecimals(1)
        self.sb_father_h.setSpecialValueText('未填写')
        self.sb_mother_h = QDoubleSpinBox()
        self.sb_mother_h.setRange(0.0, 250.0)
        self.sb_mother_h.setSuffix(' cm')
        self.sb_mother_h.setDecimals(1)
        self.sb_mother_h.setSpecialValueText('未填写')
        self.sb_sleep = QDoubleSpinBox()
        self.sb_sleep.setRange(0.0, 24.0)
        self.sb_sleep.setSuffix(' h')
        self.sb_sleep.setDecimals(1)
        self.sb_sleep.setSpecialValueText('未填写')
        self.sb_nutrition = QSpinBox()
        self.sb_nutrition.setRange(0, 5)
        self.sb_nutrition.setSpecialValueText('未填写')
        self.sb_nutrition.setToolTip('营养均衡评分：1 差 ~ 5 优')
        self.sb_sports = QSpinBox()
        self.sb_sports.setRange(0, 3000)
        self.sb_sports.setSuffix(' min')
        self.sb_sports.setSpecialValueText('未填写')
        self.sb_sports.setToolTip('每周运动总时长（分钟）')
        gl2.addWidget(QLabel('父身高'), 0, 0)
        gl2.addWidget(self.sb_father_h, 0, 1)
        gl2.addWidget(QLabel('母身高'), 0, 2)
        gl2.addWidget(self.sb_mother_h, 0, 3)
        gl2.addWidget(QLabel('睡眠'), 1, 0)
        gl2.addWidget(self.sb_sleep, 1, 1)
        gl2.addWidget(QLabel('营养评分'), 1, 2)
        gl2.addWidget(self.sb_nutrition, 1, 3)
        gl2.addWidget(QLabel('周运动'), 2, 0)
        gl2.addWidget(self.sb_sports, 2, 1)
        lay.addLayout(gl2)

        # BMI 实时预览
        bmi_box = QFrame()
        bmi_box.setObjectName('card')
        bl = QVBoxLayout(bmi_box)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.setSpacing(6)
        self.lbl_bmi_title = QLabel('BMI 实时计算')
        self.lbl_bmi_title.setStyleSheet('color:#FF6B47; font-weight:bold;')
        bl.addWidget(self.lbl_bmi_title)
        self.lbl_bmi_value = QLabel('—')
        self.lbl_bmi_value.setStyleSheet('font-size:22px; font-weight:bold; color:#34D399;')
        bl.addWidget(self.lbl_bmi_value)
        self.lbl_body_type = QLabel('—')
        self.lbl_body_type.setStyleSheet('color:#9B9B9B;')
        bl.addWidget(self.lbl_body_type)
        self.lbl_advice = QLabel('—')
        self.lbl_advice.setStyleSheet('color:#6B6B6B; font-size:12px;')
        self.lbl_advice.setWordWrap(True)
        bl.addWidget(self.lbl_advice)
        lay.addWidget(bmi_box)

        # 数值变化时实时刷新 BMI
        self.sb_height.valueChanged.connect(self._refresh_bmi)
        self.sb_weight.valueChanged.connect(self._refresh_bmi)
        self.sb_age.valueChanged.connect(self._on_age_changed)
        self.sb_age.valueChanged.connect(self._refresh_bmi)

        # 备注
        lay.addWidget(QLabel('备注'))
        self.te_note = QTextEdit(placeholderText='健康史、运动习惯、家长联系方式等...')
        self.te_note.setFixedHeight(70)
        lay.addWidget(self.te_note)

        lay.addStretch()

        # 底部按钮
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_cancel = QPushButton('取消')
        btn_cancel.setObjectName('secondary')
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton('保存')
        btn_ok.setObjectName('primary')
        btn_ok.clicked.connect(self._on_save)
        btn_lay.addWidget(btn_cancel)
        btn_lay.addWidget(btn_ok)
        lay.addLayout(btn_lay)

        self._on_age_changed(self.sb_age.value())
        self._refresh_bmi()

    def _on_age_changed(self, age: int):
        """年龄变化时联动年级选择框：7岁以下强制学龄前并禁用。"""
        if age and age < 7:
            # 强制学龄前并禁用选择
            idx = self.cb_grade.findText('学龄前')
            if idx >= 0:
                self.cb_grade.setCurrentIndex(idx)
            self.cb_grade.setEnabled(False)
            # 7岁以下默认不录入身高体重（可手动勾选）
            self.cb_height_weight.setChecked(False)
        else:
            self.cb_grade.setEnabled(True)

    def _on_toggle_hw(self, checked: bool):
        """切换身高体重录入开关。"""
        self.sb_height.setEnabled(checked)
        self.sb_weight.setEnabled(checked)
        self._refresh_bmi()

    def _refresh_bmi(self):
        """实时刷新 BMI 预览。"""
        age = self.sb_age.value()
        if not self.cb_height_weight.isChecked():
            self.lbl_bmi_value.setText('—')
            self.lbl_bmi_value.setStyleSheet('font-size:22px; font-weight:bold; color:#9B9B9B;')
            self.lbl_body_type.setText('体型：未录入')
            self.lbl_advice.setText('勾选「录入身高体重」以计算 BMI')
            return
        h = self.sb_height.value()
        w = self.sb_weight.value()
        bmi = calc_bmi(h, w)
        body_type = classify_body_type(bmi, age)
        color = body_type_color(body_type)
        self.lbl_bmi_value.setText(f'{bmi}')
        self.lbl_bmi_value.setStyleSheet(f'font-size:22px; font-weight:bold; color:{color};')
        self.lbl_body_type.setText(f'体型：{body_type}')
        self.lbl_advice.setText(get_bmi_advice(bmi, age))

    def _fill_form(self, s: dict):
        self.le_name.setText(s.get('name', ''))
        self.sb_age.setValue(int(s.get('age', 12) or 12))
        g = s.get('gender', '男')
        idx = self.cb_gender.findText(g if g in ('男', '女') else '男')
        self.cb_gender.setCurrentIndex(max(idx, 0))
        self.le_school.setText(s.get('school', ''))
        self.le_phone.setText(s.get('phone', ''))
        # 遗传与生活习惯（0/None → 保持"未填写"特殊值 0）
        self.sb_father_h.setValue(float(s.get('father_height') or 0))
        self.sb_mother_h.setValue(float(s.get('mother_height') or 0))
        self.sb_sleep.setValue(float(s.get('sleep_hours') or 0))
        self.sb_nutrition.setValue(int(s.get('nutrition_score') or 0))
        self.sb_sports.setValue(int(s.get('sports_mins') or 0))
        # 身高体重：已有值则填入并勾选，否则不勾选
        h = s.get('height')
        w = s.get('weight')
        if h not in (None, '', 0):
            self.cb_height_weight.setChecked(True)
            self.sb_height.setValue(float(h))
        else:
            self.cb_height_weight.setChecked(False)
        if w not in (None, '', 0):
            self.sb_weight.setValue(float(w))
        grade = s.get('grade', '')
        idx = self.cb_grade.findText(grade)
        if idx >= 0:
            self.cb_grade.setCurrentIndex(idx)
        self.te_note.setPlainText(s.get('note', ''))
        # 触发年龄联动
        self._on_age_changed(self.sb_age.value())
        self._refresh_bmi()

    def _on_save(self):
        name = self.le_name.text().strip()
        if not name:
            dialog.warn(self, '提示', '请输入学员姓名')
            return
        # 身高体重：未勾选时传 None
        if self.cb_height_weight.isChecked():
            height = self.sb_height.value()
            weight = self.sb_weight.value()
        else:
            height = None
            weight = None
        try:
            self._result = pm.save_student(
                archive_dir=self._archive_dir,
                name=name,
                age=self.sb_age.value(),
                height=height,
                weight=weight,
                grade=self.cb_grade.currentText(),
                note=self.te_note.toPlainText().strip(),
                gender=self.cb_gender.currentText(),
                school=self.le_school.text().strip(),
                phone=self.le_phone.text().strip(),
                father_height=self.sb_father_h.value() or None,
                mother_height=self.sb_mother_h.value() or None,
                sleep_hours=self.sb_sleep.value(),
                nutrition_score=self.sb_nutrition.value(),
                sports_mins=self.sb_sports.value(),
            )
            self.accept()
        except Exception as e:
            dialog.error(self, '保存失败', str(e))

    def get_result(self) -> dict:
        return getattr(self, '_result', None)


class _LessonRecordEditDialog(QDialog):
    """单条上课记录编辑弹窗（内部使用）。"""

    def __init__(self, parent=None, record: dict = None):
        super().__init__(parent)
        self.setWindowTitle('编辑上课记录')
        self.resize(440, 320)
        self.date_str = ''
        self.count = 0
        self.content = ''
        self.note = ''
        self._init_ui(record or {})

    def _init_ui(self, rec: dict):
        from PySide6.QtWidgets import QFormLayout, QDateEdit
        from PySide6.QtCore import QDate
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        # 日期
        self.dte = QDateEdit()
        self.dte.setCalendarPopup(True)
        self.dte.setDisplayFormat('yyyy-MM-dd')
        date_str = str(rec.get('date', '') or '')
        if date_str:
            try:
                y, m, d = date_str.split('-')
                self.dte.setDate(QDate(int(y), int(m), int(d)))
            except Exception:
                self.dte.setDate(QDate.currentDate())
        else:
            self.dte.setDate(QDate.currentDate())
        # 课时数
        self.le_count = QLineEdit(str(rec.get('count', 1) or 1))
        # 训练内容
        self.le_content = QLineEdit(str(rec.get('content', '') or ''))
        self.le_content.setPlaceholderText('如：体能训练、跳绳强化...')
        # 备注
        self.le_note = QLineEdit(str(rec.get('note', '') or ''))
        self.le_note.setPlaceholderText('备注（选填）')
        form.addRow('上课日期：', self.dte)
        form.addRow('本次课时：', self.le_count)
        form.addRow('训练内容：', self.le_content)
        form.addRow('备注：', self.le_note)
        lay.addLayout(form)
        lay.addStretch()
        # 按钮
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_cancel = QPushButton('取消', objectName='secondary')
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton('保存', objectName='primary')
        btn_ok.clicked.connect(self._on_save)
        btn_lay.addWidget(btn_cancel)
        btn_lay.addWidget(btn_ok)
        lay.addLayout(btn_lay)

    def _on_save(self):
        self.date_str = self.dte.date().toString('yyyy-MM-dd')
        try:
            self.count = int(self.le_count.text().strip())
            if self.count <= 0:
                raise ValueError
        except ValueError:
            dialog.warn(self, '提示', '课时数请输入正整数')
            return
        self.content = self.le_content.text().strip()
        self.note = self.le_note.text().strip()
        self.accept()
