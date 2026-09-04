# -*- coding: utf-8 -*-
"""UI 层：首页（应用打开时的默认页面）。

职责：
- 展示欢迎信息与真实数据概览条（学员总数 / 需续费 / 课时关注 / 剩余课时）
- 存在需续费学员时显示预警横幅，点击跳转学员档案页
- 提供快捷入口卡片（Bento Grid），点击后跳转到对应业务页面
- 提供「+ 新增学员」主操作直达

单一职责：仅承担「首页展示与快捷跳转」，
- 通过 quickNav(index) / addStudentRequested() 信号通知主窗口
- 数据只读（profile_manager.list_students），不在首页做任何写操作
"""
import logging
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QSizePolicy
)

from base_components import ColorPalette, Shapes, IconBox, StatCell, compute_overview


# Re-export 保持向后兼容（test_tool.py 仍从此处导入）
__all__ = ['compute_overview', 'StatCell', 'HomePage']


class _QuickCard(QFrame):
    """快捷入口卡片（图标居左 + 标题/描述 + 右侧箭头，悬浮橙描边）。"""

    def __init__(self, title: str, desc: str, icon_type: int, target_index: int,
                 accent: str = ColorPalette.PRIMARY, parent=None):
        super().__init__(parent)
        self._target = target_index
        self.setObjectName('Card')
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(104)
        self._apply_style(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(12)
        icon = IconBox(icon_type, size=40, bg_color=ColorPalette.PRIMARY_LIGHT,
                       fg_color=accent)
        head.addWidget(icon)
        t = QLabel(title)
        t.setStyleSheet(f'''
            color: {ColorPalette.TEXT};
            font-size: 16px;
            font-weight: 700;
            background: transparent;
        ''')
        head.addWidget(t)
        head.addStretch()
        arrow = QLabel('›')
        arrow.setStyleSheet(
            f'color: {ColorPalette.TEXT_MUTED}; font-size: 20px; background: transparent;'
        )
        head.addWidget(arrow)
        lay.addLayout(head)

        d = QLabel(desc)
        d.setStyleSheet(f'''
            color: {ColorPalette.TEXT_SECONDARY};
            font-size: 13px;
            background: transparent;
        ''')
        d.setWordWrap(True)
        lay.addWidget(d)

    def _apply_style(self, hover: bool):
        self.setStyleSheet(f'''
            QFrame#Card {{
                background-color: {ColorPalette.PRIMARY_LIGHT if hover else ColorPalette.CARD};
                border: 1px solid {ColorPalette.PRIMARY if hover else ColorPalette.BORDER};
                border-radius: {Shapes.CARD_RADIUS}px;
            }}
        ''')

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """点击卡片发射跳转信号。"""
        if event.button() == Qt.LeftButton:
            parent = self.parent()
            while parent is not None:
                if isinstance(parent, HomePage):
                    parent.quickNav.emit(self._target)
                    return
                parent = parent.parent()
        super().mousePressEvent(event)


class HomePage(QWidget):
    """首页：欢迎区 + 真数据概览条 + 快捷入口卡片网格（2x2 Bento Grid）。

    信号:
        quickNav(int): 快捷卡片/预警横幅被点击时发射，参数为目标页面索引
        addStudentRequested(): 「+ 新增学员」被点击时发射
    """

    quickNav = Signal(int)
    addStudentRequested = Signal()

    def __init__(self, parent=None, coach_name: str = '教练', archive_dir_getter=None):
        """
        参数:
            coach_name: 当前登录教练名（用于欢迎语）
            archive_dir_getter: 返回当前档案目录的可调用对象（概览数据来源）
        """
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        self.setStyleSheet(f'background-color: {ColorPalette.BG};')

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(16)

        # === 标题行：欢迎语 + 主操作 ===
        head = QHBoxLayout()
        head.setSpacing(12)
        head_col = QVBoxLayout()
        head_col.setSpacing(2)
        welcome = QLabel(f'你好，{coach_name}')
        welcome.setStyleSheet(f'''
            color: {ColorPalette.TEXT};
            font-size: 26px;
            font-weight: 800;
            background: transparent;
        ''')
        head_col.addWidget(welcome)
        self.subtitle = QLabel(
            datetime.now().strftime('欢迎回来，今天是%m月%d日 %a')
        )
        self.subtitle.setStyleSheet(f'''
            color: {ColorPalette.TEXT_SECONDARY};
            font-size: 13px;
            background: transparent;
        ''')
        head_col.addWidget(self.subtitle)
        head.addLayout(head_col, 1)

        self.btn_add_student = QPushButton('+ 新增学员')
        self.btn_add_student.setObjectName('primary')
        self.btn_add_student.setCursor(Qt.PointingHandCursor)
        self.btn_add_student.clicked.connect(self.addStudentRequested.emit)
        head.addWidget(self.btn_add_student)
        root.addLayout(head)

        # === 真数据概览条（参考 SaaS 统计条样式：白底一行四格竖线分隔） ===
        strip = QFrame()
        strip.setObjectName('statStrip')
        strip.setStyleSheet(f'''
            QFrame#statStrip {{
                background: {ColorPalette.CARD};
                border: 1px solid {ColorPalette.BORDER};
                border-radius: {Shapes.CARD_RADIUS}px;
            }}
        ''')
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(20, 14, 20, 14)
        strip_lay.setSpacing(0)
        self.cell_total = StatCell('学员总数')
        self.cell_red = StatCell('需续费（≤3课时）', accent='#F87171')
        self.cell_yellow = StatCell('课时关注（≤6课时）', accent='#F59E0B')
        self.cell_remaining = StatCell('剩余课时合计')
        cells = [self.cell_total, self.cell_red, self.cell_yellow, self.cell_remaining]
        for i, cell in enumerate(cells):
            if i:
                line = QLabel()
                line.setFixedSize(1, 36)
                line.setStyleSheet(
                    f'background: {ColorPalette.DIVIDER}; border: none;'
                )
                strip_lay.addWidget(line)
            strip_lay.addWidget(cell, 1)
        root.addWidget(strip)

        # === 续费预警横幅（仅有需续费学员时显示，点击跳学员档案） ===
        self.btn_alert = QPushButton()
        self.btn_alert.setCursor(Qt.PointingHandCursor)
        self.btn_alert.setObjectName('alertBanner')
        self.btn_alert.setStyleSheet(f'''
            QPushButton#alertBanner {{
                background: #FFF5F5;
                border: 1px solid #FFD5D5;
                border-radius: 12px;
                padding: 10px 16px;
                color: #E53E3E;
                font-size: 13px;
                font-weight: 600;
                text-align: left;
            }}
            QPushButton#alertBanner:hover {{ background: #FFE9E9; }}
        ''')
        self.btn_alert.clicked.connect(lambda: self.quickNav.emit(1))
        self.btn_alert.hide()
        root.addWidget(self.btn_alert)

        root.addSpacing(4)

        # === 快捷入口标题 ===
        section = QLabel('快捷入口')
        section.setStyleSheet(f'''
            color: {ColorPalette.TEXT};
            font-size: 15px;
            font-weight: 600;
            background: transparent;
        ''')
        root.addWidget(section)

        # === 快捷卡片网格（2x2 Bento Grid） ===
        grid_container = QWidget()
        grid_container.setStyleSheet('background: transparent;')
        grid = QVBoxLayout(grid_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(_QuickCard('学员档案', '基础信息、BMI 计算、续费预警管理',
                                  IconBox.USER, 1))
        row1.addWidget(_QuickCard('体测档案与课时', '测评录入、课时管理与签到签退',
                                  IconBox.CHART_BAR, 2))
        grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(_QuickCard('训练任务编排', '单次训练单 / 周计划表，导出 Excel/Word',
                                  IconBox.DUMBBELL, 3))
        row2.addWidget(_QuickCard('数据中心', '备份恢复、成长报告、续费预警汇总',
                                  IconBox.ARCHIVE, 4))
        grid.addLayout(row2)

        root.addWidget(grid_container)
        root.addStretch()

    def showEvent(self, event):
        """每次切到首页都刷新概览（轻量 xlsx 读取，失败静默降级为 —）。"""
        self.refresh_overview()
        super().showEvent(event)

    def refresh_overview(self):
        """读取学员列表并刷新概览条与预警横幅。"""
        overview = {'total': 0, 'red': 0, 'yellow': 0, 'remaining': 0}
        red_names = []
        try:
            # 延迟导入：模块加载路径由 app.py 注入，纯函数测试时无需 Qt 外依赖
            import profile_manager as pm
            students = pm.list_students(self._get_dir())
            overview = compute_overview(students)
            red_names = [s['name'] for s in students if s.get('warn_level') == 'red']
        except Exception:
            logging.exception('首页概览数据加载失败')
        self.cell_total.set_value(overview['total'])
        self.cell_red.set_value(overview['red'])
        self.cell_yellow.set_value(overview['yellow'])
        self.cell_remaining.set_value(overview['remaining'])
        if overview['red'] > 0:
            names = '、'.join(red_names[:5])
            if len(red_names) > 5:
                names += f' 等 {len(red_names)} 人'
            self.btn_alert.setText(
                f'●  {overview["red"]} 名学员课时即将耗尽，需提醒续费：{names}　›'
            )
            self.btn_alert.show()
        else:
            self.btn_alert.hide()
