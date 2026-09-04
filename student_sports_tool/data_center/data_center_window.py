# -*- coding: utf-8 -*-
"""UI 层：数据中心 Tab 容器。

职责：
- 作为「数据中心」Tab 的根容器
- 内部用子 Tab 聚合：数据备份 / 成长报告 / 续费预警
- 统一管理档案目录的获取与显示
- v4 新增：底部状态栏显示"上次自动备份"时间
- v4 新增：启动 AutoBackupManager 后台线程，每日凌晨 2:00 自动备份
"""
import modern_dialog as dialog
import os
import sys
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QFileDialog, QMessageBox, QComboBox, QSpinBox,
    QCheckBox, QGroupBox, QFrame
)
from PySide6.QtGui import QFont

# 注入父目录（student_sports_tool/）以便导入 base_components
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from backup_panel import BackupPanel
from report_panel import ReportPanel
from renewal_panel import RenewalPanel
from schedule_achievement_panel import ScheduleAchievementPanel
from base_components import ColorPalette, StatCell

DEFAULT_DIR = os.path.join(os.path.expanduser('~'), 'Desktop', '学员档案')


class AutoBackupPanel(QWidget):
    """自动备份配置面板：频率 / 保留份数 / 开关 / 上次备份时间。"""

    FREQ_LABELS = {'daily': '每日（凌晨 4:00）', 'weekly': '每周（周一 4:00）', 'manual': '手动'}

    def __init__(self, dir_getter, parent=None):
        super().__init__(parent)
        self._dir_getter = dir_getter
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(22)
        lay.setContentsMargins(0, 0, 0, 0)

        gb = QGroupBox('自动备份设置')
        gb.setObjectName('card')
        form = QVBoxLayout(gb)
        form.setSpacing(14)

        # 开关
        self.chk_enabled = QCheckBox('启动自动备份')
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        form.addWidget(self.chk_enabled)

        # 频率
        row_freq = QHBoxLayout()
        row_freq.addWidget(QLabel('备份频率：'))
        self.cb_freq = QComboBox()
        for key, label in self.FREQ_LABELS.items():
            self.cb_freq.addItem(label, key)
        self.cb_freq.currentIndexChanged.connect(self._on_freq_changed)
        row_freq.addWidget(self.cb_freq)
        row_freq.addStretch()
        form.addLayout(row_freq)

        # 保留份数
        row_max = QHBoxLayout()
        row_max.addWidget(QLabel('保留备份份数：'))
        self.sp_max = QSpinBox()
        self.sp_max.setRange(1, 50)
        self.sp_max.setValue(5)
        self.sp_max.valueChanged.connect(self._on_max_changed)
        row_max.addWidget(self.sp_max)
        row_max.addStretch()
        form.addLayout(row_max)

        # 上次备份时间（只读状态栏）
        self.lbl_last = QLabel('')
        self.lbl_last.setStyleSheet('color:#9B9B9B; font-size:11px;')
        form.addWidget(self.lbl_last)

        lay.addWidget(gb)
        lay.addStretch()

    def refresh(self):
        """从配置读取当前值填充控件（不触发保存）。"""
        try:
            import config_manager
            cfg = config_manager.load_config(self._dir_getter() if self._dir_getter else '')
            self.chk_enabled.blockSignals(True)
            self.chk_enabled.setChecked(bool(cfg.get('auto_backup_enabled', True)))
            self.chk_enabled.blockSignals(False)
            freq = cfg.get('auto_backup_frequency', 'daily')
            idx = self.cb_freq.findData(freq)
            self.cb_freq.blockSignals(True)
            self.cb_freq.setCurrentIndex(idx if idx >= 0 else 0)
            self.cb_freq.blockSignals(False)
            self.sp_max.blockSignals(True)
            self.sp_max.setValue(int(cfg.get('max_auto_backups', 5)))
            self.sp_max.blockSignals(False)
            last = cfg.get('last_auto_backup_at', '')
            self.lbl_last.setText(
                f'上次自动备份：{last}' if last else '尚未自动备份'
            )
        except Exception:
            logging.exception('刷新自动备份配置面板失败')

    def _save(self, **kwargs):
        """写入配置文件（auto_backup_manager 每分钟重读，自动生效）。"""
        try:
            import config_manager
            config_manager.update_config(
                self._dir_getter() if self._dir_getter else '', **kwargs
            )
        except Exception:
            logging.exception('保存自动备份配置失败')

    def _on_enabled_toggled(self, checked):
        self._save(auto_backup_enabled=bool(checked))

    def _on_freq_changed(self, index):
        self._save(auto_backup_frequency=self.cb_freq.itemData(index))

    def _on_max_changed(self, value):
        self._save(max_auto_backups=int(value))


class DataCenterWindow(QWidget):
    """数据中心容器：聚合备份/报告/预警三大面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dir_path = DEFAULT_DIR
        self._auto_backup_mgr = None
        self._lan_sender = None
        self._backup_session_count = 0  # 本次会话内完成的备份次数（真数据）
        self._init_ui()
        self._init_auto_backup()
        # === v5 新增：连接 LAN 接收器信号，监听 Android 端推送的精彩瞬间 ===
        self._init_lan_moment_listener()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(22)
        lay.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel('数据中心')
        title.setObjectName('title')
        _f = QFont('微软雅黑'); _f.setPointSize(20); _f.setBold(True)
        title.setFont(_f)
        lay.addWidget(title)

        # === 数据中心概览条（真数据：自动备份状态 / 上次备份 / 本次会话备份次数 / 档案文件数）===
        dc_strip = QFrame()
        dc_strip.setObjectName('statStrip')
        dc_strip.setStyleSheet(f'''
            QFrame#statStrip {{
                background: {ColorPalette.CARD};
                border: 1px solid #E5E5E5;
                border-radius: 16px;
            }}
        ''')
        dsl = QHBoxLayout(dc_strip)
        dsl.setContentsMargins(20, 14, 20, 14)
        dsl.setSpacing(0)
        self.cell_backup_status = StatCell('自动备份')
        self.cell_last_backup = StatCell('上次备份')
        self.cell_session_count = StatCell('本次会话备份次数')
        self.cell_archive_files = StatCell('档案文件数')
        dc_cells = [self.cell_backup_status, self.cell_last_backup,
                    self.cell_session_count, self.cell_archive_files]
        for i, cell in enumerate(dc_cells):
            if i:
                line = QLabel()
                line.setFixedSize(1, 36)
                line.setStyleSheet('background: #E5E5E5; border: none;')
                dsl.addWidget(line)
            dsl.addWidget(cell, 1)
        lay.addWidget(dc_strip)

        # 档案目录选择栏（紧凑水平排布，输入框限宽不再独占整行）
        dir_w = QWidget()
        dl = QHBoxLayout(dir_w)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(12)
        dl.addWidget(QLabel('档案目录：'))
        self.le_dir = QLineEdit(self._dir_path)
        self.le_dir.setStyleSheet('color:#9B9B9B;')
        self.le_dir.setMaximumWidth(400)
        dl.addWidget(self.le_dir)
        self.btn_browse = QPushButton('浏览', objectName='secondary')
        self.btn_browse.clicked.connect(self.on_browse)
        dl.addWidget(self.btn_browse)
        # 优化6新增：检查更新按钮（点击后调用顶层主窗口的 show_update_dialog）
        self.btn_update = QPushButton('检查更新', objectName='secondary')
        self.btn_update.setToolTip('检查 GitHub 是否有新版本并自动下载更新')
        self.btn_update.clicked.connect(self._on_check_update)
        dl.addWidget(self.btn_update)
        # === v5 优化6 新增：数据库时光机按钮 ===
        # 弹出 DbSnapshotDialog，让教练拖动时间滑条回滚数据库
        # 用于"AI 或教练自己手误把数据库改坏"的死循环抢救场景
        self.btn_db_snapshot = QPushButton('时光机', objectName='secondary')
        self.btn_db_snapshot.setToolTip('查看并回滚数据库历史快照（每次恢复前自动生成）')
        self.btn_db_snapshot.clicked.connect(self._on_open_db_snapshot)
        dl.addWidget(self.btn_db_snapshot)
        dl.addStretch()
        lay.addWidget(dir_w)

        # 子 Tab
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: #F5F7FA; }
            QTabBar::tab {
                background: #FFFFFF;
                color: #6B6B6B;
                padding: 10px 28px;
                font-size: 14px;
                font-weight: 600;
                border: none;
                border-bottom: 2px solid transparent;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                margin-right: 4px;
            }
            QTabBar::tab:hover { background: #F5F7FA; color: #FF6B47; }
            QTabBar::tab:selected {
                background: #FFFFFF;
                color: #FF6B47;
                border-bottom: 2px solid #FF6B47;
            }
        """)

        self.panel_backup = BackupPanel(self._get_dir, on_auto_backup_clicked=self._open_auto_backup_panel)
        self.tabs.addTab(self.panel_backup, '  数据备份与导入  ')

        # === 自动备份配置面板（频率/保留份数/设置）===
        # 配置直接写入 _data_center_config.json，auto_backup_manager 每分钟重读生效
        self.panel_auto_backup = AutoBackupPanel(self._get_dir)
        self.tabs.addTab(self.panel_auto_backup, '  自动备份设置  ')

        self.panel_report = ReportPanel(self._get_dir)
        self.tabs.addTab(self.panel_report, '  一键成长报告  ')

        self.panel_renewal = RenewalPanel(self._get_dir)
        self.tabs.addTab(self.panel_renewal, '  课时与续费提醒  ')

        # === v5 优化5 新增：训练达成率偏差分析面板 ===
        # 对比 Android 端排课计划与本地课时记录，自动生成"训练达成率"图表
        # 教练可截图发家长，展示专业教学管理能力
        self.panel_achievement = ScheduleAchievementPanel(self._get_dir)
        self.tabs.addTab(self.panel_achievement, '  训练达成率分析  ')

        lay.addWidget(self.tabs, 1)

        # === v4 新增：底部状态栏 ===
        # 显示"上次自动备份：YYYY-MM-DD HH:MM"，
        # 让教练对数据安全有直观掌控感
        self.lbl_auto_backup_status = QLabel('')
        self.lbl_auto_backup_status.setStyleSheet(
            'color:#9B9B9B; font-size:11px; padding:4px 8px;'
        )
        lay.addWidget(self.lbl_auto_backup_status)
        self._refresh_auto_backup_label()

    def _init_auto_backup(self):
        """初始化自动备份管理器（启动后台 QThread）。"""
        try:
            from auto_backup_manager import AutoBackupManager
            self._auto_backup_mgr = AutoBackupManager(self._get_dir, parent=self)
            self._auto_backup_mgr.backup_finished.connect(
                self._on_auto_backup_finished
            )
            self._auto_backup_mgr.start()
        except Exception as e:
            # 自动备份启动失败不阻塞 UI，仅记录日志
            logging.exception('自动备份启动失败')
            self.lbl_auto_backup_status.setText(
                f'自动备份未启用：{e}'
            )

    def _refresh_auto_backup_label(self):
        """刷新底部状态栏的"上次自动备份"时间，并同步顶部概览条。"""
        if not self._auto_backup_mgr:
            return
        try:
            last = self._auto_backup_mgr.get_last_backup_time()
            enabled = self._auto_backup_mgr.is_enabled()
            # 同步到自动备份配置面板的只读状态栏
            if hasattr(self, 'panel_auto_backup'):
                self.panel_auto_backup.refresh()
            if not enabled:
                self.lbl_auto_backup_status.setText('自动备份：已关闭')
            elif last:
                self.lbl_auto_backup_status.setText(
                    f'上次自动备份：{last}'
                )
            else:
                self.lbl_auto_backup_status.setText(
                    '自动备份已开启，等待凌晨 4:00 首次执行'
                )
            # 同步顶部概览条
            self._refresh_stat_strip(enabled=enabled, last=last)
        except Exception:
            logging.exception('刷新自动备份状态失败')

    def _refresh_stat_strip(self, enabled=None, last=None):
        """刷新顶部概览条四格：自动备份状态 / 上次备份 / 本次会话备份次数 / 档案文件数。

        档案文件数 = 当前档案目录下 .xlsx 个数（轻量目录扫描）。
        失败时静默回落为 —，不打断 UI。
        """
        try:
            if enabled is None:
                enabled = bool(self._auto_backup_mgr and self._auto_backup_mgr.is_enabled())
            if last is None and self._auto_backup_mgr:
                last = self._auto_backup_mgr.get_last_backup_time() or ''
            self.cell_backup_status.set_value('已开启' if enabled else '已关闭')
            self.cell_last_backup.set_value(last if last else '等待首次')
            self.cell_session_count.set_value(self._backup_session_count)
            # 档案文件：扫描当前目录的 .xlsx 文件数
            d = self.le_dir.text().strip() if hasattr(self, 'le_dir') else ''
            count = 0
            if d and os.path.isdir(d):
                for _name in os.listdir(d):
                    if _name.lower().endswith('.xlsx') and not _name.startswith('~$'):
                        count += 1
            self.cell_archive_files.set_value(count)
        except Exception:
            logging.exception('刷新数据中心概览条失败')
            for cell in (self.cell_backup_status, self.cell_last_backup,
                         self.cell_session_count, self.cell_archive_files):
                cell.set_value('—')
        except Exception:
            logging.exception('刷新自动备份状态失败')

    def _open_auto_backup_panel(self):
        """备份面板入口按钮：切换到自动备份设置 Tab。"""
        self.tabs.setCurrentWidget(self.panel_auto_backup)
        self.panel_auto_backup.refresh()

    def _on_auto_backup_finished(self, success, message, timestamp):
        """自动备份完成回调：累加本次会话计数并刷新状态栏 + 概览条。"""
        if success:
            self._backup_session_count += 1
        self._refresh_auto_backup_label()

    def stop_auto_backup(self):
        """停止自动备份（应用退出时调用）。"""
        if self._auto_backup_mgr:
            try:
                self._auto_backup_mgr.stop()
            except Exception:
                logging.exception('停止自动备份失败')

    def trigger_auto_backup_now(self):
        """立即触发一次自动备份（外部主动调用）。"""
        if self._auto_backup_mgr:
            self._auto_backup_mgr.trigger_now()

    # ============================================================
    # === v5 新增：精彩瞬间接收信号 → UI 状态栏通知 ===
    # ============================================================

    def _init_lan_moment_listener(self):
        """连接 LanPlanSender 单例的 momentReceived 信号。

        - 单例在首次访问时创建 HTTP 服务线程
        - 信号通过 Qt 跨线程机制投递到主线程
        - 失败不阻塞 UI（教练可能未启用局域网同步）
        """
        try:
            from training_tool.lan_plan_sender import get_sender
            self._lan_sender = get_sender()
            # 防止重复连接（DataCenterWindow 可能多次构造）
            # 注意：PySide6 在 disconnect 一个未连接的槽时会发出 RuntimeWarning
            # （而非 Exception，try/except 抓不到），需用 warnings 上下文抑制
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                try:
                    self._lan_sender.momentReceived.disconnect(self._on_moment_received)
                except RuntimeError:
                    pass
            self._lan_sender.momentReceived.connect(self._on_moment_received)
        except Exception as e:
            # 静默失败：不影响数据中心其他功能
            logging.exception('精彩瞬间监听初始化失败')
            self.lbl_auto_backup_status.setText(
                f'精彩瞬间接收未启用：{e}'
            )

    def _on_moment_received(self, student_name: str, save_path: str, file_size: int) -> None:
        """收到 Android 端推送的精彩瞬间照片时的回调（Qt 主线程）。

        - 在底部状态栏显示"收到精彩瞬间：学员名 (大小)"
        - 5 秒后自动恢复为自动备份状态文案
        - 不弹模态对话框，避免打断教练当前操作
        """
        try:
            size_kb = file_size / 1024
            if size_kb >= 1024:
                size_text = f'{size_kb / 1024:.1f}MB'
            else:
                size_text = f'{size_kb:.0f}KB'
            self.lbl_auto_backup_status.setText(
                f'✓ 收到精彩瞬间：{student_name}（{size_text}）'
            )
            # 5 秒后恢复自动备份状态显示
            from PySide6.QtCore import QTimer
            QTimer.singleShot(5000, self._refresh_auto_backup_label)
        except Exception:
            logging.exception('收到精彩瞬间通知处理失败')

    def get_moments_dir(self) -> str:
        """返回精彩瞬间照片保存目录（供报告面板读取融合）。"""
        try:
            from training_tool.lan_plan_sender import _PlanImageHTTPHandler
            return _PlanImageHTTPHandler._get_moments_dir()
        except Exception:
            logging.exception('获取精彩瞬间目录失败')
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            return os.path.join(base, 'MomentsPhotos')

    def _get_dir(self):
        """返回当前档案目录路径。"""
        return self.le_dir.text().strip()

    def get_current_directory(self):
        """公开 getter：返回当前档案目录，替代外部直接访问 _get_dir / _dir_path。"""
        return self._get_dir()

    def on_browse(self):
        """选择档案目录。"""
        path = QFileDialog.getExistingDirectory(
            self, '选择档案目录', self.le_dir.text() or DEFAULT_DIR)
        if path:
            self.le_dir.setText(path)
            self._dir_path = path
            self._refresh_all()

    def _refresh_all(self):
        """刷新所有子面板。"""
        self.panel_backup.refresh()
        self.panel_report.refresh()
        self.panel_renewal.refresh()
        self.panel_auto_backup.refresh()
        # v5 优化5：训练达成率面板为按需触发，无需在 _refresh_all 中自动刷新
        # 但保留接口调用以备后续扩展
        if hasattr(self.panel_achievement, 'refresh'):
            self.panel_achievement.refresh()
        # 顶部概览条跟随档案目录变化刷新
        if hasattr(self, '_refresh_stat_strip'):
            self._refresh_stat_strip()

    def set_archive_dir(self, dir_path):
        """外部设置档案目录（与体测档案模块同步）。"""
        if dir_path:
            self.le_dir.setText(dir_path)
            self._dir_path = dir_path
            self._refresh_all()

    def _on_check_update(self):
        """优化6新增：手动触发检查更新。

        向上遍历找到统一主窗口 App，调用其 show_update_dialog 方法。
        若未找到主窗口（独立运行模式），则直接弹出 UpdateDialog。
        """
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                top = app.activeWindow()
                # 向上查找持有 show_update_dialog 的顶层窗口
                while top is not None:
                    if hasattr(top, 'show_update_dialog'):
                        top.show_update_dialog()
                        return
                    parent = top.parentWidget()
                    if parent is None or parent is top:
                        break
                    top = parent
            # 回退：直接弹出对话框
            from update_dialog import UpdateDialog
            dlg = UpdateDialog(parent=self)
            dlg.exec()
        except Exception as e:
            logging.exception('检查更新失败')
            dialog.warn(self, '更新检查失败', str(e))

    def _on_open_db_snapshot(self):
        """v5 优化6 新增：打开数据库时光机回滚对话框。

        - 列出 _db_snapshots/ 下所有 .db 快照
        - 教练拖动滑条选择回滚点
        - 回滚前自动生成保护快照（防撤回）
        - 回滚成功后建议重启应用
        """
        try:
            from db_snapshot_dialog import DbSnapshotDialog
            dlg = DbSnapshotDialog(parent=self, dir_path=self.get_current_directory())
            ret = dlg.exec()
            if ret == dlg.Accepted:
                # 回滚成功：刷新所有面板并提示重启
                self._refresh_all()
                dialog.info(
                    self, '建议重启应用',
                    '数据库已成功回滚。\n\n'
                    '为刷新所有缓存，建议关闭并重新打开应用。'
                )
        except Exception as e:
            logging.exception('时光机打开失败')
            dialog.warn(self, '时光机打开失败', str(e))
