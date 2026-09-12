# -*- coding: utf-8 -*-
"""数据层：UDP 心跳 HMAC 配对密钥（生成 / 存储 / 签名）。

v1.0.6 安全加固（对应 Android SyncPacketAuth.kt，协议跨端严格对齐）：

- 密钥：32 字节随机，base64 编码后作为"配对码"，首次配对时生成，
  手动复制到手机端「桌面同步 → 配对码」（两端一致后心跳报文携带 HMAC 签名）
- 签名：HMAC-SHA256，签名字段 sig（base64），规范化串为
  "desktop_online|{host}|{port}|{timestamp}|{token}|{name}"
- 存储：Windows DPAPI（CryptProtectData，当前用户绑定）加密后写入
  数据中心配置文件（_data_center_config.json 的 sync_pairing_key 字段），
  配置文件泄露时其他机器/用户无法解出密钥
- 兼容：未配对（无密钥）时心跳不带 sig，手机端按旧协议降级接受

无 GUI 依赖（纯 ctypes + hmac + config_manager），供面板与服务层共用。
"""
import base64
import ctypes
import ctypes.wintypes
import hashlib
import hmac
import logging
import secrets

# 配置文件中存储 DPAPI 密文的字段名（config_manager 透传）
CONFIG_FIELD = 'sync_pairing_key'


def generate_pairing_code() -> str:
    """生成 32 字节随机密钥并返回 base64 配对码（44 字符）。"""
    return base64.b64encode(secrets.token_bytes(32)).decode('ascii')


def canonical_online(host: str, port: int, timestamp: int,
                     token: str, name: str) -> str:
    """心跳报文的规范化签名串（与 Android SyncPacketAuth 严格一致，勿单端改动）。"""
    return 'desktop_online|%s|%d|%d|%s|%s' % (host, int(port), int(timestamp),
                                              token or '', name or '')


def sign(pairing_code: str, canonical: str) -> str:
    """对规范化串计算 HMAC-SHA256，返回 base64 签名。密钥为配对码解码后的 32 字节。"""
    key = base64.b64decode(pairing_code)
    digest = hmac.new(key, canonical.encode('utf-8'), hashlib.sha256).digest()
    return base64.b64encode(digest).decode('ascii')


# ---------- DPAPI 加密存储（Windows 原生，无第三方依赖） ----------

def _dpapi_protect(plain: bytes) -> bytes:
    """CryptProtectData：密文绑定当前用户，换机器/换用户无法解密。"""
    class _BLOB(ctypes.Structure):
        _fields_ = [('cbData', ctypes.wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(plain, len(plain))
    inp = _BLOB(len(plain), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(out), None, ctypes.byref(inp), None, None, 0):
        raise OSError('CryptProtectData 失败')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _dpapi_unprotect(cipher: bytes) -> bytes:
    class _BLOB(ctypes.Structure):
        _fields_ = [('cbData', ctypes.wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(cipher, len(cipher))
    inp = _BLOB(len(cipher), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(out), None, ctypes.byref(inp), None, None, 0):
        raise OSError('CryptUnprotectData 失败')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def load_pairing_key(archive_dir: str = '') -> str:
    """从数据中心配置读取配对码（DPAPI 解密）。

    返回 base64 配对码；未配置或解密失败（换机器恢复配置文件属正常情况）
    返回空串 —— 上层按"未配对"降级为无签名心跳。
    """
    try:
        from data_center.config_manager import load_config
        stored = str(load_config(archive_dir).get(CONFIG_FIELD) or '')
        if not stored:
            return ''
        return _dpapi_unprotect(base64.b64decode(stored)).decode('ascii')
    except Exception:
        logging.info('读取配对密钥失败，按未配对处理（心跳不带签名）')
        return ''


def save_pairing_key(archive_dir: str, pairing_code: str) -> bool:
    """生成并保存新配对码（DPAPI 加密后入配置）。

    返回 True 表示已写入；失败返回 False（调用方提示用户）。
    """
    try:
        from data_center.config_manager import update_config
        cipher = _dpapi_protect(pairing_code.encode('ascii'))
        update_config(archive_dir,
                      **{CONFIG_FIELD: base64.b64encode(cipher).decode('ascii')})
        return True
    except Exception:
        logging.exception('保存配对密钥失败')
        return False


def clear_pairing_key(archive_dir: str = '') -> bool:
    """清除配对码（重新配对入口）。"""
    try:
        from data_center.config_manager import update_config
        update_config(archive_dir, **{CONFIG_FIELD: ''})
        return True
    except Exception:
        logging.exception('清除配对密钥失败')
        return False
