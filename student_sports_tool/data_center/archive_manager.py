# -*- coding: utf-8 -*-
"""管理层：档案目录扫描、zip 打包解包、文件占用检测。

职责：
- 扫描档案目录下所有学员文件（.xlsx，排除课时记录与临时文件）
- 将整个档案目录打包为带时间戳的 zip
- 从 zip 还原档案目录（含 Android 端 .db / export_meta.json / 签到照片）
- 检测文件是否被其他程序占用

并发安全：
- backup_directory 与 restore_from_zip 使用 portalocker 排他锁
  防止多端（手机/桌面）同时读写同一 ZIP 导致文件损坏
- 检测到文件被占用时安全等待 1 秒重试，超时抛出 LockTimeoutError
"""
import os
import sys
import shutil
import zipfile
import logging
from datetime import datetime

# 引入统一文件锁（位于父目录）
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
from file_lock import file_lock, with_retry


def scan_student_files(dir_path):
    """扫描档案目录，返回学员 Excel 文件列表。

    返回: [(文件名, 完整路径)]，排除课时记录与临时文件。
    """
    logging.info(f'开始扫描档案目录：{dir_path}')
    result = []
    if not os.path.isdir(dir_path):
        logging.warning(f'档案目录不存在：{dir_path}')
        return result
    for f in sorted(os.listdir(dir_path)):
        if not f.lower().endswith('.xlsx'):
            continue
        if f.startswith('~$') or f == '课时记录.xlsx':
            continue
        result.append((f, os.path.join(dir_path, f)))
    logging.info(f'扫描完成：找到 {len(result)} 个学员文件')
    return result


def is_file_locked(file_path):
    """检测文件是否被占用（尝试以追加模式打开）。"""
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, 'a'):
            pass
        return False
    except PermissionError:
        return True


def backup_directory(dir_path, target_zip_path):
    """将档案目录打包为 zip。

    参数:
        dir_path: 档案目录
        target_zip_path: 目标 zip 文件路径

    返回:
        (成功文件数, 跳过文件列表)

    并发安全：使用 portalocker 排他锁防止备份过程中文件被修改。
    """
    packed = 0
    skipped = []
    if not os.path.isdir(dir_path):
        return 0, skipped
    os.makedirs(os.path.dirname(target_zip_path) or '.', exist_ok=True)

    def _do_backup():
        with file_lock(target_zip_path, timeout=10.0):
            with zipfile.ZipFile(target_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for f in os.listdir(dir_path):
                    if not f.lower().endswith('.xlsx'):
                        continue
                    fp = os.path.join(dir_path, f)
                    if is_file_locked(fp):
                        skipped.append(f)
                        continue
                    # zip 内部统一使用 / 作为路径分隔符（跨平台兼容）
                    zf.write(fp, arcname=f.replace(os.sep, '/'))
                    packed_count[0] += 1

    packed_count = [0]
    with_retry(_do_backup, max_retries=3, retry_interval=1.0)
    return packed_count[0], skipped


def restore_from_zip(zip_path, target_dir, progress_cb=None):
    """从 zip 还原完整备份（学员 Excel + Android .db / export_meta.json / 签到照片）。

    遍历 zip 内全部文件，按 zip 内相对路径（arcname）落到 target_dir，保留目录结构。
    Android 端 .db / export_meta.json / 照片因此一并还原，不再仅限 .xlsx。

    参数:
        zip_path: 备份 zip 文件路径
        target_dir: 还原目标目录
        progress_cb: 可选回调 (message: str) -> None

    返回:
        还原文件数

    并发安全：使用 portalocker 排他锁防止手机端正在写入时桌面端读取损坏。
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f'备份文件不存在：{zip_path}')
    os.makedirs(target_dir, exist_ok=True)

    def _do_restore():
        with file_lock(zip_path, mode='r', timeout=10.0):
            count = 0
            skipped_locked = 0
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for name in zf.namelist():
                    # 跨平台路径归一化：zip 内部使用 /，Windows 上拼接前需 normpath
                    norm_name = os.path.normpath(name)
                    base = os.path.basename(norm_name)
                    # 跳过目录条目（zip 中目录名以 / 结尾）
                    if name.endswith('/') or not base:
                        continue
                    # 跳过 Office 临时锁文件
                    if base.startswith('~$'):
                        continue
                    # 用 arcname 相对路径落到 target_dir，保留子目录结构
                    target_path = os.path.normpath(os.path.join(target_dir, norm_name))
                    # 防 zip-slip：还原目标必须仍在 target_dir 内
                    if not (target_path == target_dir or target_path.startswith(target_dir + os.sep)):
                        if progress_cb:
                            progress_cb(f'跳过越界路径：{name}')
                        continue
                    if is_file_locked(target_path):
                        skipped_locked += 1
                        if progress_cb:
                            progress_cb(f'跳过被占用文件：{base}')
                        continue
                    try:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zf.open(name) as src, open(target_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                        count += 1
                    except OSError as e:
                        if progress_cb:
                            progress_cb(f'还原失败：{base}（{e}）')
            if progress_cb and skipped_locked:
                progress_cb(f'共跳过 {skipped_locked} 个被占用文件')
            return count

    return with_retry(_do_restore, max_retries=3, retry_interval=1.0)


def extract_android_assets(zip_path, target_dir, progress_cb=None):
    """从 Android 备份 zip 中提取 .db、export_meta.json 与签到照片。

    照片原样拷贝到 {target_dir}/photos/，保持目录结构。
    .db 与 export_meta.json 拷贝到 {target_dir}/_android/ 临时目录，
    由 android_backup_parser 解析后转换为桌面端 Excel。

    参数:
        zip_path: Android 备份 zip 路径
        target_dir: 桌面端档案目录
        progress_cb: 可选回调 (message: str) -> None

    返回:
        {'db_path': str|None, 'meta_path': str|None, 'photo_count': int}

    并发安全：使用 portalocker 共享锁防止 zip 文件被并发写入。
    """
    if not os.path.exists(zip_path):
        return {'db_path': None, 'meta_path': None, 'photo_count': 0}

    android_dir = os.path.join(target_dir, '_android')
    photo_dir = os.path.join(target_dir, 'photos')
    os.makedirs(android_dir, exist_ok=True)
    os.makedirs(photo_dir, exist_ok=True)

    # 照片扩展名（含加密后缀）
    photo_exts = ('.jpg', '.jpeg', '.png', '.jpg.enc', '.png.enc', '.dat')

    def _do_extract():
        with file_lock(zip_path, mode='r', timeout=10.0):
            db_path = None
            meta_path = None
            photo_count = 0
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for name in zf.namelist():
                    norm_name = os.path.normpath(name)
                    base = os.path.basename(norm_name)
                    if not base:
                        continue
                    lower = base.lower()

                    # Android 端数据库文件
                    # BackupManager 打包时条目名为 sports_coach_db / sports_coach_db-wal /
                    # sports_coach_db-shm（无 .db 后缀），同时兼容标准 .db 后缀。
                    # P0 修复：原逻辑只匹配 .db 后缀，导致无后缀的 sports_coach_db 被丢弃，
                    # 进而 _convert_android_to_excel 拿不到 db_path，双端数据无法打通。
                    is_android_db = (
                        (lower.endswith('.db') and not lower.startswith('sqlite_'))
                        or base in ('sports_coach_db', 'sports_coach_db-wal', 'sports_coach_db-shm')
                    )
                    if is_android_db:
                        out_path = os.path.join(android_dir, base)
                        try:
                            with zf.open(name) as src, open(out_path, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
                            # 仅主数据库文件记入 db_path（wal/shm 仅供 SQLite 恢复时配对）
                            if not base.endswith(('-wal', '-shm')):
                                db_path = out_path
                            if progress_cb:
                                progress_cb(f'已提取 Android 数据库：{base}')
                        except OSError:
                            pass
                        continue

                    # export_meta.json
                    if base == 'export_meta.json':
                        out_path = os.path.join(android_dir, base)
                        try:
                            with zf.open(name) as src, open(out_path, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
                            meta_path = out_path
                            if progress_cb:
                                progress_cb('已提取 Android 元数据索引：export_meta.json')
                        except OSError:
                            pass
                        continue

                    # 签到照片
                    if any(lower.endswith(ext) for ext in photo_exts):
                        rel_dir = os.path.dirname(norm_name)
                        # 去掉前导 photos/ 前缀避免重复嵌套
                        if rel_dir.lower().startswith('photos'):
                            rel_dir = rel_dir[len('photos'):].lstrip(os.sep)
                        # P0 修复（Zip Slip）：照片相对目录归一化后必须仍在 photo_dir 内，
                        # 防止 zip 条目内 "../" 把照片写到档案目录之外
                        out_dir = os.path.normpath(os.path.join(photo_dir, rel_dir)) if rel_dir else photo_dir
                        if not (out_dir == photo_dir or out_dir.startswith(photo_dir + os.sep)):
                            if progress_cb:
                                progress_cb(f'跳过越界照片路径：{name}')
                            continue
                        os.makedirs(out_dir, exist_ok=True)
                        out_path = os.path.join(out_dir, base)
                        try:
                            with zf.open(name) as src, open(out_path, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
                            photo_count += 1
                            if progress_cb and photo_count % 20 == 0:
                                progress_cb(f'已迁移 {photo_count} 张签到照片...')
                        except OSError:
                            continue

            if progress_cb and photo_count:
                progress_cb(f'签到照片迁移完成：共 {photo_count} 张')

            return {'db_path': db_path, 'meta_path': meta_path, 'photo_count': photo_count}

    return with_retry(_do_extract, max_retries=3, retry_interval=1.0)


def cleanup_android_assets(target_dir):
    """清理 _android 临时目录（解析完成后调用）。"""
    android_dir = os.path.join(target_dir, '_android')
    if os.path.isdir(android_dir):
        try:
            shutil.rmtree(android_dir)
        except OSError:
            pass


def make_backup_filename(prefix='学员档案备份'):
    """生成带时间戳的备份文件名。"""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'{prefix}_{ts}.zip'
