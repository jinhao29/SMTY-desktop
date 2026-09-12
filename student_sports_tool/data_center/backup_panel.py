# -*- coding: utf-8 -*-
"""UI 层：数据备份/导入/导出/恢复面板。

职责：
- 提供四个操作按钮与进度日志显示
- 调用 backup_coordinator 完成具体操作（M4-S2 起改用 worker_pool 后台线程化）
- 档案目录由父窗口传入

M4-S2 改造：
- do_backup / do_restore / do_export_summary / import_students_from_excel
  全部移到 BaseWorker 子类中执行，避免阻塞主线程
- 通过 WorkerSignals.progress / finished / error 实时反馈 UI
- 任务执行期间禁用所有按钮，防止并发触发
"""
import modern_dialog as dialog
import logging
import os
import sys
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QTextEdit, QFileDialog, QMessageBox, QLabel, QLineEdit, QProgressBar
)
from PySide6.QtGui import QFont

# 注入父目录（student_sports_tool/）与 training_tool 设计资产目录
# （styles/cards 为包内 path-insert 式顶层模块，app.py 启动时同样插入）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, 'training_tool'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import backup_coordinator as bc
from worker_pool import BaseWorker, run_worker
# 新设计语言令牌与组件（灰白简约 · 珊瑚橙强调）
from styles import Spacing
from cards import Card


#==== 后台 Worker 子类（每个耗时操作一个）====

class BackupWorker(BaseWorker):
    """一键备份 Worker。"""

    def __init__(self, dir_path, target_dir):
        super().__init__()
        self.dir_path = dir_path
        self.target_dir = target_dir

    def run_task(self):
        cb = self.make_progress_cb()
        self.emit_progress(5, f'开始备份：{self.dir_path} → {self.target_dir}')
        result = bc.do_backup(self.dir_path, self.target_dir, cb)
        self.emit_progress(100, f'✓ 备份完成：{result[1]} 个文件')
        self.emit_finished(result)  # (zip_path, packed, skipped)


class RestoreWorker(BaseWorker):
    """从备份恢复 Worker（含 Android 数据转换）。"""

    def __init__(self, zip_path, target_dir, conflict_resolutions=None):
        super().__init__()
        self.zip_path = zip_path
        self.target_dir = target_dir
        # v5 优化4：冲突解决策略（由 DataConflictResolver 弹窗返回）
        self.conflict_resolutions = conflict_resolutions

    def run_task(self):
        cb = self.make_progress_cb()
        self.emit_progress(5, f'开始恢复：{self.zip_path} → {self.target_dir}')
        result = bc.do_restore(
            self.zip_path, self.target_dir, cb,
            conflict_resolutions=self.conflict_resolutions
        )
        self.emit_progress(100, f'✓ 恢复完成：{result[0]} 个文件')
        self.emit_finished(result)  # (count, auto_backup_path)


class ExportSummaryWorker(BaseWorker):
    """导出学员总览 Worker。"""

    def __init__(self, dir_path, output_path):
        super().__init__()
        self.dir_path = dir_path
        self.output_path = output_path

    def run_task(self):
        cb = self.make_progress_cb()
        self.emit_progress(5, f'开始导出总览：{self.dir_path} → {self.output_path}')
        count = bc.do_export_summary(self.dir_path, self.output_path, cb)
        self.emit_progress(100, f'✓ 导出完成：{count} 位学员')
        self.emit_finished({'count': count, 'path': self.output_path})


class ImportStudentsWorker(BaseWorker):
    """批量导入学员名单 Worker。"""

    def __init__(self, import_path, dir_path):
        super().__init__()
        self.import_path = import_path
        self.dir_path = dir_path

    def run_task(self):
        cb = self.make_progress_cb()
        self.emit_progress(5, f'开始导入：{self.import_path} → {self.dir_path}')
        created, conflicts = bc.import_students_from_excel(
            self.import_path, self.dir_path, cb
        )
        self.emit_progress(100, f'✓ 导入完成：新建 {created} 个档案')
        self.emit_finished({'created': created, 'conflicts': conflicts})


class MiniprogramExportWorker(BaseWorker):
    """导出小程序备份 JSON Worker（阶段五互通）。"""

    def __init__(self, dir_path, mode, output_path):
        super().__init__()
        self.dir_path = dir_path
        self.mode = mode
        self.output_path = output_path

    def run_task(self):
        cb = self.make_progress_cb()
        result = bc.export_miniprogram_backup(self.dir_path, self.mode,
                                              self.output_path, cb)
        self.emit_progress(100, f'✓ 导出完成：{result["students"]} 位学员')
        self.emit_finished(result)


class MiniprogramImportWorker(BaseWorker):
    """导入小程序备份 JSON Worker（阶段五互通）。"""

    def __init__(self, import_path, dir_path):
        super().__init__()
        self.import_path = import_path
        self.dir_path = dir_path

    def run_task(self):
        cb = self.make_progress_cb()
        result = bc.import_miniprogram_backup(self.import_path, self.dir_path, cb)
        self.emit_progress(100, '✓ 导入完成')
        self.emit_finished(result)


#==== UI 面板 ====

class BackupPanel(QWidget):
    """数据备份与导入导出面板。"""

    def __init__(self, dir_getter, on_auto_backup_clicked=None, parent=None):
        """
        参数:
            dir_getter: 返回当前档案目录路径的回调函数 () -> str
            on_auto_backup_clicked: 点击"自动备份设置"时回调（切换到配置 Tab）
        """
        super().__init__(parent)
        self._dir_getter = dir_getter
        self._on_auto_backup_clicked = on_auto_backup_clicked
        self._running = False  # 任务运行中标志
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(Spacing.CARD)
        lay.setContentsMargins(0, 0, 0, 0)

        # 档案目录显示卡
        card_dir = Card('当前档案目录')
        dl = QHBoxLayout()
        dl.setContentsMargins(0, 0, 0, 0)
        self.lbl_dir = QLabel('（未选择）')
        self.lbl_dir.setStyleSheet('color:#9B9B9B;')
        dl.addWidget(self.lbl_dir)
        card_dir.set_content_layout(dl)
        lay.addWidget(card_dir)

        # 操作按钮卡（3列网格，整齐排列）
        card_ops = Card('数据操作')
        ol = QVBoxLayout()
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(14)
        ops_grid = QGridLayout()
        ops_grid.setSpacing(14)
        self.btn_backup = QPushButton('一键备份所有档案', objectName='primary')
        self.btn_backup.clicked.connect(self.on_backup)
        self.btn_restore = QPushButton('从备份恢复', objectName='secondary')
        self.btn_restore.clicked.connect(self.on_restore)
        self.btn_export = QPushButton('导出学员总览 Excel', objectName='tertiary')
        self.btn_export.clicked.connect(self.on_export_summary)
        self.btn_import = QPushButton('批量导入学员名单', objectName='tertiary')
        self.btn_import.clicked.connect(self.on_import)
        self.btn_template = QPushButton('下载导入模板', objectName='secondary')
        self.btn_template.clicked.connect(self.on_download_template)
        # 阶段五互通：与微信小程序本地数据互导
        self.btn_mp_export = QPushButton('导出小程序数据(JSON)', objectName='tertiary')
        self.btn_mp_export.clicked.connect(self.on_miniprogram_export)
        self.btn_mp_import = QPushButton('导入小程序数据(JSON)', objectName='tertiary')
        self.btn_mp_import.clicked.connect(self.on_miniprogram_import)
        # 入口按钮：打开自动备份配置页（回调由 DataCenterWindow 提供）
        self.btn_auto_backup = QPushButton('自动备份设置', objectName='tertiary')
        if self._on_auto_backup_clicked:
            self.btn_auto_backup.clicked.connect(self._on_auto_backup_clicked)
        else:
            self.btn_auto_backup.setEnabled(False)
            self.btn_auto_backup.setToolTip('自动备份设置入口未连接')
        ops_grid.addWidget(self.btn_backup, 0, 0)
        ops_grid.addWidget(self.btn_restore, 0, 1)
        ops_grid.addWidget(self.btn_export, 0, 2)
        ops_grid.addWidget(self.btn_import, 1, 0)
        ops_grid.addWidget(self.btn_template, 1, 1)
        ops_grid.addWidget(self.btn_auto_backup, 1, 2)
        ops_grid.addWidget(self.btn_mp_export, 2, 0)
        ops_grid.addWidget(self.btn_mp_import, 2, 1)
        # 售后支持：远程排查入口（日志在 %USERPROFILE%\.shangmentiyu\app.log）
        self.btn_log_dir = QPushButton('打开日志文件夹（远程排查用）', objectName='tertiary')
        self.btn_log_dir.clicked.connect(self.on_open_log_folder)
        ops_grid.addWidget(self.btn_log_dir, 2, 2)
        for c in range(3):
            ops_grid.setColumnStretch(c, 1)
        ol.addLayout(ops_grid)
        card_ops.set_content_layout(ol)
        lay.addWidget(card_ops)

        # 备份加密口令卡（v1.0.3）：解密从手机传入的加密备份
        card_pwd = Card('备份加密口令')
        pl = QVBoxLayout()
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)
        lbl_pwd_hint = QLabel(
            '手机端「设置 → 数据管理 → 备份加密口令」设置了口令后，'
            '备份包内的数据库将加密存储；在此填入同一口令方可恢复。留空表示备份未加密。')
        lbl_pwd_hint.setWordWrap(True)
        lbl_pwd_hint.setStyleSheet('color:#9B9B9B;')
        pl.addWidget(lbl_pwd_hint)
        pwd_row = QHBoxLayout()
        pwd_row.setSpacing(10)
        self.le_backup_passphrase = QLineEdit()
        self.le_backup_passphrase.setEchoMode(QLineEdit.Password)
        self.le_backup_passphrase.setPlaceholderText('加密口令（未加密备份可留空）')
        try:
            from data_center.config_manager import load_config
            self.le_backup_passphrase.setText(
                str(load_config(self._dir_getter()).get('backup_passphrase') or ''))
        except Exception:
            pass
        self.le_backup_passphrase.editingFinished.connect(self._save_backup_passphrase)
        pwd_row.addWidget(self.le_backup_passphrase, 1)
        self.btn_pwd_toggle = QPushButton('显示', objectName='tertiary')
        self.btn_pwd_toggle.setCheckable(True)
        self.btn_pwd_toggle.setFixedWidth(64)
        self.btn_pwd_toggle.toggled.connect(self._toggle_passphrase_echo)
        pwd_row.addWidget(self.btn_pwd_toggle)
        pl.addLayout(pwd_row)
        card_pwd.set_content_layout(pl)
        lay.addWidget(card_pwd)

        # 进度条（M4-S2 新增）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        lay.addWidget(self.progress_bar)

        # 操作日志卡（固定高度 150px，内部滚动，不再弹性拉伸）
        card_log = Card('操作日志')
        ll = QVBoxLayout()
        ll.setContentsMargins(0, 0, 0, 0)
        self.te_log = QTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setFixedHeight(150)
        self.te_log.setPlaceholderText('操作日志将显示在这里...')
        ll.addWidget(self.te_log)
        card_log.set_content_layout(ll)
        lay.addWidget(card_log)
        lay.addStretch()

    def refresh(self):
        """刷新目录显示。"""
        d = self._dir_getter()
        self.lbl_dir.setText(d or '（未选择）')

    # === v1.0.3 备份加密口令 ===

    def _toggle_passphrase_echo(self, checked: bool):
        """切换口令明文/密文显示。"""
        self.le_backup_passphrase.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password)
        self.btn_pwd_toggle.setText('隐藏' if checked else '显示')

    def _save_backup_passphrase(self):
        """口令变更后写入配置（持久化，重启不丢）。"""
        try:
            from data_center.config_manager import update_config
            update_config(self._dir_getter(),
                          backup_passphrase=self.le_backup_passphrase.text().strip())
        except Exception as e:
            logging.getLogger(__name__).warning('保存备份加密口令失败：%s', e)

    def _current_passphrase(self) -> str:
        """取当前口令：优先界面输入，回退环境变量 SMTY_BACKUP_PASSPHRASE。"""
        value = self.le_backup_passphrase.text().strip()
        if value:
            return value
        return (os.environ.get('SMTY_BACKUP_PASSPHRASE') or '').strip()

    @staticmethod
    def _backup_looks_encrypted(zip_path: str) -> bool:
        """探测备份包是否为加密包（读 manifest）。

        提前拦截的意义：加密包在缺口令时若直接进恢复流程，
        会以"数据库损坏"的面目失败，误导教练以为备份坏了。
        """
        import json
        import zipfile
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if 'backup_manifest.json' not in zf.namelist():
                    return False
                manifest = json.loads(zf.read('backup_manifest.json').decode('utf-8'))
                return bool(manifest.get('encrypted'))
        except (zipfile.BadZipFile, OSError, ValueError, KeyError):
            return False

    def _log(self, msg):
        """追加日志。"""
        from datetime import datetime
        ts = datetime.now().strftime('%H:%M:%S')
        self.te_log.append(f'[{ts}] {msg}')

    def _set_running(self, running: bool):
        """切换任务运行状态：禁用/启用按钮 + 显示/隐藏进度条。"""
        self._running = running
        for btn in (self.btn_backup, self.btn_restore,
                    self.btn_export, self.btn_import, self.btn_template,
                    self.btn_mp_export, self.btn_mp_import):
            btn.setEnabled(not running)
        self.progress_bar.setVisible(running)
        if running:
            self.progress_bar.setValue(0)

    def _connect_worker(self, worker, on_finished, task_name: str):
        """统一连接 Worker 信号：进度→进度条+日志；完成→自定义回调+恢复 UI；错误→日志+弹框。"""
        def on_progress(percent, msg):
            self.progress_bar.setValue(percent)
            if msg:
                self._log(msg)

        def on_error(err_str):
            self._set_running(False)
            self._log(f'✗ {task_name}失败：{err_str}')
            dialog.error(self, f'{task_name}失败', err_str)

        def _on_finished(result):
            self._set_running(False)
            self.progress_bar.setValue(100)
            on_finished(result)

        worker.signals.progress.connect(on_progress)
        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(on_error)
        self._set_running(True)
        run_worker(worker)

    #==== 操作回调 ====

    def on_backup(self):
        """一键备份（后台线程）。"""
        if self._running:
            return
        dir_path = self._dir_getter()
        if not dir_path or not os.path.isdir(dir_path):
            dialog.warn(self, '提示', '请先选择有效的档案目录')
            return
        target_dir = QFileDialog.getExistingDirectory(self, '选择备份保存位置', os.path.expanduser('~'))
        if not target_dir:
            return

        worker = BackupWorker(dir_path, target_dir)

        def on_finished(result):
            zip_path, packed, skipped = result
            if skipped:
                self._log(f'  跳过被占用文件：{", ".join(skipped)}')
            dialog.info(
                self, '备份成功', f'已备份 {packed} 个文件到：\n{zip_path}'
            )

        self._connect_worker(worker, on_finished, '备份')

    def on_restore(self):
        """从备份恢复（后台线程）。"""
        if self._running:
            return
        dir_path = self._dir_getter()
        if not dir_path:
            dialog.warn(self, '提示', '请先选择档案目录')
            return
        zip_path, _ = QFileDialog.getOpenFileName(
            self, '选择备份文件', '', '备份文件 (*.zip)')
        if not zip_path:
            return
        reply = dialog.confirm(
            self, '确认恢复',
            f'将从备份恢复到：{dir_path}\n'
            f'恢复前会自动备份当前数据。\n\n确认继续？')
        if not reply:
            return

        # === v5 优化4 新增：恢复前先检测冲突，让教练逐条确认 ===
        # 通过进度对话框展示检测过程（避免界面无响应）
        conflict_resolutions = None
        try:
            from PySide6.QtWidgets import QProgressDialog
            from conflict_detector import detect_conflicts_from_zip
            from data_conflict_resolver import DataConflictResolver

            progress = QProgressDialog('正在检测数据冲突...', None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setCancelButton(None)
            progress.setMinimumDuration(0)
            progress.show()

            # 检测在主线程同步执行（zip 解析通常 < 2s）
            conflicts = detect_conflicts_from_zip(zip_path, dir_path)

            progress.hide()

            if conflicts:
                dlg = DataConflictResolver(conflicts, parent=self)
                if dlg.exec() == dlg.Accepted:
                    conflict_resolutions = dlg.get_resolutions()
                else:
                    # 教练取消：放弃恢复
                    self._log('已取消恢复（冲突解决未确认）')
                    return
        except Exception as e:
            # 冲突检测失败不阻塞恢复流程，按原默认逻辑执行
            dialog.warn(
                self, '冲突检测跳过',
                f'冲突检测过程出错，将按默认逻辑恢复：\n{e}'
            )
            conflict_resolutions = None

        # v1.0.3：把界面口令注入环境变量，供 archive_manager 解密加密备份
        # （口径统一在 archive_manager 的 SMTY_BACKUP_PASSPHRASE，避免多处解析）
        passphrase = self._current_passphrase()
        if passphrase:
            os.environ['SMTY_BACKUP_PASSPHRASE'] = passphrase
        else:
            os.environ.pop('SMTY_BACKUP_PASSPHRASE', None)
            if self._backup_looks_encrypted(zip_path):
                dialog.warn(
                    self, '需要加密口令',
                    '该备份已加密，但未填写「备份加密口令」。\n'
                    '请在备份面板的「备份加密口令」一栏填入手机端设置的同一口令后重试。')
                return

        worker = RestoreWorker(zip_path, dir_path, conflict_resolutions)

        def on_finished(result):
            count, auto_backup = result
            if auto_backup:
                self._log(f'  恢复前自动备份已保存：{auto_backup}')
            dialog.info(self, '恢复成功', f'已恢复 {count} 个文件')

        self._connect_worker(worker, on_finished, '恢复')

    def on_export_summary(self):
        """导出学员总览（后台线程）。"""
        if self._running:
            return
        dir_path = self._dir_getter()
        if not dir_path or not os.path.isdir(dir_path):
            dialog.warn(self, '提示', '请先选择有效的档案目录')
            return
        default_name = f'学员总览_{os.path.basename(dir_path)}.xlsx'
        path, _ = QFileDialog.getSaveFileName(
            self, '导出学员总览', default_name, 'Excel文件 (*.xlsx)')
        if not path:
            return
        if not path.endswith('.xlsx'):
            path += '.xlsx'

        worker = ExportSummaryWorker(dir_path, path)

        def on_finished(result):
            dialog.info(
                self, '导出成功',
                f'已导出 {result["count"]} 位学员数据到：\n{result["path"]}'
            )

        self._connect_worker(worker, on_finished, '导出')

    def on_import(self):
        """批量导入学员（后台线程）。"""
        if self._running:
            return
        dir_path = self._dir_getter()
        if not dir_path:
            dialog.warn(self, '提示', '请先选择档案目录')
            return
        path, _ = QFileDialog.getOpenFileName(
            self, '选择学员名单 Excel', '', 'Excel文件 (*.xlsx *.xls)')
        if not path:
            return

        worker = ImportStudentsWorker(path, dir_path)

        def on_finished(result):
            created = result['created']
            conflicts = result['conflicts']
            if conflicts:
                self._log(f'  已存在跳过：{", ".join(conflicts)}')
            dialog.info(
                self, '导入成功',
                f'新建 {created} 个学员档案' +
                (f'\n跳过 {len(conflicts)} 个已存在' if conflicts else '')
            )

        self._connect_worker(worker, on_finished, '导入')

    def on_download_template(self):
        """下载导入模板（轻量操作，保持同步执行）。"""
        path, _ = QFileDialog.getSaveFileName(
            self, '保存导入模板', '学员名单导入模板.xlsx', 'Excel文件 (*.xlsx)')
        if not path:
            return
        if not path.endswith('.xlsx'):
            path += '.xlsx'
        try:
            bc.generate_import_template(path)
            self._log(f'✓ 模板已保存：{path}')
            dialog.info(self, '模板已生成', f'模板已保存到：\n{path}')
        except Exception as e:
            self._log(f'✗ 模板生成失败：{e}')
            dialog.error(self, '生成失败', str(e))

    def _current_mode(self) -> str:
        """当前数据模式（shangmen/club），取不到时回退 shangmen。"""
        try:
            from data_center.mode_config import get_current_mode
            return str(get_current_mode() or 'shangmen')
        except Exception:
            return 'shangmen'

    def on_open_log_folder(self):
        """远程排查入口：打开运行日志所在文件夹（app.log 由 RotatingFileHandler 写入）。"""
        log_dir = os.path.join(os.path.expanduser('~'), '.shangmentiyu')
        os.makedirs(log_dir, exist_ok=True)
        try:
            os.startfile(log_dir)  # noqa: only Windows
            self._log(f'已打开日志文件夹：{log_dir}')
        except Exception as e:
            self._log(f'✗ 打开日志文件夹失败：{e}（请手动访问 {log_dir}）')

    def on_miniprogram_export(self):
        """导出小程序备份 JSON（后台线程）。"""
        if self._running:
            return
        dir_path = self._dir_getter()
        if not dir_path or not os.path.isdir(dir_path):
            dialog.warn(self, '提示', '请先选择有效的档案目录')
            return
        mode = self._current_mode()
        default_name = f'backup_{mode}_{datetime.now().strftime("%Y-%m-%d")}.json'
        path, _ = QFileDialog.getSaveFileName(
            self, '导出小程序数据', default_name, 'JSON文件 (*.json)')
        if not path:
            return

        worker = MiniprogramExportWorker(dir_path, mode, path)

        def on_finished(result):
            dialog.info(
                self, '导出成功',
                f'已导出 {result["students"]} 位学员到：\n{result["path"]}\n\n'
                f'文件发送到手机微信后，在小程序「我的 → 数据 → 导入备份」中选择即可导入。')

        self._connect_worker(worker, on_finished, '导出小程序数据')

    def on_miniprogram_import(self):
        """导入小程序备份 JSON（后台线程）。"""
        if self._running:
            return
        dir_path = self._dir_getter()
        if not dir_path or not os.path.isdir(dir_path):
            dialog.warn(self, '提示', '请先选择有效的档案目录')
            return
        path, _ = QFileDialog.getOpenFileName(
            self, '选择小程序备份 JSON', '', 'JSON文件 (*.json)')
        if not path:
            return

        worker = MiniprogramImportWorker(path, dir_path)

        def on_finished(result):
            msg = (f'新建 {result["created"]} 个学员，更新 {result["updated"]} 个，'
                   f'跳过软删 {result["skipped_deleted"]} 个；'
                   f'写入剩余课时 {result["lessons_applied"]} 人')
            self._log(f'  {msg}；跳过表：{", ".join(result["skipped_tables"]) or "无"}')
            dialog.info(self, '导入成功', msg)

        self._connect_worker(worker, on_finished, '导入小程序数据')
