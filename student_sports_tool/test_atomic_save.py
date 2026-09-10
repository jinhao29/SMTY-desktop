# -*- coding: utf-8 -*-
"""原子写回归用例：验证 atomic_save_workbook 的崩溃安全语义。

背景
----
2026-09-10：桌面端 23 处 xlsx 写入统一从 `wb.save(fpath)` 直写改为
`atomic_save_workbook(wb, fpath)`（同目录临时文件 + os.replace）。
直写的问题：写入过程中断电/崩溃/进程被杀，目标文件被截断即整体损坏，
且无可回滚副本 —— 学员档案与课时记录是整个工具的全部家当。

本文件固化该改造，重点验证「失败时原文件必须完好」这一核心契约。
"""
import os

import pytest
from openpyxl import Workbook, load_workbook

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from file_lock import atomic_save_workbook


def _mkwb(value):
    wb = Workbook()
    wb.active['A1'] = value
    return wb


def _read(path):
    wb = load_workbook(path)
    try:
        return wb.active['A1'].value
    finally:
        wb.close()


# =========================================================================
# 1. 正常路径
# =========================================================================

def test_save_creates_file(tmp_path):
    fpath = str(tmp_path / 'a.xlsx')
    atomic_save_workbook(_mkwb('hello'), fpath)
    assert os.path.exists(fpath)
    assert _read(fpath) == 'hello'


def test_save_overwrites_existing(tmp_path):
    """覆盖已存在文件后，内容应为新值。"""
    fpath = str(tmp_path / 'a.xlsx')
    atomic_save_workbook(_mkwb('old'), fpath)
    atomic_save_workbook(_mkwb('new'), fpath)
    assert _read(fpath) == 'new'


def test_save_leaves_no_temp_file_on_success(tmp_path):
    """成功后同目录不应残留 .tmp 文件。"""
    fpath = str(tmp_path / 'a.xlsx')
    atomic_save_workbook(_mkwb('v'), fpath)
    leftovers = [f for f in os.listdir(tmp_path) if f.endswith('.tmp')]
    assert leftovers == [], f'残留临时文件: {leftovers}'


# =========================================================================
# 2. 核心契约：写入失败时原文件必须完好
# =========================================================================

class _ExplodingWorkbook:
    """save() 抛异常的假工作簿，模拟写入中途崩溃。"""

    def __init__(self, exc=None):
        self.exc = exc or RuntimeError('模拟写入中断')

    def save(self, f):
        # 先写一部分字节，再抛异常 —— 逼近「写到一半崩溃」的真实场景
        f.write(b'PK\x03\x04partial-garbage')
        raise self.exc


def test_failure_preserves_original_file(tmp_path):
    """★ 核心：写入失败后，原文件内容必须与写入前完全一致。"""
    fpath = str(tmp_path / 'a.xlsx')
    atomic_save_workbook(_mkwb('original'), fpath)
    before = open(fpath, 'rb').read()

    with pytest.raises(RuntimeError):
        atomic_save_workbook(_ExplodingWorkbook(), fpath)

    after = open(fpath, 'rb').read()
    assert after == before, '原文件在写入失败后被改动，原子性被破坏'
    assert _read(fpath) == 'original', '原文件内容损坏'


def test_failure_cleans_up_temp_file(tmp_path):
    """★ 写入失败后必须清理临时文件，不留垃圾。"""
    fpath = str(tmp_path / 'a.xlsx')
    atomic_save_workbook(_mkwb('original'), fpath)

    with pytest.raises(RuntimeError):
        atomic_save_workbook(_ExplodingWorkbook(), fpath)

    leftovers = [f for f in os.listdir(tmp_path) if f.endswith('.tmp')]
    assert leftovers == [], f'失败后残留临时文件: {leftovers}'


def test_failure_on_nonexistent_target_leaves_nothing(tmp_path):
    """目标文件不存在时写入失败 —— 不应产生半成品文件。"""
    fpath = str(tmp_path / 'not_yet.xlsx')
    with pytest.raises(RuntimeError):
        atomic_save_workbook(_ExplodingWorkbook(), fpath)
    assert not os.path.exists(fpath), '失败后不应创建目标文件'
    assert [f for f in os.listdir(tmp_path) if f.endswith('.tmp')] == []


def test_keyboard_interrupt_also_cleans_up(tmp_path):
    """BaseException（如 Ctrl+C）同样要清理临时文件。

    实现用的是 `except BaseException`，此处锁定该行为：
    否则中断会留下 .tmp 垃圾，且半成品文件可能被误认为有效数据。
    """
    fpath = str(tmp_path / 'a.xlsx')
    atomic_save_workbook(_mkwb('original'), fpath)

    with pytest.raises(KeyboardInterrupt):
        atomic_save_workbook(_ExplodingWorkbook(KeyboardInterrupt()), fpath)

    assert _read(fpath) == 'original'
    assert [f for f in os.listdir(tmp_path) if f.endswith('.tmp')] == []


# =========================================================================
# 3. 路径处理边界
# =========================================================================

def test_save_to_path_without_dirname(tmp_path, monkeypatch):
    """fpath 只有文件名（无目录）时，dir 应回落当前目录而非空字符串。

    实现里 `os.path.dirname(...) or '.'` 就是这个用途；mkstemp(dir='')
    在部分平台会抛 FileNotFoundError。
    """
    monkeypatch.chdir(tmp_path)
    atomic_save_workbook(_mkwb('bare'), 'bare.xlsx')
    assert os.path.exists(tmp_path / 'bare.xlsx')


def test_save_to_relative_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs('sub', exist_ok=True)
    atomic_save_workbook(_mkwb('rel'), os.path.join('sub', 'r.xlsx'))
    assert _read(tmp_path / 'sub' / 'r.xlsx') == 'rel'


def test_temp_file_is_in_same_dir(tmp_path):
    """临时文件必须与目标同目录 —— 跨盘 os.replace 不是原子操作。

    通过给 wb.save 传一个真实文件对象来读取其路径；真 openpyxl 在
    真实调用中同样收到 os.fdopen 的文件对象。
    """
    fpath = str(tmp_path / 'a.xlsx')
    seen = {}

    class _Spy:
        def save(self, f):
            # f 是 atomic_save_workbook 里 os.fdopen(fd,'wb') 的产物；
            # 其 name 为 fd 整数，改用 /proc 风格不可跨平台，故包一层：
            # 直接看文件系统里此刻的 .tmp 位置更可靠。
            import glob
            cands = glob.glob(os.path.join(str(tmp_path), '*.tmp'))
            seen['candidates'] = cands
            seen['write_ok'] = True
            wb = _mkwb('spied')
            wb.save(f)

    atomic_save_workbook(_Spy(), fpath)
    assert seen.get('write_ok') is True
    assert seen['candidates'], '写入过程中未在同目录找到临时文件'
    for c in seen['candidates']:
        assert os.path.dirname(c) == str(tmp_path)


# =========================================================================
# 4. 与 file_lock 叠加（真实调用形态）
# =========================================================================

def test_works_under_file_lock(tmp_path):
    """实际调用点都是 `with file_lock(p): atomic_save_workbook(wb, p)`。"""
    from file_lock import file_lock
    fpath = str(tmp_path / 'locked.xlsx')
    with file_lock(fpath):
        atomic_save_workbook(_mkwb('under-lock'), fpath)
    assert _read(fpath) == 'under-lock'


def test_unicode_filename(tmp_path):
    """中文文件名（项目里全是「学员档案.xlsx」这类）。"""
    fpath = str(tmp_path / '学员档案.xlsx')
    atomic_save_workbook(_mkwb('张三'), fpath)
    assert _read(fpath) == '张三'
