# -*- coding: utf-8 -*-
"""updater.py 安全修复回归测试（2026-08-30 P0 修复配套）。

覆盖两条不变量，任何一条被改回去都会导致测试失败：

1. Zip Slip：`extract_to_temp` 必须拒绝绝对路径 / 盘符路径 / 含 `..` 的穿越条目，
   且拒绝时**整体中止**（不做部分解压）。
2. fail-closed：`verify_zip_sha256` 在缺少预期 hash 时必须返回 False，
   而不是"跳过校验直接放行"。

运行方式：python -m pytest test_updater_security.py -v
"""
import hashlib
import os
import zipfile

import pytest

import updater


def _make_zip(path, entries):
    """构造测试用 zip。entries: {条目名: 内容或 None（None 表示目录条目）}"""
    with zipfile.ZipFile(path, 'w') as zf:
        for name, content in entries.items():
            if content is None:
                zf.writestr(zipfile.ZipInfo(name), b'')
            else:
                zf.writestr(name, content)
    return str(path)


# ==================== 1. Zip Slip 防护 ====================

@pytest.mark.parametrize('bad_name', [
    '../evil.exe',                 # 经典穿越
    'a/b/../../evil.exe',          # 嵌套穿越
    '/etc/cron.d/evil',            # 绝对路径（POSIX 风格）
    'C:/Windows/Temp/evil.exe',    # 盘符绝对路径（Windows）
    '..\\evil.exe',                # 反斜杠穿越（Windows 打包常见）
])
def test_extract_rejects_malicious_entries(tmp_path, bad_name):
    zip_path = _make_zip(tmp_path / 'update.zip', {bad_name: 'malicious'})
    target_dir = tmp_path / 'app'
    target_dir.mkdir()

    assert updater.extract_to_temp(zip_path, str(target_dir)) is None


def test_extract_reject_does_not_write_outside(tmp_path):
    """拒绝后不得在目标目录之外留下任何文件。"""
    zip_path = _make_zip(tmp_path / 'update.zip', {'../evil.exe': 'pwned'})
    target_dir = tmp_path / 'app'
    target_dir.mkdir()

    updater.extract_to_temp(zip_path, str(target_dir))

    assert not (tmp_path / 'evil.exe').exists()


def test_extract_normal_package_ok(tmp_path):
    """正常更新包不受影响：文件与目录结构正确还原。"""
    zip_path = _make_zip(tmp_path / 'update.zip', {
        'app.py': 'print("hi")',
        'pkg/__init__.py': '',
        'pkg/mod.py': 'X = 1',
    })
    target_dir = tmp_path / 'app'
    target_dir.mkdir()

    staging = updater.extract_to_temp(zip_path, str(target_dir))

    assert staging is not None
    assert (os.path.join(staging, 'app.py')).endswith('app.py')
    with open(os.path.join(staging, 'app.py'), encoding='utf-8') as f:
        assert f.read() == 'print("hi")'
    with open(os.path.join(staging, 'pkg', 'mod.py'), encoding='utf-8') as f:
        assert f.read() == 'X = 1'


# ==================== 2. SHA-256 fail-closed ====================

def test_verify_rejects_when_expected_hash_missing(tmp_path):
    """缺 hash 必须拒绝（旧行为 return True 会让校验形同虚设）。"""
    zip_path = _make_zip(tmp_path / 'update.zip', {'app.py': 'x'})

    ok, msg = updater.verify_zip_sha256(zip_path, None)

    assert ok is False
    assert '拒绝' in msg


def test_verify_accepts_matching_hash(tmp_path):
    zip_path = _make_zip(tmp_path / 'update.zip', {'app.py': 'x'})
    digest = hashlib.sha256(open(zip_path, 'rb').read()).hexdigest()

    ok, _ = updater.verify_zip_sha256(zip_path, digest)

    assert ok is True


def test_verify_rejects_mismatched_hash(tmp_path):
    zip_path = _make_zip(tmp_path / 'update.zip', {'app.py': 'x'})

    ok, msg = updater.verify_zip_sha256(zip_path, '0' * 64)

    assert ok is False
    assert '校验失败' in msg
