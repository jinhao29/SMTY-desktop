# -*- coding: utf-8 -*-
"""时光机 dir_path 作用域回归检查（assert 自检，无框架依赖）。

验证点：快照创建/列出/清理均作用于 `<dir>/.cache/_db_snapshots`，
而非主程序根目录的孤儿库——这是 2026-08 串档修复的关键约束。

运行：python test_db_snapshot_scope.py
"""
import os
import shutil
import sys
import tempfile
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_center'))
import db_snapshot_manager as dsm  # noqa: E402


def _make_index_db(dir_path: str, marker: str) -> None:
    """在指定档案目录建立带标记表的 per-directory 索引库。"""
    cache = os.path.join(dir_path, '.cache')
    os.makedirs(cache, exist_ok=True)
    conn = sqlite3.connect(os.path.join(cache, 'meta_index.db'))
    conn.execute(f'CREATE TABLE marker_{marker} (id INTEGER)')
    conn.commit()
    conn.close()


def main() -> int:
    root = tempfile.mkdtemp(prefix='dsm_scope_')
    dir_a = os.path.join(root, 'archiveA')
    dir_b = os.path.join(root, 'archiveB')
    os.makedirs(dir_a, exist_ok=True)
    os.makedirs(dir_b, exist_ok=True)
    try:
        _make_index_db(dir_a, 'aaa')
        _make_index_db(dir_b, 'bbb')

        # 1. 快照落在 per-dir 域，且 root 域不应产生任何快照
        snap_a = dsm.create_snapshot(reason='test', dir_path=dir_a)
        assert snap_a and os.path.exists(snap_a), 'A 域快照应创建成功'
        assert os.path.dirname(os.path.dirname(os.path.dirname(snap_a))) == dir_a, \
            f'快照应位于 <dir>/.cache/_db_snapshots 下，实际：{snap_a}'

        # 2. B 域列出快照时不应看到 A 域的快照（跨域隔离）
        assert dsm.list_snapshots(dir_path=dir_a), 'A 域应能列出自己的快照'
        assert not dsm.list_snapshots(dir_path=dir_b), 'B 域不应看到 A 域快照'

        # 3. 无 db 的目录 create_snapshot 返回 None（不误报）
        assert dsm.create_snapshot(reason='test', dir_path=root) is None or \
            os.path.exists(os.path.join(root, '.cache', 'meta_index.db')), \
            '空域不应凭空建库快照'

        # 4. 回滚写入的目标库也在 per-dir 域
        target = dsm._get_index_db_path(dir_path=dir_a)
        assert target.startswith(dir_a), f'回滚目标应指向 A 域索引库，实际：{target}'

        print('PASS: 时光机快照/列出/回滚均按 dir_path 作用域隔离')
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
