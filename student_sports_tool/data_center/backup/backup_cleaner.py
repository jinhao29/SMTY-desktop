# -*- coding: utf-8 -*-
"""备份清理策略：滚动清理旧自动备份。"""
import os
import logging

from backup.backup_list_manager import list_auto_backups


def _cleanup_old_auto_backups(auto_dir, max_keep):
    """清理旧自动备份文件，仅保留最新 max_keep 份。

    策略：
    - 列出 AutoBackups/ 目录下所有 AutoBackup_*.zip 文件（按 mtime 降序）
    - 保留前 max_keep 个，删除其余

    返回: 已删除的文件数（清理异常仅记录，不影响主流程）
    """
    try:
        files = list_auto_backups(auto_dir)
        if len(files) <= max_keep:
            return 0

        deleted = 0
        for f in files[max_keep:]:
            try:
                os.remove(os.path.join(auto_dir, f))
                deleted += 1
            except (FileNotFoundError, PermissionError) as e:
                logging.error(f'删除旧自动备份失败：{os.path.join(auto_dir, f)}，原因={e}', exc_info=True)
        return deleted
    except (FileNotFoundError, PermissionError) as e:
        logging.error(f'清理旧自动备份失败：目录={auto_dir}，原因={e}', exc_info=True)
        return 0
