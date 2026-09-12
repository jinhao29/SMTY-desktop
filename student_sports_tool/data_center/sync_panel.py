# -*- coding: utf-8 -*-
"""UI 层：双端同步服务面板（数据中心子 Tab）。

v23.5 设备自动发现与信任：
- 服务随主程序自动启动（sync_service.get_service 全局单例，app.py 驱动），
  面板按钮只做启停切换，与主程序共享同一服务实例
- 心跳广播携带 token 与 PC 名称，手机端零配置自动填充
- 手机回执设备指纹（ANDROID_ID）→ 本面板「发现的设备」列表展示，
  教练一键信任；未信任设备仅登记，不影响数据通道鉴权（token 机制独立）

配置持久化：config_manager（sync_port / sync_token / sync_devices）。
"""
import os
import socket
import sys
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QSpinBox,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, 'training_tool'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import tray_notifier
except Exception:  # 托盘不可用时静默降级
    tray_notifier = None

# 新设计语言令牌与组件（灰白简约 · 珊瑚橙强调）
from cards import Card
from styles import Palette

DEFAULT_PORT = 8765


def _local_ip() -> str:
    """探测本机局域网 IP（用于界面展示手机端应填的地址）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()


class SyncServerPanel(QWidget):
    """双端同步服务面板（与主程序共享全局服务实例）。"""

    def __init__(self, archive_dir_getter=None, parent=None):
        super().__init__(parent)
        self._get_dir = archive_dir_getter or (lambda: '')
        self._init_ui()
        self._load_config()
        # 设备列表 / 状态定时刷新（服务线程异步写 config，轮询最简单可靠）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_devices)
        self._timer.timeout.connect(self._refresh_hint)
        self._timer.start(5000)
        self._refresh_devices()
        self._refresh_hint()

    # ---------- UI ----------

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        # 服务控制卡（状态/按钮、端口/token、配对码三行，避免拥挤重叠）
        card = Card('服务控制')
        cl = QVBoxLayout()
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)

        row1 = QHBoxLayout()
        self.lbl_status = QLabel('服务未启动')
        self.lbl_status.setStyleSheet(f'font-weight:bold; color:{Palette.MUTED};')
        row1.addWidget(self.lbl_status)
        row1.addStretch()
        self.btn_toggle = QPushButton('启动同步服务')
        self.btn_toggle.setObjectName('primary')
        self.btn_toggle.setFixedWidth(140)
        self.btn_toggle.clicked.connect(self._on_toggle)
        row1.addWidget(self.btn_toggle)
        cl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel('端口'))
        self.sb_port = QSpinBox()
        self.sb_port.setRange(1024, 65535)
        self.sb_port.setValue(DEFAULT_PORT)
        self.sb_port.setFixedWidth(100)
        row2.addWidget(self.sb_port)
        row2.addSpacing(24)
        row2.addWidget(QLabel('token（两端一致，留空不鉴权）'))
        self.le_token = QLineEdit()
        self.le_token.setPlaceholderText('留空跳过鉴权')
        self.le_token.setMaximumWidth(220)
        row2.addWidget(self.le_token)
        row2.addStretch()
        cl.addLayout(row2)

        # v1.0.6 心跳 HMAC 配对：生成配对码 → 手机端「桌面同步 → 配对码」粘贴，
        # 两端一致后心跳报文携带 HMAC 签名，同网段伪造心跳无法劫持上传目标
        row3 = QHBoxLayout()
        row3.addWidget(QLabel('配对码（心跳防伪造）'))
        self.le_pairing = QLineEdit()
        self.le_pairing.setReadOnly(True)
        self.le_pairing.setPlaceholderText('未配对（心跳不签名，仍可自动发现）')
        self.le_pairing.setMaximumWidth(340)
        row3.addWidget(self.le_pairing)
        self.btn_pair = QPushButton('生成 / 重新配对')
        self.btn_pair.setObjectName('secondary')
        self.btn_pair.setFixedWidth(130)
        self.btn_pair.clicked.connect(self._on_generate_pairing)
        row3.addWidget(self.btn_pair)
        self.btn_unpair = QPushButton('清除')
        self.btn_unpair.setObjectName('secondary')
        self.btn_unpair.setFixedWidth(70)
        self.btn_unpair.clicked.connect(self._on_clear_pairing)
        row3.addWidget(self.btn_unpair)
        row3.addStretch()
        cl.addLayout(row3)

        self.lbl_hint = QLabel('')
        self.lbl_hint.setObjectName('hint')
        self.lbl_hint.setWordWrap(True)
        cl.addWidget(self.lbl_hint)
        card.set_content_layout(cl)
        lay.addWidget(card)

        # 说明卡（固定内容，三行以内，不被列表挤压）
        guide = Card()
        gl = QVBoxLayout()
        gl.setContentsMargins(0, 0, 0, 0)
        steps = QLabel(
            '① 服务随主程序自动开启：USB 手机插入即连，同一 Wi-Fi 手机端「自动发现 PC」即可；'
            '② 下方信任自己的手机；③ 连不上先运行 desktop_sync/firewall_allow.bat')
        steps.setObjectName('hint')
        steps.setWordWrap(True)
        gl.addWidget(steps)
        guide.set_content_layout(gl)
        lay.addWidget(guide)

        # 发现的设备卡（最小高度保证标题与列表可见）
        dev_card = Card('发现的设备（信任后标记为自己的设备）')
        dl = QVBoxLayout()
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(110)
        dl.addWidget(self.device_list, 1)
        btn_row = QHBoxLayout()
        self.btn_trust = QPushButton('信任选中设备')
        self.btn_trust.setObjectName('secondary')
        self.btn_trust.clicked.connect(self._on_trust_selected)
        btn_row.addWidget(self.btn_trust)
        self.btn_untrust = QPushButton('取消信任')
        self.btn_untrust.setObjectName('secondary')
        self.btn_untrust.clicked.connect(self._on_untrust_selected)
        btn_row.addWidget(self.btn_untrust)
        btn_row.addStretch()
        dl.addLayout(btn_row)
        dev_card.set_content_layout(dl)
        lay.addWidget(dev_card, 3)

        # 同步日志卡
        log_card = Card('同步日志')
        ll = QVBoxLayout()
        ll.setContentsMargins(0, 0, 0, 0)
        self.log_list = QListWidget()
        self.log_list.setMinimumHeight(90)
        ll.addWidget(self.log_list)
        log_card.set_content_layout(ll)
        lay.addWidget(log_card, 2)

    # ---------- 配置 ----------

    def _load_config(self):
        try:
            from data_center.config_manager import load_config
            from data_center.pairing_key import load_pairing_key
            cfg = load_config(self._get_dir())
            self.sb_port.setValue(int(cfg.get('sync_port') or DEFAULT_PORT))
            self.le_token.setText(str(cfg.get('sync_token') or ''))
            self.le_pairing.setText(load_pairing_key(self._get_dir()))
        except Exception:
            pass
        self._refresh_hint()

    def _save_config(self):
        try:
            from data_center.config_manager import update_config
            update_config(self._get_dir(),
                          sync_port=self.sb_port.value(),
                          sync_token=self.le_token.text().strip())
        except Exception:
            logging.exception('保存同步配置失败')

    def _refresh_hint(self):
        from data_center.sync_service import get_service
        running = get_service().is_running()
        if running:
            self.lbl_hint.setText(
                f'手机端配置：地址 {_local_ip()}，端口 {self.sb_port.value()}'
                f'（USB 连接则地址填 127.0.0.1，插入即自动连接）')
            self.lbl_status.setText('服务运行中（随主程序自动启动）')
            self.lbl_status.setStyleSheet(f'font-weight:bold; color:{Palette.GREEN};')
            self.btn_toggle.setText('停止同步服务')
        else:
            self.lbl_hint.setText('主程序启动时会自动开启服务；也可在此手动启动。')
            self.lbl_status.setText('服务未启动')
            self.lbl_status.setStyleSheet(f'font-weight:bold; color:{Palette.MUTED};')
            self.btn_toggle.setText('启动同步服务')

    # ---------- 服务启停（全局单例） ----------

    def _on_toggle(self):
        from data_center.sync_service import get_service
        svc = get_service()
        if svc.is_running():
            svc.stop()
            self._refresh_hint()
            return
        archive_dir = self._get_dir()
        if not archive_dir or not os.path.isdir(archive_dir):
            try:
                import modern_dialog as dialog
                dialog.warn(self, '提示', '请先在上方设置有效的档案目录')
            except Exception:
                pass
            return
        self._save_config()
        svc.add_log_callback(self._on_log)
        svc.start(port=self.sb_port.value(),
                  token=self.le_token.text().strip(),
                  archive_dir=archive_dir)
        self._refresh_hint()

    # ---------- 配对码（心跳 HMAC） ----------

    def _restart_service_if_running(self):
        """配对码变更后重启服务，让心跳签名立即生效（幂等：未运行则不动）。"""
        from data_center.sync_service import get_service
        svc = get_service()
        if not svc.is_running():
            return
        svc.stop()
        archive_dir = self._get_dir()
        svc.add_log_callback(self._on_log)
        svc.start(port=self.sb_port.value(),
                  token=self.le_token.text().strip(),
                  archive_dir=archive_dir)

    def _on_generate_pairing(self):
        from data_center.pairing_key import generate_pairing_code, save_pairing_key
        code = generate_pairing_code()
        if not save_pairing_key(self._get_dir(), code):
            self._append_log('配对码保存失败（配置文件不可写？）')
            return
        self.le_pairing.setText(code)
        self._restart_service_if_running()
        self._append_log('已生成新配对码：请复制到手机端「设置 → 桌面同步 → 配对码」完成配对')

    def _on_clear_pairing(self):
        from data_center.pairing_key import clear_pairing_key
        clear_pairing_key(self._get_dir())
        self.le_pairing.clear()
        self._restart_service_if_running()
        self._append_log('已清除配对码：心跳恢复无签名（手机端自动降级兼容）')

    def _append_log(self, msg: str):
        self._on_log('[%s] [同步] %s' % (
            __import__('time').strftime('%Y-%m-%d %H:%M:%S'), msg))

    def _on_log(self, line: str):
        self.log_list.addItem(line)
        # v23.6：设备上线/新设备 → 系统托盘通知（手机连上 PC 时教练立即可感知）
        if ('发现新设备' in line or '设备上线' in line) and tray_notifier:
            try:
                tray_notifier.notify('双端同步', line.split('] ', 1)[-1])
            except Exception:
                pass
        # 限制日志条数，避免长期运行内存膨胀
        while self.log_list.count() > 200:
            self.log_list.takeItem(0)
        self.log_list.scrollToBottom()

    # ---------- 设备信任 ----------

    def _load_devices(self) -> dict:
        try:
            from data_center.config_manager import load_config
            if not self._get_dir():
                return {}
            return load_config(self._get_dir()).get('sync_devices') or {}
        except Exception:
            return {}

    def _refresh_devices(self):
        """刷新设备列表（轮询 config，5 秒一次）。"""
        if not hasattr(self, 'device_list'):
            return
        devices = self._load_devices()
        self.device_list.clear()
        if not devices:
            self.device_list.addItem('（尚未发现设备：手机连接同一 Wi-Fi 或 USB 后自动回执）')
            return
        for device_id, dev in sorted(devices.items(),
                                     key=lambda kv: kv[1].get('last_seen', ''),
                                     reverse=True):
            trusted = bool(dev.get('trusted'))
            tag = '✓ 已信任' if trusted else '待信任'
            item = QListWidgetItem(
                f"{dev.get('name', '未知设备')}　·　{tag}　·　最近在线 {dev.get('last_seen', '')}")
            item.setData(Qt.UserRole, device_id)
            item.setForeground(Qt.darkGreen if trusted else Qt.darkYellow)
            self.device_list.addItem(item)

    def _set_trust(self, trusted: bool):
        selected = self.device_list.currentItem()
        if selected is None or not selected.data(Qt.UserRole):
            return
        device_id = selected.data(Qt.UserRole)
        try:
            from data_center.config_manager import load_config, update_config
            devices = self._load_devices()
            if device_id in devices:
                devices[device_id]['trusted'] = trusted
                update_config(self._get_dir(), sync_devices=devices)
            self._refresh_devices()
            if tray_notifier:
                name = devices.get(device_id, {}).get('name', device_id[:8])
                tray_notifier.notify('双端同步',
                                     ('已信任设备：%s' if trusted else '已取消信任：%s') % name)
        except Exception:
            logging.exception('更新设备信任状态失败')

    def _on_trust_selected(self):
        self._set_trust(True)

    def _on_untrust_selected(self):
        self._set_trust(False)

    def shutdown(self):
        """窗口关闭时清理（服务为全局单例，随主程序常驻）。"""
        try:
            from data_center.sync_service import get_service
            get_service().remove_log_callback(self._on_log)
        except Exception:
            pass
        self._timer.stop()
