# -*- coding: utf-8 -*-
"""全局浅色珊瑚橙主题 QSS（Light Coral Orange Theme）。

职责：
- 提供统一的暖白背景、纯白卡片、珊瑚橙主色、浅灰边框的 Qt 样式表
- 供 main.py、training_tool/main.py、app.py 统一引用，避免样式漂移
- 主色 #FF6B47（活力珊瑚橙）与 Android 端完全一致，实现双端视觉统一

色彩令牌（与 Android 端 UI 规范严格对齐）：
- 背景：#F5F7FA（暖白） / 侧边栏：#F5F5F5
- 卡片：#FFFFFF（纯白） / 边框：#E5E5E5（浅灰）
- 主色：#FF6B47（活力珊瑚橙，选中态背景，文字反白为 #FFFFFF）
- 文字：#1A1A1A（主，≥12:1） / #6B6B6B（次，≥4.6:1） / #9B9B9B（弱）
"""

# 浅色珊瑚橙主题（主推，与 Android 端视觉统一）
LIGHT_QSS = """
/* ========== 全局基础 ========== */
QMainWindow, QWidget {
    background: #F5F7FA;
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
    border-radius: 10px;
    padding: 8px 12px;
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
    padding: 7px 11px;
}
QLineEdit::placeholder, QTextEdit::placeholder {
    color: #9B9B9B;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #6B6B6B;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 10px;
    color: #1A1A1A;
    selection-background-color: rgba(255, 107, 71, 0.12);
    selection-color: #FF6B47;
    padding: 4px;
    outline: none;
}

/* ========== 按钮体系 ========== */
QPushButton {
    border-radius: 10px;
    padding: 9px 20px;
    color: #1A1A1A;
    font-weight: 600;
    border: none;
    min-height: 22px;
    background: #F0F0F0;
}
QPushButton:hover { background: #E5E5E5; }
QPushButton:pressed { background: #D5D5D5; }

/* 主操作（珊瑚橙底白色字） */
QPushButton#primary {
    background: #FF6B47;
    color: #FFFFFF;
}
QPushButton#primary:hover { background: #FF8866; }
QPushButton#primary:pressed { background: #E55A3A; }

/* 次要操作（透明底珊瑚橙字） */
QPushButton#secondary {
    background: transparent;
    border: 1px solid #E5E5E5;
    color: #FF6B47;
}
QPushButton#secondary:hover {
    background: rgba(255, 107, 71, 0.08);
    border: 1px solid #FF6B47;
}
QPushButton#secondary:pressed { background: rgba(255, 107, 71, 0.15); }

/* 普通功能 */
QPushButton#tertiary {
    background: #F0F0F0;
    color: #1A1A1A;
}
QPushButton#tertiary:hover { background: #E5E5E5; }
QPushButton#tertiary:pressed { background: #D5D5D5; }

/* 危险操作 */
QPushButton#danger {
    background: transparent;
    border: 1px solid #FFD5D5;
    color: #E53E3E;
}
QPushButton#danger:hover {
    background: #FFF5F5;
    border: 1px solid #E53E3E;
}
QPushButton#danger:pressed { background: #FFE5E5; }

/* 智能推荐 */
QPushButton#recommend {
    background: #F59E0B;
    color: #FFFFFF;
}
QPushButton#recommend:hover { background: #D97706; }
QPushButton#recommend:pressed { background: #B45309; }

/* 小尺寸 */
QPushButton#small {
    padding: 5px 12px;
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
    background: #F8F8F8;
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
    background: #F8F8F8;
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

/* ========== 单选 / 复选 ========== */
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
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 2px solid #D5D5D5;
    background: #FFFFFF;
}
QCheckBox::indicator:checked {
    border: 2px solid #FF6B47;
    background: #FF6B47;
    image: none;
}
QCheckBox::indicator:hover { border: 2px solid #6B6B6B; }

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
QDialog { background: #F5F7FA; }
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

# 向后兼容别名：原深色主题已弃用，统一指向浅色珊瑚橙主题
# 老 import 语句 `from theme import DARK_QSS` / `from theme import FINANCIAL_QSS`
# 无需改动即可获得新主题
DARK_QSS = LIGHT_QSS
FINANCIAL_QSS = LIGHT_QSS
