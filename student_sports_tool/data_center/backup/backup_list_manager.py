# -*- coding: utf-8 -*-
"""备份列表管理：列出自动备份文件。"""
import os

from backup import AUTO_BACKUP_FILE_PREFIX


def list_auto_backups(auto_dir):
    """列出 auto_dir 下所有自动备份文件，按修改时间降序（最新在前）。

    仅识别 AUTO_BACKUP_FILE_PREFIX 前缀 + .zip 后缀的文件，
    与手动备份区分。目录不存在返回空列表。
    """
    if not os.path.isdir(auto_dir):
        return []
    files = [
        f for f in os.listdir(auto_dir)
        if f.startswith(AUTO_BACKUP_FILE_PREFIX) and f.endswith('.zip')
    ]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(auto_dir, f)), reverse=True)
    return files
