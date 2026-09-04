# -*- coding: utf-8 -*-
"""课时信息编辑对话框：修改总课时 + 编辑历史明细。

拆分自 profile_screen.py（P2 超大文件拆分）。
"""
import modern_dialog as dialog
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QGroupBox, QHeaderView, QMessageBox,
)
from base_components import install_row_actions, refresh_row_actions

from profile_dialogs import _LessonRecordEditDialog


class LessonEditDialog(QDialog):
    """课时信息直接编辑弹窗：修改总课时 + 编辑历史明细。

    功能：
    - 顶部：设置/修改总课时
    - 下部：选中学员的历史上课明细表，双击或点击编辑按钮可修改单条记录
    """

    def __init__(self, parent=None, name: str = '', archive_dir: str = '',
                 lesson_mgr=None):
        super().__init__(parent)
        self.setWindowTitle(f'修改课时 - {name}')
        self.resize(720, 560)
        self._name = name
        self._archive_dir = archive_dir
        self._lm = lesson_mgr
        self._loading = False
        self._init_ui()
        self._refresh()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(18, 18, 18, 18)

        # 顶部：课时信息总览 + 修改
        gb_total = QGroupBox('课时信息')
        tl = QGridLayout(gb_total)
        tl.setHorizontalSpacing(16)
        tl.setVerticalSpacing(10)
        tl.setContentsMargins(16, 20, 16, 16)

        # 读取当前课时汇总
        cur = self._get_current_summary()
        cur_total = cur.get('total', 0) if cur else 0
        cur_attended = cur.get('attended', 0) if cur else 0
        cur_remaining = cur.get('remaining', 0) if cur else 0

        # 第一行：只读显示当前状态
        self.lbl_total = QLabel(f'{cur_total}')
        self.lbl_attended = QLabel(f'{cur_attended}')
        self.lbl_remaining = QLabel(f'{cur_remaining}')
        # 剩余<=0 红色，<=5 黄色，>0 正常
        rem_color = '#F87171' if cur_remaining <= 0 else ('#FBBF24' if cur_remaining <= 5 else '#34D399')
        self.lbl_remaining.setStyleSheet(f'font-size:16px; font-weight:bold; color:{rem_color};')
        for lbl in (self.lbl_total, self.lbl_attended):
            lbl.setStyleSheet('font-size:16px; font-weight:bold; color:#1A1A1A;')
        tl.addWidget(QLabel(f'学员：{self._name}'), 0, 0, 1, 2)
        tl.addWidget(QLabel('总课时'), 1, 0)
        tl.addWidget(self.lbl_total, 1, 1)
        tl.addWidget(QLabel('已上课时'), 1, 2)
        tl.addWidget(self.lbl_attended, 1, 3)
        tl.addWidget(QLabel('剩余课时'), 1, 4)
        tl.addWidget(self.lbl_remaining, 1, 5)

        # 第二行：修改总课时
        self.le_total = QLineEdit(str(cur_total) if cur_total else '')
        self.le_total.setPlaceholderText('总课时')
        self.le_total.setMaximumWidth(100)
        btn_set_total = QPushButton('保存总课时', objectName='primary')
        btn_set_total.clicked.connect(self._on_set_total)
        tl.addWidget(QLabel('修改总课时：'), 2, 0)
        tl.addWidget(self.le_total, 2, 1)
        tl.addWidget(btn_set_total, 2, 2)

        # 第三行：修改剩余课时（自动调整总课时 = 已上 + 剩余）
        self.le_remaining = QLineEdit(str(cur_remaining) if cur_remaining else '0')
        self.le_remaining.setPlaceholderText('剩余课时')
        self.le_remaining.setMaximumWidth(100)
        btn_set_rem = QPushButton('保存剩余课时', objectName='primary')
        btn_set_rem.clicked.connect(self._on_set_remaining)
        btn_finish = QPushButton('标记为已上完', objectName='secondary')
        btn_finish.setToolTip('将剩余课时设为 0（总课时 = 已上课时）')
        btn_finish.clicked.connect(self._on_mark_finished)
        tl.addWidget(QLabel('修改剩余课时：'), 3, 0)
        tl.addWidget(self.le_remaining, 3, 1)
        tl.addWidget(btn_set_rem, 3, 2)
        tl.addWidget(btn_finish, 3, 3)
        lay.addWidget(gb_total)

        # 明细表
        lay.addWidget(QLabel('上课明细（双击行可编辑）'))
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(7)
        self.tbl.setHorizontalHeaderLabels(['行号', '序号', '日期', '学员', '课时数', '训练内容', '备注'])
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.tbl.doubleClicked.connect(self._on_edit_record)
        install_row_actions(self.tbl, [
            ('编辑', lambda t, r: self._on_edit_record(r)),
            ('删除', lambda t, r: self._on_del_record(r)),
        ])
        lay.addWidget(self.tbl, 1)

        # 底部操作
        btn_lay = QHBoxLayout()
        self.btn_edit = QPushButton('编辑选中记录', objectName='secondary')
        self.btn_edit.clicked.connect(self._on_edit_record)
        self.btn_del = QPushButton('删除选中记录', objectName='danger')
        self.btn_del.clicked.connect(self._on_del_record)
        self.btn_close = QPushButton('关闭')
        self.btn_close.clicked.connect(self.accept)
        btn_lay.addWidget(self.btn_edit)
        btn_lay.addWidget(self.btn_del)
        btn_lay.addStretch()
        btn_lay.addWidget(self.btn_close)
        lay.addLayout(btn_lay)

    def _get_current_summary(self) -> dict:
        """从汇总数据中获取当前学员的课时汇总。"""
        try:
            if hasattr(self._lm, 'get_lesson_summary'):
                return self._lm.get_lesson_summary(self._archive_dir, self._name)
            # 兼容旧版本：从 get_summary 中筛选
            data = self._lm.get_summary(self._archive_dir)
            for d in data:
                if d['name'] == self._name:
                    return d
        except Exception:
            pass
        return None

    def _refresh_top_labels(self):
        """刷新顶部课时信息显示。"""
        cur = self._get_current_summary()
        if not cur:
            return
        total = cur.get('total', 0)
        attended = cur.get('attended', 0)
        remaining = cur.get('remaining', 0)
        self.lbl_total.setText(f'{total}')
        self.lbl_attended.setText(f'{attended}')
        self.lbl_remaining.setText(f'{remaining}')
        rem_color = '#F87171' if remaining <= 0 else ('#FBBF24' if remaining <= 5 else '#34D399')
        self.lbl_remaining.setStyleSheet(f'font-size:16px; font-weight:bold; color:{rem_color};')
        # 同步输入框
        self.le_total.setText(str(total) if total else '')
        self.le_remaining.setText(str(remaining) if remaining else '0')

    def _refresh(self):
        """刷新明细表 + 顶部课时信息。"""
        self._loading = True
        self.tbl.setSortingEnabled(False)  # 填充期间禁用排序，避免行错乱
        try:
            data = self._lm.get_detail(self._archive_dir, self._name)
            self.tbl.setRowCount(0)
            for i, d in enumerate(data):
                self.tbl.insertRow(i)
                vals = [d.get('row', ''), d.get('seq', ''), d.get('date', ''),
                        d.get('name', ''), d.get('count', ''),
                        d.get('content', ''), d.get('note', '')]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setTextAlignment(Qt.AlignCenter)
                    self.tbl.setItem(i, j, item)
        finally:
            self._loading = False
        self.tbl.setSortingEnabled(True)  # 列头点击排序
        refresh_row_actions(self.tbl)
        # 同步刷新顶部课时信息
        self._refresh_top_labels()

    def _selected_row_num(self, row=None):
        if row is None:
            rows = self.tbl.selectionModel().selectedRows()
            if not rows:
                return None
            row = rows[0].row()
        try:
            return int(self.tbl.item(row, 0).text())
        except (ValueError, AttributeError):
            return None

    def _on_set_total(self):
        """保存总课时。"""
        try:
            total = int(self.le_total.text().strip())
            if total < 0:
                raise ValueError
        except ValueError:
            dialog.warn(self, '提示', '总课时请输入非负整数')
            return
        self._lm.set_total_lessons(self._archive_dir, self._name, total)
        dialog.info(self, '成功', f'已设置 {self._name} 总课时为 {total}')
        self._refresh()

    def _on_set_remaining(self):
        """保存剩余课时（自动调整总课时 = 已上 + 剩余）。

        适用场景：教练已上完若干节课但未录入明细，或需直接校正剩余课时数。
        通过反算总课时保持数据一致性，不影响明细记录的已上课时统计。
        """
        try:
            remaining = int(self.le_remaining.text().strip())
            if remaining < 0:
                raise ValueError
        except ValueError:
            dialog.warn(self, '提示', '剩余课时请输入非负整数')
            return
        # 获取当前已上课时
        cur = self._get_current_summary()
        attended = cur.get('attended', 0) if cur else 0
        new_total = attended + remaining
        reply = dialog.confirm(
            self, '确认修改剩余课时',
            f'当前已上课时：{attended}\n'
            f'设置剩余课时：{remaining}\n'
            f'将自动调整总课时为：{new_total}\n\n确认保存？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if not reply:
            return
        try:
            if hasattr(self._lm, 'set_remaining_lessons'):
                self._lm.set_remaining_lessons(self._archive_dir, self._name, remaining)
            else:
                # 兼容旧版本：直接设置总课时
                self._lm.set_total_lessons(self._archive_dir, self._name, new_total)
            dialog.info(self, '成功',
                                    f'已设置剩余课时为 {remaining}\n总课时自动调整为 {new_total}')
            self._refresh()
        except Exception as e:
            dialog.error(self, '保存失败', str(e))

    def _on_mark_finished(self):
        """标记为已上完：将剩余课时设为 0（总课时 = 已上课时）。

        适用场景：学员课程已全部结束，一键归零剩余课时，避免继续出现在预警列表。
        """
        cur = self._get_current_summary()
        if not cur:
            dialog.warn(self, '失败', '无法读取当前课时信息')
            return
        attended = cur.get('attended', 0)
        remaining = cur.get('remaining', 0)
        if remaining == 0:
            dialog.info(self, '提示', '剩余课时已为 0，无需操作')
            return
        reply = dialog.confirm(
            self, '确认标记为已上完',
            f'当前已上课时：{attended}\n当前剩余课时：{remaining}\n\n'
            f'将把剩余课时归零，总课时调整为 {attended}。\n'
            f'操作后该学员将不再出现在续费预警列表中。\n\n确认操作？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if not reply:
            return
        try:
            if hasattr(self._lm, 'set_remaining_lessons'):
                self._lm.set_remaining_lessons(self._archive_dir, self._name, 0)
            else:
                self._lm.set_total_lessons(self._archive_dir, self._name, attended)
            dialog.info(self, '已标记',
                                    f'已将 {self._name} 标记为已上完\n总课时调整为 {attended}，剩余课时为 0')
            self._refresh()
        except Exception as e:
            dialog.error(self, '操作失败', str(e))

    def _on_edit_record(self, row=None):
        """编辑选中的明细记录（row 为空时取当前选中行）。"""
        row_num = self._selected_row_num(row)
        if row_num is None:
            dialog.info(self, '提示', '请先选中要编辑的记录')
            return
        rec = self._lm.get_lesson_by_row(self._archive_dir, row_num)
        if not rec:
            dialog.warn(self, '失败', '记录读取失败')
            return
        dlg = _LessonRecordEditDialog(self, record=rec)
        if dlg.exec() == QDialog.Accepted:
            try:
                self._lm.update_lesson(
                    self._archive_dir, row_num,
                    date=dlg.date_str,
                    count=dlg.count,
                    content=dlg.content,
                    note=dlg.note,
                )
                self._refresh()
                dialog.info(self, '已修改', '记录已更新')
            except Exception as e:
                dialog.error(self, '修改失败', str(e))

    def _on_del_record(self, row=None):
        """删除选中的明细记录（row 为空时取当前选中行）。"""
        row_num = self._selected_row_num(row)
        if row_num is None:
            dialog.info(self, '提示', '请先选中要删除的记录')
            return
        ret = dialog.confirm(self, '确认删除',
                                   '确定删除该条上课记录？\n删除后已上课时将回退。')
        if not ret:
            return
        if self._lm.delete_lesson(self._archive_dir, row_num):
            self._refresh()
            dialog.info(self, '已删除', '记录已删除，课时已回退。')
        else:
            dialog.warn(self, '失败', '删除失败，行号无效。')
