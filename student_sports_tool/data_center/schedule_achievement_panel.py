# -*- coding: utf-8 -*-
"""UI 层：训练达成率偏差分析面板（v5 优化5 新增）。

职责：
- 选择 Android 备份 zip 与目标月份
- 调用 schedule_lesson_analyzer.analyze_schedule_lesson_deviation 获取分析结果
- 使用 QtCharts 绘制柱状图（计划 vs 实际，按学员维度）
- 概览卡片展示：计划排课数 / 实际签到数 / 缺勤数 / 达成率
- 学员明细表 + 缺勤日期列表
- 支持导出图表为 PNG（教练可截图发家长）

设计原则：
- 纯展示层，业务逻辑由 schedule_lesson_analyzer 处理
- 后台线程执行分析，避免阻塞 UI
- 失败静默降级（无 schedules 表时提示"无排课数据"）
"""
import modern_dialog as dialog
import logging
import os
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QComboBox, QLabel, QLineEdit, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter
)
from PySide6.QtCharts import (
    QChartView, QChart, QBarSeries, QBarSet, QBarCategoryAxis,
    QValueAxis, QLineSeries
)

from worker_pool import BaseWorker, run_worker


# 浅色珊瑚橙主题配色（与 chart_renderer 保持一致）
COLOR_PLANNED = '#FF6B47'    # 计划：珊瑚橙
COLOR_ACTUAL = '#22c55e'     # 实际：绿
COLOR_ABSENT = '#ef4444'     # 缺勤：红
COLOR_GRID = '#E5E5E5'
COLOR_TEXT = '#6B6B6B'
COLOR_BG = '#F5F7FA'


class AchievementWorker(BaseWorker):
    """训练达成率分析 Worker（后台线程）。"""

    def __init__(self, zip_path, target_dir, year, month):
        super().__init__()
        self.zip_path = zip_path
        self.target_dir = target_dir
        self.year = year
        self.month = month

    def run_task(self):
        import schedule_lesson_analyzer as sla
        cb = self.make_progress_cb()
        self.emit_progress(10, f'正在分析 {self.year}-{self.month:02d} 训练达成率...')
        try:
            result = sla.analyze_schedule_lesson_deviation(
                self.zip_path, self.target_dir,
                year=self.year, month=self.month,
                progress_cb=cb
            )
            self.emit_progress(100, '✓ 分析完成')
            self.emit_finished(result)
        except Exception as e:
            self.emit_error(str(e))


class ScheduleAchievementPanel(QWidget):
    """训练达成率偏差分析面板（v5 优化5）。"""

    def __init__(self, dir_getter, parent=None):
        """
        参数:
            dir_getter: 返回当前档案目录路径的回调函数 () -> str
        """
        super().__init__(parent)
        self._dir_getter = dir_getter
        self._running = False
        self._last_result = None  # 缓存最近一次分析结果（导出 PNG 用）
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(0, 0, 0, 0)

        # === 顶部控制栏 ===
        gb_ctrl = QGroupBox('分析参数')
        gb_ctrl.setObjectName('card')
        cl = QHBoxLayout(gb_ctrl)
        cl.setSpacing(10)

        cl.addWidget(QLabel('Android 备份 zip：'))
        self.le_zip = QLineEdit()
        self.le_zip.setPlaceholderText('自动使用双端同步的最新手机备份，也可手动选择')
        self.le_zip.setStyleSheet('color:#1A1A1A;')
        cl.addWidget(self.le_zip, 1)

        self.btn_pick_zip = QPushButton('选择', objectName='secondary')
        self.btn_pick_zip.clicked.connect(self._on_pick_zip)
        cl.addWidget(self.btn_pick_zip)

        self.btn_autodetect = QPushButton('找最新', objectName='secondary')
        self.btn_autodetect.setToolTip('自动查找双端同步接收的最新手机备份')
        self.btn_autodetect.clicked.connect(self._autodetect_backup)
        cl.addWidget(self.btn_autodetect)

        cl.addWidget(QLabel('月份：'))
        self.cb_month = QComboBox()
        self._fill_month_combo()
        self.cb_month.currentIndexChanged.connect(self._on_month_changed)
        cl.addWidget(self.cb_month)

        self.btn_analyze = QPushButton('生成达成率报告', objectName='primary')
        self.btn_analyze.clicked.connect(self._on_analyze)
        cl.addWidget(self.btn_analyze)

        self.btn_export_png = QPushButton('导出 PNG', objectName='tertiary')
        self.btn_export_png.setToolTip('将当前图表导出为 PNG 图片，可截图发家长')
        self.btn_export_png.clicked.connect(self._on_export_png)
        self.btn_export_png.setEnabled(False)
        cl.addWidget(self.btn_export_png)

        lay.addWidget(gb_ctrl)

        # === 概览卡片：计划/实际/缺勤/达成率 ===
        gb_overview = QGroupBox('本月概览')
        gb_overview.setObjectName('card')
        ol = QHBoxLayout(gb_overview)
        ol.setSpacing(10)
        self.lbl_planned = self._make_metric_card(ol, '计划排课', '0', COLOR_PLANNED)
        self.lbl_actual = self._make_metric_card(ol, '实际签到', '0', COLOR_ACTUAL)
        self.lbl_absent = self._make_metric_card(ol, '缺勤次数', '0', COLOR_ABSENT)
        self.lbl_rate = self._make_metric_card(ol, '达成率', '0.0%', '#a855f7')
        lay.addWidget(gb_overview)

        # === 图表 + 明细表（左右分栏） ===
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：图表
        gb_chart = QGroupBox('训练达成率柱状图（按学员）')
        gb_chart.setObjectName('card')
        chl = QVBoxLayout(gb_chart)
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(320)
        chl.addWidget(self.chart_view)
        splitter.addWidget(gb_chart)

        # 右侧：明细表
        gb_detail = QGroupBox('学员明细')
        gb_detail.setObjectName('card')
        dl = QVBoxLayout(gb_detail)
        self.tbl_detail = QTableWidget(0, 5)
        self.tbl_detail.setHorizontalHeaderLabels(
            ['学员', '计划', '实际', '缺勤', '达成率']
        )
        self.tbl_detail.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_detail.setEditTriggers(QTableWidget.NoEditTriggers)
        dl.addWidget(self.tbl_detail)
        splitter.addWidget(gb_detail)

        splitter.setSizes([520, 380])
        lay.addWidget(splitter, 1)

        # === 缺勤明细 ===
        gb_absent = QGroupBox('缺勤明细（计划了但未签到）')
        gb_absent.setObjectName('card')
        al = QVBoxLayout(gb_absent)
        self.tbl_absent = QTableWidget(0, 3)
        self.tbl_absent.setHorizontalHeaderLabels(['学员', '日期', '计划内容'])
        self.tbl_absent.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_absent.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_absent.setMinimumHeight(140)
        al.addWidget(self.tbl_absent)
        lay.addWidget(gb_absent)

        # === v23.5：面板打开即自动填充双端同步的最新手机备份 ===
        self._autodetect_backup(quiet=True)

    def _autodetect_backup(self, quiet: bool = False):
        """自动查找最新的手机端备份（同步接收目录优先），填入输入框。

        quiet=True 时不弹提示（面板初始化静默调用）。
        """
        try:
            try:
                from schedule_lesson_analyzer import find_latest_phone_backup
            except ImportError:
                # 测试/包导入环境：data_center 不在 sys.path 时走包导入
                from data_center.schedule_lesson_analyzer import find_latest_phone_backup
            path = find_latest_phone_backup(self._dir_getter() or '')
        except Exception:
            logging.exception('自动查找手机备份失败')
            path = ''
        if path:
            self.le_zip.setText(path)
            if not quiet:
                self._on_analyze()
        elif not quiet:
            try:
                import modern_dialog as dialog
                dialog.info(self, '提示',
                            '未找到手机端备份：请先完成一次双端同步（或手动选择备份文件）')
            except Exception:
                pass

    def _make_metric_card(self, parent_layout, title, value, color):
        """创建一个概览指标卡片（垂直布局：标题 + 大数值）。"""
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background: #FFFFFF;
                border: 1px solid #E5E5E5;
                border-radius: 10px;
                padding: 12px 8px;
            }}
        """)
        v = QVBoxLayout(card)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet('color:#6B6B6B; font-size:11px; border:none; background:transparent;')
        lbl_title.setAlignment(Qt.AlignCenter)
        v.addWidget(lbl_title)
        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(
            f'color:{color}; font-size:22px; font-weight:bold; '
            f'border:none; background:transparent;'
        )
        lbl_val.setAlignment(Qt.AlignCenter)
        v.addWidget(lbl_val)
        parent_layout.addWidget(card)
        return lbl_val

    def _fill_month_combo(self):
        """填充月份下拉框：默认本月，向前展示近 12 个月。"""
        now = datetime.now()
        items = []
        for i in range(0, 12):
            y = now.year - ((now.month - 1 - i) // 12)
            m = (now.month - 1 - i) % 12 + 1
            items.append((y, m))
        for y, m in items:
            self.cb_month.addItem(f'{y}-{m:02d}', (y, m))
        # 默认选本月（index=0）
        self.cb_month.setCurrentIndex(0)

    def _on_month_changed(self, _idx):
        # 月份切换后自动重新分析（如果已有 zip 路径）
        if self.le_zip.text().strip() and self._last_result:
            self._on_analyze()

    def _on_pick_zip(self):
        """选择 Android 备份 zip 文件。"""
        start_dir = self._dir_getter() or os.path.expanduser('~')
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 Android 备份 zip', start_dir, 'ZIP 备份 (*.zip)'
        )
        if path:
            self.le_zip.setText(path)

    def _on_analyze(self):
        """触发训练达成率分析（后台线程）。"""
        if self._running:
            return
        zip_path = self.le_zip.text().strip()
        if not zip_path or not os.path.exists(zip_path):
            dialog.warn(self, '参数错误', '请先选择有效的 Android 备份 zip 文件')
            return
        target_dir = self._dir_getter()
        if not target_dir or not os.path.isdir(target_dir):
            dialog.warn(self, '参数错误', '档案目录无效')
            return
        ym = self.cb_month.currentData()
        if not ym:
            return
        year, month = ym

        self._running = True
        self.btn_analyze.setEnabled(False)
        self.btn_export_png.setEnabled(False)

        worker = AchievementWorker(zip_path, target_dir, year, month)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)
        run_worker(worker)

    def _on_progress(self, percent, message):
        """进度回调（保留接口，目前不显示进度条）。"""
        pass

    def _on_finished(self, result):
        """分析完成：渲染图表与明细表。"""
        self._running = False
        self.btn_analyze.setEnabled(True)
        self._last_result = result

        if not result:
            return

        if not result.get('has_schedule_data'):
            dialog.info(
                self, '无排课数据',
                '该备份 zip 中未找到 schedules 表（或为空）。\n'
                '请确认 Android 端已通过「数据备份」导出含排课计划的 zip。'
            )

        self._render_overview(result)
        self._render_chart(result)
        self._render_detail_table(result)
        self._render_absent_table(result)
        self.btn_export_png.setEnabled(True)

    def _on_error(self, err_msg):
        self._running = False
        self.btn_analyze.setEnabled(True)
        dialog.warn(self, '分析失败', err_msg)

    def _render_overview(self, result):
        """渲染概览卡片。"""
        self.lbl_planned.setText(str(result.get('planned_count', 0)))
        self.lbl_actual.setText(str(result.get('actual_count', 0)))
        self.lbl_absent.setText(str(result.get('absent_count', 0)))
        rate = result.get('achievement_rate', 0.0) or 0.0
        self.lbl_rate.setText(f'{rate * 100:.1f}%')

    def _render_chart(self, result):
        """渲染柱状图（按学员：计划 vs 实际）。"""
        per_student = result.get('per_student', []) or []
        chart = QChart()
        chart.setTitle(f"训练达成率（{result.get('period', '')}）")
        chart.setTitleBrush(QColor(COLOR_TEXT))
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignBottom)
        chart.legend().setLabelBrush(QColor(COLOR_TEXT))
        chart.setBackgroundBrush(QColor(COLOR_BG))
        chart.setBackgroundPen(QPen(QColor(COLOR_GRID)))

        if not per_student:
            chart.setTitle('暂无学员维度数据')
            self.chart_view.setChart(chart)
            return

        # 限制最多展示前 15 个学员，避免柱子过密
        show_list = per_student[:15]
        set_planned = QBarSet('计划排课')
        set_planned.setColor(QColor(COLOR_PLANNED))
        set_actual = QBarSet('实际签到')
        set_actual.setColor(QColor(COLOR_ACTUAL))
        categories = []
        for item in show_list:
            set_planned.append(item.get('planned', 0))
            set_actual.append(item.get('actual', 0))
            name = item.get('student_name', '') or '?'
            # 截断超长姓名
            categories.append(name[:6] if len(name) > 6 else name)

        series = QBarSeries()
        series.append(set_planned)
        series.append(set_actual)
        chart.addSeries(series)

        # X 轴：学员姓名
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setTitleText('学员')
        axis_x.setTitleBrush(QColor(COLOR_TEXT))
        axis_x.setLabelsBrush(QColor(COLOR_TEXT))
        axis_x.setGridLineVisible(False)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attach(axis_x)

        # Y 轴：次数
        max_val = max(
            (max(s.get('planned', 0), s.get('actual', 0)) for s in show_list),
            default=10
        )
        axis_y = QValueAxis()
        axis_y.setRange(0, max(10, max_val + 2))
        axis_y.setTitleText('课时数')
        axis_y.setTitleBrush(QColor(COLOR_TEXT))
        axis_y.setLabelsBrush(QColor(COLOR_TEXT))
        axis_y.setGridLineColor(QColor(COLOR_GRID))
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attach(axis_y)

        # 添加达成率折线（叠加在柱状图上，右轴）
        if len(show_list) > 0:
            line_series = QLineSeries()
            line_series.setName('达成率')
            pen = QPen(QColor('#a855f7'), 2)
            line_series.setPen(pen)
            for i, item in enumerate(show_list):
                rate = item.get('rate', 0.0) or 0.0
                line_series.append(float(i), rate * 100)
            chart.addSeries(line_series)
            axis_rate = QValueAxis()
            axis_rate.setRange(0, 110)
            axis_rate.setTitleText('达成率 %')
            axis_rate.setTitleBrush(QColor(COLOR_TEXT))
            axis_rate.setLabelsBrush(QColor(COLOR_TEXT))
            axis_rate.setGridLineVisible(False)
            chart.addAxis(axis_rate, Qt.AlignRight)
            line_series.attach(axis_rate)

        chart.setAnimationOptions(QChart.SeriesAnimations)
        self.chart_view.setChart(chart)

    def _render_detail_table(self, result):
        """渲染学员明细表。"""
        per_student = result.get('per_student', []) or []
        self.tbl_detail.setRowCount(len(per_student))
        for row, item in enumerate(per_student):
            name = item.get('student_name', '')
            planned = item.get('planned', 0)
            actual = item.get('actual', 0)
            absent = item.get('absent', 0)
            rate = item.get('rate', 0.0) or 0.0
            self.tbl_detail.setItem(row, 0, QTableWidgetItem(name))
            self.tbl_detail.setItem(row, 1, QTableWidgetItem(str(planned)))
            self.tbl_detail.setItem(row, 2, QTableWidgetItem(str(actual)))
            self.tbl_detail.setItem(row, 3, QTableWidgetItem(str(absent)))
            rate_item = QTableWidgetItem(f'{rate * 100:.1f}%')
            # 低达成率标红，高达成率标绿
            if planned > 0:
                if rate >= 0.9:
                    rate_item.setForeground(QColor(COLOR_ACTUAL))
                elif rate < 0.6:
                    rate_item.setForeground(QColor(COLOR_ABSENT))
            self.tbl_detail.setItem(row, 4, QTableWidgetItem(rate_item))

    def _render_absent_table(self, result):
        """渲染缺勤明细表。"""
        absent_dates = result.get('absent_dates', []) or []
        self.tbl_absent.setRowCount(len(absent_dates))
        for row, item in enumerate(absent_dates):
            self.tbl_absent.setItem(
                row, 0, QTableWidgetItem(item.get('student_name', ''))
            )
            self.tbl_absent.setItem(row, 1, QTableWidgetItem(item.get('date', '')))
            content = item.get('planned_content', '')
            self.tbl_absent.setItem(row, 2, QTableWidgetItem(content))

    def _on_export_png(self):
        """将当前图表导出为 PNG 图片。"""
        if not self._last_result:
            return
        period = self._last_result.get('period', '')
        default_name = f'训练达成率_{period}.png'
        target_dir = self._dir_getter() or os.path.expanduser('~')
        default_path = os.path.join(target_dir, default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, '导出 PNG 图片', default_path, 'PNG 图片 (*.png)'
        )
        if not path:
            return
        try:
            pixmap = self.chart_view.grab()
            pixmap.save(path, 'PNG')
            dialog.info(
                self, '导出成功',
                f'图表已保存：\n{path}\n\n'
                f'教练可直接将此图片发送给家长，展示教学管理能力。'
            )
        except Exception as e:
            dialog.warn(self, '导出失败', str(e))

    def refresh(self):
        """外部刷新接口（与 BackupPanel 等保持一致签名）。"""
        # 当前面板为按需触发分析，refresh 不自动执行
        pass
