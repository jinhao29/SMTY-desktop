# -*- coding: utf-8 -*-
"""UI 层：单次训练任务单 + 动作库弹窗（灰白简约 · 蓝紫强调，对齐图2）。

职责：
- 界面交互、状态管理
- 区块编辑、动作增删改、上下移
- 智能推荐：委托 plan_coordinator 完成业务编排

布局（三列，由外层 main 三列壳提供右列操作面板）：
- 左列：训练任务列表（Card，每项 = 日期 + 区块标题，选中高亮 + 编辑图标）
- 中列（可滚动）：
    · 当日编排头部卡（日期·训练课 + 核心内容大标题 + 时长/器材标签）
    · 基本信息卡
    · 训练内容卡（动作增删改 + 表格）
    · 寄语与备注卡

所有数据模型交互（blocks / tasks / collect_plan / refresh_students / 推荐）保持不变。
区块切换通过隐藏的 cb_block 复用既有 on_block_changed 逻辑，左列列表仅为其可视化前端。
"""
import modern_dialog as dialog
import os
import logging
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
    QMessageBox, QDateEdit, QDialog, QFrame, QScrollArea, QGridLayout,
    QListWidget, QListWidgetItem, QInputDialog, QSizePolicy
)
from exercise_library import list_categories, list_exercises
from task_model import Block, Task, SinglePlan
import summary_processor
import plan_coordinator

# 新设计语言组件
from styles import Palette, Radius, Spacing, Type
from cards import Card, Tag, TagInput, SectionTitle, TaskListItem, IconButton
from base_components import FormSheet


_WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


class ExercisePickerDialog(QDialog):
    """动作库选择弹窗（公共组件，使用新卡片样式）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('从动作库选择')
        self.resize(720, 560)
        self._selected = []
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        title = QLabel('动作库')
        title.setFont(Type.page_title())
        title.setStyleSheet(f'color: {Palette.TEXT}; background: transparent;')
        lay.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(16)

        # 左：分类
        cat_card = Card('分类')
        cat_lay = QVBoxLayout()
        cat_lay.setContentsMargins(0, 0, 0, 0)
        cat_lay.setSpacing(8)
        self.lw_cat = QListWidget()
        for cat in list_categories():
            self.lw_cat.addItem(QListWidgetItem(cat))
        self.lw_cat.currentRowChanged.connect(self.on_cat_changed)
        cat_lay.addWidget(self.lw_cat, 1)
        cat_card.set_content_layout(cat_lay)
        body.addWidget(cat_card, 1)

        # 右：动作
        ex_card = Card('动作（双击加入）')
        ex_lay = QVBoxLayout()
        ex_lay.setContentsMargins(0, 0, 0, 0)
        ex_lay.setSpacing(8)
        self.lw_ex = QListWidget()
        self.lw_ex.itemDoubleClicked.connect(self.on_add)
        ex_lay.addWidget(self.lw_ex, 1)
        ex_card.set_content_layout(ex_lay)
        body.addWidget(ex_card, 2)

        lay.addLayout(body, 1)

        # 已选列表
        sel_card = Card('已选动作')
        sel_lay = QVBoxLayout()
        sel_lay.setContentsMargins(0, 0, 0, 0)
        sel_lay.setSpacing(8)
        sel_header = QHBoxLayout()
        sel_header.addStretch()
        btn_clear = QPushButton('清空', objectName='secondary')
        btn_clear.clicked.connect(self.on_clear)
        sel_header.addWidget(btn_clear)
        sel_lay.addLayout(sel_header)
        self.lw_sel = QListWidget()
        self.lw_sel.setMinimumHeight(120)
        sel_lay.addWidget(self.lw_sel)
        sel_card.set_content_layout(sel_lay)
        lay.addWidget(sel_card)

        # 底部按钮
        btn_w = QHBoxLayout()
        btn_w.addStretch()
        btn_cancel = QPushButton('取消', objectName='secondary')
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton('加入训练单', objectName='primary')
        btn_ok.clicked.connect(self.accept)
        btn_w.addWidget(btn_cancel)
        btn_w.addWidget(btn_ok)
        lay.addLayout(btn_w)

    def on_cat_changed(self, row):
        if row < 0:
            return
        cat = self.lw_cat.item(row).text()
        self.lw_ex.clear()
        for ex in list_exercises(cat):
            it = QListWidgetItem(f"{ex[0]}    {ex[1]}组 × {ex[2]}    {ex[3]}")
            it.setToolTip(f"{ex[3]}")
            it.setData(Qt.UserRole, (ex[0], ex[1], ex[2], ex[3]))
            self.lw_ex.addItem(it)

    def on_add(self, item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        self._selected.append(data)
        self.lw_sel.addItem(QListWidgetItem(f"{data[0]}  -  {data[1]}组 × {data[2]}"))

    def on_clear(self):
        self._selected.clear()
        self.lw_sel.clear()

    def get_selected(self):
        return self._selected


class SingleTab(QWidget):
    """单次训练任务单编辑（灰白卡片式三列布局）。

    左列：训练任务列表（区块导航）
    中列：当日编排头部 + 基本信息 + 训练内容 + 寄语与备注
    右列：由外层 main 提供操作面板
    """

    def __init__(self, archive_dir_getter=None, parent=None):
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        self._blocks, self._default_count = plan_coordinator.load_initial_blocks()
        self._cur_block_idx = 0
        self._task_items = []
        self._init_ui()
        self._refresh_blocks()
        self._persist()

    def _init_ui(self):
        main_lay = QHBoxLayout(self)
        main_lay.setSpacing(Spacing.CARD)
        main_lay.setContentsMargins(0, 0, 0, 0)

        # ==================== 左列：训练任务列表 ====================
        left_card = Card('训练任务')
        left_card.setMinimumWidth(200)
        left_card.setMaximumWidth(240)
        left_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_lay = QVBoxLayout()
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(Spacing.SM)

        # 新增区块按钮
        self.btn_add_block = QPushButton('＋ 新增区块', objectName='primary')
        self.btn_add_block.setCursor(Qt.PointingHandCursor)
        self.btn_add_block.setMinimumHeight(34)
        self.btn_add_block.clicked.connect(self.on_add_block)
        left_lay.addWidget(self.btn_add_block)

        # 任务列表（可滚动）
        list_scroll = QScrollArea()
        list_scroll.setWidgetResizable(True)
        list_scroll.setFrameShape(QFrame.NoFrame)
        list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        list_content = QWidget()  # 透明背景由 TRAINING_QSS 全局规则提供（裸声明会压掉按钮背景）
        self._task_list_lay = QVBoxLayout(list_content)
        self._task_list_lay.setContentsMargins(0, 0, 0, 0)
        self._task_list_lay.setSpacing(6)
        self._task_list_lay.addStretch()
        list_scroll.setWidget(list_content)
        left_lay.addWidget(list_scroll, 1)

        # 区块管理按钮（重命名 / 删除）
        mgr_row = QHBoxLayout()
        mgr_row.setSpacing(8)
        self.btn_rename_block = QPushButton('✎ 重命名', objectName='secondary')
        self.btn_rename_block.setCursor(Qt.PointingHandCursor)
        self.btn_rename_block.setMinimumHeight(30)
        self.btn_rename_block.clicked.connect(self.on_rename_block)
        self.btn_del_block = QPushButton('删除', objectName='danger')
        self.btn_del_block.setCursor(Qt.PointingHandCursor)
        self.btn_del_block.setMinimumHeight(30)
        self.btn_del_block.setEnabled(False)
        self.btn_del_block.clicked.connect(self.on_del_block)
        mgr_row.addWidget(self.btn_rename_block)
        mgr_row.addWidget(self.btn_del_block)
        left_lay.addLayout(mgr_row)

        left_card.set_content_layout(left_lay)
        main_lay.addWidget(left_card)

        # ==================== 中列：可滚动主内容 ====================
        # v23.5 修复：横向滚动条按需出现（此前 AlwaysOff 导致窄窗口下内容被静默裁切）
        mid_scroll = QScrollArea()
        mid_scroll.setWidgetResizable(True)
        mid_scroll.setFrameShape(QFrame.NoFrame)
        mid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        mid_scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        mid_content = QWidget()  # 透明背景由 TRAINING_QSS 全局规则提供（裸声明会压掉按钮背景）
        mid_lay = QVBoxLayout(mid_content)
        mid_lay.setSpacing(Spacing.CARD)
        mid_lay.setContentsMargins(0, 0, 0, 0)

        # ---------- 连续版面（v25：单张白纸分节，替代多卡框套框） ----------
        sheet = FormSheet()

        hl = QVBoxLayout()
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.MD)
        # 日期 + 训练课
        self._lbl_session = QLabel('训练课')
        self._lbl_session.setFont(Type.caption())
        self._lbl_session.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        hl.addWidget(self._lbl_session)
        # 核心内容大标题
        self._lbl_hero = QLabel('训练核心内容')
        self._lbl_hero.setObjectName('hero')
        self._lbl_hero.setFont(Type.hero())
        self._lbl_hero.setStyleSheet(f'color: {Palette.TEXT}; background: transparent;')
        self._lbl_hero.setWordWrap(True)
        hl.addWidget(self._lbl_hero)
        # 标签行：训练时长 + 器材
        tag_row = QHBoxLayout()
        tag_row.setSpacing(Spacing.SM)
        lbl_dur = Tag('训练时长')
        self.le_duration = TagInput(placeholder='如 55分钟')
        lbl_eq = Tag('器材')
        self.le_equipment = TagInput(placeholder='如 绳梯1个、垫子1个、标志桶2个')
        tag_row.addWidget(lbl_dur)
        tag_row.addWidget(self.le_duration)
        tag_row.addSpacing(8)
        tag_row.addWidget(lbl_eq)
        tag_row.addWidget(self.le_equipment, 1)
        tag_row.addStretch()
        hl.addLayout(tag_row)
        sheet.add_section(None, hl)

        # ---------- 基本信息节 ----------
        gl = QGridLayout()
        gl.setHorizontalSpacing(14)
        gl.setVerticalSpacing(14)
        gl.setContentsMargins(0, 0, 0, 0)

        self.cb_name = QComboBox()
        self.cb_name.setEditable(True)
        self.cb_name.setPlaceholderText('学员姓名（可下拉选择或手动输入）')
        self.cb_gender = QComboBox(); self.cb_gender.addItems(['男', '女'])
        self.le_age = QLineEdit(placeholderText='如 12岁')
        self.le_coach = QLineEdit(placeholderText='教练姓名')
        self.dte_date = QDateEdit(QDate.currentDate())
        self.dte_date.setCalendarPopup(True)
        self.dte_date.setDisplayFormat('yyyy-MM-dd')
        self.le_loc = QLineEdit(placeholderText='如 深圳体育中心')
        self.le_goal = QLineEdit(placeholderText='如 增强上肢力量与核心稳定性')

        # v25: 2 字段/行（4 字段/行在中列 ~560px 宽度下横向裁切）
        _rows = [
            [('姓名', self.cb_name), ('性别', self.cb_gender)],
            [('年龄', self.le_age), ('教练', self.le_coach)],
            [('训练日期', self.dte_date), ('训练地点', self.le_loc)],
        ]
        for r, pairs in enumerate(_rows):
            for c, (lab, w) in enumerate(pairs):
                lbl = QLabel(lab)
                lbl.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
                gl.addWidget(lbl, r, c * 2)
                gl.addWidget(w, r, c * 2 + 1)
        lbl_goal = QLabel('训练目标')
        lbl_goal.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        gl.addWidget(lbl_goal, 3, 0)
        gl.addWidget(self.le_goal, 3, 1)
        self.btn_recommend = QPushButton('智能推荐', objectName='recommend')
        self.btn_recommend.setToolTip('根据学员年龄自动匹配对应年龄段教案，推荐训练内容（可在此基础上自定义）')
        self.btn_recommend.setMinimumWidth(120)
        self.btn_recommend.setCursor(Qt.PointingHandCursor)
        self.btn_recommend.clicked.connect(self.on_recommend_single)
        gl.addWidget(self.btn_recommend, 3, 2, 1, 2)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(3, 1)
        sheet.add_section('基本信息', gl)

        # ---------- 训练内容节 ----------
        cl = QVBoxLayout()
        cl.setSpacing(Spacing.MD)
        cl.setContentsMargins(0, 0, 0, 0)

        # 隐藏的区块下拉（保留以复用 on_block_changed 逻辑，左列列表为其可视化前端）
        self.cb_block = QComboBox()
        self.cb_block.setVisible(False)
        self.cb_block.currentIndexChanged.connect(self.on_block_changed)
        cl.addWidget(self.cb_block)

        # 动作按钮栏
        action_bar = QHBoxLayout()
        action_bar.setSpacing(Spacing.SM)
        self.btn_pick = QPushButton('从动作库添加', objectName='primary')
        self.btn_pick.setCursor(Qt.PointingHandCursor)
        self.btn_pick.clicked.connect(self.on_pick_exercise)
        self.btn_add_custom = QPushButton('+ 自定义动作', objectName='primary')
        self.btn_add_custom.setCursor(Qt.PointingHandCursor)
        self.btn_add_custom.clicked.connect(self.on_add_custom)
        action_bar.addWidget(self.btn_pick)
        action_bar.addWidget(self.btn_add_custom)
        action_bar.addStretch()
        # v25: 顶部「删除选中行」移除——表格操作列每行已有删除按钮，冗余且撑宽按钮行
        self.btn_up = QPushButton('↑ 上移', objectName='secondary')
        self.btn_up.setCursor(Qt.PointingHandCursor)
        self.btn_dn = QPushButton('↓ 下移', objectName='secondary')
        self.btn_dn.setCursor(Qt.PointingHandCursor)
        self.btn_up.clicked.connect(lambda: self._move_task(-1))
        self.btn_dn.clicked.connect(lambda: self._move_task(1))
        action_bar.addWidget(self.btn_up)
        action_bar.addWidget(self.btn_dn)
        cl.addLayout(action_bar)

        # 任务表
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['动作名称', '组数', '次数/时长', '要点提示', '操作'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        # v26.1：操作列固定宽（ResizeToContents 在窗口变窄时会被压缩，按钮文字竖排截断）
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 84)
        self.table.setMinimumHeight(280)
        self.table.setAlternatingRowColors(True)
        cl.addWidget(self.table)
        sheet.add_section('训练内容', cl, stretch=1)

        # ---------- 寄语与备注节 ----------
        rl = QVBoxLayout()
        rl.setSpacing(14)
        rl.setContentsMargins(0, 0, 0, 0)

        r1 = QHBoxLayout()
        lab_note = QLabel('教练寄语')
        lab_note.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        r1.addWidget(lab_note, 0, Qt.AlignTop)
        self.te_note = QTextEdit(placeholderText='对学员的鼓励、训练总结...')
        self.te_note.setMinimumHeight(70)
        r1.addWidget(self.te_note, 1)
        rl.addLayout(r1)

        r2 = QHBoxLayout()
        lab_rem = QLabel('注意事项')
        lab_rem.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        r2.addWidget(lab_rem, 0, Qt.AlignTop)
        self.te_remarks = QTextEdit(placeholderText='训练前热身、器材准备、安全提示...')
        self.te_remarks.setMinimumHeight(70)
        r2.addWidget(self.te_remarks, 1)
        rl.addLayout(r2)

        r3 = QHBoxLayout()
        lab_next = QLabel('下次课预告')
        lab_next.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        r3.addWidget(lab_next)
        self.le_next = QLineEdit(placeholderText='如 下周二 18:00 速度训练')
        r3.addWidget(self.le_next, 1)
        rl.addLayout(r3)
        sheet.add_section('寄语与备注', rl)
        mid_lay.addWidget(sheet, 1)  # 版面必须挂入布局，否则 _init_ui 返回即被 GC（use-after-free 崩溃）

        mid_scroll.setWidget(mid_content)
        main_lay.addWidget(mid_scroll, 1)

        # 头部数据联动
        self.le_goal.textChanged.connect(self._refresh_header)
        self.dte_date.dateChanged.connect(lambda _: self._refresh_header())

    # ==================== 左列任务列表 + 头部刷新 ====================

    def _refresh_task_list(self):
        """重建左列任务项（日期 + 区块标题），标记当前选中。"""
        for it in getattr(self, '_task_items', []):
            it.setParent(None)
            it.deleteLater()
        self._task_items = []
        date_str = self.dte_date.date().toString('yyyy-MM-dd')
        # 插到 stretch 之前
        stretch_idx = self._task_list_lay.count() - 1
        for i, b in enumerate(self._blocks):
            item = TaskListItem(
                index=i, date_str=date_str, title=b.title,
                selected=(i == self._cur_block_idx)
            )
            item.clicked.connect(self._on_task_clicked)
            item.edit_clicked.connect(self._on_task_edit)
            self._task_list_lay.insertWidget(stretch_idx, item)
            self._task_items.append(item)

    def _on_task_clicked(self, idx):
        """左列任务项点击 → 驱动隐藏 cb_block 切换区块（复用 on_block_changed）。"""
        self.cb_block.setCurrentIndex(idx)

    def _on_task_edit(self, idx):
        """左列编辑图标 → 选中该项后重命名。"""
        self.cb_block.setCurrentIndex(idx)
        self.on_rename_block()

    def _refresh_header(self):
        """刷新当日编排头部：日期+训练课 + 核心内容大标题。"""
        d = self.dte_date.date()
        wd = _WEEKDAYS[d.dayOfWeek() - 1] if 1 <= d.dayOfWeek() <= 7 else ''
        self._lbl_session.setText(f'{wd} {d.toString("yyyy-MM-dd")} · 训练课')
        goal = self.le_goal.text().strip()
        self._lbl_hero.setText(goal if goal else '训练核心内容')

    # ==================== 区块刷新（原有逻辑 + 同步左列/头部） ====================

    def _refresh_blocks(self):
        self.cb_block.blockSignals(True)
        self.cb_block.clear()
        for b in self._blocks:
            self.cb_block.addItem(b.title)
        self.cb_block.blockSignals(False)
        if self._cur_block_idx >= len(self._blocks):
            self._cur_block_idx = len(self._blocks) - 1
        self.cb_block.setCurrentIndex(self._cur_block_idx)
        # 默认区块不可删除
        self.btn_del_block.setEnabled(self._cur_block_idx >= self._default_count)
        self._refresh_task_list()
        self._refresh_header()
        self._refresh_table()
        self._update_right_panel()

    def _update_right_panel(self):
        """刷新右侧概览卡片与图表数据（右侧辅助区已移除，保留空实现以兼容现有调用）。"""
        pass

    def _persist(self):
        """将当前区块标题列表保存到配置文件（委托 plan_coordinator）。"""
        plan_coordinator.save_blocks_config([b.title for b in self._blocks])

    def on_block_changed(self, idx):
        # 切换区块前，先把当前区块的表格编辑同步回数据模型
        self._sync_table_to_data()
        self._cur_block_idx = idx
        self.btn_del_block.setEnabled(idx >= self._default_count)
        self._refresh_task_list()
        self._refresh_table()

    def on_add_block(self):
        name, ok = QInputDialog.getText(self, '新增区块', '区块标题：')
        if ok and name.strip():
            self._sync_table_to_data()
            self._blocks.append(Block(title=name.strip()))
            self._cur_block_idx = len(self._blocks) - 1
            self._refresh_blocks()
            self._persist()

    def on_rename_block(self):
        if self._cur_block_idx < 0 or self._cur_block_idx >= len(self._blocks):
            return
        block = self._blocks[self._cur_block_idx]
        name, ok = QInputDialog.getText(
            self, '重命名区块', '新的区块标题：', text=block.title
        )
        if ok and name.strip() and name.strip() != block.title:
            block.title = name.strip()
            self._refresh_blocks()
            self._persist()

    def on_del_block(self):
        if self._cur_block_idx < self._default_count:
            return
        reply = dialog.confirm(self, '确认', f'删除区块 [{self._blocks[self._cur_block_idx].title}]？')
        if reply :
            del self._blocks[self._cur_block_idx]
            self._cur_block_idx = max(0, self._cur_block_idx - 1)
            self._refresh_blocks()
            self._persist()

    def on_pick_exercise(self):
        self._sync_table_to_data()
        dlg = ExercisePickerDialog(self)
        if dlg.exec() == QDialog.Accepted:
            for data in dlg.get_selected():
                task = Task(name=data[0], sets=data[1], reps=data[2], note=data[3])
                self._blocks[self._cur_block_idx].tasks.append(task)
            self._refresh_table()
            self._update_right_panel()

    def on_add_custom(self):
        name, ok = QInputDialog.getText(self, '自定义动作', '动作名称：')
        if ok and name.strip():
            self._sync_table_to_data()
            task = Task(name=name.strip(), sets=3, reps='15次', note='')
            self._blocks[self._cur_block_idx].tasks.append(task)
            self._refresh_table()
            self._update_right_panel()

    def _sync_table_to_data(self):
        block = self._blocks[self._cur_block_idx]
        if not block.tasks or self.table.rowCount() == 0:
            return
        for i in range(min(len(block.tasks), self.table.rowCount())):
            t = block.tasks[i]
            item_name = self.table.item(i, 0)
            item_sets = self.table.item(i, 1)
            item_reps = self.table.item(i, 2)
            item_note = self.table.item(i, 3)
            if item_name:
                t.name = item_name.text()
            if item_sets:
                try:
                    t.sets = int(item_sets.text())
                except ValueError:
                    pass
            if item_reps:
                t.reps = item_reps.text()
            if item_note:
                t.note = item_note.text()

    def _refresh_table(self):
        self.table.setRowCount(0)
        block = self._blocks[self._cur_block_idx]
        if not block.tasks:
            self.table.setRowCount(1)
            placeholder = QTableWidgetItem('暂无训练动作，点击上方按钮添加')
            placeholder.setTextAlignment(Qt.AlignCenter)
            placeholder.setFlags(Qt.ItemIsEnabled)
            placeholder.setForeground(QColor(Palette.TEXT_SUB))
            self.table.setSpan(0, 0, 1, 5)
            self.table.setItem(0, 0, placeholder)
            self.table.resizeRowsToContents()
            return
        self.table.setRowCount(len(block.tasks))
        for i, task in enumerate(block.tasks):
            it_name = QTableWidgetItem(task.name)
            it_name.setTextAlignment(Qt.AlignCenter)
            it_sets = QTableWidgetItem(str(task.sets))
            it_sets.setTextAlignment(Qt.AlignCenter)
            it_reps = QTableWidgetItem(task.reps)
            it_reps.setTextAlignment(Qt.AlignCenter)
            it_note = QTableWidgetItem(task.note)
            btn_del = QPushButton('删除')
            btn_del.setObjectName('danger')
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet(
                f"QPushButton {{ background: transparent; border: 1px solid {Palette.RED}; "
                f"color: {Palette.RED}; border-radius: 4px; padding: 4px 10px; "
                f"font-size: 12px; font-weight: 500; min-height: 18px; }}"
                f"QPushButton:hover {{ background: rgba(239, 68, 68, 0.08); }}"
                f"QPushButton:pressed {{ background: rgba(239, 68, 68, 0.15); }}"
            )
            btn_del.setMinimumWidth(60)
            btn_del.clicked.connect(lambda checked, row=i: self._delete_row_by_btn(row))
            self.table.setItem(i, 0, it_name)
            self.table.setItem(i, 1, it_sets)
            self.table.setItem(i, 2, it_reps)
            self.table.setItem(i, 3, it_note)
            self.table.setCellWidget(i, 4, btn_del)
        self.table.resizeRowsToContents()

    def on_del_task(self):
        row = self.table.currentRow()
        if row < 0:
            dialog.info(self, '提示', '请先选中要删除的行')
            return
        if not self._blocks[self._cur_block_idx].tasks:
            return
        self._sync_table_to_data()
        del self._blocks[self._cur_block_idx].tasks[row]
        self._refresh_table()
        self._update_right_panel()

    def _delete_row_by_btn(self, row: int):
        if not self._blocks[self._cur_block_idx].tasks:
            return
        if row < 0 or row >= len(self._blocks[self._cur_block_idx].tasks):
            return
        self._sync_table_to_data()
        del self._blocks[self._cur_block_idx].tasks[row]
        self._refresh_table()
        self._update_right_panel()

    def _move_task(self, delta):
        row = self.table.currentRow()
        if row < 0:
            return
        tasks = self._blocks[self._cur_block_idx].tasks
        if not tasks:
            return
        self._sync_table_to_data()
        new_row = row + delta
        if 0 <= new_row < len(tasks):
            tasks[row], tasks[new_row] = tasks[new_row], tasks[row]
            self._refresh_table()
            self.table.setCurrentCell(new_row, 0)

    def collect_plan(self):
        self._sync_table_to_data()
        return SinglePlan(
            student_name=self.cb_name.currentText().strip(),
            gender=self.cb_gender.currentText(),
            age=self.le_age.text().strip(),
            coach=self.le_coach.text().strip(),
            train_date=self.dte_date.date().toString('yyyy-MM-dd'),
            location=self.le_loc.text().strip(),
            goal=self.le_goal.text().strip(),
            blocks=self._blocks,
            coach_note=self.te_note.toPlainText().strip(),
            remarks=self.te_remarks.toPlainText().strip(),
            next_preview=self.le_next.text().strip(),
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

    def on_recommend_single(self):
        """智能推荐：按学员年龄段教案池随机搭配生成训练内容（委托 plan_coordinator）。

        每次点击从该年龄段全部教案的各时间段任务池（热身/教学类别/放松）
        随机抽取动作搭配，连续排课不重样；生成后可自由修改。
        """
        name = self.cb_name.currentText().strip()
        archive_dir = self._get_dir() or ''
        result = plan_coordinator.recommend_random_single(name, archive_dir)
        if not result.get('ok'):
            dialog.warn(self, '提示', result.get('reason', '推荐失败'))
            return

        age = result['age']
        age_group = result['age_group']
        lesson = result['lesson']

        if lesson.core_content:
            self.le_goal.setText(lesson.core_content)
        self.le_age.setText(f'{age}岁')

        new_blocks = plan_coordinator.lesson_to_blocks(lesson)
        if not new_blocks or not any(b.tasks for b in new_blocks):
            dialog.info(self, '提示', '教案内容为空')
            return

        self._sync_table_to_data()
        self._blocks[:self._default_count] = new_blocks
        self._cur_block_idx = 0
        self._refresh_blocks()
        dialog.info(
            self, '推荐成功',
            f'已为学员「{name}」（{age}岁 / {age_group}）随机搭配训练课：\n'
            f'{lesson.title} · 共{lesson.total_duration}分钟\n'
            f'热身{len(new_blocks[0].tasks)}项 / '
            f'主项{len(new_blocks[1].tasks)}项 / '
            f'放松{len(new_blocks[2].tasks)}项\n\n'
            f'再次点击「智能推荐」可重新随机搭配，可在此基础上自由修改。'
        )
