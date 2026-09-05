# -*- coding: utf-8 -*-
"""安全层：手机备份 zip 内容校验（无 GUI 依赖，供主程序与同步服务共用）。

校验规则：
1. 拒绝 zip 条目路径穿越（绝对路径 / 包含 ".."）
2. 拒绝可执行 / 脚本文件
3. 拒绝空 zip
4. 安全锁：拒绝「零内容备份」合并进非空档案目录（防清空，v23.8）

调用方：auto_sync.AutoSyncManager（目录扫描自动恢复）、data_center.sync_server（LAN 接收合并）。
"""
import json
import os
import zipfile

# 危险扩展名：任何情况下拒绝自动恢复（可执行 / 脚本 / 快捷方式）
BLOCKED_EXTS = (
    '.exe', '.dll', '.com', '.scr', '.pif', '.msi', '.ps1', '.bat', '.cmd',
    '.vbs', '.js', '.jse', '.wsf', '.wsh', '.jar', '.lnk', '.sh', '.py', '.pyc',
)

# 主数据文件（不是学员档案，安全锁清点学员数时排除）
_MASTER_XLSX = {'学员档案.xlsx', '教练档案.xlsx', '课时记录.xlsx', '收费记录.xlsx'}


def validate_backup_zip(zip_path: str):
    """恢复前内容安全校验（默认拒绝可疑备份）。

    返回 (ok: bool, reason: str)。ok=False 时 reason 为拒绝原因。
    """
    if not os.path.exists(zip_path):
        return False, f'备份文件不存在：{zip_path}'
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            if not names:
                return False, '备份 zip 为空'
            for name in names:
                # 路径穿越：绝对路径或归一化后含 ".." 段
                norm = os.path.normpath(name)
                if os.path.isabs(norm):
                    return False, f'备份包含绝对路径条目：{name}'
                parts = norm.replace('\\', '/').split('/')
                if '..' in parts:
                    return False, f'备份包含路径穿越条目：{name}'
                base = os.path.basename(norm)
                if not base or name.endswith('/'):
                    continue
                if base.lower().endswith(BLOCKED_EXTS):
                    return False, f'备份包含可执行文件：{base}'
            return True, ''
    except zipfile.BadZipFile as e:
        return False, f'备份不是有效的 zip：{e}'


def count_backup_entities(zip_path: str):
    """统计备份内的学员/课时/课时包数量（读 export_meta.json）。

    返回 dict {'students': int, 'lessons': int, 'packages': int}；
    meta 缺失或损坏时返回 None（无法判断，调用方自行决定放行）。
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'export_meta.json' not in zf.namelist():
                return None
            raw = zf.read('export_meta.json').decode('utf-8')
        meta = json.loads(raw)
        return {
            'students': len(meta.get('students') or []),
            'lessons': len(meta.get('lessons') or []),
            'packages': len(meta.get('packages') or []),
        }
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, OSError, KeyError):
        return None


def reject_wiped_backup(zip_path: str, archive_dir: str):
    """安全锁：零内容备份（0 学员 / 0 课时 / 0 课时包）不得合并进非空档案目录。

    场景：手机重装/清数据后自动同步把空库备份反复推给 PC——虽然合并本身
    不删除 PC 数据，但教练无法分辨「备份是空的」还是「同步坏了」，且空备份
    会覆盖 恢复前自动备份 链路的判断。宁可拒绝并大声提示，人工确认后
    （如确需重置）可临时改用手动恢复。

    返回 (ok: bool, reason: str)。ok=False 时 reason 为拒绝原因。
    """
    counts = count_backup_entities(zip_path)
    if counts is None:
        return True, ''  # 无 meta（旧版备份/纯 .db）：无法判断，放行交给后续合并
    if any(counts.values()):
        return True, ''
    students = 0
    if archive_dir and os.path.isdir(archive_dir):
        students = sum(
            1 for f in os.listdir(archive_dir)
            if f.lower().endswith('.xlsx') and not f.startswith('~$')
            and f not in _MASTER_XLSX)
    if students > 0:
        return False, ('安全锁：备份内容为空（0 学员 / 0 课时 / 0 课时包），'
                       f'已拒绝合并进含 {students} 名学员的档案目录。'
                       '若确为重置手机后的正常备份，请人工到数据中心确认处理。')
    return True, ''
