# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包规范文件（重建版，覆盖全模块）。

入口：app.py（统一主窗口，Tab 容器）
覆盖模块：
  - 根目录：main / theme / ui_components / excel_builder / scorer / standards
            summary_builder / lesson_manager / lesson_window
  - 根目录新增：modern_dialog（统一现代化弹窗）/ base_components（视觉令牌 + 行操作列）
  - student_profile：profile_screen / profile_storage / profile_manager / bmi_processor
  - data_center：archive_manager / backup_coordinator / backup_panel / data_center_window
                 report_coordinator / report_exporter / report_panel / report_templates
                 chart_renderer / config_manager / data_exporter / followup_manager
                 renewal_coordinator / renewal_panel / renewal_processor
                 android_backup_parser / photo_bridge / worker_pool / filename_sanitizer
                 conflict_detector / data_conflict_resolver （v5 优化4：数据冲突解决）
                 schedule_lesson_analyzer / schedule_achievement_panel （v5 优化5：训练达成率）
                 db_snapshot_manager / db_snapshot_dialog （v5 优化6：数据库时光机）
                 meta_index_store （SQLite 索引存储）
  - training_tool：main / exercise_library / task_model / exporter / lesson_plan_loader
                   feedback_storage / summary_processor / stage_summary_screen
                   template_library_window / template_manager / template_recommender

数据资源：
  - training_tool/blocks_config.json
  - training_tool/demo_weekly_plan_4-6岁.docx
  - training_tool/demo_weekly_plan_4-6岁.xlsx

依赖：PySide6 / openpyxl / python-docx / Pillow / sqlite3(标准库)
"""

import os
import shutil

block_cipher = None

# UPX 探测：本机已安装 upx 时启用压缩并指向其目录，未安装则留空（PyInstaller 自动跳过）
UPX_EXE = shutil.which('upx')
UPX_DIR = os.path.dirname(UPX_EXE) if UPX_EXE else None

# 数据资源（非 .py 文件）：(源相对路径, 目标目录)
datas = [
    # 版本真源：运行时 updater.get_current_version 从 exe 同目录读取
    ('VERSION', '.'),
    ('training_tool\\blocks_config.json', 'training_tool'),
    ('training_tool\\demo_weekly_plan_4-6岁.docx', 'training_tool'),
    ('training_tool\\demo_weekly_plan_4-6岁.xlsx', 'training_tool'),
    # 整包目录：确保打包产物中物理存在这些子包，供运行时 os.path.dirname(__file__) 定位
    ('student_profile', 'student_profile'),
    ('data_center', 'data_center'),
    ('theme.py', '.'),
    # 动态加载入口（app.py 用 spec_from_file_location 加载，PyInstaller 无法静态收集，
    # 必须物理打包，否则 exe 启动即 FileNotFoundError）
    ('main.py', '.'),
    ('training_tool\\main.py', 'training_tool'),
    ('training_tool\\cards.py', 'training_tool'),
    ('training_tool\\exercise_library.py', 'training_tool'),
    ('training_tool\\exporter.py', 'training_tool'),
    ('training_tool\\feedback_storage.py', 'training_tool'),
    ('training_tool\\lan_plan_sender.py', 'training_tool'),
    ('training_tool\\layouts.py', 'training_tool'),
    ('training_tool\\lesson_plan_loader.py', 'training_tool'),
    ('training_tool\\plan_coordinator.py', 'training_tool'),
    ('training_tool\\stage_summary_screen.py', 'training_tool'),
    ('training_tool\\styles.py', 'training_tool'),
    ('training_tool\\summary_processor.py', 'training_tool'),
    ('training_tool\\task_model.py', 'training_tool'),
    ('training_tool\\template_library_window.py', 'training_tool'),
    ('training_tool\\template_manager.py', 'training_tool'),
    ('training_tool\\template_recommender.py', 'training_tool'),
    ('training_tool\\test_export.py', 'training_tool'),
    ('training_tool\\ui_plan_screen.py', 'training_tool'),
    ('training_tool\\ui_template_screen.py', 'training_tool'),
]

# 隐式导入（PyInstaller 无法静态推断的模块）
hiddenimports = [
    # 第三方库
    'openpyxl',
    'openpyxl.cell',
    'openpyxl.styles',
    'openpyxl.utils',
    'openpyxl.workbook',
    'openpyxl.worksheet',
    'docx',
    'docx.templates',
    'docx.templates.default-docx-template',
    'PIL',
    'PIL._imaging',
    'PySide6.QtCharts',
    'PySide6.QtWidgets',
    'PySide6.QtGui',
    'PySide6.QtCore',
    'PySide6.QtPrintSupport',  # 第3轮新增：QPrinter 支持
    # 优化2新增：跨进程文件锁
    'portalocker',
    # 优化6新增：HTTP 客户端
    'requests',
    'certifi',
    'charset_normalizer',
    'urllib3',
    'idna',
    # 标准库（显式声明，避免某些精简环境缺失）
    'sqlite3',
    'json',
    'zipfile',
    'shutil',
    'tempfile',
    'importlib',
    # v25 新增：lan_plan_sender 使用的标准库 HTTP/Socket 模块
    'http.server',
    'socket',
    'socketserver',
    'threading',
    # 根目录模块
    'theme',
    'main',                  # app.py 通过 _load_module 动态加载，PyInstaller 无法静态推断
    'main_window',            # 主窗口容器，被 app.py / home_page 间接引用
    'home_page',              # app.py 静态导入，保险起见显式声明
    'side_navigation',        # app.py 静态导入，保险起见显式声明
    'stat_components',        # 首页统计卡片组件
    'nav_components',         # 侧边栏导航组件
    'chart_components',        # 图表组件（被 home_page / data_center 引用）
    'ui_components',
    'base_components',
    'modern_dialog',   # 统一现代化弹窗（全项目 QMessageBox 迁移目标）
    'excel_builder',
    'scorer',
    'standards',
    'summary_builder',
    'lesson_manager',
    'lesson_window',
    'filename_sanitizer',
    'archive_controller',
    'worker_pool',
    'file_lock',  # 优化2新增：跨进程文件锁工具
    'updater',    # 优化6新增：GitHub 自动更新核心模块
    'update_worker',  # 优化6新增：QThread 后台下载 Worker
    'update_dialog',  # 优化6新增：更新对话框 UI
    'auto_sync',  # 优化4新增：QTimer 自动同步模块
    'tray_notifier',  # 优化4新增：托盘通知模块
    # student_profile 子包
    'student_profile',
    'student_profile.profile_screen',
    'student_profile.profile_storage',
    'student_profile.profile_manager',
    'student_profile.bmi_processor',
    'student_profile.student_table_model',  # 优化5新增：QAbstractTableModel 表格模型
    'student_profile.profile_dialogs',
    'student_profile.profile_handlers',
    'student_profile.growth_tools_dialog',  # 成长工具弹窗（函数级懒导入，需显式声明）
    'growth_processor',                     # 身高预测/TDEE/膳食模板 纯算法层
    # data_center 子包
    'data_center',
    'data_center.archive_manager',
    'data_center.backup_coordinator',
    'data_center.sync_server',      # 双端同步服务（内嵌 HTTP 服务）
    'data_center.sync_panel',       # 数据中心「双端同步」面板
    'data_center.sync_exporter',    # PC→手机 学员同步包生成
    'data_center.firewall_helper',  # LAN 防火墙自动放行（Wi-Fi 互通）
    'data_center.sync_service',     # 全局同步服务管理器（主程序自动启动）
    'data_center.usb_helper',       # USB adb reverse 自动连接
    'backup_validator',             # 备份 zip 安全校验（auto_sync/sync_server 共用）
    # backup 子包（P2 超大文件拆分：备份创建/恢复/列表/清理）
    'data_center.backup',
    'data_center.backup.backup_creator',
    'data_center.backup.backup_restorer',
    'data_center.backup.backup_cleaner',
    'data_center.backup.backup_list_manager',
    'data_center.backup_panel',
    'data_center.auto_backup_manager',
    'data_center.data_center_window',
    'data_center.report_coordinator',
    'data_center.report_exporter',
    'data_center.report_panel',
    'data_center.report_templates',
    'data_center.chart_renderer',
    'data_center.config_manager',
    'data_center.data_exporter',
    'data_center.followup_manager',
    'data_center.renewal_coordinator',
    'data_center.renewal_panel',
    'data_center.renewal_processor',
    'data_center.android_backup_parser',
    'data_center.photo_bridge',
    'data_center.android_db_inspector',  # 遗漏模块：Android 数据库检查器
    # v5 优化4 新增：数据冲突检测与解决
    'data_center.conflict_detector',
    'data_center.data_conflict_resolver',
    # v5 优化5 新增：训练达成率偏差分析
    'data_center.schedule_lesson_analyzer',
    'data_center.schedule_achievement_panel',
    # v5 优化6 新增：数据库时光机快照
    'data_center.db_snapshot_manager',
    'data_center.db_snapshot_dialog',
    # 索引存储（meta_index_store）
    'data_center.meta_index_store',
    # training_tool 子包
    'training_tool',
    'training_tool.main',
    'training_tool.ui_plan_screen',       # 优化3新增：周计划 UI
    'training_tool.ui_template_screen',   # 优化3新增：模板库 UI
    'training_tool.plan_coordinator',     # 优化3新增：训练计划编排
    'training_tool.exercise_library',
    'training_tool.task_model',
    'training_tool.exporter',
    'training_tool.lesson_plan_loader',
    'training_tool.feedback_storage',
    'training_tool.summary_processor',
    'training_tool.stage_summary_screen',
    'training_tool.template_library_window',
    'training_tool.template_manager',
    'training_tool.template_recommender',
    'training_tool.lan_plan_sender',      # v25 新增：局域网截图发送器（HTTP + UDP）
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # P1 修复：显式排除历史实验残留的大包（torch/transformers/yolos/onnxruntime/sklearn/polars/pyarrow 等），
    # 避免 PyInstaller 从环境中误收集，减小发布包体积（约 1GB+ 降至数百 MB）
    excludes=[
        'torch', 'torchvision', 'transformers', 'yolos', 'onnxruntime',
        'sklearn', 'scipy', 'polars', 'pyarrow', 'pandas',
        'matplotlib', 'numpy', 'cv2', 'mediapipe',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='上门体育教学管理工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # 已启用；本机未安装 UPX 时自动跳过压缩，不影响产物
    upx_dir=UPX_DIR,  # 自动探测，未安装则 None（PyInstaller 跳过）
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_dir=UPX_DIR,
    upx_exclude=[
        # 关键二进制不压缩，避免运行时加载失败
        '*.dll',             # 动态库（VC 运行时等）
        'vcruntime140.dll',  # VC 运行时
        'vcruntime140_1.dll',
        'msvcp140.dll',
    ],
    name='上门体育教学管理工具',
)
