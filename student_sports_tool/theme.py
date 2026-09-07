# -*- coding: utf-8 -*-
"""全局浅色珊瑚橙主题 QSS（Light Coral Orange Theme）。

职责：
- 提供统一的暖白背景、纯白卡片、珊瑚橙主色、浅灰边框的 Qt 样式表
- 供 main.py、training_tool/main.py、app.py 统一引用，避免样式漂移
- 主色 #FF6B47（活力珊瑚橙）与 Android 端完全一致，实现双端视觉统一

色彩令牌（与 Android 端 UI 规范严格对齐）：
- 背景：#FFFFFF（纯白，v25.1 李哥反馈灰底显脏）/ 侧边栏：#FFFFFF + 1px 右描边
- 卡片：#FFFFFF（纯白） / 边框：#E5E5E5（浅灰）
- 主色：#FF6B47（活力珊瑚橙，选中态背景，文字反白为 #FFFFFF）
- 文字：#1A1A1A（主，≥12:1） / #6B6B6B（次，≥4.6:1） / #9B9B9B（弱）
"""

# 浅色珊瑚橙主题（主推，与 Android 端视觉统一）

# ==== 勾选框对勾图标（QSS 无法绘制勾，运行时生成 SVG 到用户数据目录引用） ====
import os as _os


def _ensure_checkbox_icons():
    """生成勾选框对勾 / 半选横线 SVG，返回 (check_svg_path, minus_svg_path)。

    写入 ~/.shangmentiyu/ui_assets/（源码运行与 PyInstaller 打包均可用）。
    生成失败返回 ('', '')，QSS 回退为无勾实底样式（不阻塞导入）。
    """
    try:
        user_dir = _os.path.join(_os.path.expanduser('~'), '.shangmentiyu', 'ui_assets')
        _os.makedirs(user_dir, exist_ok=True)
        check_path = _os.path.join(user_dir, 'checkbox_check.svg')
        minus_path = _os.path.join(user_dir, 'checkbox_minus.svg')
        if not _os.path.exists(check_path):
            with open(check_path, 'w', encoding='utf-8') as f:
                f.write(
                    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>"
                    "<path d='M3.2 8.6 6.6 12 12.8 4.4' fill='none' stroke='white' "
                    "stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'/></svg>")
        if not _os.path.exists(minus_path):
            with open(minus_path, 'w', encoding='utf-8') as f:
                f.write(
                    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>"
                    "<path d='M3.5 8h9' fill='none' stroke='white' "
                    "stroke-width='2.4' stroke-linecap='round'/></svg>")
        return check_path.replace('\\', '/'), minus_path.replace('\\', '/')
    except OSError:
        return '', ''


_CHECK_SVG, _MINUS_SVG = _ensure_checkbox_icons()

# 勾选框三态 image 规则（SVG 生成失败时回退空串，QSS 里空 url 行会破坏语法，需条件拼接）


def _checkbox_image_rules() -> str:
    if _CHECK_SVG and _MINUS_SVG:
        return (
            f'QCheckBox::indicator:checked {{ image: url({_CHECK_SVG}); }}\n'
            f'QCheckBox::indicator:indeterminate {{ image: url({_MINUS_SVG}); }}\n'
            'QCheckBox::indicator:checked:disabled '
            f'{{ image: url({_CHECK_SVG}); }}\n'
        )
    return ''


LIGHT_QSS = """
/* ========== 全局基础 ========== */
QMainWindow, QWidget {
    background: #FFFFFF;
    color: #1A1A1A;
    font-family: 'Inter', 'Segoe UI', 'Microsoft YaHei UI', '微软雅黑';
    font-size: 14px;
}
QLabel {
    color: #1A1A1A;
    background: transparent;
}
QLabel#hint {
    color: #6B6B6B;
}
QLabel#title {
    color: #FF6B47;
    font-weight: 700;
}
QLabel#section {
    color: #1A1A1A;
    font-weight: 600;
}

/* ========== 卡片容器 ========== */
QGroupBox,
QGroupBox#card,
QFrame#card,
QFrame.Card {
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 16px;
    margin-top: 0;
    padding: 20px;
}
QGroupBox::title {
    color: #FF6B47;
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 16px; top: 12px;
    padding: 0 6px;
    background: transparent;
    font-weight: 600;
    font-size: 15px;
}
QGroupBox#card::title {
    color: #FF6B47;
    subcontrol-origin: margin;
    left: 12px; top: 4px;
    padding: 0 8px;
    font-weight: 600;
    font-size: 14px;
}

/* ========== 输入控件 ========== */
QLineEdit, QComboBox, QTextEdit, QDateEdit, QSpinBox {
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 12px;
    padding: 9px 14px;
    color: #1A1A1A;
    selection-background-color: #FF6B47;
    selection-color: #FFFFFF;
    min-height: 22px;
}
QLineEdit:hover, QComboBox:hover, QTextEdit:hover, QDateEdit:hover, QSpinBox:hover {
    border: 1px solid #D5D5D5;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QDateEdit:focus, QSpinBox:focus {
    border: 2px solid #FF6B47;
    padding: 8px 13px;
}
QLineEdit::placeholder, QTextEdit::placeholder {
    color: #9B9B9B;
}
QComboBox::drop-down {
    border: none;
    width: 32px;
}
/* down-arrow 不再自定义：border-triangle 技巧在部分 Qt 版本渲染为实心小方块，
   原生箭头完整清晰（2026-09-06 修复下拉框图案残缺） */
QComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 12px;
    color: #1A1A1A;
    padding: 8px;
    outline: none;
}
QComboBox QAbstractItemView::item {
    min-height: 36px;
    padding: 6px 14px;
    margin: 2px 4px;
    border-radius: 9px;
    color: #1A1A1A;
}
QComboBox QAbstractItemView::item:hover {
    background: rgba(255, 107, 71, 0.08);
}
QComboBox QAbstractItemView::item:selected {
    background: rgba(255, 107, 71, 0.12);
    color: #FF6B47;
}

/* ---------- 微调框（QSpinBox/QDateEdit）：隐藏原生上下按钮，纯键盘输入（iOS 风） ---------- */
QSpinBox::up-button, QDateEdit::up-button, QTimeEdit::up-button, QDateTimeEdit::up-button,
QSpinBox::down-button, QDateEdit::down-button, QTimeEdit::down-button, QDateTimeEdit::down-button {
    width: 0;
    border: none;
    background: transparent;
}
QSpinBox::up-arrow, QDateEdit::up-arrow, QTimeEdit::up-arrow, QDateTimeEdit::up-arrow,
QSpinBox::down-arrow, QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {
    image: none;
    width: 0; height: 0;
    border: none;
}
/* QDateEdit 日历弹出按钮：与 QComboBox 下拉箭头同款 */
QDateEdit::drop-down {
    border: none;
    width: 26px;
}
/* QDateEdit::down-arrow 同上：交还原生箭头 */


/* ---------- 日历弹窗（QDateEdit calendarPopup）全面主题化 ---------- */
QCalendarWidget QWidget {
    alternate-background-color: #F8F8F8;
}
QCalendarWidget QAbstractItemView {
    background: #FFFFFF;
    color: #1A1A1A;
    selection-background-color: #FF6B47;
    selection-color: #FFFFFF;
    outline: none;
    border: none;
}
QCalendarWidget QToolButton {
    background: transparent;
    color: #1A1A1A;
    border-radius: 8px;
    padding: 4px 8px;
    font-weight: 600;
}
QCalendarWidget QToolButton:hover {
    background: rgba(255, 107, 71, 0.10);
    color: #FF6B47;
}
QCalendarWidget QToolButton::menu-indicator { image: none; }
#qt_calendar_navigationbar {
    background: #FFFFFF;
    border-bottom: 1px solid #E5E5E5;
    padding: 4px;
}
#qt_calendar_yearedit, #qt_calendar_monthedit {
    background: #F5F7FA;
    border: 1px solid #E5E5E5;
    border-radius: 8px;
    padding: 2px 8px;
    color: #1A1A1A;
    font-weight: 600;
}
#qt_calendar_monthbutton { color: #FF6B47; }
#qt_calendar_yearbutton { color: #FF6B47; }
#qt_calendar_prevmonth, #qt_calendar_nextmonth {
    background: transparent;
    border-radius: 8px;
}
#qt_calendar_prevmonth:hover, #qt_calendar_nextmonth:hover {
    background: rgba(255, 107, 71, 0.10);
}
#qt_calendar_calendarview {
    background: #FFFFFF;
    border: none;
    gridline-color: transparent;
}

/* ========== 按钮体系（胶囊风格，参考李哥 2026-09-07 Click 样式图） ========== */
QPushButton {
    border-radius: 18px;
    padding: 8px 22px;
    color: #1A1A1A;
    font-weight: 600;
    border: 1px solid transparent;
    min-height: 20px;
    background: #F0F0F0;
}
QPushButton:hover { background: #E5E5E5; }
QPushButton:pressed { background: #D5D5D5; }

/* 主操作（珊瑚橙实底胶囊 + 白字） */
QPushButton#primary {
    background: #FF6B47;
    color: #FFFFFF;
    border: none;
}
QPushButton#primary:hover { background: #FF8866; }
QPushButton#primary:pressed { background: #E55A3A; }

/* 次要操作（描边胶囊：白底细描边，hover 反色——参考 Click 按钮图） */
QPushButton#secondary {
    background: #FFFFFF;
    border: 1.5px solid #1A1A1A;
    color: #1A1A1A;
}
QPushButton#secondary:hover {
    background: #1A1A1A;
    border: 1.5px solid #1A1A1A;
    color: #FFFFFF;
}
QPushButton#secondary:pressed { background: #333333; border: 1.5px solid #333333; color: #FFFFFF; }

/* 普通功能 */
QPushButton#tertiary {
    background: #F0F0F0;
    color: #1A1A1A;
}
QPushButton#tertiary:hover { background: #E5E5E5; }
QPushButton#tertiary:pressed { background: #D5D5D5; }

/* 危险操作（描边胶囊） */
QPushButton#danger {
    background: transparent;
    border: 1.5px solid #FFD5D5;
    color: #E53E3E;
}
QPushButton#danger:hover {
    background: #E53E3E;
    border: 1.5px solid #E53E3E;
    color: #FFFFFF;
}
QPushButton#danger:pressed { background: #C53030; border: 1.5px solid #C53030; color: #FFFFFF; }

/* 智能推荐 */
QPushButton#recommend {
    background: #F59E0B;
    color: #FFFFFF;
    border: none;
}
QPushButton#recommend:hover { background: #D97706; }
QPushButton#recommend:pressed { background: #B45309; }

/* 小尺寸 */
QPushButton#small {
    padding: 4px 14px;
    min-height: 18px;
    font-size: 12px;
    font-weight: 500;
}

/* ========== 表格（QTableWidget 与 QTableView 统一覆盖） ========== */
QTableWidget, QTableView {
    background: #FFFFFF;
    alternate-background-color: #FFFFFF;
    gridline-color: transparent;
    border: 1px solid #E5E5E5;
    border-radius: 12px;
    color: #1A1A1A;
    selection-background-color: rgba(255, 107, 71, 0.12);
    selection-color: #FF6B47;
    outline: none;
}
QTableWidget::item, QTableView::item {
    padding: 12px 8px;
    border-bottom: 1px solid #F0F0F0;
}
QTableWidget::item:hover, QTableView::item:hover { background: #F8F8F8; }
QTableWidget::item:selected, QTableView::item:selected {
    background: rgba(255, 107, 71, 0.12); color: #FF6B47;
}
QHeaderView::section {
    background: #FFFFFF;
    color: #6B6B6B;
    padding: 11px 10px;
    border: none;
    border-bottom: 1px solid #E5E5E5;
    font-weight: 600;
    font-size: 13px;
}
QHeaderView::section:first { border-top-left-radius: 12px; }
QHeaderView::section:last { border-top-right-radius: 12px; }
QTableCornerButton::section {
    background: #FFFFFF;
    border: none;
    border-top-left-radius: 12px;
}

/* ========== 列表 ========== */
QListWidget {
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 12px;
    color: #1A1A1A;
    padding: 6px;
    outline: none;
}
QListWidget::item {
    padding: 10px 12px;
    border-radius: 8px;
    border-bottom: 1px solid #F0F0F0;
}
QListWidget::item:hover { background: #F8F8F8; }
QListWidget::item:selected { background: rgba(255, 107, 71, 0.12); color: #FF6B47; }

/* ========== Tab 层级（业务模块内部 Tab 保留兼容） ========== */
QTabWidget::pane {
    border: none;
    background: #F5F7FA;
}
QTabBar::tab {
    background: #FFFFFF;
    color: #6B6B6B;
    padding: 11px 28px;
    border: none;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    margin-right: 4px;
}
QTabBar::tab:hover { background: #F8F8F8; color: #FF6B47; }
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #FF6B47;
    border-bottom: 2px solid #FF6B47;
}

/* ========== 单选 / 复选（勾选框参考李哥 2026-09-07 样式图：圆角方块 + 对勾） ========== */
QRadioButton {
    color: #1A1A1A;
    padding: 4px 12px 4px 0;
    background: transparent;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
}
QRadioButton::indicator:unchecked {
    border: 2px solid #D5D5D5;
    background: #FFFFFF;
}
QRadioButton::indicator:checked {
    border: 2px solid #FF6B47;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #FF6B47, stop:0.55 #FF6B47, stop:0.6 #FFFFFF, stop:1 #FFFFFF);
}
QCheckBox {
    color: #1A1A1A;
    background: transparent;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 6px;
    border: 2px solid #C9CDD4;
    background: #FFFFFF;
}
QCheckBox::indicator:hover {
    border: 2px solid #FF6B47;
    background: #FFF7F4;
}
QCheckBox::indicator:checked {
    border: 2px solid #FF6B47;
    background: #FF6B47;
}
QCheckBox::indicator:indeterminate {
    border: 2px solid #FF6B47;
    background: #FF6B47;
}
QCheckBox::indicator:disabled {
    border: 2px solid #E5E5E5;
    background: #F0F0F0;
}
QCheckBox::indicator:checked:disabled {
    border: 2px solid #E5E5E5;
    background: #C9CDD4;
}

/* ========== 滚动条 ========== */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: #D5D5D5;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #FF6B47; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #D5D5D5;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #FF6B47; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ========== 对话框 / 提示 ========== */
QDialog { background: #FFFFFF; }
QScrollArea { border: none; background: transparent; }
QToolTip {
    background: #FFFFFF;
    color: #1A1A1A;
    border: 1px solid #E5E5E5;
    border-radius: 8px;
    padding: 4px 8px;
}

/* ========== 菜单 ========== */
QMenu {
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 24px;
    border-radius: 6px;
    color: #1A1A1A;
}
QMenu::item:selected { background: rgba(255, 107, 71, 0.12); color: #FF6B47; }
QMenu::separator {
    height: 1px;
    background: #E5E5E5;
    margin: 4px 8px;
}
"""

# 勾选框对勾 / 半选图标（QSS 无法自绘勾，运行时 SVG 追加；生成失败时无 image 规则，
# checked 仍为橙色实底方块，样式不破坏）
LIGHT_QSS += _checkbox_image_rules()

# 向后兼容别名：原深色主题已弃用，统一指向浅色珊瑚橙主题
# 老 import 语句 `from theme import DARK_QSS` / `from theme import FINANCIAL_QSS`
# 无需改动即可获得新主题
DARK_QSS = LIGHT_QSS
FINANCIAL_QSS = LIGHT_QSS
