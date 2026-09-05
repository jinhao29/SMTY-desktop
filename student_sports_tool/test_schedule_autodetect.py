# -*- coding: utf-8 -*-
"""达成率面板「最新手机备份自动检测」自检测试。

运行：pytest test_schedule_autodetect.py -v
"""
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_center.schedule_lesson_analyzer import (
    find_latest_phone_backup, is_phone_backup)


def _make_phone_backup(path):
    """构造含 schedules 表的手机备份 zip。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('export_meta.json', json.dumps({'students': []}))
        # 最小 sqlite：含 schedules 空表
        import sqlite3
        tmp = path + '.db.tmp'
        conn = sqlite3.connect(tmp)
        conn.execute('CREATE TABLE schedules (id INTEGER, student_name TEXT, date TEXT)')
        conn.commit()
        conn.close()
        zf.write(tmp, 'sports_coach.db')
        os.remove(tmp)
    with open(path, 'wb') as f:
        f.write(buf.getvalue())


def test_is_phone_backup():
    d = os.path.dirname(os.path.abspath(__file__))
    pc_zip = os.path.join(d, '_pc_backup_test.zip')
    phone_zip = os.path.join(d, '_phone_backup_test.zip')
    try:
        # PC 目录自备份（纯 xlsx）→ 非手机备份
        with zipfile.ZipFile(pc_zip, 'w') as zf:
            zf.writestr('学员档案.xlsx', 'x')
        assert is_phone_backup(pc_zip) is False
        # 手机备份（含 export_meta.json）→ 是
        with zipfile.ZipFile(phone_zip, 'w') as zf:
            zf.writestr('export_meta.json', '{}')
        assert is_phone_backup(phone_zip) is True
        # 不存在 → False
        assert is_phone_backup(os.path.join(d, 'nope.zip')) is False
    finally:
        for p in (pc_zip, phone_zip):
            if os.path.exists(p):
                os.remove(p)


def test_find_latest_prefers_sync_dir_and_newest():
    import tempfile
    import time
    archive = tempfile.mkdtemp(prefix='smty_sched_')
    sync_dir = os.path.join(archive, '.sync_backups')
    os.makedirs(sync_dir)

    # PC 自备份：应被排除
    with zipfile.ZipFile(os.path.join(archive, '恢复前自动备份_x.zip'), 'w') as zf:
        zf.writestr('学员档案.xlsx', 'x')

    # 旧手机备份（同步目录）
    old = os.path.join(sync_dir, 'smty_backup_old.smty_backup')
    _make_phone_backup(old)
    os.utime(old, (time.time() - 3600,) * 2)

    # 新手机备份（同步目录，更晚 mtime）
    new = os.path.join(sync_dir, 'smty_backup_new.smty_backup')
    _make_phone_backup(new)

    assert find_latest_phone_backup(archive) == new

    # 更新的备份放在档案根目录（手动拖入场景）→ 应胜出
    newer = os.path.join(archive, '手动导入.zip')
    _make_phone_backup(newer)
    os.utime(newer, (time.time() + 10,) * 2)
    assert find_latest_phone_backup(archive) == newer

    # 空目录 → ''
    empty = tempfile.mkdtemp(prefix='smty_sched_empty_')
    assert find_latest_phone_backup(empty) == ''


def test_panel_autodetect_fills_lineedit():
    """面板初始化时自动填充最新备份路径。"""
    import tempfile
    import time as _t
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    archive = tempfile.mkdtemp(prefix='smty_panel_ad_')
    sync_dir = os.path.join(archive, '.sync_backups')
    os.makedirs(sync_dir)
    bak = os.path.join(sync_dir, 'smty_backup_a.smty_backup')
    _make_phone_backup(bak)

    from data_center.schedule_achievement_panel import ScheduleAchievementPanel
    panel = ScheduleAchievementPanel(dir_getter=lambda: archive)
    assert panel.le_zip.text() == bak, panel.le_zip.text()


if __name__ == '__main__':
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('PASS %s' % name)
            except AssertionError as e:
                fails += 1
                print('FAIL %s: %s' % (name, e))
    sys.exit(1 if fails else 0)
