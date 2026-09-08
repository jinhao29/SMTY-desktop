# -*- coding: utf-8 -*-
"""租户隔离守卫（v23.12 多租户·物理隔离）。

判定规则（双端约定，与 Android ModeManager 的模式值一致）：
- 'coaching' 上门体育：PC 档案目录 = Desktop\\学员档案（任意非俱乐部目录）
- 'club'     俱乐部  ：PC 档案目录 = Desktop\\学员档案俱乐部

手机备份 zip 的 export_meta.json（v23.12 起）带 meta.mode 字段；
PC 合并前校验两者一致，不一致拒绝合并——防两端模式错位导致串库。
旧版备份（无 mode 字段）视为 'coaching'（向后兼容，俱乐部库备份必带）。
"""
import json
import os
import zipfile

CLUB_DIR_NAME = '学员档案俱乐部'


def dir_mode(archive_dir: str) -> str:
    """PC 档案目录对应的工作模式。"""
    try:
        if os.path.basename(os.path.normpath(archive_dir or '')) == CLUB_DIR_NAME:
            return 'club'
    except Exception:
        pass
    return 'coaching'


def backup_mode(zip_path: str) -> str:
    """读取备份 zip 的工作模式标记；旧版备份无标记时按 'coaching'。"""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if 'export_meta.json' not in zf.namelist():
            return 'coaching'
        data = zf.read('export_meta.json').decode('utf-8', errors='replace')
        meta = json.loads(data)
        return str((meta.get('meta') or {}).get('mode') or 'coaching')


def check_backup_mode(zip_path: str, archive_dir: str):
    """校验备份模式与目录模式一致。返回 (ok, reason)。"""
    bm = backup_mode(zip_path)
    dm = dir_mode(archive_dir)
    if bm == dm:
        return True, ''
    return False, (
        '备份来自「%s」模式，但当前目录是「%s」模式的数据，拒绝合并'
        % ('俱乐部' if bm == 'club' else '上门体育',
           '俱乐部' if dm == 'club' else '上门体育'))
