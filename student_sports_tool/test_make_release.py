# -*- coding: utf-8 -*-
"""make_release.py 最小自检：版本真源格式 + sha256 侧车格式契约。"""
import hashlib
import os
import re
import sys

import make_release


def test_read_version_valid(tmp_path, monkeypatch):
    (tmp_path / 'VERSION').write_text('v1.2.3\n', encoding='utf-8')
    monkeypatch.setattr(make_release, 'HERE', str(tmp_path))
    assert make_release.read_version() == 'v1.2.3'


def test_read_version_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(make_release, 'HERE', str(tmp_path))
    # 缺文件
    try:
        make_release.read_version()
        assert False, '应因缺 VERSION 失败'
    except SystemExit:
        pass
    # 非法格式（run_number 风格）
    (tmp_path / 'VERSION').write_text('v62', encoding='utf-8')
    try:
        make_release.read_version()
        assert False, '应因格式非法失败'
    except SystemExit:
        pass


def test_sha256_sidecar_matches_updater_contract(tmp_path):
    """侧车格式必须能被 updater._fetch_sidecar_sha256 的解析规则读回。"""
    zip_path = tmp_path / make_release.zip_name_for("v1.0.0")
    payload = b'fake zip bytes'
    zip_path.write_bytes(payload)
    digest = make_release.make_sha256(str(zip_path))
    assert digest == hashlib.sha256(payload).hexdigest()
    sidecar = (tmp_path / (make_release.zip_name_for("v1.0.0") + ".sha256")).read_text(encoding='utf-8')
    m = re.search(r'[0-9a-f]{64}', sidecar, re.I)
    assert m and m.group(0).lower() == digest


def test_get_current_version_reads_version_file(tmp_path, monkeypatch):
    """exe 旁 VERSION 优先于 __VERSION__；_internal/VERSION 是打包兜底。"""
    import updater
    fake = type(sys)('fake_sys')
    fake.frozen = True
    fake.executable = str(tmp_path / 'app.exe')
    monkeypatch.setattr(updater, 'sys', fake)
    # exe 旁
    (tmp_path / 'VERSION').write_text('v9.9.9', encoding='utf-8')
    assert updater.get_current_version() == 'v9.9.9'
    # 只有 _internal/VERSION 时兜底可读
    (tmp_path / 'VERSION').unlink()
    internal = tmp_path / '_internal'
    internal.mkdir()
    (internal / 'VERSION').write_text('v8.8.8', encoding='utf-8')
    assert updater.get_current_version() == 'v8.8.8'
    # 都没有 → 硬编码
    (internal / 'VERSION').unlink()
    assert updater.get_current_version() == updater.__VERSION__
