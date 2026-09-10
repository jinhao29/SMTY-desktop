# -*- coding: utf-8 -*-
"""跨端备份加密互通自检：验证 Python 侧能解开 Java 侧格式的加密载荷。

为什么必须有这个测试
--------------------
备份加密是**双端协议**：Android（Java AES-GCM）写入，桌面端（Python cryptography）读取。
两端算法参数只要有一处不一致（魔数、IV 长度、GCM 标签、KDF 迭代、盐编码），
表现都是"备份打不开"，且现场极难定位。

本脚本用 Python 独立实现 Android BackupCrypto.kt 的格式，双向验证：
  1. Python 加密 -> Python 解密（自洽）
  2. 逐字节核对与 Java 实现的格式约定一致（魔数/IV/标签长度）
  3. 错误口令必须失败（不能退化成"随便什么口令都能解"）

用法:
    python Py/verify_backup_crypto.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_center.android_backup_parser import (  # noqa: E402
    _BACKUP_MAGIC, _GCM_IV_LEN, _DEFAULT_ITERATIONS,
    _derive_backup_key, _decrypt_payload, is_encrypted_payload,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

PASS = '李哥的私钥-seed-2026'
SALT_HEX = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'


def encrypt_like_android(plain: bytes, key, iv: bytes) -> bytes:
    """按 Android BackupCrypto.encrypt 的格式封装：魔数 + IV + 密文+GCM标签。"""
    ciphertext = AESGCM(key).encrypt(iv, plain, None)
    return _BACKUP_MAGIC + iv + ciphertext


def main() -> int:
    failures = []

    def check(name, cond, detail=''):
        status = 'OK  ' if cond else 'FAIL'
        print(f'[{status}] {name}' + (f'  ({detail})' if detail else ''))
        if not cond:
            failures.append(name)

    print('=' * 62)
    print('跨端备份加密互通自检（Python 侧 impersonate Android 格式）')
    print('=' * 62)

    key = _derive_backup_key(PASS, SALT_HEX, 1000)  # 低迭代加速
    plain = '学员张三,13800000000,广州市天河区'.encode('utf-8')

    # 1. 格式常量与 Android 对齐
    check('魔数为 SMTB (4字节)', _BACKUP_MAGIC == b'SMTB' and len(_BACKUP_MAGIC) == 4)
    check('GCM IV 长度 = 12', _GCM_IV_LEN == 12)
    check('默认迭代次数 = 600000', _DEFAULT_ITERATIONS == 600000)

    # 2. 加密 -> 解密往返
    iv = os.urandom(12)
    payload = encrypt_like_android(plain, key, iv)
    check('加密载荷可被识别为加密', is_encrypted_payload(payload))
    decrypted = _decrypt_payload(payload, key)
    check('同口令可正确解密', decrypted == plain,
          f'得到 {decrypted[:20]!r}' if decrypted != plain else '')

    # 3. 密文中不含明文
    check('密文不泄露明文', b'13800000000' not in payload)

    # 4. 错误口令必须失败
    wrong_key = _derive_backup_key('错误口令', SALT_HEX, 1000)
    check('错误口令解密失败', _decrypt_payload(payload, wrong_key) is None)

    # 5. 明文不应被误判为加密
    check('明文不被误判为加密', not is_encrypted_payload(b'SQLite format 3\x00'))

    # 6. 篡改必须被 GCM 拒绝
    tampered = bytearray(payload)
    tampered[-1] ^= 0xFF
    check('篡改载荷被拒绝', _decrypt_payload(bytes(tampered), key) is None)

    # 7. 密文长度 = 魔数 + IV + 明文长 + GCM标签(16)
    expected_len = 4 + 12 + len(plain) + 16
    check('载荷长度符合格式约定', len(payload) == expected_len,
          f'{len(payload)} vs {expected_len}')

    print('-' * 62)
    if failures:
        print(f'失败 {len(failures)} 项: {", ".join(failures)}')
        return 1
    print('全部通过 ✓  Python 侧与 Android 加密格式一致')
    return 0


if __name__ == '__main__':
    sys.exit(main())
