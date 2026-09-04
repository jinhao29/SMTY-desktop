# -*- coding: utf-8 -*-
"""备份子包：备份创建 / 恢复 / 列表管理 / 清理。

拆分自 backup_coordinator.py（P2 超大文件拆分），
backup_coordinator.py 保留为协调入口，对外接口不变。
"""

# 自动备份存放子目录名（位于主程序目录下）
AUTO_BACKUP_DIR_NAME = 'AutoBackups'

# 自动备份文件名前缀（与手动备份区分，便于清理识别）
AUTO_BACKUP_FILE_PREFIX = 'AutoBackup'
