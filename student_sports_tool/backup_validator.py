# -*- coding: utf-8 -*-
"""安全层：手机备份 zip 内容校验（无 GUI 依赖，供主程序与同步服务共用）。

校验规则：
1. 拒绝 zip 条目路径穿越（绝对路径 / 包含 ".."）
2. 拒绝可执行 / 脚本文件
3. 拒绝空 zip

调用方：auto_sync.AutoSyncManager（目录扫描自动恢复）、data_center.sync_server（LAN 接收合并）。
"""
import os
import zipfile

# 危险扩展名：任何情况下拒绝自动恢复（可执行 / 脚本 / 快捷方式）
BLOCKED_EXTS = (
    '.exe', '.dll', '.com', '.scr', '.pif', '.msi', '.ps1', '.bat', '.cmd',
    '.vbs', '.js', '.jse', '.wsf', '.wsh', '.jar', '.lnk', '.sh', '.py', '.pyc',
)


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
