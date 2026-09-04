# -*- coding: utf-8 -*-
"""管理层：本地 SQLite 数据库时光机快照（v5 优化6 新增）。

职责：
- 在 do_restore 执行前，自动备份 meta_index.db 到 _db_snapshots/ 目录
- 备份文件命名：meta_index.db.old_YYYYMMDD_HHmmss
- 提供快照列表查询、按时间戳回滚、滚动清理能力
- 与 archive_manager / backup_coordinator 解耦，仅负责 .db 文件级快照

设计原则：
- 仅拷贝数据库文件本身（含 -wal / -shm 副本，保证 WAL 模式一致性）
- 失败静默记录，绝不阻塞 do_restore 主流程
- 滚动保留最近 N 份（默认 20），超出删除最旧
- 回滚操作前再生成一份"回滚前"快照，避免回滚后无法撤回

并发安全：
- 拷贝时使用 sqlite3 backup API（在线热备份），避免读锁冲突
- 若 backup API 不可用（旧版本/无 db），降级为 shutil.copy2

dir_path 作用域（2026-08-30 修复）：
- 索引库是 **per-directory** 的（`<dir>/.cache/meta_index.db`，见 meta_index_store），
  因此本模块的快照/回滚必须与档案目录同域，否则时光机操作的是主程序根目录下的
  孤儿库——与线上实际查询的库不是同一个文件，导致"快照静默失效 / 回滚无效"。
- 所有公开函数均接受 dir_path；为空时回退到主程序根目录（向后兼容旧调用）。
"""
import os
import shutil
import sqlite3
import logging
from datetime import datetime
from typing import List, Optional, Tuple


# 快照存放子目录名（位于桌面端主程序根目录下，与 meta_index.db 同级）
SNAPSHOT_DIR_NAME = '_db_snapshots'

# 默认滚动保留份数
DEFAULT_MAX_SNAPSHOTS = 20

# 快照文件名前缀
SNAPSHOT_PREFIX = 'meta_index.db.old_'


def _get_base_dir() -> str:
    """返回桌面端主程序根目录（与 data_center 同级）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_snapshot_dir(dir_path: str = '') -> str:
    """返回快照存放目录的完整路径（自动创建）。

    dir_path 非空 → `<dir>/.cache/_db_snapshots`（与 per-directory 索引同域，
    杜绝跨档案目录串档）；为空 → 主程序根目录（向后兼容）。
    """
    if dir_path:
        snap_dir = os.path.join(dir_path, '.cache', SNAPSHOT_DIR_NAME)
    else:
        snap_dir = os.path.join(_get_base_dir(), SNAPSHOT_DIR_NAME)
    try:
        os.makedirs(snap_dir, exist_ok=True)
    except OSError:
        pass
    return snap_dir


def _get_index_db_path(dir_path: str = '') -> str:
    """返回 meta_index.db 完整路径（按 dir_path 作用域）。

    延迟导入 meta_index_store，避免循环依赖。
    """
    try:
        import meta_index_store as mis
        return mis._get_index_db_path(dir_path)
    except Exception:
        # 回退：与 meta_index_store 同逻辑（per-dir 落在 <dir>/.cache 下）
        if dir_path:
            return os.path.join(dir_path, '.cache', 'meta_index.db')
        return os.path.join(_get_base_dir(), 'meta_index.db')


def create_snapshot(reason: str = 'restore', dir_path: str = '') -> Optional[str]:
    """创建一份带时间戳的数据库快照（v5 优化6 核心）。

    流程：
    1. 检查 meta_index.db 是否存在，不存在则返回 None
    2. 在 _db_snapshots/ 下生成 meta_index.db.old_YYYYMMDD_HHmmss_{reason}.db
    3. 使用 sqlite3 backup API 在线热备份（避免读锁冲突）
    4. 备份失败时降级为 shutil.copy2（拷贝 db + -wal + -shm）
    5. 滚动清理超出 DEFAULT_MAX_SNAPSHOTS 的旧快照

    参数:
        reason: 快照触发原因（restore / rollback / manual），仅用于文件名标识
        dir_path: 档案目录。非空时快照该目录的 per-directory 索引库
                  （`<dir>/.cache/meta_index.db`）到 `<dir>/.cache/_db_snapshots`

    返回: 快照文件完整路径；失败返回 None
    """
    src_db = _get_index_db_path(dir_path)
    if not os.path.exists(src_db):
        # 数据库尚未建立，无需快照
        return None

    snap_dir = get_snapshot_dir(dir_path)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_reason = ''.join(c for c in reason if c.isalnum()) or 'restore'
    snap_name = f'{SNAPSHOT_PREFIX}{timestamp}_{safe_reason}.db'
    snap_path = os.path.join(snap_dir, snap_name)

    # 优先尝试 sqlite3 在线热备份（保证 WAL 模式一致性）
    backup_ok = False
    try:
        src_conn = sqlite3.connect(src_db)
        dst_conn = sqlite3.connect(snap_path)
        try:
            src_conn.backup(dst_conn)
            backup_ok = True
        finally:
            dst_conn.close()
            src_conn.close()
    except Exception:
        backup_ok = False

    # 降级：直接拷贝文件（db + wal + shm）
    if not backup_ok:
        try:
            shutil.copy2(src_db, snap_path)
            for suffix in ('-wal', '-shm'):
                side = src_db + suffix
                if os.path.exists(side):
                    shutil.copy2(side, snap_path + suffix)
            backup_ok = os.path.exists(snap_path)
        except Exception:
            backup_ok = False

    if not backup_ok:
        # 清理可能残留的不完整快照
        try:
            if os.path.exists(snap_path):
                os.remove(snap_path)
        except OSError:
            pass
        return None

    # 滚动清理旧快照（同一 dir_path 域内）
    try:
        cleanup_old_snapshots(DEFAULT_MAX_SNAPSHOTS, dir_path=dir_path)
    except Exception:
        logging.exception('滚动清理旧快照失败')

    return snap_path


def list_snapshots(dir_path: str = '') -> List[Tuple[str, str, int]]:
    """列出指定档案目录域内的所有可用快照，按时间倒序返回。

    参数:
        dir_path: 档案目录（与 create_snapshot 保持一致的作用域）

    返回: [(快照文件名, 完整路径, 文件大小字节)]
    """
    snap_dir = get_snapshot_dir(dir_path)
    if not os.path.isdir(snap_dir):
        return []

    items: List[Tuple[str, str, int]] = []
    for f in os.listdir(snap_dir):
        if not f.startswith(SNAPSHOT_PREFIX) or not f.endswith('.db'):
            continue
        full = os.path.join(snap_dir, f)
        if not os.path.isfile(full):
            continue
        try:
            size = os.path.getsize(full)
        except OSError:
            size = 0
        items.append((f, full, size))

    # 按文件名时间戳倒序（文件名含 YYYYMMDD_HHMMSS，字符串排序即时间序）
    items.sort(key=lambda x: x[0], reverse=True)
    return items


def rollback_to_snapshot(snap_path: str, dir_path: str = '',
                         progress_cb=None) -> Tuple[bool, str]:
    """回滚数据库到指定快照（v5 优化6 核心）。

    流程：
    1. 校验快照文件存在且为 .db 文件
    2. 回滚前再生成一份"回滚前"快照（防止回滚后无法撤回）
    3. 关闭现有 meta_index.db 连接（由调用方确保无活跃连接）
    4. 拷贝快照覆盖现有 db 文件（同时清理 -wal / -shm）
    5. 校验回滚后的 db 完整性（PRAGMA integrity_check）

    参数:
        snap_path: 快照文件完整路径
        dir_path: 档案目录。决定回滚写入哪个索引库（必须与生成快照时的 dir_path 一致）
        progress_cb: 可选回调 (message: str) -> None

    返回: (success, message)
    """
    if not snap_path or not os.path.exists(snap_path):
        return False, '快照文件不存在'
    if not snap_path.endswith('.db'):
        return False, '快照文件格式不正确'

    target_db = _get_index_db_path(dir_path)
    target_dir = os.path.dirname(target_db) or '.'
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError:
        pass

    # 回滚前再生成一份快照（防撤回保护），与目标库同域
    if progress_cb:
        progress_cb('正在生成回滚前保护快照...')
    pre_snap = create_snapshot(reason='pre_rollback', dir_path=dir_path)
    if pre_snap and progress_cb:
        progress_cb(f'已生成保护快照：{os.path.basename(pre_snap)}')

    # 清理现有 db 的 WAL/SHM 副本，避免恢复后状态错乱
    for suffix in ('-wal', '-shm'):
        side = target_db + suffix
        if os.path.exists(side):
            try:
                os.remove(side)
            except OSError:
                pass

    # 拷贝快照覆盖现有 db
    if progress_cb:
        progress_cb('正在回滚数据库文件...')
    try:
        shutil.copy2(snap_path, target_db)
    except OSError as e:
        return False, f'回滚失败：{e}'

    # 校验完整性
    if progress_cb:
        progress_cb('正在校验数据库完整性...')
    ok, check_msg = verify_snapshot_integrity(target_db)
    if not ok:
        return False, f'回滚后完整性校验失败：{check_msg}'

    if progress_cb:
        progress_cb('数据库回滚成功')
    return True, '回滚成功'


def verify_snapshot_integrity(db_path: str) -> Tuple[bool, str]:
    """校验 SQLite 数据库完整性（PRAGMA integrity_check）。

    返回: (ok, message)
    """
    if not os.path.exists(db_path):
        return False, '数据库文件不存在'
    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute('PRAGMA integrity_check')
            row = cur.fetchone()
            msg = row[0] if row else 'unknown'
            return msg == 'ok', msg
        finally:
            conn.close()
    except Exception as e:
        return False, str(e)


def cleanup_old_snapshots(max_keep: int = DEFAULT_MAX_SNAPSHOTS,
                          dir_path: str = '') -> int:
    """清理旧快照，仅保留最新 max_keep 份（作用于 dir_path 域）。

    返回: 已删除的文件数
    """
    items = list_snapshots(dir_path)  # 已按时间倒序
    if len(items) <= max_keep:
        return 0

    to_delete = items[max_keep:]
    deleted = 0
    for _, full, _ in to_delete:
        try:
            os.remove(full)
            # 同步清理可能存在的 -wal / -shm 副本
            for suffix in ('-wal', '-shm'):
                side = full + suffix
                if os.path.exists(side):
                    try:
                        os.remove(side)
                    except OSError:
                        pass
            deleted += 1
        except OSError:
            pass
    return deleted


def parse_snapshot_timestamp(snap_name: str) -> Optional[datetime]:
    """从快照文件名解析时间戳。

    文件名格式：meta_index.db.old_YYYYMMDD_HHMMSS_{reason}.db
    """
    if not snap_name.startswith(SNAPSHOT_PREFIX):
        return None
    try:
        body = snap_name[len(SNAPSHOT_PREFIX):]
        # 去掉末尾 .db
        if body.endswith('.db'):
            body = body[:-3]
        # 取前 15 个字符 YYYYMMDD_HHMMSS
        ts_str = body[:15]
        return datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
    except Exception:
        return None
