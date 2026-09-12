# -*- coding: utf-8 -*-
"""UI 层：一键成长报告面板。

职责：
- 学员选择与测评期次勾选
- QtCharts 趋势图预览
- 评语编辑与自动生成
- 导出 PDF 报告（M4-S3 起后台线程化）

M4-S3 改造：
- PDF 渲染（reportlab 文件 I/O）移入 ReportWorker，避免主线程阻塞
- QChart grab() 必须主线程，故保留 prepare_report_assets 在主线程执行
- 通过 WorkerSignals.progress / finished / error 实时反馈 UI
- 任务执行期间禁用导出按钮，防止并发触发
"""
import modern_dialog as dialog
import os
import sys
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QComboBox, QLabel, QTextEdit, QFileDialog, QMessageBox,
    QSplitter, QProgressBar
)
from PySide6.QtCharts import QChartView, QChart

# 注入父目录（student_sports_tool/）与 training_tool 设计资产目录
# （styles/cards 为包内 path-insert 式顶层模块，app.py 启动时同样插入）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, 'training_tool'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import report_coordinator as rco
from chart_renderer import create_trend_chart
from archive_manager import scan_student_files
from worker_pool import BaseWorker, run_worker
# 新设计语言令牌与组件（灰白简约 · 珊瑚橙强调）
from styles import Palette
from cards import Card


#==== 后台 Worker ====

class ReportWorker(BaseWorker):
    """PDF 报告生成 Worker（后台线程）。

    主线程已通过 prepare_report_assets 完成 QChart grab()，
    本 Worker 仅执行 finalize_report_pdf（reportlab 渲染 + 文件 I/O）。
    """

    def __init__(self, assets, output_path):
        super().__init__()
        self.assets = assets
        self.output_path = output_path

    def run_task(self):
        self.emit_progress(20, '正在生成 PDF 报告...')
        rco.finalize_report_pdf(
            self.assets, self.output_path, progress_cb=self._on_progress_cb
        )
        self.emit_progress(100, f'✓ PDF 已生成：{self.output_path}')
        self.emit_finished(self.output_path)

    def _on_progress_cb(self, message: str):
        """兼容 rco.finalize_report_pdf 的 (message:str)->None 回调。"""
        # 阶段二内部消息，固定在 20-90 区间，避免提前 100
        self.emit_progress(60, message)


#==== UI 面板 ====

class ReportPanel(QWidget):
    """一键成长报告面板。"""

    def __init__(self, dir_getter, parent=None):
        """
        参数:
            dir_getter: 返回当前档案目录路径的回调函数 () -> str
        """
        super().__init__(parent)
        self._dir_getter = dir_getter
        self._records = []
        self._running = False  # 任务运行中标志
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(0, 0, 0, 0)

        # 顶部：学员选择 + 操作按钮
        card_top = Card('选择学员与测评')
        tl = QHBoxLayout()
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(10)
        tl.addWidget(QLabel('学员：'))
        self.cb_student = QComboBox()
        self.cb_student.setMinimumWidth(140)
        self.cb_student.currentIndexChanged.connect(self.on_student_changed)
        tl.addWidget(self.cb_student)
        tl.addSpacing(16)
        tl.addWidget(QLabel('对比：'))
        self.cb_first = QComboBox()
        self.cb_first.setMinimumWidth(120)
        self.cb_last = QComboBox()
        self.cb_last.setMinimumWidth(120)
        tl.addWidget(QLabel('首次'))
        tl.addWidget(self.cb_first)
        tl.addWidget(QLabel('最近'))
        tl.addWidget(self.cb_last)
        tl.addStretch()
        self.btn_refresh = QPushButton('刷新学员', objectName='secondary')
        self.btn_refresh.clicked.connect(self.refresh)
        tl.addWidget(self.btn_refresh)
        self.btn_preview = QPushButton('预览趋势图', objectName='tertiary')
        self.btn_preview.clicked.connect(self.on_preview)
        tl.addWidget(self.btn_preview)
        self.btn_auto_comment = QPushButton('自动生成评语', objectName='secondary')
        self.btn_auto_comment.clicked.connect(self.on_auto_comment)
        tl.addWidget(self.btn_auto_comment)
        card_top.set_content_layout(tl)
        lay.addWidget(card_top)

        # 主体：左图表预览 / 右评语
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        # 左：图表
        card_chart = Card('总分趋势预览')
        cl = QVBoxLayout()
        cl.setContentsMargins(0, 0, 0, 0)
        self.chart_view = QChartView()
        # 全局 QSS 的 font-size:14px（像素字号）会让 QtCharts 内部 QFont pointSize=-1，
        # 每次 chart 渲染都刷 "QFont::setPointSize: Point size <= 0 (-1)" 警告；
        # 此处用 pt 单位覆盖（pt 会映射为合法 pointSize），警告消除
        self.chart_view.setStyleSheet(f'font-size: 10.5pt; background: {Palette.CARD};')
        self.chart_view.setMinimumHeight(300)
        cl.addWidget(self.chart_view)
        card_chart.set_content_layout(cl)
        splitter.addWidget(card_chart)

        # 右：评语
        card_comment = Card('教练评语（可编辑）')
        cml = QVBoxLayout()
        cml.setContentsMargins(0, 0, 0, 0)
        self.te_comment = QTextEdit()
        self.te_comment.setPlaceholderText('点击"自动生成评语"或手动输入...')
        cml.addWidget(self.te_comment)
        card_comment.set_content_layout(cml)
        splitter.addWidget(card_comment)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        lay.addWidget(splitter, 1)

        # 底部导出
        card_export = Card('导出报告')
        el = QVBoxLayout()
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(8)

        # 进度条（M4-S3 新增）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        el.addWidget(self.progress_bar)

        row_export = QHBoxLayout()
        row_export.addStretch()
        self.btn_export = QPushButton('导出 PDF 成长报告', objectName='primary')
        self.btn_export.clicked.connect(self.on_export_pdf)
        row_export.addWidget(self.btn_export)
        el.addLayout(row_export)
        card_export.set_content_layout(el)
        lay.addWidget(card_export)

    #==== 公共接口 ====

    def refresh(self):
        """刷新学员列表。"""
        dir_path = self._dir_getter()
        self.cb_student.blockSignals(True)
        self.cb_student.clear()
        self.cb_student.addItem('请选择学员')
        if dir_path and os.path.isdir(dir_path):
            for fname, _ in scan_student_files(dir_path):
                self.cb_student.addItem(fname[:-5])
        self.cb_student.blockSignals(False)
        self._records = []
        self.cb_first.clear()
        self.cb_last.clear()
        self.chart_view.setChart(QChart())

    #==== 内部状态切换 ====

    def _set_running(self, running: bool):
        """切换任务运行状态：禁用/启用按钮 + 显示/隐藏进度条。"""
        self._running = running
        for btn in (self.btn_refresh, self.btn_preview,
                    self.btn_auto_comment, self.btn_export,
                    self.cb_student, self.cb_first, self.cb_last):
            btn.setEnabled(not running)
        self.progress_bar.setVisible(running)
        if running:
            self.progress_bar.setValue(0)

    def _connect_worker(self, worker, on_finished, task_name: str):
        """统一连接 Worker 信号：进度→进度条；完成→自定义回调+恢复 UI；错误→弹框。"""

        def on_progress(percent, msg):
            self.progress_bar.setValue(percent)
            if msg:
                self.te_comment.setPlaceholderText(msg)

        def on_error(err_str):
            self._set_running(False)
            self.te_comment.setPlaceholderText('点击"自动生成评语"或手动输入...')
            dialog.error(self, f'{task_name}失败', err_str)

        def _on_finished(result):
            self._set_running(False)
            self.progress_bar.setValue(100)
            self.te_comment.setPlaceholderText('点击"自动生成评语"或手动输入...')
            on_finished(result)

        worker.signals.progress.connect(on_progress)
        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(on_error)
        self._set_running(True)
        run_worker(worker)

    #==== 业务回调 ====

    def on_student_changed(self, idx):
        """选择学员后加载测评记录。"""
        if idx <= 0:
            self._records = []
            self.cb_first.clear()
            self.cb_last.clear()
            self.chart_view.setChart(QChart())
            return
        name = self.cb_student.itemText(idx)
        dir_path = self._dir_getter()
        try:
            info, records = rco.load_student_records(dir_path, name)
            self._records = rco.get_scored_records(records)
        except Exception:
            self._records = []
        # 填充期次选择
        self.cb_first.clear()
        self.cb_last.clear()
        for i, rec in enumerate(self._records):
            label = f"第{rec.get('seq', i+1)}次 {rec.get('date', '')} ({round(rec.get('total',0),1)}分)"
            self.cb_first.addItem(label)
            self.cb_last.addItem(label)
        if len(self._records) >= 2:
            self.cb_first.setCurrentIndex(0)
            self.cb_last.setCurrentIndex(len(self._records) - 1)
        elif self._records:
            self.cb_first.setCurrentIndex(0)
            self.cb_last.setCurrentIndex(0)
        self.on_preview()

    def on_preview(self):
        """预览趋势图。"""
        if not self._records:
            return
        try:
            chart = create_trend_chart(self._records)
            # chart_renderer 默认灰底，这里适配卡片白底
            chart.setBackgroundBrush(QColor(Palette.CARD))
            self.chart_view.setChart(chart)
        except Exception as e:
            dialog.warn(self, '预览失败', str(e))

    def on_auto_comment(self):
        """自动生成评语。"""
        if not self._records or len(self._records) < 2:
            dialog.info(self, '提示', '至少需要2次测评才能生成评语')
            return
        first_idx = self.cb_first.currentIndex()
        last_idx = self.cb_last.currentIndex()
        if first_idx < 0 or last_idx < 0:
            return
        try:
            comment = rco.generate_default_comment(self._records, first_idx, last_idx)
            self.te_comment.setPlainText(comment)
        except Exception as e:
            dialog.warn(self, '生成失败', str(e))

    def on_export_pdf(self):
        """导出 PDF 报告（后台线程化）。

        阶段一（主线程）：prepare_report_assets - 加载记录、生成评语、QChart grab()
        阶段二（后台）：finalize_report_pdf - reportlab 渲染 + 文件 I/O
        """
        if self._running:
            return
        name = self.cb_student.currentText()
        if not name or name == '请选择学员':
            dialog.warn(self, '提示', '请先选择学员')
            return
        if not self._records:
            dialog.warn(self, '提示', '该学员无测评记录')
            return
        first_idx = max(0, self.cb_first.currentIndex())
        last_idx = max(0, self.cb_last.currentIndex())
        comment = self.te_comment.toPlainText().strip()

        default_name = f'{name}_成长报告.pdf'
        path, _ = QFileDialog.getSaveFileName(
            self, '导出成长报告', default_name, 'PDF文件 (*.pdf)')
        if not path:
            return
        if not path.endswith('.pdf'):
            path += '.pdf'

        dir_path = self._dir_getter()

        # 阶段一：主线程准备资源（含 QChart grab，必须主线程）
        try:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(5)
            self.te_comment.setPlaceholderText('正在准备报告资源...')
            assets = rco.prepare_report_assets(
                dir_path, name, first_idx, last_idx, comment
            )
        except Exception as e:
            self.progress_bar.setVisible(False)
            self.te_comment.setPlaceholderText('点击"自动生成评语"或手动输入...')
            dialog.error(self, '导出失败', str(e))
            return

        # 阶段二：后台线程渲染 PDF
        worker = ReportWorker(assets, path)

        def on_finished(result_path):
            # 清理阶段一临时图片
            try:
                rco.cleanup_report_assets(assets)
            except Exception:
                logging.exception('清理报告临时资源失败')
            dialog.info(
                self, '导出成功', f'报告已保存到：\n{result_path}'
            )

        self._connect_worker(worker, on_finished, '导出报告')
