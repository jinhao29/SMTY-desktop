# -*- coding: utf-8 -*-
"""启动模式选择页：上门体育 / 俱乐部。

参考李哥提供的 Select Model 卡片交互：
- 两张大卡片，点击选中（珊瑚橙描边 + 浅橙底），双击直接进入
- 右下角 Continue 胶囊按钮确认
- ESC / 关闭 = 退出程序

俱乐部端尚未建设（占位）：选中后提示"建设中"，留在选择页。
"""
import os
import sys

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget
)

PRIMARY = '#FF6B47'
TEXT = '#1A1A1A'
TEXT_MUTED = '#9B9B9B'
BORDER = '#E5E5E5'


class ModeCard(QWidget):
    """模式选择卡：圆角白卡，可选中。选中态珊瑚橙描边 + 浅橙底。"""

    def __init__(self, title: str, desc: str, badge: str,
                 badge_color: str, icon_kind: str, parent=None):
        super().__init__(parent)
        self._selected = False
        self._icon_kind = icon_kind
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(240, 220)
        self.setObjectName('modeCard')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(6)

        badge_lbl = QLabel(badge)
        badge_lbl.setFixedHeight(22)
        badge_lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        badge_lbl.setStyleSheet(
            f'color: {badge_color}; font-size: 11px; font-weight: 700;'
            f'border: 1px solid {badge_color}; border-radius: 11px;'
            'padding: 2px 10px; background: transparent;'
        )
        badge_lbl.setFixedWidth(badge_lbl.fontMetrics().horizontalAdvance(badge) + 24)
        lay.addWidget(badge_lbl)
        lay.addStretch()

        t = QLabel(title)
        t.setStyleSheet(
            f'color: {TEXT}; font-size: 19px; font-weight: 800;'
            'background: transparent; border: none;'
        )
        lay.addWidget(t)

        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(
            f'color: {TEXT_MUTED}; font-size: 12px;'
            'background: transparent; border: none;'
        )
        lay.addWidget(d)

    # 右上角图标走 paintEvent 自绘（几何简形，与黑白极简统一）
    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        selected = self._selected
        # 卡片底 + 描边
        card = QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(PRIMARY if selected else BORDER),
                      2 if selected else 1))
        p.setBrush(QColor('#FFF7F4' if selected else '#FFFFFF'))
        p.drawRoundedRect(card, 16, 16)
        # 右上角圆形图标（直径 34）
        cx, cy, rad = r.width() - 40, 36, 17
        icon_color = QColor(PRIMARY if selected else TEXT_MUTED)
        p.setPen(QPen(icon_color, 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        if self._icon_kind == 'stopwatch':
            # 秒表简形：圆盘 + 指针 + 顶部柄
            p.drawEllipse(QPointF(cx, cy + 2), rad - 6, rad - 6)
            p.drawLine(QPointF(cx, cy - rad + 2), QPointF(cx, cy - rad + 6))
            p.drawLine(QPointF(cx, cy + 2), QPointF(cx + 5, cy - 3))
        else:
            # 俱乐部：闪电简形
            p.drawLine(QPointF(cx + 3, cy - 9), QPointF(cx - 4, cy + 1))
            p.drawLine(QPointF(cx - 4, cy + 1), QPointF(cx + 1, cy + 1))
            p.drawLine(QPointF(cx + 1, cy + 1), QPointF(cx - 3, cy + 9))
        p.end()

    def mousePressEvent(self, ev):
        self._selected = True
        self.update()
        self.window().select_card(self)

    def mouseDoubleClickEvent(self, ev):
        self.window().confirm()


class ModeSelector(QDialog):
    """启动模式选择对话框。exec() 返回 'coaching' / 'club' / None(退出)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择工作模式')
        self.setModal(True)
        self.setFixedWidth(640)
        self.choice = None
        self._cards = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(16)

        title = QLabel('选择工作模式')
        title.setStyleSheet(
            f'color: {TEXT}; font-size: 20px; font-weight: 800;'
            'background: transparent; border: none;'
        )
        root.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(16)
        self._cards = [
            ModeCard('上门体育', '学员档案 · 课时排课 · 财务记账 · 数据中心',
                     '常用', PRIMARY, 'stopwatch'),
            ModeCard('俱乐部', 'EVOLVE 进化体育 · 独立数据空间，与上门体育完全隔离',
                     'NEW', '#10B981', 'bolt'),
        ]
        for c in self._cards:
            row.addWidget(c, 1)
        root.addLayout(row)
        root.addStretch()

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn = QPushButton('进入')
        btn.setObjectName('primary')
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(112, 40)
        btn.clicked.connect(self.confirm)
        bottom.addWidget(btn)
        root.addLayout(bottom)

        # 默认选中第一张（上门体育）
        self._cards[0]._selected = True
        self.choice = 'coaching'

    def select_card(self, card: ModeCard):
        for c in self._cards:
            c._selected = c is card
            c.update()
        self.choice = 'coaching' if card is self._cards[0] else 'club'

    def confirm(self):
        self.accept()


# ============================================================
# 模式持久化 + 俱乐部数据目录（v23.12 多租户·物理隔离）
# ============================================================

_MODE_FILE = os.path.join(os.path.expanduser('~'), '.shangmentiyu', 'app_mode.json')


def club_archive_dir() -> str:
    """俱乐部档案目录（单俱乐部阶段：Desktop\\学员档案俱乐部）。

    与上门体育的 Desktop\\学员档案 平级，物理隔离零串库。
    """
    return os.path.join(os.path.expanduser('~'), 'Desktop', '学员档案俱乐部')


def ensure_club_dir() -> str:
    """确保俱乐部目录存在（首次自动创建；xlsx 骨架由各 storage 的 ensure 逻辑按需建）。"""
    d = club_archive_dir()
    os.makedirs(d, exist_ok=True)
    return d


def load_last_mode() -> str:
    """上次使用的模式（'coaching' / 'club'；无记录返回 'coaching'）。"""
    try:
        import json
        with open(_MODE_FILE, encoding='utf-8') as f:
            return json.load(f).get('mode') or 'coaching'
    except Exception:
        return 'coaching'


def save_mode(mode: str):
    try:
        import json
        os.makedirs(os.path.dirname(_MODE_FILE), exist_ok=True)
        with open(_MODE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'mode': mode}, f, ensure_ascii=False)
    except Exception:
        pass


def run_selector() -> str:
    """独立入口：弹出选择页，返回 'coaching' / 'club' / None(退出)。

    俱乐部模式 = 独立档案目录（ensure_club_dir 自动创建）跑同一套功能，
    数据与上门体育完全隔离（v23.12 多租户·物理隔离）。
    """
    app = QApplication.instance() or QApplication(sys.argv)
    import theme
    app.setStyleSheet(theme.LIGHT_QSS)
    dlg = ModeSelector()
    dlg.exec()
    return dlg.choice


if __name__ == '__main__':
    print('choice =', run_selector())
