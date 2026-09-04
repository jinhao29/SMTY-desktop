# -*- coding: utf-8 -*-
"""管理层：Windows 系统托盘通知。

职责：
- 在不依赖 QSystemTrayIcon 实例化前置条件的情况下，安全地弹出托盘通知
- 自动检测系统是否支持托盘，不支持时降级为 print 输出
- 由 auto_sync / updater 等后台模块调用

设计原则：调用方无需关心托盘是否存在，本模块内部安全降级。
"""
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QSystemTrayIcon, QMessageBox
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter


# 全局托盘单例（由 app.py 在启动时调用 set_tray 注入）
_tray: QSystemTrayIcon = None
_parent: QObject = None


def _make_default_icon() -> QIcon:
    """生成默认应用图标（蓝色圆形 + 白色对勾），无外部资源依赖。"""
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))  # 透明背景
    painter = QPainter(pix)
    try:
        # 蓝色圆底
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor('#3B82F6'))
        painter.setPen(QColor('#3B82F6'))
        painter.drawEllipse(4, 4, 56, 56)
        # 白色对勾
        painter.setPen(QColor('#FFFFFF'))
        font = painter.font()
        font.setPointSize(28)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, '✓')
    finally:
        painter.end()
    return QIcon(pix)


def set_tray(tray: QSystemTrayIcon):
    """注入全局托盘实例（由 app.py 启动后调用）。

    参数:
        tray: 已 show() 的 QSystemTrayIcon 实例；传 None 表示清除引用
    """
    global _tray
    _tray = tray


def set_parent(parent: QObject):
    """注入父 QObject，用于在没有托盘时回退到 QMessageBox 的父窗口。"""
    global _parent
    _parent = parent


def ensure_tray(parent=None) -> QSystemTrayIcon:
    """若全局托盘不存在，则创建一个最小可用的托盘实例。

    参数:
        parent: 父 QObject

    返回:
        QSystemTrayIcon 实例；系统不支持托盘时返回 None
    """
    global _tray, _parent
    if _parent is None and parent is not None:
        _parent = parent
    if _tray is not None:
        return _tray
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    if _parent is None:
        return None
    tray = QSystemTrayIcon(_make_default_icon(), _parent)
    tray.setToolTip('上门体育教学管理工具')
    tray.show()
    _tray = tray
    return _tray


def notify(title: str, message: str, timeout_ms: int = 5000,
           severity: str = 'info'):
    """弹出托盘通知。

    参数:
        title: 通知标题
        message: 通知正文
        timeout_ms: 显示时长（毫秒），系统托盘可能忽略此值
        severity: 'info' / 'warning' / 'critical'，决定图标类型

    若托盘不可用，降级为 print 输出。
    """
    icon_map = {
        'info': QSystemTrayIcon.Information,
        'warning': QSystemTrayIcon.Warning,
        'critical': QSystemTrayIcon.Critical,
    }
    icon = icon_map.get(severity, QSystemTrayIcon.Information)

    tray = _tray
    if tray is None:
        tray = ensure_tray()
    if tray is not None:
        try:
            tray.showMessage(title, message, icon, timeout_ms)
            return
        except Exception:
            pass
    # 降级：控制台输出
    print(f'[{severity.upper()}] {title}: {message}')
