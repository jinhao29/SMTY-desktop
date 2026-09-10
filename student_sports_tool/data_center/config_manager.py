# -*- coding: utf-8 -*-
"""管理层：数据中心配置读写。

职责：
- 管理续费预警阈值、未上课天数等可配置参数
- 管理数据中心通用配置（如默认档案目录记忆）
- 配置文件存储为 JSON，位于档案目录下 _data_center_config.json
"""
import os
import json
import tempfile
from file_lock import file_lock

CONFIG_FILE = '_data_center_config.json'

# 默认配置
DEFAULTS = {
    'renewal_threshold': 5,       # 续费预警阈值（剩余课时 <= 此值时提醒）
    'inactive_days': 14,          # 长期未上课天数阈值
    'last_archive_dir': '',       # 上次使用的档案目录
    # 优化4新增：手机备份同步目录（教练手机备份后通过数据线/WiFi 传到电脑的目录）
    # auto_sync 模块每分钟扫描此目录，发现新 .zip 自动恢复并托盘通知
    'phone_backup_sync_dir': '',
    # 优化4新增：已处理的备份 zip 文件名列表（避免重复恢复）
    # 超过 100 条时自动清理旧记录
    'synced_zip_history': [],
    # === v4 自动无感备份配置（自动备份调度器使用）===
    # auto_backup_enabled：是否启用自动备份（默认 True）
    # auto_backup_frequency：备份频率（daily=每日4:00 / weekly=每周一4:00 / manual=仅手动）
    # max_auto_backups：滚动备份保留份数（默认 5，超出删除最旧）
    # last_auto_backup_at：上次自动备份时间戳字符串（UI 状态栏展示用）
    'auto_backup_enabled': True,
    'auto_backup_frequency': 'daily',
    'max_auto_backups': 5,
    'last_auto_backup_at': '',
    # === v1.0.3 备份加密口令 ===
    # 手机端设置了「备份加密口令」后，备份包内的数据库会 AES-GCM 加密；
    # 桌面端需填入同一口令才能恢复。留空表示备份未加密（旧格式）。
    'backup_passphrase': '',
}


def _config_path(dir_path):
    """返回配置文件的完整路径。"""
    return os.path.join(dir_path, CONFIG_FILE) if dir_path else CONFIG_FILE


def load_config(dir_path=''):
    """Read config, fill missing keys with defaults. Returns dict."""
    cfg = dict(DEFAULTS)
    fpath = _config_path(dir_path)
    if os.path.exists(fpath):
        try:
            with file_lock(fpath, mode='r', timeout=3.0):
                with open(fpath, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        cfg.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(dir_path, cfg):
    """Save config to JSON file with atomic write + file lock.

    Atomic write strategy: write to temp file, then os.replace (atomic on Windows/POSIX).
    File lock prevents concurrent reads from seeing a half-written file.
    """
    if not dir_path:
        return
    os.makedirs(dir_path, exist_ok=True)
    fpath = _config_path(dir_path)
    try:
        with file_lock(fpath, timeout=3.0):
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, fpath)
            except OSError:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
    except OSError:
        pass


def update_config(dir_path, **kwargs):
    """增量更新配置项。"""
    cfg = load_config(dir_path)
    cfg.update(kwargs)
    save_config(dir_path, cfg)
    return cfg
