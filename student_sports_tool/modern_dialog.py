# -*- coding: utf-8 -*-
"""现代化弹窗组件：统一替换原生 QMessageBox。

职责：
- ModernDialog：无边框、白底大圆角、弥散阴影、珊瑚橙主按钮的自定义对话框
- info / warn / error / confirm：与 QMessageBox 同名同参的便捷入口，
  供全项目批量替换（QMessageBox.information -> dialog.info 等）

色彩与圆角令牌复用 base_components（与全局浅色珊瑚橙主题一致）。
confirm 兼容 QMessageBox.question 的 (parent, title, text, buttons, default)
签名，忽略按钮参数，返回 bool（True=确认）。
"""
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)
from base_components import ColorPalette, Shapes, BaseCard

_GLYPHS = {
    'info': ('!', ColorPalette.PRIMARY),
    'warn': ('!', '#F59E0B'),
    'error': ('✕', '#E53E3E'),
    'confirm': ('?', ColorPalette.PRIMARY),
}

_CIRCLE_BG = {
    'info': '#FFEDE8',
    'warn': '#FFF7E6',
    'error': '#FFEBEB',
    'confirm': '#FFEDE8',
}


class ModernDialog(QDialog):
    """无边框圆角弹窗：图标 + 标题 + 正文 + 操作按钮。"""

    def __init__(self, parent=None, title='', text='', kind='info',
                 ok_text='确定', cancel_text='取消'):
        super().__init__(parent)
        self._kind = kind
        self._drag_pos = None
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        card = BaseCard(self)
        card._main_layout.setContentsMargins(24, 20, 24, 18)
        card._main_layout.setSpacing(10)

        glyph, color = _GLYPHS.get(kind, _GLYPHS['info'])

        # 图标圆 + 标题
        head = QHBoxLayout()
        head.setSpacing(12)
        icon = QLabel(glyph)
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f'background: {_CIRCLE_BG[kind]}; color: {color};'
            f'border-radius: 22px; font-size: 20px; font-weight: 700;'
            f'font-family: "Segoe UI Symbol";'
        )
        head.addWidget(icon)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f'color: {ColorPalette.TEXT}; font-size: 15px; font-weight: 700;'
            f'background: transparent;'
        )
        title_lbl.setWordWrap(True)
        head.addWidget(title_lbl, 1)
        card._main_layout.addLayout(head)

        # 正文
        msg = QLabel(text)
        msg.setStyleSheet(
            f'color: {ColorPalette.TEXT_SECONDARY}; font-size: 13px;'
            f'background: transparent;'
        )
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card._main_layout.addWidget(msg)

        # 按钮行
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch(1)
        if kind == 'confirm':
            btn_cancel = QPushButton(cancel_text)
            btn_cancel.setObjectName('secondary')
            btn_cancel.setCursor(Qt.PointingHandCursor)
            btn_cancel.clicked.connect(self.reject)
            btns.addWidget(btn_cancel)
        btn_ok = QPushButton(ok_text)
        btn_ok.setObjectName('primary')
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setMinimumWidth(96)
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_ok)
        card._main_layout.addLayout(btns)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.setMinimumWidth(400)
        self.adjustSize()

    # ---- 无边框拖动 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        elif event.key() == Qt.Key_Escape:
            if self._kind == 'confirm':
                self.reject()
            else:
                self.accept()
        else:
            super().keyPressEvent(event)


def _run(parent, title, text, kind, ok_text='确定', cancel_text='取消'):
    dlg = ModernDialog(parent, title, text, kind, ok_text, cancel_text)
    accepted = dlg.exec() == QDialog.Accepted
    if kind == 'confirm':
        return accepted
    return True


def info(parent, title, text):
    """信息提示（自动关闭）。"""
    return _run(parent, title, text, 'info')


def warn(parent, title, text):
    """警告提示（自动关闭）。"""
    return _run(parent, title, text, 'warn')


def error(parent, title, text):
    """错误提示（自动关闭）。"""
    return _run(parent, title, text, 'error')


def confirm(parent, title, text, buttons=None, default=None):
    """确认弹窗：返回 True=确认 / False=取消。

    参数 buttons / default 仅为兼容 QMessageBox.question 的旧调用签名，
    由自定义弹窗统一渲染样式，不区分按钮种类。
    """
    return _run(parent, title, text, 'confirm', ok_text='确定', cancel_text='取消')
