# -*- coding: utf-8 -*-
"""备份创建：手动备份 + 自动无感备份。"""
import os
import zipfile
import logging
from datetime import datetime

from archive_manager import backup_directory, make_backup_filename
import config_manager
from backup import AUTO_BACKUP_DIR_NAME, AUTO_BACKUP_FILE_PREFIX
from backup.backup_cleaner import _cleanup_old_auto_backups


def do_backup(dir_path, target_dir, progress_cb=None):
    """执行备份：打包档案目录为 zip。

    参数:
        dir_path: 档案目录
        target_dir: 备份 zip 存放目录
        progress_cb: 可选回调 (message: str) -> None

    返回: (zip_path, packed_count, skipped_files)
    """
    dir_path = os.path.normpath(dir_path)
    target_dir = os.path.normpath(target_dir)
    logging.info(f'开始备份：档案目录={dir_path}, 目标目录={target_dir}')
    if progress_cb:
        progress_cb('正在扫描档案目录...')
    zip_name = make_backup_filename()
    zip_path = os.path.join(target_dir, zip_name)
    if progress_cb:
        progress_cb(f'正在打包到 {zip_name}...')
    packed, skipped = backup_directory(dir_path, zip_path)
    if progress_cb:
        progress_cb(f'备份完成：{packed} 个文件' +
                    (f'，跳过 {len(skipped)} 个被占用文件' if skipped else ''))
    logging.info(f'备份完成：{zip_path}, 成功={packed}, 跳过={len(skipped)}')
    return zip_path, packed, skipped


def do_auto_backup(dir_path, progress_cb=None):
    """执行自动无感备份（v4 新增）。

    触发时机：
    - AutoBackupManager 每日凌晨 2:00 定时调用
    - do_restore 成功后立即调用（防止恢复数据覆盖意外）

    流程：
    1. 读取 config_manager 配置，校验 auto_backup_enabled
    2. 在主程序目录下创建 AutoBackups/ 子目录
    3. 生成文件名 AutoBackup_YYYYMMDD_HHmmss.zip
    4. 调用 archive_manager.backup_directory 执行打包
    5. 清理旧备份，仅保留 max_auto_backups 份
    6. 更新 last_auto_backup_at 配置项（状态栏展示用）

    静默原则：异常仅记录到日志，不弹窗，不抛异常。

    返回: (success: bool, zip_path: str or None, message: str)
    """
    dir_path = os.path.normpath(dir_path)
    if not dir_path or not os.path.isdir(dir_path):
        msg = '档案目录无效，跳过自动备份'
        if progress_cb:
            progress_cb(msg)
        return False, None, msg

    cfg = config_manager.load_config('')
    if not cfg.get('auto_backup_enabled', True):
        msg = '自动备份已关闭，跳过本次触发'
        if progress_cb:
            progress_cb(msg)
        return False, None, msg

    max_keep = int(cfg.get('max_auto_backups', 10))

    # 自动备份目录：主程序目录（cwd 上溯一层）下的 AutoBackups/
    # 与 config_manager 同级，便于清理与状态栏定位
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    auto_dir = os.path.join(base_dir, AUTO_BACKUP_DIR_NAME)
    try:
        os.makedirs(auto_dir, exist_ok=True)
    except OSError as e:
        msg = f'创建自动备份目录失败：{e}'
        if progress_cb:
            progress_cb(msg)
        return False, None, msg

    # 生成带时间戳的文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_name = f'{AUTO_BACKUP_FILE_PREFIX}_{timestamp}.zip'
    zip_path = os.path.join(auto_dir, zip_name)

    if progress_cb:
        progress_cb(f'正在自动备份到 {zip_name}...')

    try:
        packed, skipped = backup_directory(dir_path, zip_path)
    except (FileNotFoundError, PermissionError, zipfile.BadZipFile) as e:
        logging.error(f'自动备份失败：目录={dir_path}，目标={zip_path}，原因={e}', exc_info=True)
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except (FileNotFoundError, PermissionError) as e2:
            logging.error(f'删除不完整备份失败：{zip_path}，原因={e2}', exc_info=True)
        msg = f'自动备份失败：{e}'
        if progress_cb:
            progress_cb(msg)
        return False, None, msg

    # 清理旧备份，仅保留 max_keep 份
    deleted = _cleanup_old_auto_backups(auto_dir, max_keep)

    # 更新配置中的上次备份时间戳
    last_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    try:
        config_manager.update_config('', last_auto_backup_at=last_at)
    except (FileNotFoundError, PermissionError) as e:
        logging.error(f'更新自动备份时间戳配置失败：{e}', exc_info=True)

    msg = f'自动备份成功：{packed} 个文件' + \
          (f'，跳过 {len(skipped)} 个被占用文件' if skipped else '') + \
          (f'，已清理 {deleted} 份旧备份' if deleted > 0 else '')
    if progress_cb:
        progress_cb(msg)
    return True, zip_path, msg
