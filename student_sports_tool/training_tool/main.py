# -*- coding: utf-8 -*-
"""UI 层：训练任务编排工具主窗口（灰白简约 · 蓝紫强调，对齐图2 设计语言）。

职责：
- 顶部导航栏（独立运行时显示：Logo + 标题 + 搜索 + 同步 + 教练；嵌入 app.py 时由外层提供）
- 模块标题头：子页切换（单次训练单 / 周计划表 / 阶段总结）+ 新增
- 主区域：三列壳（左列任务列表[由 SingleTab 提供] / 中列页面栈 / 右列操作面板）
- 底部状态栏：当前编辑状态

设计语言（styles.py 令牌，仅作用域 #training_root）：
- 背景 #F2F4F8 / 卡片 #FFFFFF / 圆角 12px / 强调色 #5B6BF7
- 不污染全局珊瑚橙主题，其它业务模块视觉零影响

业务逻辑（导出 / 打开文件夹 / 模板库 / 截图发到手机）接线保持不变，
仅把按钮从原底部导出栏迁移到右列操作面板。
"""
import modern_dialog as dialog
import os
import sys
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QFileDialog,
    QStackedWidget, QSizePolicy
)
from task_model import make_default_week
from exporter import (
    export_single_excel, export_single_word,
    export_weekly_excel, export_weekly_word
)
from stage_summary_screen import StageSummaryScreen

# 拆分后的子页面 Widget
from ui_template_screen import SingleTab
from ui_plan_screen import WeeklyTab

# 新设计语言组件
from styles import TRAINING_QSS, Palette, Spacing
from layouts import (
    TopNavBar, ModuleHeader, RightActionPanel, BottomStatusBar,
)

# v25 新增：局域网训练计划截图发送器（截图 + HTTP + UDP 广播）
from lan_plan_sender import get_sender as get_lan_plan_sender


class MainWindow(QMainWindow):
    def __init__(self, embedded=True):
        """参数:
            embedded: True=嵌入 app.py（不渲染顶部导航栏，由外层提供）；
                      False=独立运行（渲染完整顶部导航栏）。
        """
        super().__init__()
        self.setWindowTitle('训练任务编排工具')
        self.resize(1280, 900)
        self._dir_getter = lambda: ''
        self._embedded = embedded
        self._init_ui()
        self._init_lan_plan_sender()

    def set_archive_dir_getter(self, getter):
        """公开 setter：注入档案目录获取器，替代外部直接赋值 _dir_getter。"""
        self._dir_getter = getter

    def _init_ui(self):
        central = QWidget()
        central.setObjectName('training_root')
        # 作用域 QSS：覆盖全局珊瑚橙，仅本模块子树生效
        central.setStyleSheet(TRAINING_QSS)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ===== 顶部导航栏（仅独立运行时渲染） =====
        if not self._embedded:
            self.top_nav = TopNavBar(coach_name='教练')
            root.addWidget(self.top_nav)

        # ===== 内容区：页面边距 24px =====
        # v24：透明背景交给 TRAINING_QSS 的 `#training_root QWidget` 全局规则；
        # 裸声明 setStyleSheet('background: transparent;') 会下压覆盖后代按钮背景（primary 曾隐形）
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(Spacing.PAGE, Spacing.PAGE, Spacing.PAGE, Spacing.PAGE)
        content_lay.setSpacing(Spacing.CARD)
        root.addWidget(content, 1)

        # 模块标题头：子页切换 + 新增
        self.header = ModuleHeader(title='训练任务编排')
        self.header.tab_changed.connect(self._on_nav_changed)
        self.header.plus_clicked.connect(self._on_plus_clicked)
        # 兼容外部对 btn_new 的引用
        self.btn_new = self.header.btn_new
        content_lay.addWidget(self.header)

        # ===== 三列壳：中列页面栈 + 右列操作面板 =====
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(Spacing.CARD)

        # 页面栈（中列）
        self.stack = QStackedWidget()
        self.stack.setStyleSheet('QStackedWidget { background: transparent; border: none; }')
        _dir_getter = lambda: getattr(self, '_dir_getter', lambda: '')()
        self.tab_single = SingleTab(archive_dir_getter=_dir_getter)
        self.tab_week = WeeklyTab(archive_dir_getter=_dir_getter)
        self.tab_summary = StageSummaryScreen(archive_dir_getter=_dir_getter)
        self.stack.addWidget(self.tab_single)
        self.stack.addWidget(self.tab_week)
        self.stack.addWidget(self.tab_summary)
        self.stack.currentChanged.connect(self._on_subtab_changed)
        body_lay.addWidget(self.stack, 1)

        # 右列操作面板
        self.right_panel = RightActionPanel()
        # 接线到既有处理函数
        self.right_panel.btn_export.clicked.connect(self._export_current)
        self.right_panel.btn_open.clicked.connect(self._open_dir)
        self.right_panel.btn_template.clicked.connect(self.on_open_template_library)
        self.right_panel.btn_send_phone.clicked.connect(self._on_send_plan_to_phone)
        self.right_panel.btn_help.clicked.connect(self._on_help)
        # 兼容旧属性引用（_on_send_plan_to_phone / _init_lan_plan_sender 等仍用 self.btn_send_to_phone）
        self.btn_send_to_phone = self.right_panel.btn_send_phone
        self.btn_template = self.right_panel.btn_template
        self.btn_open = self.right_panel.btn_open
        body_lay.addWidget(self.right_panel)

        content_lay.addWidget(body, 1)

        # ===== 底部状态栏 =====
        self.status_bar = BottomStatusBar()
        self.status_bar.set_status('就绪 · 单次训练单')
        self.status_bar.set_right('上门体育教学管理平台')
        root.addWidget(self.status_bar)

        self._last_dir = os.path.join(os.path.expanduser('~'), 'Desktop')

    # ==================== 子页切换 ====================

    def _on_nav_changed(self, idx):
        """模块标题头子页切换。"""
        self.stack.setCurrentIndex(idx)
        self.header.set_active_tab(idx)
        names = ['单次训练单', '周计划表', '阶段总结']
        if 0 <= idx < len(names):
            self.status_bar.set_status(f'就绪 · {names[idx]}')

    def _on_plus_clicked(self):
        """新增按钮：根据当前页执行新建操作。"""
        idx = self.stack.currentIndex()
        if idx == 0:
            self.tab_single.on_add_block()
        elif idx == 1:
            self.tab_week._days = make_default_week()
            self.tab_week._on_start_date_changed(self.tab_week.dte_start.date())
            self.tab_week._refresh_table()
            self.tab_week._update_right_panel()

    def _on_subtab_changed(self, idx):
        """子页面切换时按需刷新学员列表 + 同步标题头选中态。"""
        try:
            self.header.set_active_tab(idx)
            names = ['单次训练单', '周计划表', '阶段总结']
            if 0 <= idx < len(names):
                self.status_bar.set_status(f'就绪 · {names[idx]}')
            # 阶段总结子页自带导出卡，外层操作面板对其冗余；隐藏后把宽度还给内容区
            self.right_panel.setVisible(idx != 2)
            if idx == 0 and hasattr(self, 'tab_single'):
                self.tab_single.refresh_students()
            elif idx == 1 and hasattr(self, 'tab_week'):
                self.tab_week.refresh_students()
            elif idx == 2 and hasattr(self, 'tab_summary'):
                self.tab_summary.refresh()
        except Exception:
            logging.exception('切换训练页刷新失败')

    # ==================== 导出（接线保持不变） ====================

    def _export_current(self):
        """右列导出按钮：按导出格式下拉选择执行 Excel/Word 导出。"""
        fmt = 'excel' if self.right_panel.cb_format.currentIndex() == 0 else 'word'
        self._export(fmt)

    def _export(self, fmt):
        idx = self.stack.currentIndex()
        # 阶段总结子页有各自的导出按钮
        if idx not in (0, 1):
            dialog.info(
                self, '提示',
                '当前子页有专属的导出按钮，请使用页面底部的导出按钮。'
            )
            return
        if idx == 0:
            plan = self.tab_single.collect_plan()
            if not plan.student_name:
                dialog.warn(self, '提示', '请输入学员姓名')
                return
            if not any(b.tasks for b in plan.blocks):
                dialog.warn(self, '提示', '请至少添加一个训练动作')
                return
            suffix = f"{plan.student_name}_{plan.train_date}_训练单"
        else:
            plan = self.tab_week.collect_plan()
            if not plan.student_name:
                dialog.warn(self, '提示', '请输入学员姓名')
                return
            suffix = f"{plan.student_name}_{plan.week_start}_周计划"

        ext = 'xlsx' if fmt == 'excel' else 'docx'
        default_name = f"{suffix}.{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self, '保存文件', os.path.join(self._last_dir, default_name),
            f'{"Excel" if fmt == "excel" else "Word"}文件 (*.{ext})'
        )
        if not path:
            return
        if not path.endswith(f'.{ext}'):
            path += f'.{ext}'
        self._last_dir = os.path.dirname(path)
        try:
            if idx == 0:
                if fmt == 'excel':
                    export_single_excel(plan, path)
                else:
                    export_single_word(plan, path)
            else:
                if fmt == 'excel':
                    export_weekly_excel(plan, path)
                else:
                    export_weekly_word(plan, path)
            dialog.info(self, '导出成功', f'已保存到：\n{path}')
            self.status_bar.set_status(f'导出成功 · {os.path.basename(path)}')
        except Exception as e:
            dialog.error(self, '导出失败', f'{e}\n\n请确认文件未被其他程序占用。')

    def _open_dir(self):
        if not os.path.exists(self._last_dir):
            os.makedirs(self._last_dir, exist_ok=True)
        os.startfile(self._last_dir)

    def on_open_template_library(self):
        """打开训练计划模板库窗口。"""
        from template_library_window import TemplateLibraryWindow
        idx = self.stack.currentIndex()

        def on_apply(exercises):
            """选用模板回调：将动作载入当前训练页。"""
            from task_model import Task
            if idx == 0:
                tab = self.tab_single
                tab._sync_table_to_data()
                block = tab._blocks[tab._cur_block_idx]
                for ex in exercises:
                    block.tasks.append(Task(
                        name=ex['name'], sets=ex['sets'],
                        reps=ex['reps'], note=ex.get('note', '')
                    ))
                tab._refresh_table()
                tab._update_right_panel()

        dir_getter = getattr(self, '_dir_getter', None)
        self._template_win = TemplateLibraryWindow(
            on_apply_callback=on_apply, dir_getter=dir_getter)
        self._template_win.show()

    # ==================== 截图发送到手机（接线保持不变） ====================

    def _init_lan_plan_sender(self):
        """初始化局域网截图发送器，连接 UI 反馈信号。"""
        try:
            self._lan_sender = get_lan_plan_sender()
            self._lan_sender.success.connect(self._on_lan_plan_success)
            self._lan_sender.failed.connect(self._on_lan_plan_failed)
        except Exception as e:
            self._lan_sender = None
            if hasattr(self, 'btn_send_to_phone'):
                self.btn_send_to_phone.setEnabled(False)
                self.btn_send_to_phone.setToolTip(f'截图发送功能初始化失败：{e}')

    def _on_send_plan_to_phone(self):
        """点击「截图发到手机」按钮：截图当前窗口并发送 UDP 广播。"""
        if not getattr(self, '_lan_sender', None):
            dialog.warn(self, '截图发送', '截图发送功能未初始化，请重启应用')
            return

        idx = self.stack.currentIndex()
        student_name = ''
        if idx == 0:
            try:
                plan = self.tab_single.collect_plan()
                student_name = plan.student_name or ''
            except Exception:
                student_name = ''
        elif idx == 1:
            try:
                plan = self.tab_week.collect_plan()
                student_name = plan.student_name or ''
            except Exception:
                student_name = ''
        else:
            dialog.info(
                self, '截图发送到手机',
                '请在「单次训练单」或「周计划表」页面使用此功能，\n'
                '以便从训练计划中提取学员姓名。'
            )
            return

        if not student_name.strip():
            dialog.warn(
                self, '截图发送到手机',
                '当前训练计划未填写学员姓名，\n'
                '请先在学员输入框中选择或输入学员姓名，\n'
                '以便手机端自动关联到对应学员。'
            )
            return

        self.btn_send_to_phone.setEnabled(False)
        self.btn_send_to_phone.setText('发送中…')
        self.status_bar.set_status('截图发送中…')

        self._lan_sender.capture_and_broadcast(
            window=self,
            student_name=student_name
        )

    def _on_lan_plan_success(self, message: str):
        self.btn_send_to_phone.setEnabled(True)
        self.btn_send_to_phone.setText('截图发到手机')
        self.status_bar.set_status('截图已发送到手机')
        dialog.info(
            self, '截图已发送到手机',
            message + '\n\n'
            '请确保手机与电脑处于同一局域网，\n'
            '手机端会自动弹出通知，点击通知或在设置页\n'
            '点击「同步电脑端截图」按钮即可下载。'
        )

    def _on_lan_plan_failed(self, message: str):
        self.btn_send_to_phone.setEnabled(True)
        self.btn_send_to_phone.setText('截图发到手机')
        self.status_bar.set_status('截图发送失败')
        dialog.warn(self, '截图发送失败', message)

    def _on_help(self):
        """帮助入口。"""
        dialog.info(
            self, '关于',
            '上门体育教学管理平台 · 训练任务编排\n'
            '灰白简约主题 v2.0\n'
            '卡片式布局 · 蓝紫强调'
        )

    def closeEvent(self, event):
        """窗口关闭时释放 HTTP 服务资源。"""
        try:
            if getattr(self, '_lan_sender', None):
                self._lan_sender.shutdown()
        except Exception:
            logging.exception('关闭截图发送服务失败')
        super().closeEvent(event)

    def refresh_current_tab_students(self):
        """刷新当前子页的学员下拉列表（供 app.py 切换顶层 Tab 时调用）。"""
        try:
            idx = self.stack.currentIndex()
            if idx == 0 and hasattr(self, 'tab_single'):
                self.tab_single.refresh_students()
            elif idx == 1 and hasattr(self, 'tab_week'):
                self.tab_week.refresh_students()
            elif idx == 2 and hasattr(self, 'tab_summary'):
                self.tab_summary.refresh()
        except Exception:
            logging.exception('同步后刷新训练页失败')


def main():
    app = QApplication(sys.argv)
    # 独立运行：加载本模块灰白蓝紫主题（作用域 #training_root）
    try:
        from theme import LIGHT_QSS
        app.setStyleSheet(LIGHT_QSS)  # 全局兜底（对话框等仍用珊瑚橙）
        _f = QFont('Microsoft YaHei UI')
        _f.setPointSize(10)
        app.setFont(_f)
    except Exception:
        pass
    w = MainWindow(embedded=False)  # 独立运行：渲染完整顶部导航栏
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
