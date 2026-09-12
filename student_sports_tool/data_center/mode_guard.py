# -*- coding: utf-8 -*-
"""租户隔离守卫（v23.13 配置化）。

判定规则不再硬编码，改为从 ``config/modes.json`` 读取
（见 [mode_config]）：

- 目录判定：``目录 basename`` → 与各模式的 ``archive_dir`` 比对反查模式 id
  （学员档案 → coaching / 学员档案俱乐部 → club_evolve）
- 备份判定：手机备份 zip 的 ``export_meta.json``（v23.12 起）带 ``meta.mode``；
  旧值经 ``aliases`` 解析（``club`` → ``club_evolve``）
- 两端模式不一致则拒绝合并 —— 防模式错位导致串库
- 旧版备份（无 mode 字段）或无法解析的值一律按 ``default_mode`` 处理

新增机构时本文件无需改动：目录名从配置来。
"""
import json
import zipfile

from mode_config import default_mode, mode_for_archive_dir, resolve_alias, get_mode


def _label(mode_id: str) -> str:
    """模式 id → 显示名（用于报错文案）。"""
    m = get_mode(mode_id)
    return (m or {}).get('display_name') or mode_id


def dir_mode(archive_dir: str) -> str:
    """PC 档案目录对应的工作模式 id（配置反查；未知目录回退 default_mode）。"""
    return mode_for_archive_dir(archive_dir) or default_mode()


def backup_mode_raw(zip_path: str):
    """读取备份包 meta.mode 的**原始值**；无法判定时返回 None。

    返回 None 的两种情况（调用方语义不同，需区分）：
    - zip 里没有 export_meta.json → **纯 PC 备份**（PC 自身备份不含该条目），
      属于当前目录体系的数据，防串库校验应跳过
    - 有条目但没有 mode 字段 → 旧版备份（俱乐部功能 v23.12 才引入，
      无标记备份必属上门体育），按 default_mode 宽容处理

    坏 zip 仍向上抛异常（与 backup_mode 一致，不能把坏包误判成默认模式）。
    """
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if 'export_meta.json' not in zf.namelist():
            return None
        data = zf.read('export_meta.json').decode('utf-8', errors='replace')
        try:
            meta = json.loads(data)
        except json.JSONDecodeError:
            return None
        raw = str((meta.get('meta') or {}).get('mode') or '').strip()
        return raw or None


def backup_mode(zip_path: str) -> str:
    """备份 zip 的工作模式 id。旧值经 aliases 解析，无法解析按 default_mode。

    注意：zip 本身损坏时仍向上抛异常（与旧实现一致，避免把坏包误判成默认模式）。
    """
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if 'export_meta.json' not in zf.namelist():
            return default_mode()
        data = zf.read('export_meta.json').decode('utf-8', errors='replace')
        try:
            meta = json.loads(data)
        except json.JSONDecodeError:
            return default_mode()
        raw = str((meta.get('meta') or {}).get('mode') or '')
    return resolve_alias(raw) or default_mode()


def check_backup_mode(zip_path: str, archive_dir: str):
    """校验备份模式与目录模式一致。返回 (ok, reason)。"""
    bm = backup_mode(zip_path)
    dm = dir_mode(archive_dir)
    if bm == dm:
        return True, ''
    return False, (
        '备份来自「%s」模式，但当前目录是「%s」模式的数据，拒绝合并'
        % (_label(bm), _label(dm)))
