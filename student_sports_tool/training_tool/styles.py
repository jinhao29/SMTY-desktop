# -*- coding: utf-8 -*-
"""训练任务编排模块样式令牌 + 作用域 QSS（灰白简约 · 蓝紫强调）。

设计语言（对齐图2）：
- 背景 #F2F4F8 / 卡片 #FFFFFF / 圆角 12px / 轻微阴影
- 主文字 #1A1A2E / 次文字 #6B7280 / 强调色 #5B6BF7
- 标签 #F3F4F6 底 / #374151 字

仅作用域 training_tool 模块根（#training_root），不污染全局珊瑚橙主题，
其它业务模块（学员档案 / 体测档案 / 数据中心）视觉零影响。

懒人说明：QSS 由 main.MainWindow 在根 widget 上 setStyleSheet，
widget 级样式表优先级高于 QApplication 级，故内部选择器无需与全局争抢特异性。
"""
from PySide6.QtGui import QFont, QColor


# ==================== 色彩令牌 ====================

class Palette:
    BG = '#FFFFFF'              # 主背景：纯白（v25.1 去灰底）
    CARD = '#FFFFFF'            # 卡片背景
    TEXT = '#1A1A2E'            # 主文字：深灰
    TEXT_SUB = '#6B7280'        # 次文字：中灰
    TEXT_TERTIARY = '#4A4A6A'   # 辅助色
    ACCENT = '#5B6BF7'          # 强调色：蓝紫（按钮/链接/选中）
    ACCENT_BLUE = '#3B82F6'     # 备选蓝
    ACCENT_HOVER = '#4A5AE0'    # 强调色加深 10%（hover）
    ACCENT_PRESSED = '#3B4AC8'  # pressed
    ACCENT_LIGHT = '#EEF0FE'    # 选中态浅背景
    DIVIDER = '#E5E7EB'         # 分割线
    BORDER = '#E5E7EB'          # 通用边框
    TAG_BG = '#F3F4F6'          # 标签背景
    TAG_TEXT = '#374151'        # 标签文字
    STATUS_BG = '#FFFFFF'       # 底部状态栏背景（v25.1 去灰底，靠上边框分界）
    HEADER_BG = '#FFFFFF'       # 顶部导航栏背景
    GREEN = '#10B981'           # 同步成功
    RED = '#EF4444'             # 危险
    MUTED = '#9CA3AF'           # 弱化


# ==================== 圆角 ====================

class Radius:
    CARD = 12
    BUTTON = 8
    TAG = 6
    PILL = 20
    SMALL = 6


# ==================== 间距 ====================

class Spacing:
    PAGE = 24          # 页面边距
    CARD = 16          # 卡片间距
    CARD_PAD = 20      # 卡片内边距
    SM = 8
    MD = 12
    LG = 16


# ==================== 字体 ====================

class Type:
    """字体令牌（像素级，对齐规格 12/14/16/20/24，行高 1.6）。"""
    _FALLBACK = ['Microsoft YaHei UI', 'Segoe UI', '微软雅黑', 'Inter', 'Roboto']

    @classmethod
    def _f(cls, px, weight=QFont.Normal):
        f = QFont(cls._FALLBACK[0])
        f.setPixelSize(px)
        f.setWeight(weight)
        return f

    @classmethod
    def caption(cls):
        """12px / 400 辅助文字"""
        return cls._f(12)

    @classmethod
    def body(cls):
        """14px / 400 正文"""
        return cls._f(14)

    @classmethod
    def card_title(cls):
        """16px / 600 卡片标题"""
        return cls._f(16, QFont.DemiBold)

    @classmethod
    def page_title(cls):
        """20px / 600 页面标题"""
        return cls._f(20, QFont.DemiBold)

    @classmethod
    def hero(cls):
        """24px / 600 大号标题"""
        return cls._f(24, QFont.DemiBold)


# ==================== 阴影参数（供 Card paintEvent） ====================

class Shadow:
    OFFSET_Y = 2
    BLUR_STEPS = 8
    MAX_ALPHA = 15  # rgba(0,0,0,0.06) 量级

    @staticmethod
    def shadow_color(alpha: int) -> QColor:
        return QColor(0, 0, 0, alpha)


# ==================== 作用域 QSS ====================

# 仅在 #training_root 子树生效，覆盖全局珊瑚橙
TRAINING_QSS = f"""
#training_root {{
    background: {Palette.BG};
}}
#training_root QWidget {{ background: transparent; }}
#training_root QLabel {{ color: {Palette.TEXT}; background: transparent; }}
#training_root QLabel#hint, #training_root QLabel#caption {{
    color: {Palette.TEXT_SUB}; font-size: 12px;
}}
#training_root QLabel#cardTitle {{
    color: {Palette.TEXT}; font-size: 16px; font-weight: 600; background: transparent;
}}
#training_root QLabel#tag {{
    background: {Palette.TAG_BG}; color: {Palette.TAG_TEXT};
    border-radius: {Radius.TAG}px; padding: 4px 10px; font-size: 12px;
}}
#training_root QLabel#pageTitle {{
    color: {Palette.TEXT}; font-size: 20px; font-weight: 600; background: transparent;
}}
#training_root QLabel#hero {{
    color: {Palette.TEXT}; font-size: 24px; font-weight: 600; background: transparent;
}}
#training_root QLabel#subtle {{ color: {Palette.TEXT_SUB}; font-size: 13px; background: transparent; }}

/* 卡片容器 */
#training_root QFrame#card {{
    background: {Palette.CARD}; border: 1px solid {Palette.DIVIDER};
    border-radius: {Radius.CARD}px;
}}

/* 输入控件 */
#training_root QLineEdit, #training_root QComboBox, #training_root QTextEdit,
#training_root QDateEdit, #training_root QSpinBox {{
    background: {Palette.CARD}; border: 1px solid {Palette.DIVIDER};
    border-radius: {Radius.BUTTON}px; padding: 8px 12px; color: {Palette.TEXT};
    selection-background-color: {Palette.ACCENT}; selection-color: #FFFFFF;
    min-height: 20px;
}}
#training_root QLineEdit:hover, #training_root QComboBox:hover,
#training_root QTextEdit:hover, #training_root QDateEdit:hover {{
    border: 1px solid #D1D5DB;
}}
#training_root QLineEdit:focus, #training_root QComboBox:focus,
#training_root QTextEdit:focus, #training_root QDateEdit:focus {{
    border: 2px solid {Palette.ACCENT}; padding: 7px 11px;
}}
#training_root QLineEdit::placeholder, #training_root QTextEdit::placeholder {{
    color: {Palette.MUTED};
}}
#training_root QComboBox::drop-down {{ border: none; width: 24px; }}
#training_root QComboBox::down-arrow {{
    image: none; border-left: 5px solid transparent; border-right: 5px solid transparent;
    border-top: 6px solid {Palette.TEXT_SUB}; margin-right: 8px;
}}
#training_root QComboBox QAbstractItemView {{
    background: {Palette.CARD}; border: 1px solid {Palette.DIVIDER};
    border-radius: {Radius.BUTTON}px; color: {Palette.TEXT};
    selection-background-color: {Palette.ACCENT_LIGHT}; selection-color: {Palette.ACCENT};
    padding: 4px; outline: none;
}}
/* 可编辑标签输入（时长/器材等，无边框圆角灰底） */
#training_root QLineEdit#tagInput {{
    background: {Palette.TAG_BG}; color: {Palette.TAG_TEXT}; border: none;
    border-radius: {Radius.TAG}px; padding: 4px 10px; font-size: 12px; min-height: 18px;
}}
#training_root QLineEdit#tagInput:focus {{ border: 2px solid {Palette.ACCENT}; padding: 3px 9px; }}

/* 按钮 */
#training_root QPushButton {{
    background: {Palette.TAG_BG}; color: {Palette.TEXT}; border: none;
    border-radius: {Radius.BUTTON}px; padding: 9px 18px; font-size: 14px; font-weight: 500;
    min-height: 20px;
}}
#training_root QPushButton:hover {{ background: #E5E7EB; }}
#training_root QPushButton:pressed {{ background: #D1D5DB; }}
#training_root QPushButton#primary {{
    background: {Palette.ACCENT}; color: #FFFFFF;
}}
#training_root QPushButton#primary:hover {{ background: {Palette.ACCENT_HOVER}; }}
#training_root QPushButton#primary:pressed {{ background: {Palette.ACCENT_PRESSED}; }}
#training_root QPushButton#secondary {{
    background: transparent; border: 1px solid {Palette.DIVIDER}; color: {Palette.ACCENT};
}}
#training_root QPushButton#secondary:hover {{
    background: {Palette.ACCENT_LIGHT}; border: 1px solid {Palette.ACCENT};
}}
#training_root QPushButton#secondary:pressed {{ background: #E0E3FB; }}
#training_root QPushButton#danger {{
    background: transparent; border: 1px solid #FECACA; color: {Palette.RED};
}}
#training_root QPushButton#danger:hover {{ background: #FEF2F2; border: 1px solid {Palette.RED}; }}
#training_root QPushButton#recommend {{
    background: {Palette.ACCENT_BLUE}; color: #FFFFFF;
}}
#training_root QPushButton#recommend:hover {{ background: #2F72E0; }}
#training_root QPushButton#small {{
    padding: 5px 12px; min-height: 18px; font-size: 12px; font-weight: 500;
}}
/* 幽灵按钮（仅图标，透明底） */
#training_root QPushButton#ghost {{
    background: transparent; border: none; padding: 4px 8px; color: {Palette.TEXT_SUB};
    font-size: 14px; min-height: 0;
}}
#training_root QPushButton#ghost:hover {{ color: {Palette.ACCENT}; background: {Palette.ACCENT_LIGHT}; }}

/* 表格 */
#training_root QTableWidget {{
    background: {Palette.CARD}; alternate-background-color: #FFFFFF;
    gridline-color: transparent; border: 1px solid {Palette.DIVIDER};
    border-radius: {Radius.CARD}px; color: {Palette.TEXT};
    selection-background-color: {Palette.ACCENT_LIGHT}; selection-color: {Palette.ACCENT};
    outline: none;
}}
#training_root QTableWidget::item {{ padding: 10px 8px; border-bottom: 1px solid #F3F4F6; }}
#training_root QTableWidget::item:hover {{ background: #F9FAFB; }}
#training_root QTableWidget::item:selected {{
    background: {Palette.ACCENT_LIGHT}; color: {Palette.ACCENT};
}}
#training_root QHeaderView::section {{
    background: #FFFFFF; color: {Palette.TEXT_SUB}; padding: 10px;
    border: none; border-bottom: 1px solid {Palette.DIVIDER};
    font-weight: 600; font-size: 12px;
}}
#training_root QTableCornerButton::section {{ background: #FFFFFF; border: none; }}

/* 列表 */
#training_root QListWidget {{
    background: transparent; border: none; color: {Palette.TEXT}; padding: 0; outline: none;
}}
#training_root QListWidget::item {{ background: transparent; border: none; padding: 0; }}

/* 滚动条 */
#training_root QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; border: none; }}
#training_root QScrollBar::handle:vertical {{
    background: #D1D5DB; border-radius: 4px; min-height: 30px;
}}
#training_root QScrollBar::handle:vertical:hover {{ background: {Palette.ACCENT}; }}
#training_root QScrollBar::add-line:vertical, #training_root QScrollBar::sub-line:vertical {{ height: 0; }}
#training_root QScrollBar::add-page:vertical, #training_root QScrollBar::sub-page:vertical {{ background: transparent; }}
#training_root QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; border: none; }}
#training_root QScrollBar::handle:horizontal {{
    background: #D1D5DB; border-radius: 4px; min-width: 30px;
}}
#training_root QScrollBar::handle:horizontal:hover {{ background: {Palette.ACCENT}; }}
#training_root QScrollBar::add-line:horizontal, #training_root QScrollBar::sub-line:horizontal {{ width: 0; }}

/* 滚动区/提示 */
#training_root QScrollArea {{ border: none; background: transparent; }}
#training_root QToolTip {{
    background: {Palette.CARD}; color: {Palette.TEXT};
    border: 1px solid {Palette.DIVIDER}; border-radius: 6px; padding: 4px 8px;
}}
#training_root QMenu {{
    background: {Palette.CARD}; border: 1px solid {Palette.DIVIDER};
    border-radius: {Radius.BUTTON}px; padding: 6px;
}}
#training_root QMenu::item {{ padding: 8px 24px; border-radius: 6px; color: {Palette.TEXT}; }}
#training_root QMenu::item:selected {{ background: {Palette.ACCENT_LIGHT}; color: {Palette.ACCENT}; }}
"""
