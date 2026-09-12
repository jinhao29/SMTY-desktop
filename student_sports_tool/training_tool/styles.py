# -*- coding: utf-8 -*-
"""训练任务编排模块样式令牌 + 作用域 QSS（灰白简约 · 珊瑚橙强调）。

设计语言（v26 统一：对齐全局珊瑚橙设计系统，与 Android 端一致）：
- 背景 #FFFFFF / 卡片 #FFFFFF / 圆角 12px / 轻微阴影
- 主文字 #1A1A2E / 次文字 #6B7280 / 强调色 #FF6B47（珊瑚橙）
- 按钮：胶囊形（radius 18）/ primary 橙底白字 / secondary 描边白底 hover 反色

仅作用域 training_tool 模块根（#training_root），不污染全局主题，
其它业务模块（学员档案 / 体测档案 / 数据中心）视觉零影响。

懒人说明：QSS 由 main.MainWindow 在根 widget 上 setStyleSheet，
widget 级样式表优先级高于 QApplication 级，故内部选择器无需与全局争抢特异性。
"""
from PySide6.QtGui import QFont, QColor
import os as _os


def _ensure_combo_arrow_icon():
    """生成下拉框箭头 chevron SVG，返回其绝对路径（正斜杠，QSS image:url 可用）。

    border-triangle / image:none 两种 QSS 画法在本机 Qt 都渲染异常
    （实心小方块 / 无箭头），与 theme.py 勾选框对勾同款方案：运行时写
    SVG 到 ~/.shangmentiyu/ui_assets/，QSS image:url 引用。
    生成失败返回 ''，QSS 回退交还原生箭头。
    """
    try:
        user_dir = _os.path.join(_os.path.expanduser('~'), '.shangmentiyu', 'ui_assets')
        _os.makedirs(user_dir, exist_ok=True)
        path = _os.path.join(user_dir, 'combobox_chevron.svg')
        if not _os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                f.write(
                    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'>"
                    "<path d='M2.5 4.2 6 7.8 9.5 4.2' fill='none' stroke='#6B7280' "
                    "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/></svg>")
        return path.replace('\\', '/')
    except OSError:
        return ''


_COMBO_ARROW_SVG = _ensure_combo_arrow_icon()

# image:url 规则条件拼接（空路径时拼空串，避免 QSS 空 url 破坏语法——theme.py 同款处理）
# 注意：本串经 {变量} 插入 f-string，不会再做 format 转义，必须用单层大括号
_COMBO_ARROW_RULE = (
    "#training_root QComboBox::down-arrow {\n"
    "    image: url(%s); width: 12px; height: 12px; margin-right: 7px;\n"
    "}\n" % _COMBO_ARROW_SVG
) if _COMBO_ARROW_SVG else (
    "/* 箭头 SVG 生成失败：交还原生箭头 */\n"
)


# ==================== 色彩令牌 ====================

class Palette:
    BG = '#FFFFFF'              # 主背景：纯白（v25.1 去灰底）
    CARD = '#FFFFFF'            # 卡片背景
    TEXT = '#1A1A2E'            # 主文字：深灰
    TEXT_SUB = '#6B7280'        # 次文字：中灰
    TEXT_TERTIARY = '#4A4A6A'   # 辅助色
    ACCENT = '#FF6B47'          # 强调色：珊瑚橙（与全局/Android 端统一，v26）
    ACCENT_HOVER = '#F5582F'    # 强调色加深（hover）
    ACCENT_PRESSED = '#E04D28'  # pressed
    ACCENT_LIGHT = '#FFF1EC'    # 选中态浅橙背景
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
    BUTTON = 18    # 胶囊按钮（对齐全局视觉规范）
    TAG = 10
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
        """22px / 700 页面标题（与主应用 PageHeader 层级统一，2026-09-07）"""
        return cls._f(22, QFont.Bold)

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
    color: {Palette.TEXT}; font-size: 22px; font-weight: 700; background: transparent;
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
{_COMBO_ARROW_RULE}
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
    background: #FFFFFF; border: 1px solid {Palette.TEXT}; color: {Palette.TEXT};
}}
#training_root QPushButton#secondary:hover {{
    background: {Palette.TEXT}; color: #FFFFFF; border: 1px solid {Palette.TEXT};
}}
#training_root QPushButton#secondary:pressed {{ background: #33334D; }}
#training_root QPushButton#danger {{
    background: transparent; border: 1px solid #FECACA; color: {Palette.RED};
}}
#training_root QPushButton#danger:hover {{
    background: {Palette.RED}; color: #FFFFFF; border: 1px solid {Palette.RED};
}}
#training_root QPushButton#danger:pressed {{ background: #DC2626; }}
#training_root QPushButton#recommend {{
    background: {Palette.ACCENT}; color: #FFFFFF;
}}
#training_root QPushButton#recommend:hover {{ background: {Palette.ACCENT_HOVER}; }}
#training_root QPushButton#recommend:pressed {{ background: {Palette.ACCENT_PRESSED}; }}
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


def scoped_qss(root_name: str = 'training_root') -> str:
    """把同一套灰白卡片 QSS 重新作用域到任意根 objectName。

    供 training_tool 之外的模块（学员档案 / 数据中心）复用同一设计语言：
    页面根容器 setObjectName('profile_root') 后调用
    ``setStyleSheet(scoped_qss('profile_root'))``，选择器逐个替换、零遗漏
    （含下拉箭头 image:url 规则）。默认参数返回原 TRAINING_QSS 等价结果。
    """
    return TRAINING_QSS.replace('#training_root', '#' + root_name)
