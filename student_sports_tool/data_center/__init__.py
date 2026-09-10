# -*- coding: utf-8 -*-
"""数据中心模块包：聚合数据备份、成长报告、续费提醒三大子功能。

包自举说明（重要）
------------------
本包内大量模块使用**扁平导入**（如 `import archive_manager`、`import lesson_manager`），
这些模块名指向本包目录与上级目录（`student_sports_tool/`）下的同名文件，而非独立 PyPI 包。

历史实现依赖主入口 `app.py` 手动把 `data_center/`、`training_tool/`、`student_profile/`
注入 `sys.path`。这导致两条路径行为不一致：

- 通过 `app.py` 启动：sys.path 已注入，扁平导入正常
- 通过包导入（pytest / 打包 / `import data_center.xxx`）：注入缺失，
  触发 `ModuleNotFoundError: No module named 'archive_manager'`

此处在包初始化时补齐路径注册，使两种入口行为一致。
幂等：路径已在 sys.path 时不重复插入；使用 append 而非 insert(0)，
避免本包目录抢占标准库/第三方包的同名模块解析优先级。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))      # .../data_center
_PARENT = os.path.dirname(_HERE)                        # .../student_sports_tool

# 本包目录（archive_manager / meta_index_store / sync_server 等）
# 父目录（lesson_manager / fee_manager / coach_manager 等顶层模块）
for _p in (_HERE, _PARENT):
    if _p not in sys.path:
        sys.path.append(_p)

del os, sys, _HERE, _PARENT, _p
