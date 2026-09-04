# -*- coding: utf-8 -*-
"""UI 层：课时管理独立窗口。

职责：界面交互与状态展示，业务逻辑委托 lesson_manager。
功能：
- 汇总表：所有学员的总课时/已上课时/剩余课时一览
- 明细表：选中学员的历次上课记录
- 设置总课时、记录上课、删除记录、同步学员
"""
import modern_dialog as dialog
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDateEdit, QTextEdit, QGroupBox, QSplitter, QFrame
)
import lesson_manager as lm
from base_components import install_row_actions, refresh_row_actions


class LessonWindow(QWidget):
    """课时管理窗口。"""

    def __init__(self, dir_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle('课时记录管理')
        self.resize(960, 720)
        self._dir_path = dir_path
        self._loading = False
        self._init_ui()
        self.refresh_all()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        # 标题
        title = QLabel('课时记录管理')
        _f = QFont('微软雅黑'); _f.setPointSize(16); _f.setBold(True)
        title.setFont(_f)
        title.setStyleSheet('color:#FF6B47;')
        lay.addWidget(title)

        # 工具栏
        toolbar = QHBoxLayout()
        self.btn_sync = QPushButton('同步学员名单', objectName='secondary')
        self.btn_sync.clicked.connect(self.on_sync)
        self.btn_refresh = QPushButton('刷新', objectName='secondary')
        self.btn_refresh.clicked.connect(self.refresh_all)
        self.btn_open = QPushButton('打开文件', objectName='secondary')
        self.btn_open.clicked.connect(self.on_open_file)
        toolbar.addWidget(self.btn_sync)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_open)
        lay.addLayout(toolbar)

        # 主体：左右分栏
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：汇总表
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel('学员课时汇总（点击行查看明细）'))
        self.tbl_summary = QTableWidget()
        self.tbl_summary.setAlternatingRowColors(True)
        self.tbl_summary.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_summary.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_summary.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_summary.itemSelectionChanged.connect(self.on_summary_select)
        ll.addWidget(self.tbl_summary, 1)

        # 左侧底部：设置总课时
        gb_total = QGroupBox('设置 / 修改总课时')
        ftl = QHBoxLayout(gb_total)
        self.cb_total_name = QComboBox()
        self.le_total = QLineEdit(placeholderText='总课时数')
        self.btn_set_total = QPushButton('保存')
        self.btn_set_total.clicked.connect(self.on_set_total)
        ftl.addWidget(QLabel('学员：'))
        ftl.addWidget(self.cb_total_name, 1)
        ftl.addWidget(self.le_total)
        ftl.addWidget(self.btn_set_total)
        ll.addWidget(gb_total)
        splitter.addWidget(left)

        # 右侧：明细 + 记录上课
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.lbl_detail_title = QLabel('上课明细（全部学员）')
        self.lbl_detail_title.setStyleSheet('color:#FF6B47; font-weight:bold;')
        rl.addWidget(self.lbl_detail_title)
        self.tbl_detail = QTableWidget()
        self.tbl_detail.setAlternatingRowColors(True)
        self.tbl_detail.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_detail.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_detail.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        install_row_actions(self.tbl_detail, [
            ('编辑', lambda t, r: self._edit_detail_row(r)),
            ('删除', lambda t, r: self._del_detail_row(r)),
        ])
        rl.addWidget(self.tbl_detail, 1)

        # 记录上课区
        gb_add = QGroupBox('记录一次上课')
        form = QFormLayout(gb_add)
        form.setSpacing(6)
        self.cb_add_name = QComboBox()
        self.dte_add = QDateEdit(QDate.currentDate())
        self.dte_add.setCalendarPopup(True)
        self.dte_add.setDisplayFormat('yyyy-MM-dd')
        self.le_count = QLineEdit('1')
        self.le_content = QLineEdit(placeholderText='如：体能训练、跳绳强化、中考模拟...')
        self.le_note = QLineEdit(placeholderText='备注（选填）')
        self.btn_add = QPushButton('确认记录（扣减课时）')
        self.btn_add.clicked.connect(self.on_add_lesson)
        self.btn_del = QPushButton('删除选中记录', objectName='secondary')
        self.btn_del.clicked.connect(self.on_del_lesson)
        form.addRow('学员：', self.cb_add_name)
        form.addRow('上课日期：', self.dte_add)
        form.addRow('本次课时：', self.le_count)
        form.addRow('训练内容：', self.le_content)
        form.addRow('备注：', self.le_note)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        form.addRow(btn_row)
        rl.addWidget(gb_add)

        splitter.addWidget(right)
        splitter.setSizes([420, 540])
        lay.addWidget(splitter, 1)

    # ---------- 数据刷新 ----------
    def refresh_all(self):
        """刷新汇总表、明细表、学员下拉。"""
        self._loading = True
        try:
            self._refresh_summary()
            self._refresh_detail()
            self._refresh_combos()
        finally:
            self._loading = False

    def _refresh_summary(self):
        data = lm.get_summary(self._dir_path)
        headers = ['学员', '总课时', '已上课时', '剩余课时', '状态', '最近上课', '备注']
        self.tbl_summary.setColumnCount(len(headers))
        self.tbl_summary.setHorizontalHeaderLabels(headers)
        self.tbl_summary.setSortingEnabled(False)
        self.tbl_summary.setRowCount(len(data))
        for i, d in enumerate(data):
            self._set_cell(self.tbl_summary, i, 0, d['name'])
            self._set_cell(self.tbl_summary, i, 1, d['total'])
            self._set_cell(self.tbl_summary, i, 2, d['attended'])
            remaining = d['remaining']
            # 剩余课时：红色=用完，绿色=未用完，灰色=未设总课时
            rem_item = QTableWidgetItem(str(remaining))
            if d['total'] > 0 and remaining <= 0:
                rem_item.setForeground(QColor('#ff6b6b'))
            elif remaining > 0:
                rem_item.setForeground(QColor('#51cf66'))
            self.tbl_summary.setItem(i, 3, rem_item)
            # 状态列：明确标注
            if d['total'] <= 0:
                status = '未设置'
                status_color = '#9B9B9B'
            elif remaining <= 0:
                status = '已用完'
                status_color = '#ff6b6b'
            elif d['attended'] > 0:
                status = '进行中'
                status_color = '#4a9eff'
            else:
                status = '未开始'
                status_color = '#9B9B9B'
            st_item = QTableWidgetItem(status)
            st_item.setForeground(QColor(status_color))
            self.tbl_summary.setItem(i, 4, st_item)
            self._set_cell(self.tbl_summary, i, 5, d['last_date'])
            self._set_cell(self.tbl_summary, i, 6, d['note'])
        self.tbl_summary.setSortingEnabled(True)

    def _refresh_detail(self):
        # 显示选中学员的明细，无选中则显示全部
        name = self._selected_summary_name()
        if name:
            data = lm.get_detail(self._dir_path, name)
            self.lbl_detail_title.setText(f'{name} 的上课明细（共 {len(data)} 次）')
        else:
            data = lm.get_detail(self._dir_path)
            self.lbl_detail_title.setText(f'上课明细（全部学员，共 {len(data)} 次）')
        headers = ['行号', '序号', '日期', '学员', '课时数', '训练内容', '备注']
        self.tbl_detail.setColumnCount(len(headers))
        self.tbl_detail.setHorizontalHeaderLabels(headers)
        self.tbl_detail.setSortingEnabled(False)
        self.tbl_detail.setRowCount(len(data))
        for i, d in enumerate(data):
            self._set_cell(self.tbl_detail, i, 0, d['row'])
            self._set_cell(self.tbl_detail, i, 1, d['seq'])
            self._set_cell(self.tbl_detail, i, 2, d['date'])
            self._set_cell(self.tbl_detail, i, 3, d['name'])
            self._set_cell(self.tbl_detail, i, 4, d['count'])
            self._set_cell(self.tbl_detail, i, 5, d['content'])
            self._set_cell(self.tbl_detail, i, 6, d['note'])
        self.tbl_detail.setSortingEnabled(True)
        refresh_row_actions(self.tbl_detail)

    def _refresh_combos(self):
        data = lm.get_summary(self._dir_path)
        names = [d['name'] for d in data]
        for cb in (self.cb_total_name, self.cb_add_name):
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(names)
            if cur in names:
                cb.setCurrentText(cur)
            cb.blockSignals(False)

    def _set_cell(self, table, row, col, value):
        table.setItem(row, col, QTableWidgetItem(str(value)))

    def _selected_summary_name(self):
        rows = self.tbl_summary.selectionModel().selectedRows()
        if not rows:
            return None
        return self.tbl_summary.item(rows[0].row(), 0).text()

    def _selected_detail_row(self):
        rows = self.tbl_detail.selectionModel().selectedRows()
        if not rows:
            return None
        return int(self.tbl_detail.item(rows[0].row(), 0).text())

    # ---------- 事件处理 ----------
    def on_summary_select(self):
        if self._loading:
            return
        self._refresh_detail()
        name = self._selected_summary_name()
        if name:
            idx = self.cb_add_name.findText(name)
            if idx >= 0:
                self.cb_add_name.setCurrentIndex(idx)

    def on_sync(self):
        added = lm.sync_students(self._dir_path)
        self.refresh_all()
        dialog.info(self, '同步完成', f'从档案目录同步学员，新增 {added} 名。')

    def on_set_total(self):
        name = self.cb_total_name.currentText().strip()
        if not name:
            dialog.warn(self, '提示', '请选择学员')
            return
        try:
            total = int(self.le_total.text().strip())
            if total < 0:
                raise ValueError
        except ValueError:
            dialog.warn(self, '提示', '总课时请输入非负整数')
            return
        lm.set_total_lessons(self._dir_path, name, total)
        self.le_total.clear()
        self.refresh_all()
        dialog.info(self, '成功', f'已设置 {name} 总课时为 {total}')

    def on_add_lesson(self):
        name = self.cb_add_name.currentText().strip()
        if not name:
            dialog.warn(self, '提示', '请选择学员')
            return
        try:
            count = int(self.le_count.text().strip())
            if count <= 0:
                raise ValueError
        except ValueError:
            dialog.warn(self, '提示', '课时数请输入正整数')
            return
        date = self.dte_add.date().toString('yyyy-MM-dd')
        content = self.le_content.text().strip()
        note = self.le_note.text().strip()
        lm.add_lesson(self._dir_path, name, date, count, content, note)
        self.le_content.clear()
        self.le_note.clear()
        self.refresh_all()
        # 选中刚记录的学员行，联动明细表只显示该学员记录
        for r in range(self.tbl_summary.rowCount()):
            item = self.tbl_summary.item(r, 0)
            if item and item.text() == name:
                self.tbl_summary.selectRow(r)
                break
        # 提示剩余
        data = lm.get_summary(self._dir_path)
        for d in data:
            if d['name'] == name:
                if d['total'] > 0 and d['remaining'] <= 0:
                    dialog.warn(self, '课时不足',
                                        f'{name} 课时已用完！总课时 {d["total"]}，已上 {d["attended"]}。')
                else:
                    dialog.info(self, '记录成功',
                                            f'{name} 本次记录 {count} 课时\n剩余 {d["remaining"]} 课时')
                break

    def on_del_lesson(self):
        row = self._selected_detail_row()
        if row is None:
            dialog.warn(self, '提示', '请先在明细表选中要删除的记录')
            return
        ret = dialog.confirm(self, '确认删除', '确定删除该条上课记录？\n删除后已上课时将回退。')
        if not ret:
            return
        if lm.delete_lesson(self._dir_path, row):
            self.refresh_all()
            dialog.info(self, '已删除', '记录已删除，课时已回退。')
        else:
            dialog.warn(self, '失败', '删除失败，行号无效。')

    def _detail_row_num(self, row: int):
        """读取明细表指定视觉行的行号（行号列）。"""
        try:
            return int(self.tbl_detail.item(row, 0).text())
        except (TypeError, ValueError, AttributeError):
            return None

    def _edit_detail_row(self, row: int):
        """操作列按钮：编辑指定明细行。"""
        row_num = self._detail_row_num(row)
        if row_num is None:
            return
        rec = lm.get_lesson_by_row(self._dir_path, row_num)
        if not rec:
            dialog.warn(self, '失败', '记录读取失败')
            return
        from PySide6.QtWidgets import QDialog, QFormLayout, QDateEdit
        from PySide6.QtCore import QDate
        dlg = QDialog(self)
        dlg.setWindowTitle(f'编辑上课记录（第 {row_num} 行）')
        dlg.resize(420, 220)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setSpacing(10)
        dte = QDateEdit()
        dte.setCalendarPopup(True)
        dte.setDisplayFormat('yyyy-MM-dd')
        try:
            y, m, d = str(rec.get('date', '')).split('-')
            dte.setDate(QDate(int(y), int(m), int(d)))
        except Exception:
            dte.setDate(QDate.currentDate())
        le_count = QLineEdit(str(rec.get('count', 1)))
        le_content = QLineEdit(str(rec.get('content', '')))
        le_note = QLineEdit(str(rec.get('note', '')))
        form.addRow('上课日期：', dte)
        form.addRow('本次课时：', le_count)
        form.addRow('训练内容：', le_content)
        form.addRow('备注：', le_note)
        lay.addLayout(form)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton('取消', objectName='secondary')
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton('保存', objectName='primary')
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            count = int(le_count.text().strip())
            if count <= 0:
                raise ValueError
        except ValueError:
            dialog.warn(self, '提示', '课时数请输入正整数')
            return
        try:
            lm.update_lesson(
                self._dir_path, row_num,
                date=dte.date().toString('yyyy-MM-dd'),
                count=count,
                content=le_content.text().strip(),
                note=le_note.text().strip(),
            )
            self.refresh_all()
            dialog.info(self, '已修改', '记录已更新')
        except Exception as e:
            dialog.error(self, '修改失败', str(e))

    def _del_detail_row(self, row: int):
        """操作列按钮：删除指定明细行。"""
        row_num = self._detail_row_num(row)
        if row_num is None:
            return
        ret = dialog.confirm(self, '确认删除', '确定删除该条上课记录？\n删除后已上课时将回退。')
        if not ret:
            return
        if lm.delete_lesson(self._dir_path, row_num):
            self.refresh_all()
            dialog.info(self, '已删除', '记录已删除，课时已回退。')
        else:
            dialog.warn(self, '失败', '删除失败，行号无效。')

    def on_open_file(self):
        import os
        fpath = lm._lesson_file_path(self._dir_path)
        if os.path.exists(fpath):
            os.startfile(fpath)
        else:
            dialog.info(self, '提示', '课时记录文件尚未创建。')
