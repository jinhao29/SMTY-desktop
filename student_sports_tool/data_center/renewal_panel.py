# -*- coding: utf-8 -*-
"""UI 层：续费预警与未上课提醒面板。

职责：
- 显示续费预警看板（按紧急程度排序，三色标识）
- 显示长期未上课学员列表
- 提供阈值配置、标记已联系、复制电话等操作
"""
import modern_dialog as dialog
import os
import logging
from file_lock import file_lock
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QSpinBox,
    QMessageBox, QMenu, QSplitter, QApplication, QDialog, QCheckBox,
    QFileDialog, QFrame, QLineEdit
)

import renewal_coordinator as rc
import config_manager
from renewal_processor import CRITICAL, WARNING, NORMAL, UNKNOWN
from base_components import install_row_actions, refresh_row_actions


# 紧急等级配色（行背景色 + 剩余课时文字色）
URGENCY_COLORS = {
    CRITICAL: {'bg': '#FFEBEB', 'fg': '#E53E3E', 'label': '紧急'},
    WARNING: {'bg': '#FFF7E6', 'fg': '#B45309', 'label': '提醒'},
    NORMAL: {'bg': '#FFFFFF', 'fg': '#1A1A1A', 'label': '正常'},
    UNKNOWN: {'bg': '#FFFFFF', 'fg': '#9B9B9B', 'label': '未设置'},
}


class RenewalPanel(QWidget):
    """续费预警与未上课提醒面板。"""

    def __init__(self, dir_getter, parent=None):
        super().__init__(parent)
        self._dir_getter = dir_getter
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(0, 0, 0, 0)

        # 阈值配置栏
        gb_cfg = QGroupBox('预警阈值配置')
        gb_cfg.setObjectName('card')
        cl = QHBoxLayout(gb_cfg)
        cl.setSpacing(12)
        cl.addWidget(QLabel('续费提醒阈值（剩余课时≤）：'))
        self.sp_renewal = QSpinBox()
        self.sp_renewal.setRange(1, 50)
        self.sp_renewal.setValue(5)
        cl.addWidget(self.sp_renewal)
        cl.addSpacing(20)
        cl.addWidget(QLabel('未上课天数提醒：'))
        self.sp_inactive = QSpinBox()
        self.sp_inactive.setRange(1, 90)
        self.sp_inactive.setValue(14)
        cl.addWidget(self.sp_inactive)
        cl.addStretch()
        self.btn_save_cfg = QPushButton('保存阈值', objectName='secondary')
        self.btn_save_cfg.clicked.connect(self.on_save_threshold)
        cl.addWidget(self.btn_save_cfg)
        cl.addSpacing(10)
        self.btn_refresh = QPushButton('刷新预警', objectName='primary')
        self.btn_refresh.clicked.connect(self.refresh)
        cl.addWidget(self.btn_refresh)
        # 免打扰名单管理：查看/恢复被误标记为已联系的学员
        self.btn_muted = QPushButton('免打扰名单', objectName='secondary')
        self.btn_muted.clicked.connect(self._show_muted_list)
        cl.addWidget(self.btn_muted)
        # === v4 新增：自动备份开关（默认开启，写入 _data_center_config.json）===
        cl.addSpacing(10)
        self.chk_auto_backup = QCheckBox('自动备份')
        self.chk_auto_backup.setToolTip('开启后每日凌晨 4:00 自动备份，并在手机端数据同步后立即备份')
        self.chk_auto_backup.toggled.connect(self._on_auto_backup_toggled)
        cl.addWidget(self.chk_auto_backup)
        # === v5 新增：高级配置按钮（展开/收起 JSON 表单编辑器）===
        cl.addSpacing(10)
        self.btn_advanced = QPushButton('高级配置 ▼', objectName='secondary')
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.toggled.connect(self._toggle_advanced_panel)
        cl.addWidget(self.btn_advanced)
        lay.addWidget(gb_cfg)
        # 初始化时读取配置填充开关状态（避免触发 toggled 信号）
        self._load_auto_backup_state()

        # === v5 新增：高级配置面板（JSON 表单编辑器）===
        # 默认隐藏，点击"高级配置"按钮展开
        self._build_advanced_panel(lay)

        # 预警列表（上下分栏）
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(8)

        # 续费预警表
        gb_renewal = QGroupBox('续费预警')
        gb_renewal.setObjectName('card')
        rl = QVBoxLayout(gb_renewal)
        self.tbl_renewal = QTableWidget()
        self.tbl_renewal.setColumnCount(7)
        self.tbl_renewal.setHorizontalHeaderLabels(
            ['学员', '总课时', '已上', '剩余', '最近上课', '状态', '跟进备注'])
        self.tbl_renewal.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.tbl_renewal.setAlternatingRowColors(True)
        self.tbl_renewal.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_renewal.customContextMenuRequested.connect(self._renewal_menu)
        self.tbl_renewal.doubleClicked.connect(self._on_renewal_double_click)
        install_row_actions(self.tbl_renewal, [
            ('标记已联系', lambda t, r: self._mark_contacted(t.item(r, 0).text())),
            ('复制电话', lambda t, r: self._copy_phone(t.item(r, 0).text())),
        ])
        rl.addWidget(self.tbl_renewal)
        splitter.addWidget(gb_renewal)

        # 未上课提醒表
        gb_inactive = QGroupBox('长期未上课提醒')
        gb_inactive.setObjectName('card')
        il = QVBoxLayout(gb_inactive)
        self.tbl_inactive = QTableWidget()
        self.tbl_inactive.setColumnCount(6)
        self.tbl_inactive.setHorizontalHeaderLabels(
            ['学员', '最近上课', '未上天数', '剩余课时', '联系电话', '状态'])
        self.tbl_inactive.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.tbl_inactive.setAlternatingRowColors(True)
        self.tbl_inactive.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_inactive.customContextMenuRequested.connect(self._inactive_menu)
        install_row_actions(self.tbl_inactive, [
            ('标记已联系', lambda t, r: self._mark_contacted(t.item(r, 0).text())),
            ('复制电话', lambda t, r: self._copy_phone(t.item(r, 0).text())),
        ])
        il.addWidget(self.tbl_inactive)
        splitter.addWidget(gb_inactive)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        lay.addWidget(splitter, 1)

    def refresh(self):
        """刷新预警数据。"""
        dir_path = self._dir_getter()
        if not dir_path or not os.path.isdir(dir_path):
            self.tbl_renewal.setRowCount(0)
            self.tbl_inactive.setRowCount(0)
            return
        try:
            data = rc.get_renewal_alerts(dir_path)
        except Exception as e:
            dialog.warn(self, '加载失败', f'读取预警数据失败：{e}')
            return

        # 更新阈值显示
        self.sp_renewal.setValue(data['threshold'])
        self.sp_inactive.setValue(data['inactive_days'])

        # 填充期间禁用排序，避免行错乱；填充后启用列头排序
        self.tbl_renewal.setSortingEnabled(False)
        self.tbl_inactive.setSortingEnabled(False)
        # 填充续费预警表
        renewal = data['renewal']
        self.tbl_renewal.setRowCount(len(renewal))
        for i, stu in enumerate(renewal):
            colors = URGENCY_COLORS.get(stu['urgency'], URGENCY_COLORS[NORMAL])
            self._set_row(self.tbl_renewal, i, [
                stu['name'], str(stu['total']), str(stu['attended']),
                str(stu['remaining']), stu.get('last_date', ''),
                colors['label'], stu.get('followup_note', ''),
            ], bg=colors['bg'], fg=colors['fg'], highlight_col=3)

        # 填充未上课表
        inactive = data['inactive']
        self.tbl_inactive.setRowCount(len(inactive))
        for i, stu in enumerate(inactive):
            colors = URGENCY_COLORS.get(stu['urgency'], URGENCY_COLORS[NORMAL])
            self._set_row(self.tbl_inactive, i, [
                stu['name'], stu.get('last_date', ''), f"{stu['inactive_days']}天",
                str(stu['remaining']), '', colors['label'],
            ], bg=colors['bg'], fg=colors['fg'], highlight_col=2)

        self.tbl_renewal.setSortingEnabled(True)
        self.tbl_inactive.setSortingEnabled(True)
        refresh_row_actions(self.tbl_renewal)
        refresh_row_actions(self.tbl_inactive)

    def _set_row(self, table, row, values, bg=None, fg=None, highlight_col=None):
        """填充一行数据并设置配色。"""
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignCenter)
            if bg:
                item.setBackground(QColor(bg))
            if fg and col == highlight_col:
                item.setForeground(QColor(fg))
                font = QFont(); font.setBold(True)
                item.setFont(font)
            table.setItem(row, col, item)

    def on_save_threshold(self):
        """保存阈值配置。"""
        dir_path = self._dir_getter()
        if not dir_path:
            dialog.warn(self, '提示', '请先选择档案目录')
            return
        rc.update_thresholds(dir_path, self.sp_renewal.value(), self.sp_inactive.value())
        dialog.info(self, '已保存', '阈值配置已保存')
        self.refresh()

    def _load_auto_backup_state(self):
        """初始化时读取自动备份开关状态（静默填充，不触发 toggled 信号）。

        配置文件 _data_center_config.json 的 auto_backup_enabled 字段，
        默认 True（首次使用即开启）。
        """
        try:
            cfg = config_manager.load_config('')
            enabled = cfg.get('auto_backup_enabled', True)
            # blockSignals 避免初始化时触发 _on_auto_backup_toggled
            self.chk_auto_backup.blockSignals(True)
            self.chk_auto_backup.setChecked(bool(enabled))
            self.chk_auto_backup.blockSignals(False)
        except Exception:
            self.chk_auto_backup.setChecked(True)

    def _on_auto_backup_toggled(self, enabled):
        """自动备份开关切换：立即写入配置文件，并通知 AutoBackupManager。

        设计：配置即生效，无需重启。
        - 关闭时：AutoBackupManager 在下次触发时读取配置自动跳过
        - 开启时：等待下次凌晨 2:00 定时触发
        """
        try:
            config_manager.update_config('', auto_backup_enabled=bool(enabled))
            # 通知父级 DataCenterWindow 刷新状态栏文案
            parent = self.parent()
            while parent is not None:
                if hasattr(parent, '_refresh_auto_backup_label'):
                    parent._refresh_auto_backup_label()
                    break
                parent = parent.parent()
        except Exception as e:
            dialog.warn(self, '保存失败', f'更新自动备份设置失败：{e}')
            # 回滚开关状态
            self.chk_auto_backup.blockSignals(True)
            self.chk_auto_backup.setChecked(not enabled)
            self.chk_auto_backup.blockSignals(False)

    # ============================================================
    # === v5 新增：JSON 表单编辑器（高级配置面板） ===
    # ============================================================
    # 设计动机：教练无需手动编辑 _data_center_config.json 文本文件，
    # 直接通过表单调整"滚动备份数"、"手机同步目录"等高级参数。
    # ============================================================

    def _build_advanced_panel(self, parent_layout):
        """构建高级配置面板（默认隐藏，点击按钮展开）。

        包含：
        - 滚动备份数（max_auto_backups，1-30）
        - 手机备份同步目录（phone_backup_sync_dir，文件夹选择器）
        - 上次自动备份时间（last_auto_backup_at，只读显示）
        - 统一保存按钮（一次保存所有高级配置）
        """
        self.gb_advanced = QGroupBox('高级配置（直接编辑 _data_center_config.json）')
        self.gb_advanced.setObjectName('card')
        al = QVBoxLayout(self.gb_advanced)
        al.setSpacing(10)
        al.setContentsMargins(14, 12, 14, 12)

        # 1. 滚动备份数 + 手机同步目录（同一行）
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(QLabel('滚动备份数：'))
        self.sp_max_backups = QSpinBox()
        self.sp_max_backups.setRange(1, 30)
        self.sp_max_backups.setValue(10)
        self.sp_max_backups.setToolTip('自动备份保留的最近 ZIP 文件份数（超出自动删除最旧的）')
        row1.addWidget(self.sp_max_backups)
        row1.addSpacing(20)
        row1.addWidget(QLabel('手机同步目录：'))
        self.edit_sync_dir = QLineEdit()
        self.edit_sync_dir.setPlaceholderText('点击右侧按钮选择手机备份同步目录...')
        self.edit_sync_dir.setReadOnly(True)
        self.edit_sync_dir.setMinimumWidth(260)
        row1.addWidget(self.edit_sync_dir, 1)
        self.btn_pick_sync_dir = QPushButton('选择目录', objectName='secondary')
        self.btn_pick_sync_dir.clicked.connect(self._pick_sync_dir)
        row1.addWidget(self.btn_pick_sync_dir)
        al.addLayout(row1)

        # 2. 上次自动备份时间（只读显示）+ 统一保存按钮
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(QLabel('上次自动备份：'))
        self.lbl_last_backup = QLabel('—')
        self.lbl_last_backup.setStyleSheet('color:#6b7280; font-style:italic;')
        row2.addWidget(self.lbl_last_backup, 1)
        self.btn_save_advanced = QPushButton('保存高级配置', objectName='primary')
        self.btn_save_advanced.clicked.connect(self._save_advanced_config)
        row2.addWidget(self.btn_save_advanced)
        al.addLayout(row2)

        # 3. 配置文件路径提示（让教练知道 JSON 在哪）
        self.lbl_config_path = QLabel('配置文件：—')
        self.lbl_config_path.setStyleSheet('color:#9ca3af; font-size:11px;')
        al.addWidget(self.lbl_config_path)

        # 默认隐藏
        self.gb_advanced.setVisible(False)
        parent_layout.addWidget(self.gb_advanced)

        # 初始化时加载已有配置填充表单
        self._load_advanced_config()

    def _toggle_advanced_panel(self, checked):
        """展开/收起高级配置面板。"""
        self.gb_advanced.setVisible(checked)
        self.btn_advanced.setText('高级配置 ▲' if checked else '高级配置 ▼')
        # 展开时刷新一次显示
        if checked:
            self._load_advanced_config()

    def _load_advanced_config(self):
        """从 _data_center_config.json 加载已有配置填充表单（静默）。"""
        try:
            cfg = config_manager.load_config('')
            # blockSignals 避免触发保存逻辑
            self.sp_max_backups.blockSignals(True)
            self.sp_max_backups.setValue(int(cfg.get('max_auto_backups', 10)))
            self.sp_max_backups.blockSignals(False)

            sync_dir = cfg.get('phone_backup_sync_dir', '')
            self.edit_sync_dir.setText(sync_dir or '')

            last_backup = cfg.get('last_auto_backup_at', '')
            self.lbl_last_backup.setText(last_backup if last_backup else '尚未自动备份过')

            # 显示配置文件绝对路径
            config_path = os.path.join(os.getcwd(), config_manager.CONFIG_FILE)
            self.lbl_config_path.setText(f'配置文件：{config_path}')
        except Exception:
            logging.exception('加载高级配置表单失败')

    def _pick_sync_dir(self):
        """选择手机备份同步目录。"""
        cur = self.edit_sync_dir.text() or os.path.expanduser('~')
        path = QFileDialog.getExistingDirectory(self, '选择手机备份同步目录', cur)
        if path:
            self.edit_sync_dir.setText(path)

    def _save_advanced_config(self):
        """统一保存高级配置到 _data_center_config.json。"""
        try:
            config_manager.update_config(
                '',
                max_auto_backups=self.sp_max_backups.value(),
                phone_backup_sync_dir=self.edit_sync_dir.text().strip()
            )
            dialog.info(self, '已保存', '高级配置已写入 _data_center_config.json')
            # 通知父级刷新状态栏
            parent = self.parent()
            while parent is not None:
                if hasattr(parent, '_refresh_auto_backup_label'):
                    parent._refresh_auto_backup_label()
                    break
                parent = parent.parent()
        except Exception as e:
            dialog.warn(self, '保存失败', f'保存高级配置失败：{e}')

    def _renewal_menu(self, pos):
        """续费表右键菜单。"""
        row = self.tbl_renewal.indexAt(pos).row()
        if row < 0:
            return
        name = self.tbl_renewal.item(row, 0).text()
        menu = QMenu(self)
        act_mark = menu.addAction('标记已联系（7天免打扰）')
        act_copy = menu.addAction('复制电话')
        act_export = menu.addAction('导出预警清单')
        action = menu.exec(self.tbl_renewal.viewport().mapToGlobal(pos))
        if action == act_mark:
            self._mark_contacted(name)
        elif action == act_copy:
            self._copy_phone(name)
        elif action == act_export:
            self._export_alerts()

    def _inactive_menu(self, pos):
        """未上课表右键菜单。"""
        row = self.tbl_inactive.indexAt(pos).row()
        if row < 0:
            return
        name = self.tbl_inactive.item(row, 0).text()
        menu = QMenu(self)
        act_mark = menu.addAction('标记已联系（7天免打扰）')
        act_copy = menu.addAction('复制电话')
        action = menu.exec(self.tbl_inactive.viewport().mapToGlobal(pos))
        if action == act_mark:
            self._mark_contacted(name)
        elif action == act_copy:
            self._copy_phone(name)

    def _on_renewal_double_click(self, index):
        """双击续费表行：标记已联系。"""
        row = index.row()
        if row < 0:
            return
        name = self.tbl_renewal.item(row, 0).text()
        self._mark_contacted(name)

    def _mark_contacted(self, name):
        """标记学员已联系。"""
        dir_path = self._dir_getter()
        if not dir_path:
            return
        from PySide6.QtWidgets import QInputDialog
        note, ok = QInputDialog.getText(self, '标记已联系', f'学员 {name} 跟进备注：')
        if ok:
            rc.mark_student_contacted(dir_path, name, note)
            dialog.info(self, '已标记', f'{name} 已标记为已联系（7天免打扰）')
            self.refresh()

    def _copy_phone(self, name):
        """复制学员电话。"""
        dir_path = self._dir_getter()
        try:
            from excel_builder import read_student_meta
            meta = read_student_meta(os.path.join(dir_path, f'{name}.xlsx'))
            if meta:
                phone = meta.get('info', {}).get('phone', '')
                if phone:
                    QApplication.clipboard().setText(phone)
                    dialog.info(self, '已复制', f'{name} 电话：{phone}')
                    return
        except Exception:
            pass
        dialog.info(self, '提示', f'未找到 {name} 的电话')

    def _export_alerts(self):
        """导出预警清单。"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, '导出预警清单', '续费预警清单.xlsx', 'Excel (*.xlsx)')
        if not path:
            return
        if not path.endswith('.xlsx'):
            path += '.xlsx'
        try:
            from data_exporter import collect_all_students
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            students = collect_all_students(self._dir_getter())
            wb = Workbook()
            ws = wb.active
            headers = ['姓名', '状态', '剩余课时', '最近上课', '联系电话']
            for i, h in enumerate(headers, 1):
                c = ws.cell(row=1, column=i, value=h)
                c.font = Font(bold=True, color='FFFFFF', name='微软雅黑')
                c.fill = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
            for r, s in enumerate(students, 2):
                if s['status'] in ('需续费', '已超支'):
                    ws.cell(row=r, column=1, value=s['name'])
                    ws.cell(row=r, column=2, value=s['status'])
                    ws.cell(row=r, column=3, value=s['remaining'])
                    ws.cell(row=r, column=4, value=s['last_date'])
                    ws.cell(row=r, column=5, value=s['phone'])
            with file_lock(path):
                wb.save(path)
            dialog.info(self, '导出成功', f'预警清单已保存到：\n{path}')
        except Exception as e:
            dialog.error(self, '导出失败', str(e))

    def _show_muted_list(self):
        """打开免打扰名单管理对话框，可查看/恢复被误标记的学员。"""
        dir_path = self._dir_getter()
        if not dir_path:
            dialog.warn(self, '提示', '请先选择档案目录')
            return
        dlg = MutedListDialog(self, dir_path=dir_path)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()


class MutedListDialog(QDialog):
    """免打扰名单管理对话框：查看所有被免打扰的学员，支持取消单个或全部。

    使用场景：教练误操作标记了学员为"已联系"，导致学员在 7 天内从预警列表消失，
    可通过此对话框恢复预警显示。
    """

    def __init__(self, parent=None, dir_path=''):
        super().__init__(parent)
        self._dir_path = dir_path
        self.setWindowTitle('免打扰名单管理')
        self.resize(680, 480)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        # 标题与说明
        title = QLabel('免打扰名单（7天免打扰期内学员不显示在预警列表）')
        title.setStyleSheet('font-size:15px; font-weight:600; color:#007AFF;')
        lay.addWidget(title)
        hint = QLabel('若误标记了学员，可选中后点击"取消免打扰"恢复预警显示。')
        hint.setStyleSheet('color:#757575; font-size:13px;')
        lay.addWidget(hint)

        # 名单表格
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(5)
        self.tbl.setHorizontalHeaderLabels(['学员', '最近联系日期', '免打扰到期', '剩余天数', '跟进备注'])
        self.tbl.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self.tbl, 1)

        # 底部操作栏
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        self.btn_unmark = QPushButton('取消免打扰（恢复预警）', objectName='primary')
        self.btn_unmark.clicked.connect(self._on_unmark)
        btn_lay.addWidget(self.btn_unmark)
        self.btn_clear_all = QPushButton('全部取消', objectName='danger')
        self.btn_clear_all.clicked.connect(self._on_clear_all)
        btn_lay.addWidget(self.btn_clear_all)
        self.btn_close = QPushButton('关闭', objectName='secondary')
        self.btn_close.clicked.connect(self.accept)
        btn_lay.addWidget(self.btn_close)
        lay.addLayout(btn_lay)

    def _load_data(self):
        """加载免打扰名单数据。"""
        try:
            self._muted = rc.get_muted_students(self._dir_path)
        except Exception as e:
            dialog.warn(self, '加载失败', f'读取免打扰名单失败：{e}')
            self._muted = []

        self.tbl.setRowCount(len(self._muted))
        for i, m in enumerate(self._muted):
            days_left = m['days_left']
            if days_left > 0:
                days_text = f'{days_left} 天'
            elif days_left == 0:
                days_text = '今日到期'
            else:
                days_text = f'已过期 {-days_left} 天'
            vals = [
                m['name'],
                m.get('last_contact', ''),
                m.get('expire', ''),
                days_text,
                m.get('note', ''),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                # 已过期的行用灰色标识
                if days_left < 0:
                    item.setForeground(QColor('#9E9E9E'))
                # 剩余天数列特殊着色
                if col == 3:
                    if days_left > 0:
                        item.setForeground(QColor('#FF3B30'))
                    elif days_left == 0:
                        item.setForeground(QColor('#FF9500'))
                self.tbl.setItem(i, col, item)

    def _on_context_menu(self, pos):
        """右键菜单：取消单个学员免打扰。"""
        row = self.tbl.indexAt(pos).row()
        if row < 0:
            return
        name = self.tbl.item(row, 0).text()
        menu = QMenu(self)
        act_unmark = menu.addAction('取消免打扰（恢复预警）')
        action = menu.exec(self.tbl.viewport().mapToGlobal(pos))
        if action == act_unmark:
            self._unmark_one(name)

    def _on_unmark(self):
        """取消选中行的免打扰。"""
        row = self.tbl.currentRow()
        if row < 0:
            dialog.info(self, '提示', '请先选中要取消免打扰的学员')
            return
        name = self.tbl.item(row, 0).text()
        self._unmark_one(name)

    def _unmark_one(self, name):
        """取消单个学员的免打扰标记。"""
        reply = dialog.confirm(
            self, '确认取消免打扰',
            f'确认恢复 "{name}" 的预警显示？\n取消后该学员将立即重新出现在预警列表中。',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if not reply:
            return
        try:
            rc.unmark_student_contacted(self._dir_path, name)
            dialog.info(self, '已取消', f'"{name}" 的免打扰已取消，预警已恢复')
            self._load_data()
        except Exception as e:
            dialog.error(self, '操作失败', str(e))

    def _on_clear_all(self):
        """清除所有免打扰标记。"""
        if not self._muted:
            dialog.info(self, '提示', '当前没有免打扰记录')
            return
        reply = dialog.confirm(
            self, '确认全部取消',
            f'共 {len(self._muted)} 条免打扰记录，确认全部清除并恢复预警？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if not reply:
            return
        try:
            rc.clear_all_followup(self._dir_path)
            dialog.info(self, '已清除', '所有免打扰记录已清除，预警已全部恢复')
            self._load_data()
        except Exception as e:
            dialog.error(self, '操作失败', str(e))
