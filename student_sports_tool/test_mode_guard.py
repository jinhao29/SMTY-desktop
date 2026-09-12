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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_center'))

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


if __name__ == '__main__':
    test_dir_mode_coaching()
    test_dir_mode_club()
    test_backup_mode_new_and_legacy()
    test_backup_mode_unknown_value_falls_back()
    test_check_same_mode_pass()
    test_check_mismatch_rejected()
    print('MODE GUARD TESTS PASS')
