# -*- coding: utf-8 -*-
"""成长工具对话框：身高预测 + 营养方案（TDEE/膳食模板）+ 体型历史。

对齐 Android 端 HeightPredictionScreen / DietManageScreen / BodyMetricChartScreen 三个页面，
合并为一个桌面端弹窗（学员档案页「成长工具」按钮入口）。
"""
import os
import sys
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QDoubleSpinBox, QSpinBox, QPushButton, QFrame, QTabWidget, QWidget,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import profile_manager as pm
from bmi_processor import calc_bmi
import growth_processor as gp
from chart_components import LineChartWidget


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName('card')
    return f


class GrowthToolsDialog(QDialog):
    """身高预测 / TDEE / 膳食模板 / 体型历史 合并工具弹窗。"""

    def __init__(self, parent=None, archive_dir: str = '', student_name: str = ''):
        super().__init__(parent)
        self.setWindowTitle('成长工具（身高预测 · 营养 · 体型历史）')
        self.resize(760, 640)
        self._archive_dir = archive_dir
        self._init_ui()
        self._load_students(preselect=student_name)

    # ---------- UI 组装 ----------

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 18, 20, 18)

        # 学员选择行
        top = QHBoxLayout()
        top.addWidget(QLabel('学员：'))
        self.cb_student = QComboBox()
        self.cb_student.setMinimumWidth(200)
        self.cb_student.currentIndexChanged.connect(self._on_student_changed)
        top.addWidget(self.cb_student)
        top.addStretch()
        self.btn_refresh = QPushButton('刷新')
        self.btn_refresh.setObjectName('secondary')
        self.btn_refresh.clicked.connect(lambda: self._load_students())
        top.addWidget(self.btn_refresh)
        lay.addLayout(top)

        self.lbl_student_info = QLabel('—')
        self.lbl_student_info.setStyleSheet('color:#6B6B6B; font-size:12px;')
        lay.addWidget(self.lbl_student_info)

        tabs = QTabWidget()
        tabs.addTab(self._build_predict_tab(), '身高预测')
        tabs.addTab(self._build_diet_tab(), '营养方案')
        tabs.addTab(self._build_history_tab(), '体型历史')
        lay.addWidget(tabs, 1)

        # 底部关闭
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_close = QPushButton('关闭', objectName='secondary')
        btn_close.clicked.connect(self.accept)
        btn_lay.addWidget(btn_close)
        lay.addLayout(btn_lay)

    def _build_predict_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 10, 4, 4)
        lay.setSpacing(14)

        # 左：输入区
        left = _card()
        gl = QGridLayout(left)
        gl.setHorizontalSpacing(12)
        gl.setVerticalSpacing(10)
        self.p_father = QDoubleSpinBox(); self.p_father.setRange(0, 250); self.p_father.setSuffix(' cm'); self.p_father.setSpecialValueText('未填写')
        self.p_mother = QDoubleSpinBox(); self.p_mother.setRange(0, 250); self.p_mother.setSuffix(' cm'); self.p_mother.setSpecialValueText('未填写')
        self.p_sleep = QDoubleSpinBox(); self.p_sleep.setRange(0, 24); self.p_sleep.setSuffix(' h'); self.p_sleep.setDecimals(1); self.p_sleep.setSpecialValueText('未填写')
        self.p_nutrition = QSpinBox(); self.p_nutrition.setRange(0, 5); self.p_nutrition.setSpecialValueText('未填写')
        self.p_sports = QSpinBox(); self.p_sports.setRange(0, 3000); self.p_sports.setSuffix(' min'); self.p_sports.setSpecialValueText('未填写')
        rows = [('父身高', self.p_father), ('母身高', self.p_mother), ('日常睡眠', self.p_sleep),
                ('营养评分(1-5)', self.p_nutrition), ('周运动时长', self.p_sports)]
        for i, (label, sb) in enumerate(rows):
            gl.addWidget(QLabel(label), i, 0)
            gl.addWidget(sb, i, 1)
        self.btn_predict = QPushButton('计算身高预测')
        self.btn_predict.setObjectName('primary')
        self.btn_predict.clicked.connect(self._on_predict)
        gl.addWidget(self.btn_predict, len(rows), 0, 1, 2)
        lay.addWidget(left)

        # 右：结果区
        right = _card()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(6)
        self.lbl_target = QLabel('遗传靶身高：—')
        self.lbl_adjust = QLabel('后天修正：—')
        self.lbl_result = QLabel('—')
        self.lbl_result.setStyleSheet('font-size:26px; font-weight:bold; color:#FF6B47;')
        self.lbl_range = QLabel('预测区间：—')
        self.lbl_rating = QLabel('身高评级：—')
        self.lbl_advice = QLabel('—')
        self.lbl_advice.setWordWrap(True)
        self.lbl_advice.setStyleSheet('color:#6B6B6B; font-size:12px;')
        self.lbl_bone = QLabel('')
        self.lbl_bone.setWordWrap(True)
        self.lbl_bone.setStyleSheet('color:#F87171; font-size:12px;')
        for lbl in (self.lbl_target, self.lbl_adjust, self.lbl_range, self.lbl_rating):
            lbl.setStyleSheet(lbl.styleSheet() or 'color:#3A3A3A;')
        rl.addWidget(self.lbl_target)
        rl.addWidget(self.lbl_adjust)
        rl.addWidget(self.lbl_result)
        rl.addWidget(self.lbl_range)
        rl.addWidget(self.lbl_rating)
        rl.addWidget(self.lbl_advice)
        rl.addWidget(self.lbl_bone)
        rl.addStretch()
        lay.addWidget(right, 1)
        return w

    def _build_diet_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 10, 4, 4)
        lay.setSpacing(10)

        # TDEE 卡片
        tdee_card = _card()
        tl = QHBoxLayout(tdee_card)
        tl.setContentsMargins(16, 12, 16, 12)
        self.d_activity = QComboBox()
        for _, _, label in gp.ACTIVITY_LEVELS:
            self.d_activity.addItem(label)
        self.d_activity.setCurrentIndex(2)  # 默认中度运动（对齐 Android DEFAULT）
        btn_tdee = QPushButton('计算 TDEE')
        btn_tdee.setObjectName('secondary')
        btn_tdee.clicked.connect(self._on_tdee)
        self.lbl_tdee = QLabel('BMR / TDEE：选择活动水平后计算')
        self.lbl_tdee.setStyleSheet('color:#3A3A3A; font-weight:bold;')
        tl.addWidget(QLabel('活动水平：'))
        tl.addWidget(self.d_activity)
        tl.addWidget(btn_tdee)
        tl.addWidget(self.lbl_tdee, 1)
        lay.addWidget(tdee_card)

        self.lbl_diet_warn = QLabel('')
        self.lbl_diet_warn.setWordWrap(True)
        self.lbl_diet_warn.setStyleSheet('color:#F59E0B; font-size:12px;')
        self.lbl_diet_warn.hide()
        lay.addWidget(self.lbl_diet_warn)

        # 模板选择 + 内容
        tpl_card = _card()
        vl = QVBoxLayout(tpl_card)
        vl.setContentsMargins(16, 12, 16, 12)
        vl.setSpacing(8)
        sel = QHBoxLayout()
        sel.addWidget(QLabel('膳食模板（3+2 饮食法）：'))
        self.cb_template = QComboBox()
        for t in gp.DIET_TEMPLATES:
            self.cb_template.addItem(t['name'], t['id'])
        self.cb_template.currentIndexChanged.connect(self._render_template)
        sel.addWidget(self.cb_template)
        sel.addStretch()
        self.lbl_bound = QLabel('')
        self.lbl_bound.setStyleSheet('color:#9B9B9B; font-size:12px;')
        sel.addWidget(self.lbl_bound)
        self.btn_bind = QPushButton('绑定到此学员')
        self.btn_bind.setObjectName('primary')
        self.btn_bind.clicked.connect(self._on_bind)
        sel.addWidget(self.btn_bind)
        vl.addLayout(sel)

        self.lbl_tpl_desc = QLabel('—')
        self.lbl_tpl_desc.setWordWrap(True)
        self.lbl_tpl_desc.setStyleSheet('color:#6B6B6B; font-size:12px;')
        vl.addWidget(self.lbl_tpl_desc)

        self.te_meals = QTextEdit()
        self.te_meals.setReadOnly(True)
        vl.addWidget(self.te_meals, 1)
        lay.addWidget(tpl_card, 1)
        return w

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 10, 4, 4)
        lay.setSpacing(10)

        self.chart = LineChartWidget()
        lay.addWidget(self.chart)

        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(['日期', '身高(cm)', '体重(kg)', 'BMI', '备注'])
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.verticalHeader().setVisible(False)
        lay.addWidget(self.history_table, 1)

        self.lbl_history_hint = QLabel('每次保存学员档案（身高体重有效）会自动记录当天测量数据')
        self.lbl_history_hint.setStyleSheet('color:#9B9B9B; font-size:12px;')
        lay.addWidget(self.lbl_history_hint)
        return w

    # ---------- 数据加载 ----------

    def _load_students(self, preselect: str = ''):
        self.cb_student.blockSignals(True)
        self.cb_student.clear()
        try:
            students = pm.list_students(self._archive_dir)
        except Exception:
            students = []
        for s in students:
            self.cb_student.addItem(s['name'], s)
        self.cb_student.blockSignals(False)
        if preselect:
            idx = self.cb_student.findText(preselect)
            if idx >= 0:
                self.cb_student.setCurrentIndex(idx)
        # 索引未变化时 currentIndexChanged 不触发，显式刷新一次（幂等）
        self._on_student_changed()

    def _current_student(self) -> dict:
        return self.cb_student.currentData() or {}

    def _on_student_changed(self):
        s = self._current_student()
        if not s:
            self.lbl_student_info.setText('暂无学员，请先在学员档案页新增')
            return
        info = (f"性别 {s.get('gender', '男')} · 年龄 {s.get('age', 0)} · "
                f"身高 {s.get('height') or '未录入'} cm · 体重 {s.get('weight') or '未录入'} kg"
                + (f" · 学校 {s['school']}" if s.get('school') else ''))
        self.lbl_student_info.setText(info)
        # 预填预测输入
        self.p_father.setValue(float(s.get('father_height') or 0))
        self.p_mother.setValue(float(s.get('mother_height') or 0))
        self.p_sleep.setValue(float(s.get('sleep_hours') or 0))
        self.p_nutrition.setValue(int(s.get('nutrition_score') or 0))
        self.p_sports.setValue(int(s.get('sports_mins') or 0))
        self._clear_predict()
        # 膳食绑定状态
        bound = pm.get_student_extra(self._archive_dir, s['name'], 'diet_plan', '')
        if bound:
            idx = self.cb_template.findData(bound)
            if idx >= 0:
                self.cb_template.blockSignals(True)
                self.cb_template.setCurrentIndex(idx)
                self.cb_template.blockSignals(False)
            self.lbl_bound.setText('已绑定该方案')
        else:
            self.lbl_bound.setText('未绑定膳食方案')
        self._render_template()
        self._on_tdee()
        self._load_history()

    def _clear_predict(self):
        self.lbl_target.setText('遗传靶身高：—')
        self.lbl_adjust.setText('后天修正：—')
        self.lbl_result.setText('—')
        self.lbl_range.setText('预测区间：—')
        self.lbl_rating.setText('身高评级：—')
        self.lbl_advice.setText('—')
        self.lbl_bone.setText('')

    # ---------- 身高预测 ----------

    def _on_predict(self):
        s = self._current_student()
        if not s:
            return
        result = gp.predict_height(
            gender=s.get('gender', '男'), age=int(s.get('age', 0) or 0),
            father_height=self.p_father.value(), mother_height=self.p_mother.value(),
            avg_sleep_hours=self.p_sleep.value(), nutrition_score=self.p_nutrition.value(),
            sports_mins_per_week=self.p_sports.value())
        if not result:
            self.lbl_result.setText('父母身高未填写，无法预测')
            self.lbl_result.setStyleSheet('font-size:16px; font-weight:bold; color:#9B9B9B;')
            return
        self.lbl_result.setStyleSheet('font-size:26px; font-weight:bold; color:#FF6B47;')
        self.lbl_target.setText(f"遗传靶身高：{result['target_height']} cm")
        sign = '+' if result['adjustment'] > 0 else ''
        self.lbl_adjust.setText(f"后天修正：{sign}{result['adjustment']} cm（睡眠/营养/运动）")
        self.lbl_result.setText(f"预测成年身高：{result['adjusted_height']} cm")
        self.lbl_range.setText(f"预测区间：{result['lower_bound']} ~ {result['upper_bound']} cm")
        rating = result.get('rating')
        if rating:
            self.lbl_rating.setText(
                f"身高评级：<span style='color:{rating['color']}; font-weight:bold;'>{rating['label']}</span>"
                f"（P3 {rating['p3']} / P50 {rating['p50']} / P97 {rating['p97']} cm）")
            self.lbl_rating.setTextFormat(Qt.RichText)
        else:
            self.lbl_rating.setText('身高评级：年龄超出 3-18 岁标准范围，未评级')
        self.lbl_advice.setText(result['advice_text'])
        self.lbl_bone.setText(result['bone_age_warning'] or '')

    # ---------- TDEE / 膳食 ----------

    def _on_tdee(self):
        s = self._current_student()
        if not s:
            return
        activity_key = gp.ACTIVITY_LEVELS[self.d_activity.currentIndex()][0]
        r = gp.calc_tdee(s.get('gender', '男'), s.get('weight') or 0,
                         s.get('height') or 0, int(s.get('age', 0) or 0), activity_key)
        if not r:
            self.lbl_tdee.setText('BMR / TDEE：学员身高体重未录入完整')
            self.lbl_diet_warn.hide()
            return
        self.lbl_tdee.setText(f"BMR {r['bmr']} 大卡 · TDEE {r['tdee']} 大卡"
                              + (f" · 减脂缺口建议 {r['deficit_advice']} 大卡/日" if r['deficit_advice'] else ''))
        if r['warning_text']:
            self.lbl_diet_warn.setText(f"⚠ {r['warning_text']}")
            self.lbl_diet_warn.show()
        else:
            self.lbl_diet_warn.hide()

    def _render_template(self):
        tpl = gp.get_template(self.cb_template.currentData())
        if not tpl:
            return
        self.lbl_tpl_desc.setText(tpl['description'])
        lines = []
        for key, label in gp.MEAL_ORDER:
            items = tpl['meals'].get(key, [])
            detail = '；'.join(f"{it['category']}：{it['content']}" for it in items)
            lines.append(f"【{label}】{detail}")
        lines.append(f"【训练前】{tpl['pre_workout_tip']}")
        lines.append(f"【训练后】{tpl['post_workout_tip']}")
        self.te_meals.setPlainText('\n'.join(lines))

    def _on_bind(self):
        s = self._current_student()
        if not s:
            return
        tpl_id = self.cb_template.currentData()
        if pm.set_student_extra(self._archive_dir, s['name'], 'diet_plan', tpl_id):
            self.lbl_bound.setText('已绑定该方案')

    # ---------- 体型历史 ----------

    def _load_history(self):
        from profile_storage import read_body_metrics
        s = self._current_student()
        history = read_body_metrics(self._archive_dir, s.get('name', '')) if s else []
        # 表格（最新在前）
        self.history_table.setRowCount(len(history))
        for i, rec in enumerate(reversed(history)):
            values = [rec['date'], f"{rec['height']:.1f}", f"{rec['weight']:.1f}",
                      f"{rec['bmi']:.1f}", rec['note']]
            for j, v in enumerate(values):
                self.history_table.setItem(i, j, QTableWidgetItem(str(v)))
        # 趋势图
        if len(history) >= 2:
            labels = [rec['date'][5:] for rec in history]  # MM-DD
            self.chart.set_data([
                ('身高', list(zip(labels, [rec['height'] for rec in history])), '#FF6B47'),
                ('体重', list(zip(labels, [rec['weight'] for rec in history])), '#60A5FA'),
                ('BMI', list(zip(labels, [rec['bmi'] for rec in history])), '#34D399'),
            ])
        else:
            self.chart.set_data([])
