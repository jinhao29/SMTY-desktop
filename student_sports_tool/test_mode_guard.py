# -*- coding: utf-8 -*-
"""mode_guard：租户隔离守卫。

v23.13 起判定改为配置驱动（config/modes.json），模式 id 用新命名：
俱乐部 = 'club_evolve'（旧值 'club' 经 aliases 解析）。
"""
import json
import os
import sys
import tempfile
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_center'))

from android_backup_parser import parse_backup_mode
from backup.backup_restorer import ensure_backup_mode
from data_center.mode_guard import backup_mode, check_backup_mode, dir_mode


def _make_backup(mode=None):
    """构造一个带 export_meta.json 的最小备份 zip。"""
    fd, path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    meta = {'meta': {'version': '1.0'}}
    if mode is not None:
        meta['meta']['mode'] = mode
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('export_meta.json', json.dumps(meta))
    return path


def test_dir_mode_coaching():
    assert dir_mode(r'C:/Users/x/Desktop/学员档案') == 'coaching'
    assert dir_mode('') == 'coaching'
    assert dir_mode(None) == 'coaching'


def test_dir_mode_club():
    assert dir_mode(r'C:/Users/x/Desktop/学员档案俱乐部') == 'club_evolve'


def test_backup_mode_new_and_legacy():
    # 手机端现阶段仍写旧值 'club' → 必须解析到 club_evolve
    assert backup_mode(_make_backup('club')) == 'club_evolve'
    assert backup_mode(_make_backup('club_evolve')) == 'club_evolve'
    assert backup_mode(_make_backup('coaching')) == 'coaching'
    assert backup_mode(_make_backup(None)) == 'coaching'  # 旧版备份无标记


def test_backup_mode_unknown_value_falls_back():
    assert backup_mode(_make_backup('garbage')) == 'coaching'


def test_check_same_mode_pass():
    p = _make_backup('club')
    ok, _ = check_backup_mode(p, r'C:/x/学员档案俱乐部')
    assert ok
    p2 = _make_backup('coaching')
    ok2, _ = check_backup_mode(p2, r'C:/x/学员档案')
    assert ok2


def test_check_mismatch_rejected():
    p = _make_backup('club')
    ok, reason = check_backup_mode(p, r'C:/x/学员档案')
    assert not ok and '俱乐部' in reason and '上门体育' in reason


# ---------------------------------------------------------------------------
# v23.13 备份防串库：手动恢复路径的 mode 校验（ensure_backup_mode）
# + 解析层 mode 入口（parse_backup_mode）
# ---------------------------------------------------------------------------

def _make_zip(entries: dict) -> str:
    fd, path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def _meta_zip(mode):
    return _make_zip({'export_meta.json': json.dumps(
        {'meta': {'version': '1.0', 'mode': mode}})})


def test_ensure_backup_mode_rejects_cross_mode(tmp_path):
    """俱乐部备份恢复进上门体育目录 → 明确报错（防串库）。"""
    coaching_dir = tmp_path / '学员档案'
    coaching_dir.mkdir()
    with pytest.raises(ValueError):
        ensure_backup_mode(_meta_zip('club'), str(coaching_dir))


def test_ensure_backup_mode_allows_legacy_value_in_club_dir(tmp_path):
    """旧值 mode=club 的备份恢复到俱乐部目录 → 归一化后放行（旧备份兼容）。"""
    club_dir = tmp_path / '学员档案俱乐部'
    club_dir.mkdir()
    ensure_backup_mode(_meta_zip('club'), str(club_dir))          # 不抛即通过
    ensure_backup_mode(_meta_zip('club_evolve'), str(club_dir))   # 新值同样放行


def test_ensure_backup_mode_allows_coaching_backup_in_coaching_dir(tmp_path):
    coaching_dir = tmp_path / '学员档案'
    coaching_dir.mkdir()
    ensure_backup_mode(_meta_zip('coaching'), str(coaching_dir))  # 不抛即通过


def test_ensure_backup_mode_skips_pure_pc_backup(tmp_path):
    """纯 PC 备份 zip（无 export_meta.json）不参与 mode 校验 —— 俱乐部目录
    恢复 PC 自己做的备份不能被误拒。"""
    zip_path = _make_zip({'学员张三.xlsx': b'fake'})
    club_dir = tmp_path / '学员档案俱乐部'
    club_dir.mkdir()
    ensure_backup_mode(zip_path, str(club_dir))                   # 不抛即通过


def test_parse_backup_mode_resolves_legacy_values(tmp_path):
    """解析层 mode 入口：历史值归一化；无标记返回 None。"""
    assert parse_backup_mode(_meta_zip('club')) == 'club_evolve'
    assert parse_backup_mode(_meta_zip('club_evolve')) == 'club_evolve'
    assert parse_backup_mode(_meta_zip('coaching')) == 'coaching'
    assert parse_backup_mode(_make_zip({'data.txt': 'x'})) is None


if __name__ == '__main__':
    test_dir_mode_coaching()
    test_dir_mode_club()
    test_backup_mode_new_and_legacy()
    test_backup_mode_unknown_value_falls_back()
    test_check_same_mode_pass()
    test_check_mismatch_rejected()
    print('MODE GUARD TESTS PASS')
