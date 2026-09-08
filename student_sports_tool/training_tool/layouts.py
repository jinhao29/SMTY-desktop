# -*- coding: utf-8 -*-
"""训练任务编排模块布局组件（灰白简约 · 蓝紫强调）。

组件：
- TopNavBar：顶部导航栏（Logo + 标题 + 搜索 + 同步状态 + 教练下拉）
             独立运行 main() 时显示；嵌入 app.py 时由外层提供，本组件不重复渲染
- ModuleHeader：模块标题头（页面标题 + 子页切换 + 新增按钮）
- BottomStatusBar：底部状态栏（编辑状态）
- SyncDot：同步状态圆点指示器

设计原则（懒人）：所有按钮对外暴露为公开属性，由 main.py 接线到既有处理函数，
本模块不包含任何业务逻辑。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QFrame, QSizePolicy, QButtonGroup
)
from styles import Palette, Radius, Spacing, Type
from cards import Card


# ==================== 同步状态圆点 ====================

class SyncDot(QWidget):
    """绿点 + 文字的同步状态指示器。

    状态机：idle(灰·待命) / ok(绿·完成) / syncing(蓝紫·同步中) / error(红·失败)
    """
    _STYLES = {
        'idle':    (Palette.MUTED, '同步待命'),
        'ok':      (Palette.GREEN, '同步完成'),
        'syncing': (Palette.ACCENT, '正在同步...'),
        'error':   (Palette.RED, '同步失败'),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._dot = QLabel('●')
        self._dot.setFont(Type.caption())
        self._lbl = QLabel('同步待命')
        self._lbl.setFont(Type.caption())
        lay.addWidget(self._dot)
        lay.addWidget(self._lbl)
        self.set_state('idle')

    def set_state(self, state: str):
        color, text = self._STYLES.get(state, self._STYLES['idle'])
        self._dot.setStyleSheet(f'color: {color}; background: transparent;')
        self._lbl.setStyleSheet(f'color: {color}; background: transparent;')
        self._lbl.setText(text)


# ==================== 顶部导航栏 ====================

class TopNavBar(QFrame):
    """顶部导航栏：白底 + 底部 1px 浅灰分割线。

    左侧：Logo 圆点 + 产品名「上门体育教学管理平台」
    右侧：搜索框（圆角 20px 灰底）+ 同步指示器 + 教练下拉
    """
    def __init__(self, coach_name='教练', parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(
            f'QFrame {{ background: {Palette.HEADER_BG}; '
            f'border-bottom: 1px solid {Palette.DIVIDER}; }}'
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(Spacing.PAGE, 8, Spacing.PAGE, 8)
        lay.setSpacing(16)

        # 左侧 Logo + 标题
        logo = QLabel('●')
        logo.setStyleSheet(f'color: {Palette.ACCENT}; font-size: 20px; background: transparent;')
        title = QLabel('上门体育教学管理平台')
        title.setFont(Type.card_title())
        title.setStyleSheet(f'color: {Palette.TEXT}; background: transparent;')
        lay.addWidget(logo)
        lay.addWidget(title)
        lay.addStretch()

        # 搜索框（圆角 20px 灰底）
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索学员 / 课程...')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(260)
        self.search.setMaximumWidth(360)
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search.setStyleSheet(f'''
            QLineEdit {{
                background: {Palette.BG}; border: 1px solid {Palette.DIVIDER};
                border-radius: {Radius.PILL}px; padding: 8px 16px;
                color: {Palette.TEXT}; min-height: 20px;
            }}
            QLineEdit:focus {{ border: 2px solid {Palette.ACCENT}; padding: 7px 15px; }}
        ''')
        lay.addWidget(self.search)

        # 同步状态指示器
        self.sync = SyncDot()
        lay.addWidget(self.sync)

        # 教练下拉
        self.cb_coach = QComboBox()
        self.cb_coach.addItem(f'●  {coach_name}')
        self.cb_coach.addItems(['设置', '退出登录'])
        self.cb_coach.setFixedHeight(34)
        self.cb_coach.setStyleSheet(f'''
            QComboBox {{
                background: transparent; border: 1px solid {Palette.DIVIDER};
                border-radius: {Radius.BUTTON}px; padding: 4px 12px;
                color: {Palette.TEXT_SUB}; min-height: 20px;
            }}
            QComboBox:hover {{ border: 1px solid {Palette.ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox::down-arrow {{
                image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
                border-top: 5px solid {Palette.TEXT_SUB}; margin-right: 8px;
            }}
        ''')
        lay.addWidget(self.cb_coach)


# ==================== 模块标题头 ====================

class ModuleHeader(QFrame):
    """模块标题头：页面标题 + 子页切换（单次训练单 / 周计划表 / 阶段总结）+ 新增按钮。

    信号：
        tab_changed(index)：子页切换
        plus_clicked()：新增按钮
    """
    tab_changed = Signal(int)
    plus_clicked = Signal()

    def __init__(self, title='训练任务编排', parent=None):
        super().__init__(parent)
        self.setStyleSheet('QFrame { background: transparent; border: none; }')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(Spacing.MD)

        page_title = QLabel(title)
        page_title.setObjectName('pageTitle')
        page_title.setFont(Type.page_title())
        page_title.setStyleSheet(f'color: {Palette.TEXT}; background: transparent;')
        lay.addWidget(page_title)

        # 子页切换按钮组
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = []
        for idx, name in enumerate(['单次训练单', '周计划表', '阶段总结']):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._tab_qss(False))
            btn.clicked.connect(lambda _=False, i=idx: self._on_tab(i))
            self._group.addButton(btn, idx)
            self._buttons.append(btn)
            lay.addWidget(btn)
        self._buttons[0].setChecked(True)
        self._buttons[0].setStyleSheet(self._tab_qss(True))

        lay.addStretch()

        self.btn_new = QPushButton('＋ 新增')
        self.btn_new.setObjectName('primary')
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.setMinimumWidth(96)
        self.btn_new.clicked.connect(self.plus_clicked.emit)
        lay.addWidget(self.btn_new)

    def _tab_qss(self, active: bool) -> str:
        if active:
            return (
                f'QPushButton {{ background: {Palette.ACCENT_LIGHT}; color: {Palette.ACCENT}; '
                f'border: none; border-radius: {Radius.BUTTON}px; '
                f'padding: 8px 18px; font-size: 14px; font-weight: 600; }}'
            )
        return (
            f'QPushButton {{ background: transparent; color: {Palette.TEXT_SUB}; '
            f'border: none; border-radius: {Radius.BUTTON}px; '
            f'padding: 8px 18px; font-size: 14px; font-weight: 500; }}'
            f'QPushButton:hover {{ color: {Palette.ACCENT}; background: {Palette.ACCENT_LIGHT}; }}'
        )

    def _on_tab(self, idx):
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(self._tab_qss(i == idx))
        self.tab_changed.emit(idx)

    def set_active_tab(self, idx):
        for i, btn in enumerate(self._buttons):
            btn.blockSignals(True)
            btn.setChecked(i == idx)
            btn.setStyleSheet(self._tab_qss(i == idx))
            btn.blockSignals(False)


# ==================== 底部状态栏 ====================

class BottomStatusBar(QFrame):
    """底部状态栏：浅灰背景，显示当前编辑状态。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            f'QFrame {{ background: {Palette.STATUS_BG}; '
            f'border-top: 1px solid {Palette.DIVIDER}; }}'
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(Spacing.PAGE, 0, Spacing.PAGE, 0)
        lay.setSpacing(12)
        self._lbl = QLabel('就绪')
        self._lbl.setFont(Type.caption())
        self._lbl.setStyleSheet(f'color: {Palette.TEXT_SUB}; background: transparent;')
        lay.addWidget(self._lbl)
        lay.addStretch()
        self._right = QLabel('')
        self._right.setFont(Type.caption())
        self._right.setStyleSheet(f'color: {Palette.MUTED}; background: transparent;')
        lay.addWidget(self._right)

    def set_status(self, text: str):
        self._lbl.setText(text)

    def set_right(self, text: str):
        self._right.setText(text)


# ==================== 三列壳 ====================

def build_three_column(left: QWidget, center: QWidget, right: QWidget,
                       left_width=240, right_width=240) -> QHBoxLayout:
    """构建三列布局：左列任务列表 / 中列当日内容 / 右列操作面板。

    中列自适应拉伸，左右列定宽。列间距 16px，整体无外边距（外层控制页面边距）。
    """
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(Spacing.CARD)
    left.setMinimumWidth(200)
    left.setMaximumWidth(left_width)
    left.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    right.setMinimumWidth(200)
    right.setMaximumWidth(right_width)
    right.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    center.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    lay.addWidget(left)
    lay.addWidget(center, 1)
    lay.addWidget(right)
    return lay
