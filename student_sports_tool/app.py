# -*- coding: utf-8 -*-
"""统一应用入口：侧边栏 + 浅色珊瑚橙主题（与 Android 端视觉统一）。

启动方式：python app.py
启动后通过左侧侧边栏切换右侧主内容：
  - 首页（欢迎 + 快捷入口）
  - 学员档案（基础信息 + BMI + 续费预警）
  - 体测档案与课时管理（测评录入 + 课时管理）
  - 训练任务编排（单次训练单 / 周计划表，导出 Excel/Word）
  - 数据中心（备份 / 成长报告 / 续费预警）

架构说明：
- 协调层：本模块组合各业务窗口，通过 QStackedWidget 切换页面
- UI 层：SideNav（侧边导航）+ HomePage（首页）+ 各业务窗口的 centralWidget
- 不改动两个现有 main.py 的内部逻辑，仅通过 takeCentralWidget() 嵌入 QStackedWidget
- 两个子 MainWindow 实例保留为成员，确保其信号槽与状态正常工作
- 共用浅色珊瑚橙主题（背景 #F5F7FA / 卡片 #FFFFFF / 主色 #FF6B47）
"""
import modern_dialog as dialog
import os
import time
import sys
import logging
import importlib.util
from logging.handlers import RotatingFileHandler


def _get_user_data_dir():
    """返回用户数据目录（日志等可写位置）。

    PyInstaller 冻结后当前工作目录不确定，日志/索引必须写入用户目录，
    避免写到 exe 目录或临时目录导致不可写 / 数据丢失。
    """
    user_dir = os.path.join(os.path.expanduser('~'), '.shangmentiyu')
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[RotatingFileHandler(
        os.path.join(_get_user_data_dir(), 'app.log'),
        maxBytes=10_000_000, backupCount=3
    )]
)
sys.excepthook = lambda type, value, traceback: logging.critical(
    "Uncaught exception", exc_info=(type, value, traceback)
)


def _get_base_dir():
    """获取基础目录：打包后用 _MEIPASS 或 exe 目录，源码运行用源码目录。"""
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass and os.path.isdir(os.path.join(meipass, 'training_tool')):
            return meipass
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


HERE = _get_base_dir()
TRAINING_DIR = os.path.join(HERE, 'training_tool')
DATA_CENTER_DIR = os.path.join(HERE, 'data_center')
PROFILE_DIR = os.path.join(HERE, 'student_profile')

# 让 training_tool / data_center / student_profile 内的模块可被顶层导入
for _d in (TRAINING_DIR, DATA_CENTER_DIR, PROFILE_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)


def _load_module(mod_name, file_path):
    """按文件路径加载模块，避免两个 main.py 同名冲突。"""
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 加载体测档案主程序（当前目录 main.py）
archive_mod = _load_module('archive_main', os.path.join(HERE, 'main.py'))
# 加载训练编排主程序（training_tool/main.py）
training_mod = _load_module('training_main', os.path.join(TRAINING_DIR, 'main.py'))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QSystemTrayIcon, QMessageBox, QLineEdit, QLabel, QSizePolicy,
    QPushButton
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from theme import LIGHT_QSS
from side_navigation import SideNav
from home_page import HomePage
from base_components import IconBox

# 优化4新增：托盘通知 + 自动同步
import tray_notifier
from auto_sync import AutoSyncManager
# 优化6新增：GitHub 自动更新
from update_dialog import check_update_on_startup

# 全局浅色珊瑚橙主题（与 Android 端视觉统一）
GLOBAL_QSS = LIGHT_QSS

# 优化6新增：GitHub 仓库全名（2026-09-09 接线：jinhao29/SMTY-desktop）
# ⚠️ 生效前提：该仓库需能匿名访问 releases（仓库转 public），或已存在带 zip+sha256 的 Release；
# 当前仓库为 private 且尚无 Release 时，检查会返回"无法获取版本信息"，属预期行为
UPDATE_REPO = 'jinhao29/SMTY-desktop'

# === 页面索引常量（与 SideNav 菜单项顺序严格对应） ===
PAGE_HOME = 0
PAGE_PROFILE = 1
PAGE_COACH = 2
PAGE_ARCHIVE = 3
PAGE_TRAINING = 4
PAGE_DATA_CENTER = 5
PAGE_FINANCE = 6
# 详情页（不在侧边栏菜单中，仅由表格行点击进入）
PAGE_STUDENT_DETAIL = 7
PAGE_COACH_DETAIL = 8


class App(QMainWindow):
    """统一主窗口：左侧 SideNav + 右侧 QStackedWidget。"""

    # v23.11：同步服务线程回调 → UI 线程桥（手机备份合并成功等）
    syncMergeOk = Signal(str)

    def __init__(self, mode: str = 'coaching'):
        super().__init__()
        # v23.12：工作模式（'coaching' 上门体育 / 'club' 俱乐部）。
        # 俱乐部模式 = 独立档案目录（物理隔离），业务层零改动。
        self.mode = mode
        self.setWindowTitle('俱乐部管理平台' if mode == 'club' else '上门体育教学管理平台')
        # 根据屏幕可用尺寸自适应设置窗口初始大小
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            init_w = min(1280, avail.width() - 40)
            init_h = min(860, avail.height() - 20)
            self.resize(init_w, init_h)
            self.setMinimumSize(min(1024, avail.width() - 40), min(600, avail.height() - 20))
        else:
            self.resize(1280, 860)
            self.setMinimumSize(1024, 600)

        # === 主容器：左右分栏 ===
        # v24 裸声明 setStyleSheet('background-color:...') 会下压覆盖后代按钮的 QSS 背景
        # （#primary 按钮曾因此隐形），背景统一交给 theme.LIGHT_QSS 的全局 QWidget 规则
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # === 左侧导航栏 ===
        # 菜单项顺序与 QStackedWidget 页面索引严格对应（第三项为导航图标类型）
        menu_items = [
            ('首页', PAGE_HOME, IconBox.HOME),
            ('学员档案', PAGE_PROFILE, IconBox.USER),
            ('教练管理', PAGE_COACH, IconBox.WHISTLE),
            ('体测档案与课时', PAGE_ARCHIVE, IconBox.CHART_BAR),
            ('训练任务编排', PAGE_TRAINING, IconBox.DUMBBELL),
            ('财务管理', PAGE_FINANCE, IconBox.CHART_LINE),
            ('数据中心', PAGE_DATA_CENTER, IconBox.ARCHIVE),
        ]
        self.side_nav = SideNav(
            menu_items,
            title='俱乐部' if mode == 'club' else '上门体育')
        self.side_nav.navChanged.connect(self._on_page_changed)
        self.side_nav.searchSubmitted.connect(self._on_global_search)
        self.side_nav.helpRequested.connect(self._on_help)
        self.side_nav.logoutRequested.connect(self._on_logout)
        root.addWidget(self.side_nav)

        # === 右侧：顶部栏 + QStackedWidget ===
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        # 顶部栏：全局搜索 + 用户信息
        self._build_top_bar(right_lay)

        # QStackedWidget：业务页面切换
        self.stack = QStackedWidget()
        self.stack.setStyleSheet('QStackedWidget { background-color: #FFFFFF; border: none; }')
        right_lay.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        # === 创建各业务页面并加入 QStackedWidget ===
        # 注意：archive_win 必须先创建，因为其他页面依赖 archive_dir_getter
        # v23.12：俱乐部模式传入独立档案目录（数据物理隔离）
        if mode == 'club':
            from mode_selector import ensure_club_dir
            self.archive_win = archive_mod.MainWindow(initial_dir=ensure_club_dir())
        else:
            self.archive_win = archive_mod.MainWindow()
        archive_widget = self.archive_win.takeCentralWidget()

        # Page 0：首页（概览数据直接读档案目录，不再依赖占位）
        self.home_page = HomePage(
            coach_name='教练',
            archive_dir_getter=lambda: self.archive_win.le_dir.text().strip(),
        )
        self.home_page.quickNav.connect(self._on_quick_nav)
        self.home_page.addStudentRequested.connect(self._on_add_student)
        self.stack.addWidget(self.home_page)

        # Page 1：学员档案
        from profile_screen import ProfileScreen
        self.profile_screen = ProfileScreen(
            archive_dir_getter=lambda: self.archive_win.le_dir.text().strip()
        )
        self.stack.addWidget(self.profile_screen)

        # Page 2：教练管理（教练档案.xlsx，软删除离职/恢复）
        from coach_screen import CoachScreen
        self.coach_screen = CoachScreen(
            archive_dir_getter=lambda: self.archive_win.le_dir.text().strip()
        )
        self.stack.addWidget(self.coach_screen)

        # Page 3：体测档案与课时管理
        self.stack.addWidget(archive_widget)

        # Page 4：训练任务编排
        self.training_win = training_mod.MainWindow()
        training_widget = self.training_win.takeCentralWidget()
        self.stack.addWidget(training_widget)

        # Page 5：数据中心
        from data_center_window import DataCenterWindow
        self.data_center = DataCenterWindow()
        self.data_center.set_archive_dir(self.archive_win.get_current_directory())
        # 训练工具的模板库弱项推荐也需要档案目录
        self.training_win.set_archive_dir_getter(self.data_center.get_current_directory)
        self.stack.addWidget(self.data_center)

        # Page 6：财务管理（记账）——必须在数据中心之后 addWidget（stack 按顺序索引）
        from finance_page import FinancePage
        self.finance_page = FinancePage()
        self.finance_page.set_archive_dir(self.archive_win.get_current_directory())
        self.stack.addWidget(self.finance_page)

        # Page 7/8：学员 / 教练个人详情页（表格行点击进入，不在侧边栏）
        from detail_page import StudentDetailPage, CoachDetailPage
        self.student_detail = StudentDetailPage(
            archive_dir_getter=lambda: self.archive_win.le_dir.text().strip()
        )
        self.student_detail.backRequested.connect(
            lambda: self._back_from_detail(PAGE_PROFILE))
        self.stack.addWidget(self.student_detail)

        self.coach_detail = CoachDetailPage(
            archive_dir_getter=lambda: self.archive_win.le_dir.text().strip()
        )
        self.coach_detail.backRequested.connect(
            lambda: self._back_from_detail(PAGE_COACH))
        self.stack.addWidget(self.coach_detail)

        # 表格行点击 → 详情页
        self.profile_screen.studentActivated.connect(self.open_student_detail)
        self.coach_screen.coachActivated.connect(self.open_coach_detail)

        # 默认选中首页
        self.side_nav.select(PAGE_HOME)
        self.stack.setCurrentIndex(PAGE_HOME)
        # 启动时初始化「学员档案」菜单项的续费预警徽标（轻量读取，失败静默）
        self._refresh_nav_badge()

        # 优化4新增：托盘通知与自动同步管理器
        self._tray = None
        self._sync_mgr = None

        # === v23.5 双端同步：随主程序自动开启同步服务（手机/USB 即插即连）===
        # - config sync_auto_start 默认 True；数据中心「双端同步」面板可启停
        # - 含心跳广播（Wi-Fi 自动发现）+ USB adb reverse 自动连接 + 防火墙自动放行
        try:
            from data_center.sync_service import get_service
            from data_center import config_manager as _cm
            _dir = self.archive_win.get_current_directory()
            _cfg = _cm.load_config(_dir)
            if _cfg.get('sync_auto_start', True):
                _svc = get_service()
                _svc.add_log_callback(lambda line: logging.info(line))
                # v23.11：手机合并成功 → 跨线程信号 → 顶栏「● 同步完成」+ 刷新页面
                # _emit_status 回调签名是 (kind, message)，信号只带 message
                _svc.add_status_callback(
                    lambda kind, msg: self.syncMergeOk.emit(msg))
                self.syncMergeOk.connect(self._on_merge_ok)
                _svc.start(
                    port=int(_cfg.get('sync_port') or 8765),
                    token=str(_cfg.get('sync_token') or ''),
                    archive_dir=_dir,
                )
        except Exception:
            logging.exception('自动启动同步服务失败')

    def _build_top_bar(self, parent_layout):
        """构建右侧顶部栏：同步状态 + 用户信息（全局搜索已移入侧边栏并接通过滤）。"""
        top = QWidget()
        top.setFixedHeight(56)
        top.setObjectName('topBar')  # 裸声明会下压后代按钮 QSS，必须 objectName 限定
        top.setStyleSheet(
            'QWidget#topBar { background-color: #FFFFFF; '
            'border-bottom: 1px solid #E5E5E5; }'
        )
        lay = QHBoxLayout(top)
        lay.setContentsMargins(24, 8, 24, 8)
        lay.setSpacing(12)

        # 页面标题随导航切换（替代原占位搜索框的信息价值）
        self.lbl_page_title = QLabel('首页')
        self.lbl_page_title.setStyleSheet('''
            color: #1A1A1A;
            font-size: 16px;
            font-weight: 700;
            background: transparent;
        ''')
        lay.addWidget(self.lbl_page_title)

        lay.addStretch()

        # 同步状态指示器（由 AutoSyncManager.syncState 驱动）
        self.lbl_sync = QLabel('●  同步待命')
        self.lbl_sync.setStyleSheet('''
            color: #9B9B9B;
            font-size: 12px;
            font-weight: 500;
            background: transparent;
            padding: 0 8px;
        ''')
        lay.addWidget(self.lbl_sync)

        # v23.6：手机在线指示（轮询 config sync_devices 的 last_seen，5 分钟内算在线）
        self.lbl_devices = QLabel('○  手机未连接')
        self.lbl_devices.setStyleSheet('''
            color: #9B9B9B;
            font-size: 12px;
            font-weight: 500;
            background: transparent;
            padding: 0 8px;
        ''')
        lay.addWidget(self.lbl_devices)

        # v23.10：PC 主动同步按钮——UDP 广播喊手机立即双向对齐（后台静默）
        self.btn_sync_now = QPushButton('⟳  同步手机')
        self.btn_sync_now.setCursor(Qt.PointingHandCursor)
        self.btn_sync_now.setStyleSheet('''
            QPushButton {
                color: #6B6B6B; font-size: 12px; font-weight: 500;
                background: transparent; border: 1px solid transparent;
                border-radius: 4px; padding: 2px 10px;
            }
            QPushButton:hover { color: #FF6B47; border-color: #FF6B47; }
        ''')
        self.btn_sync_now.clicked.connect(self._manual_sync_now)
        lay.addWidget(self.btn_sync_now)
        self._device_timer = QTimer(self)
        self._device_timer.timeout.connect(self._refresh_device_indicator)
        self._device_timer.start(15_000)  # v23.10：30s→15s，业务请求即在线后更快亮灯
        QTimer.singleShot(3_000, self._refresh_device_indicator)

        # 用户信息
        user = QLabel('●  教练')
        user.setStyleSheet('''
            color: #6B6B6B;
            font-size: 13px;
            font-weight: 500;
            background: transparent;
            padding: 0 8px;
        ''')
        lay.addWidget(user)

        parent_layout.addWidget(top)

    def _manual_sync_now(self):
        """v23.10：PC 主动同步——双通道：
        ① UDP 广播 desktop_data_changed（Wi-Fi 场景即时生效）；
        ② touch 信号文件计入 /sync/version（USB/蜂窝场景由手机在线探测轮询发现）。
        手机端同步完成后 Toast 反馈；PC 端显示广播是否发出。"""
        try:
            from data_center.sync_beacon import notify_data_changed
            sent = notify_data_changed()
            # 信号文件：version 跳变，USB/蜂窝下手机探测循环 10s 内发现
            archive_dir = self.archive_win.get_current_directory()
            signal_path = os.path.join(archive_dir, '.cache', '.sync_signal')
            os.makedirs(os.path.dirname(signal_path), exist_ok=True)
            with open(signal_path, 'w', encoding='utf-8') as f:
                f.write(str(time.time()))
            if sent:
                self.lbl_sync.setText('●  已广播，手机收到后自动同步')
            else:
                self.lbl_sync.setText('●  已记录同步指令（USB 模式，手机稍后自动拉取）')
        except Exception as e:
            self.lbl_sync.setText('○  通知失败：%s' % (e or '未知错误'))
        QTimer.singleShot(6_000, lambda: self.lbl_sync.setText('●  同步待命'))

    def _refresh_device_indicator(self):
        """v23.6：刷新顶栏「手机在线」指示（config sync_devices 最近回执 5 分钟内算在线）。"""
        try:
            from data_center import config_manager as _cm
            import time as _time
            cfg = _cm.load_config(self.archive_win.get_current_directory())
            devices = cfg.get('sync_devices') or {}
            online = []
            for dev in devices.values():
                try:
                    last = _time.mktime(_time.strptime(
                        dev.get('last_seen', ''), '%Y-%m-%d %H:%M:%S'))
                    if _time.time() - last < 300:
                        online.append(dev.get('name') or '手机')
                except (ValueError, TypeError, OSError):
                    continue
            if online:
                self.lbl_devices.setText('●  手机在线：%s' % '、'.join(online[:2]))
                self.lbl_devices.setStyleSheet('''
                    color: #34D399;
                    font-size: 12px;
                    font-weight: 600;
                    background: transparent;
                    padding: 0 8px;
                ''')
            else:
                self.lbl_devices.setText('○  手机未连接')
                self.lbl_devices.setStyleSheet('''
                    color: #9B9B9B;
                    font-size: 12px;
                    font-weight: 500;
                    background: transparent;
                    padding: 0 8px;
                ''')
        except Exception:
            pass  # 配置读取失败静默保持原状

    # === 导航事件处理 ===

    _PAGE_TITLES = ('首页', '学员档案', '教练管理', '体测档案与课时', '训练任务编排',
                    '数据中心', '财务管理', '学员详情', '教练详情')

    def _on_page_changed(self, index: int):
        """侧边栏菜单项点击：切换 QStackedWidget 页面。"""
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self._PAGE_TITLES):
            self.lbl_page_title.setText(self._PAGE_TITLES[index])
        self._refresh_nav_badge()
        self._sync_archive_dir_for_page(index)

    #==== 详情页导航 ====

    def open_student_detail(self, name: str):
        """打开学员详情页（学员档案表格行点击 / 详情按钮）。"""
        self._detail_origin = PAGE_PROFILE
        self.student_detail.load_student(name)
        self.stack.setCurrentIndex(PAGE_STUDENT_DETAIL)
        self.lbl_page_title.setText(self._PAGE_TITLES[PAGE_STUDENT_DETAIL])

    def open_coach_detail(self, name: str):
        """打开教练详情页（教练管理表格行点击 / 详情按钮）。"""
        self._detail_origin = PAGE_COACH
        self.coach_detail.load_coach(name)
        self.stack.setCurrentIndex(PAGE_COACH_DETAIL)
        self.lbl_page_title.setText(self._PAGE_TITLES[PAGE_COACH_DETAIL])

    def _back_from_detail(self, default_page: int):
        """详情页「返回」：回到来源管理页（默认学员档案/教练管理）。"""
        target = getattr(self, '_detail_origin', default_page) or default_page
        self.stack.setCurrentIndex(target)
        self.side_nav.select(target)
        if 0 <= target < len(self._PAGE_TITLES):
            self.lbl_page_title.setText(self._PAGE_TITLES[target])
        self._sync_archive_dir_for_page(target)

    def _on_global_search(self, text: str):
        """侧边栏全局搜索：跳转学员档案页并按关键字过滤（回车提交）。"""
        self.stack.setCurrentIndex(PAGE_PROFILE)
        self.side_nav.select(PAGE_PROFILE)
        self.lbl_page_title.setText(self._PAGE_TITLES[PAGE_PROFILE])
        if hasattr(self, 'profile_screen'):
            self.profile_screen.le_search.setText(text)
            self.profile_screen.refresh()
        self._sync_archive_dir_for_page(PAGE_PROFILE)

    def _on_add_student(self):
        """首页「+ 新增学员」：跳转学员档案页并直接打开新增对话框。"""
        self.stack.setCurrentIndex(PAGE_PROFILE)
        self.side_nav.select(PAGE_PROFILE)
        self.lbl_page_title.setText(self._PAGE_TITLES[PAGE_PROFILE])
        if hasattr(self, 'profile_screen'):
            self.profile_screen.refresh()
            self.profile_screen.on_add()
        self._refresh_nav_badge()

    def _refresh_nav_badge(self):
        """刷新侧边栏「学员档案」菜单项的续费预警红色徽标（需续费人数）。

        读取失败时静默保持现状（首页概览会再次暴露同样数据，不会误导）。
        """
        try:
            import profile_manager as pm
            students = pm.list_students(self.archive_win.le_dir.text().strip())
            red = sum(1 for s in students if s.get('warn_level') == 'red')
            self.side_nav.set_badge(PAGE_PROFILE, red)
        except Exception:
            logging.exception('刷新导航预警徽标失败')

    def _on_quick_nav(self, index: int):
        """首页快捷卡片点击：切换页面并同步侧边栏选中态。"""
        self.stack.setCurrentIndex(index)
        self.side_nav.select(index)
        if 0 <= index < len(self._PAGE_TITLES):
            self.lbl_page_title.setText(self._PAGE_TITLES[index])
        self._sync_archive_dir_for_page(index)

    def _sync_archive_dir_for_page(self, index: int):
        """切换页面时同步档案目录到数据中心与学员档案。

        页面索引（与 PAGE_* 常量一致）：
            0 首页 | 1 学员档案 | 2 教练管理 | 3 体测档案与课时 | 4 训练任务编排 | 5 数据中心
        """
        try:
            archive_dir = self.archive_win.le_dir.text().strip()
            if archive_dir:
                if archive_dir != self.data_center.le_dir.text():
                    self.data_center.set_archive_dir(archive_dir)
                if archive_dir != self.finance_page.get_current_directory():
                    self.finance_page.set_archive_dir(archive_dir)
                # 切换到学员档案页时自动刷新
                if index == PAGE_PROFILE and hasattr(self, 'profile_screen'):
                    self.profile_screen.refresh()
                # 切换到教练管理页时自动刷新
                if index == PAGE_COACH and hasattr(self, 'coach_screen'):
                    self.coach_screen.refresh()
            # 切换到训练任务编排页时，刷新当前子页的学员下拉列表
            if index == PAGE_TRAINING and hasattr(self, 'training_win'):
                self.training_win.refresh_current_tab_students()
        except Exception:
            logging.exception('切换页面同步档案目录失败')

    def _on_help(self):
        """帮助菜单：弹出关于对话框。"""
        dialog.info(
            self, '关于',
            '上门体育教学管理平台\n'
            '侧边栏导航 + 多页面切换\n\n'
            '学员数据（含不满十四周岁未成年人个人信息）仅存储在本机，\n'
            '档案与备份均加密保存，不会上传至任何服务器。\n\n'
            '《用户协议》《隐私政策》全文见安装目录 legal/ 文件夹。'
        )

    def _on_logout(self):
        """退出登录菜单：退出应用。"""
        reply = dialog.confirm(
            self, '退出登录',
            '确定要退出登录吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply :
            QApplication.quit()

    def _setup_tray_and_sync(self):
        """初始化系统托盘与自动同步管理器（在 show() 之后调用）。

        必须延后到 show() 之后：QSystemTrayIcon 需要主窗口已显示才能正常弹出通知。
        同时启动 GitHub 自动更新检查（优化6新增）。
        """
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = tray_notifier.ensure_tray(parent=self)
        self._sync_mgr = AutoSyncManager(
            parent=self,
            archive_dir_getter=lambda: self.archive_win.le_dir.text().strip(),
        )
        self._sync_mgr.syncState.connect(self._on_sync_state)
        self._sync_mgr.start()
        # 启动后延迟 5 秒静默检查 GitHub 更新
        check_update_on_startup(parent_window=self, repo=UPDATE_REPO, delay_ms=5000)

    def show_update_dialog(self):
        """手动触发更新对话框（供数据中心"检查更新"按钮调用）。"""
        if not UPDATE_REPO:
            from modern_dialog import dialog
            dialog.info(self, '提示', '尚未配置更新源，请联系开发者设置 GitHub 仓库地址。')
            return
        try:
            from update_dialog import UpdateDialog
            dlg = UpdateDialog(parent=self, repo=UPDATE_REPO)
            dlg.exec()
        except Exception as e:
            logging.exception('手动检查更新失败')
            dialog.warn(self, '更新检查失败', str(e))

    def _on_sync_state(self, state: str):
        """同步状态指示器：idle/syncing/ok/error 切换颜色与文案。"""
        styles = {
            'idle':    ('#9B9B9B', '●  同步待命'),
            'syncing': ('#FF6B47', '●  正在同步...'),
            'ok':      ('#10B981', '●  同步完成'),
            'error':   ('#E53E3E', '●  同步失败'),
        }
        color, text = styles.get(state, styles['idle'])
        self.lbl_sync.setText(text)
        self.lbl_sync.setStyleSheet(f'''
            color: {color};
            font-size: 12px;
            font-weight: 500;
            background: transparent;
            padding: 0 8px;
        ''')

    def _on_merge_ok(self, message: str):
        """手机端备份合并成功（v23.11）：顶栏亮绿 + 刷新各页数据，6 秒后回待命。"""
        self._on_sync_state('ok')
        self.refresh_after_sync()
        self._merge_ok_reset = QTimer(self)
        self._merge_ok_reset.setSingleShot(True)
        self._merge_ok_reset.timeout.connect(lambda: self._on_sync_state('idle'))
        self._merge_ok_reset.start(6000)

    def refresh_after_sync(self):
        """自动同步完成后调用：刷新各页面的学员列表与档案数据。"""
        try:
            if hasattr(self, 'profile_screen'):
                self.profile_screen.refresh()
            if hasattr(self, 'training_win'):
                self.training_win.refresh_current_tab_students()
        except Exception:
            logging.exception('同步后刷新页面失败')

    def closeEvent(self, event):
        """退出前统一收尾后台线程（修复退出时 QThread still running 报错）。

        - AutoBackupManager 的 QThread：停止调度器（此前其 closeEvent 因
          嵌在 QStackedWidget 中永远不会触发，线程随 QApplication 销毁时报错）
        - 自动同步管理器：停止扫描定时器，等待进行中的 SyncWorker 退出
        - 双端同步服务（HTTP/心跳/USB 轮询 daemon 线程）：优雅 shutdown
        """
        try:
            if getattr(self, '_sync_mgr', None) is not None:
                self._sync_mgr.stop()
                # 若有恢复任务在跑，最多等 3 秒（避免 QThread 销毁时仍在运行）
                worker = getattr(self._sync_mgr, '_worker', None)
                if worker is not None and worker.isRunning():
                    worker.wait(3000)
        except Exception:
            logging.exception('停止自动同步管理器失败')
        try:
            self.data_center.stop_auto_backup()
        except Exception:
            logging.exception('停止自动备份线程失败')
        try:
            from data_center.sync_service import get_service
            get_service().stop()
        except Exception:
            logging.exception('停止双端同步服务失败')
        try:
            if getattr(self, '_tray', None) is not None:
                self._tray.hide()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)
    _f = QFont('Inter'); _f.setPointSize(10)
    app.setFont(_f)
    # 启动模式选择：上门体育 / 俱乐部（v23.12，俱乐部数据独立目录物理隔离）
    from mode_selector import run_selector, save_mode
    mode = run_selector()
    if mode is None:
        sys.exit(0)
    save_mode(mode)
    w = App(mode=mode)
    w.show()
    # 主窗口显示后初始化托盘与自动同步
    w._setup_tray_and_sync()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
