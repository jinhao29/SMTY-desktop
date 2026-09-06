# -*- coding: utf-8 -*-
"""UI 层：财务管理页（记账系统）。

每学员一行：应收（总课时×单价）/ 实收（收费记录累计）/ 已消课费用
（已上课时×单价），全部由 fee_manager 自动推导；录课时或收费后
切换到本页即刷新（refresh 在页面显示时触发）。

布局（李哥 2026-09-05 参考图：浅色大留白、方框卡片、干净输入控件）：
- 顶部统计卡行：实收总额 / 应收总额 / 待收总额 / 本月实收
- 中列：学员财务一览表 + 收费记录表（FormSheet 连续版面）
- 右栏：新增收费 / 刷新 / 计费口径说明
"""
import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QDateEdit, QLineEdit,
    QTextEdit, QDialog, QGridLayout, QAbstractItemView,
)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from base_components import FormSheet, IconBox, ColorPalette
from stat_components import StatCard
import fee_manager as fm

DEFAULT_DIR = os.path.expanduser('~/Desktop/学员档案')

# 状态色（中式财务口径：绿=结清、橙=待收、灰=未收费）
_STATUS_COLORS = {
    '已结清': '#1F9D55',
    '待收款': '#E55A3A',
    '未收费': '#9B9B9B',
}


def _fmt_money(v):
    return f'¥{v:,.2f}'


class PaymentDialog(QDialog):
    """新增收费弹窗：学员 / 日期 / 金额 / 对应课时数 / 方式 / 备注。"""

    def __init__(self, students, parent=None, default_name=''):
        super().__init__(parent)
        self.setWindowTitle('新增收费')
        self.setModal(True)
        self.setMinimumWidth(420)
        self.result_data = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel('新增收费')
        title.setObjectName('section')
        lay.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        def _lbl(text, row, col):
            lbl = QLabel(text)
            grid.addWidget(lbl, row, col)

        _lbl('学员', 0, 0)
        self.cb_student = QComboBox()
        self.cb_student.addItems(students)
        if default_name:
            self.cb_student.setCurrentText(default_name)
        grid.addWidget(self.cb_student, 0, 1)

        _lbl('收费日期', 1, 0)
        self.dte_date = QDateEdit(QDate.currentDate())
        self.dte_date.setCalendarPopup(True)
        self.dte_date.setDisplayFormat('yyyy-MM-dd')
        grid.addWidget(self.dte_date, 1, 1)

        _lbl('收费金额（¥）', 2, 0)
        self.le_amount = QLineEdit(placeholderText='如 4000')
        grid.addWidget(self.le_amount, 2, 1)

        _lbl('对应课时数', 3, 0)
        self.le_hours = QLineEdit(placeholderText='如 20（用于推算课时单价）')
        grid.addWidget(self.le_hours, 3, 1)

        _lbl('收款方式', 4, 0)
        self.cb_method = QComboBox()
        self.cb_method.addItems(['微信', '支付宝', '现金', '银行转账', '其他'])
        grid.addWidget(self.cb_method, 4, 1)

        _lbl('备注', 5, 0)
        self.le_note = QLineEdit(placeholderText='选填，如 续费 20 节、老学员优惠')
        grid.addWidget(self.le_note, 5, 1)

        lay.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton('取消', objectName='secondary')
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton('保存收费', objectName='primary')
        btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

    def _on_ok(self):
        try:
            amount = float(self.le_amount.text().strip())
            hours = float(self.le_hours.text().strip())
        except ValueError:
            from modern_dialog import ModernDialog
            ModernDialog(self, title='输入有误', text='金额和课时数必须是数字',
                         kind='warning').exec()
            return
        if amount <= 0 or hours <= 0:
            from modern_dialog import ModernDialog
            ModernDialog(self, title='输入有误', text='金额和课时数必须大于 0',
                         kind='warning').exec()
            return
        name = self.cb_student.currentText().strip()
        if not name:
            return
        self.result_data = {
            'name': name,
            'date': self.dte_date.date().toString('yyyy-MM-dd'),
            'amount': amount,
            'hours': hours,
            'method': self.cb_method.currentText(),
            'note': self.le_note.text().strip(),
        }
        self.accept()


class FinancePage(QWidget):
    """财务管理页：统计卡 + 学员财务表 + 收费记录。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dir_path = DEFAULT_DIR
        self.setObjectName('financeRoot')
        self._build_ui()

    #==== UI 构建 ====

    def _build_ui(self):
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(24, 16, 24, 16)
        main_lay.setSpacing(16)

        # ----- 中列 -----
        mid = QWidget()
        mid_lay = QVBoxLayout(mid)
        mid_lay.setContentsMargins(0, 0, 0, 0)
        mid_lay.setSpacing(14)

        # 统计卡行（4 张）
        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)
        self.stat_paid = StatCard(IconBox.ARCHIVE, '实收总额', '¥0.00')
        self.stat_receivable = StatCard(IconBox.CHART_BAR, '应收总额', '¥0.00')
        self.stat_due = StatCard(IconBox.TREND_UP, '待收总额', '¥0.00')
        self.stat_month = StatCard(IconBox.CALENDAR, '本月实收', '¥0.00')
        for s in (self.stat_paid, self.stat_receivable, self.stat_due, self.stat_month):
            stats_row.addWidget(s, 1)
        mid_lay.addLayout(stats_row)

        # 连续版面：学员财务一览 + 收费记录
        sheet = FormSheet()
        mid_lay.addWidget(sheet, 1)

        # --- 学员财务一览 ---
        stu_lay = QVBoxLayout()
        stu_lay.setContentsMargins(0, 0, 0, 0)
        stu_lay.setSpacing(8)
        self.table_students = QTableWidget()
        self.table_students.setColumnCount(9)
        self.table_students.setHorizontalHeaderLabels(
            ['学员', '总课时', '已消课', '课时单价', '已消课费用', '应收', '实收', '待收', '状态'])
        self.table_students.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_students.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table_students.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 9):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        self.table_students.verticalHeader().setVisible(False)
        self.table_students.setAlternatingRowColors(False)
        stu_lay.addWidget(self.table_students)
        sheet.add_section('学员财务一览（应收/已消课费用按课时单价自动计算）', stu_lay, stretch=1)

        # --- 收费记录 ---
        pay_lay = QVBoxLayout()
        pay_lay.setContentsMargins(0, 0, 0, 0)
        pay_lay.setSpacing(8)
        self.table_payments = QTableWidget()
        self.table_payments.setColumnCount(6)
        self.table_payments.setHorizontalHeaderLabels(
            ['日期', '学员', '金额', '课时数', '方式', '操作'])
        self.table_payments.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_payments.setSelectionBehavior(QAbstractItemView.SelectRows)
        pheader = self.table_payments.horizontalHeader()
        pheader.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        pheader.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        pheader.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_payments.verticalHeader().setVisible(False)
        self.table_payments.setMaximumHeight(220)
        pay_lay.addWidget(self.table_payments)
        sheet.add_section('收费记录（最近 50 条）', pay_lay)

        main_lay.addWidget(mid, 1)

        # ----- 右栏操作面板 -----
        right = QWidget()
        right.setFixedWidth(220)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(12)

        self.btn_add = QPushButton('＋ 新增收费', objectName='primary')
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self.on_add_payment)
        right_lay.addWidget(self.btn_add)

        self.btn_refresh = QPushButton('↻ 刷新', objectName='secondary')
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh)
        right_lay.addWidget(self.btn_refresh)

        note = QLabel(
            '计费口径\n\n'
            '· 课时单价 = 实收 ÷ 已购课时（加权平均）\n'
            '· 应收 = 总课时 × 单价\n'
            '· 已消课费用 = 已上课时 × 单价\n'
            '· 待收 = 应收 − 实收\n\n'
            '录入课时或收费后，切到本页自动刷新。')
        note.setObjectName('hint')
        note.setWordWrap(True)
        note.setStyleSheet('QLabel#hint { color: #6B6B6B; background: transparent; }')
        right_lay.addWidget(note)
        right_lay.addStretch()

        main_lay.addWidget(right)

    #==== 数据 ====

    def set_archive_dir(self, dir_path):
        self._dir_path = dir_path
        self.refresh()

    def get_current_directory(self):
        return self._dir_path

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        """重读课时汇总 + 收费记录，刷新统计卡与两张表。"""
        try:
            if not os.path.isdir(self._dir_path):
                return
            rows = fm.compute_finance(self._dir_path)
            payments = fm.get_payments(self._dir_path)
            totals = fm.compute_totals(rows, payments)
            self._fill_stats(totals)
            self._fill_student_table(rows)
            self._fill_payment_table(payments)
        except Exception:
            import logging
            logging.exception('财务页刷新失败')

    def _fill_stats(self, totals):
        self.stat_paid.lbl_value.setText(_fmt_money(totals['total_paid']))
        self.stat_receivable.lbl_value.setText(_fmt_money(totals['total_receivable']))
        self.stat_due.lbl_value.setText(_fmt_money(totals['total_due']))
        self.stat_month.lbl_value.setText(
            f"{_fmt_money(totals['month_paid'])}（{totals['month_prefix']}）")

    def _fill_student_table(self, rows):
        t = self.table_students
        t.setRowCount(len(rows))
        bold = QFont()
        bold.setBold(True)
        for r, row in enumerate(rows):
            vals = [
                row['name'],
                str(row['total']),
                str(row['attended']),
                _fmt_money(row['unit_price']) if row['unit_price'] else '—',
                _fmt_money(row['consumed']),
                _fmt_money(row['receivable']),
                _fmt_money(row['paid']),
                _fmt_money(row['due']) if row['due'] > 0 else '—',
                row['status'],
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if c == 0:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if c in (4, 5, 6, 7):
                    item.setFont(bold)
                if c == 8:
                    color = _STATUS_COLORS.get(row['status'], '#1A1A1A')
                    item.setForeground(QColor(color))
                    item.setFont(bold)
                t.setItem(r, c, item)

    def _fill_payment_table(self, payments):
        payments = payments[:50]
        t = self.table_payments
        t.setRowCount(len(payments))
        for r, p in enumerate(payments):
            vals = [p['date'], p['name'], _fmt_money(p['amount']),
                    f"{p['hours']:g}", p['method'] or '—']
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignCenter)
                if c == 1:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                t.setItem(r, c, item)
            btn = QPushButton('删除')
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(52, 24)
            btn.setStyleSheet(
                'QPushButton { background: transparent; border: 1px solid #FFD5D5;'
                ' color: #E53E3E; border-radius: 6px; padding: 0;'
                ' font-size: 12px; }'
                'QPushButton:hover { background: #FFF5F5; border-color: #E53E3E; }')
            btn.clicked.connect(lambda _=False, row=p['row']: self.on_del_payment(row))
            t.setCellWidget(r, 5, btn)

    #==== 操作 ====

    def _students(self):
        """学员名单 = 课时汇总里的名字 ∪ 收费记录里的名字。"""
        try:
            from lesson_manager import get_summary
            names = {s['name'] for s in get_summary(self._dir_path)}
            names |= {p['name'] for p in fm.get_payments(self._dir_path)}
            return sorted(names)
        except Exception:
            return []

    def on_add_payment(self):
        dlg = PaymentDialog(self._students(), parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.result_data:
            return
        d = dlg.result_data
        # 2026-09-06 修复：add_payment 对金额/课时数<=0 静默拒绝（返回 False），
        # 此前忽略返回值导致教练以为已入账、记录实际未保存（"收费记录没了"事故）。
        ok = fm.add_payment(self._dir_path, d['name'], d['date'],
                            d['amount'], d['hours'], d['method'], d['note'])
        if not ok:
            from modern_dialog import ModernDialog
            ModernDialog(
                self, title='保存失败',
                text='收费记录未保存：学员、金额、课时数均为必填，且金额和课时数必须大于 0。',
                kind='warning').exec()
            self.refresh()
            return
        self.refresh()

    def on_del_payment(self, row_num):
        from modern_dialog import ModernDialog
        dlg = ModernDialog(self, title='删除收费记录',
                           text='确定删除这条收费记录吗？删除后财务数据自动重算。',
                           kind='warning', ok_text='删除')
        if dlg.exec() != QDialog.Accepted:
            return
        fm.delete_payment(self._dir_path, row_num)
        self.refresh()


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    from theme import LIGHT_QSS
    app.setStyleSheet(LIGHT_QSS)
    w = FinancePage()
    w.resize(1180, 700)
    w.show()
    app.exec()
