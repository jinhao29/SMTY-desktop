# -*- coding: utf-8 -*-
"""管理层：GitHub 自动更新检查与下载应用。

职责：
- 调用 GitHub Releases API 获取最新版本信息
- 与本地版本号对比（语义化版本 v1.2.3）
- 后台下载更新包 zip 到临时目录
- 生成 updater.bat 重启脚本，关闭主程序后完成原地替换与重启

设计说明：
- 仅依赖标准库 + requests，避免引入额外打包复杂度
- 所有网络调用设置 15s 连接 / 60s 读超时，失败时安全返回
- 文件替换策略：
  * 源码模式（python app.py）：直接解压覆盖源码目录，提示手动重启
  * 打包模式（PyInstaller onedir）：生成 bat 脚本，等待 exe 退出后
    使用 xcopy /E /Y 替换 _internal 与 exe，再重启
- 版本号约定：v1.2.3 或 1.2.3，解析为 (1, 2, 3) 元组比较
"""
import os
import sys
import re
import json
import time
import shutil
import hashlib
import zipfile
import tempfile
import subprocess
from typing import Callable, Optional, Tuple, Dict, Any, List

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


# ============================================================
# 用户配置文件保护清单
# ============================================================
# 更新覆盖时这些文件不会被新版同名文件覆盖，确保用户已设置的：
# - 续费阈值（_data_center_config.json）
# - 免打扰状态、跟单偏好（_followup.json）
# - 训练模块列表（training_tool/blocks_config.json）
# - 学员档案与备份目录（_archive_config.json / _backup_config.json）
# 不会被清空。
# 说明：路径相对应用根目录；匹配规则为「完整路径结尾匹配」。
PROTECTED_CONFIG_FILES: List[str] = [
    '_data_center_config.json',
    '_followup.json',
    '_archive_config.json',
    '_backup_config.json',
    'training_tool/blocks_config.json',
    'training_tool\\blocks_config.json',  # Windows 路径分隔符兼容
    'data_center/_data_center_config.json',
    'data_center\\_data_center_config.json',
]


def is_protected_config_file(file_path: str, base_dir: str = '') -> bool:
    """判断给定文件是否属于受保护的配置文件。

    参数:
        file_path: 待判定文件绝对路径或相对 base_dir 的路径
        base_dir: 应用根目录，用于将绝对路径转换为相对路径

    返回: True 表示该文件在更新时应跳过覆盖
    """
    if not file_path:
        return False
    # 统一分隔符
    norm_path = file_path.replace('\\', '/').lower()
    base_norm = base_dir.replace('\\', '/').lower() if base_dir else ''
    if base_norm and norm_path.startswith(base_norm):
        rel = norm_path[len(base_norm):].lstrip('/')
    else:
        rel = norm_path

    for protected in PROTECTED_CONFIG_FILES:
        p = protected.replace('\\', '/').lower()
        # 结尾匹配：支持相对路径或绝对路径两种传入
        if rel == p or rel.endswith('/' + p):
            return True
    return False


def write_xcopy_exclude_file(exclude_path: str) -> bool:
    """生成 xcopy /EXCLUDE 用的排除规则文件。

    xcopy EXCLUDE 文件每行是一个子串，xcopy 会跳过路径包含该子串的文件。
    我们将每个受保护文件名（仅 basename）写入一行，避免路径分隔符差异。

    返回: True 成功；False 失败
    """
    try:
        seen = set()
        lines = []
        for p in PROTECTED_CONFIG_FILES:
            base = os.path.basename(p.replace('\\', '/'))
            if base and base not in seen:
                seen.add(base)
                lines.append(base)
        with open(exclude_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            f.write('\n')
        return True
    except OSError:
        return False


# ============================================================
# 版本号处理
# ============================================================

# 当前桌面端版本号（每次发版需同步更新）
# 约定：v主.次.修订，例如 'v1.0.0'
__VERSION__ = 'v1.0.0'


def get_current_version() -> str:
    """返回当前桌面端版本号。

    优先级：
    1. 同目录 VERSION 文件（开发者可手动维护）
    2. updater.__VERSION__ 硬编码
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, 'frozen', False):
        here = os.path.dirname(sys.executable)
    version_file = os.path.join(here, 'VERSION')
    if os.path.exists(version_file):
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                v = f.read().strip()
                if v:
                    return v
        except OSError:
            pass
    return __VERSION__


def parse_version(version: str) -> Tuple[int, int, int]:
    """解析语义化版本号字符串为 (major, minor, patch) 元组。

    支持：v1.2.3 / 1.2.3 / v1.2 / 1.2
    无效输入返回 (0, 0, 0)
    """
    if not version:
        return (0, 0, 0)
    s = str(version).strip().lstrip('vV').strip()
    m = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', s)
    if not m:
        return (0, 0, 0)
    major = int(m.group(1) or 0)
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    return (major, minor, patch)


def compare_versions(v1: str, v2: str) -> int:
    """比较两个版本号。

    返回:
         1  v1 > v2
         0  v1 == v2
        -1  v1 < v2
    """
    a = parse_version(v1)
    b = parse_version(v2)
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


# ============================================================
# GitHub API 调用
# ============================================================

GITHUB_API_BASE = 'https://api.github.com/repos'


def fetch_latest_release(repo: str, timeout: Tuple[float, float] = (15.0, 30.0)) -> Optional[Dict[str, Any]]:
    """调用 GitHub API 获取最新 release 信息。

    参数:
        repo: 仓库全名，如 'your_username/your_repo'
        timeout: (连接超时, 读取超时) 秒

    返回:
        dict {
            'tag_name': 'v1.2.3',
            'name': 'Release 标题',
            'body': 'Release notes',
            'html_url': 'https://github.com/...',
            'assets': [{'name', 'browser_download_url', 'size'}, ...],
            'published_at': '2026-07-01T...'
        }
        失败返回 None
    """
    if requests is None:
        return None
    url = f'{GITHUB_API_BASE}/{repo}/releases/latest'
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'shangmentiyu-desktop-updater',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        assets = []
        for a in data.get('assets', []) or []:
            assets.append({
                'name': a.get('name', ''),
                'browser_download_url': a.get('browser_download_url', ''),
                'size': a.get('size', 0),
            })
        return {
            'tag_name': data.get('tag_name', ''),
            'name': data.get('name', ''),
            'body': data.get('body', ''),
            'html_url': data.get('html_url', ''),
            'assets': assets,
            'published_at': data.get('published_at', ''),
        }
    except (requests.RequestException, ValueError, OSError):
        return None


def find_release_asset(release: Dict[str, Any], preferred_name: str = '上门体育教学管理工具.zip') -> Optional[Dict[str, Any]]:
    """从 release 信息中查找目标下载资源。

    优先匹配 preferred_name，否则取第一个 .zip 资源。
    """
    if not release:
        return None
    assets = release.get('assets', []) or []
    if not assets:
        return None
    # 精确匹配
    for a in assets:
        if a.get('name') == preferred_name:
            return a
    # 模糊匹配 zip
    for a in assets:
        name = a.get('name', '').lower()
        if name.endswith('.zip'):
            return a
    return None


# ============================================================
# 下载
# ============================================================

def download_release_zip(url: str, target_path: str,
                         progress_cb: Optional[Callable[[int, int, str], None]] = None,
                         timeout: Tuple[float, float] = (15.0, 60.0)) -> bool:
    """流式下载 release zip 到 target_path。

    参数:
        url: browser_download_url
        target_path: 本地保存路径
        progress_cb: (downloaded_bytes, total_bytes, message) -> None
                     total_bytes 为 -1 表示未知大小

    返回: True 下载成功；False 失败（含网络异常或 IO 异常）
    """
    if requests is None:
        if progress_cb:
            progress_cb(0, -1, 'requests 库未安装，无法下载更新')
        return False
    try:
        headers = {'User-Agent': 'shangmentiyu-desktop-updater'}
        with requests.get(url, headers=headers, timeout=timeout, stream=True) as resp:
            if resp.status_code != 200:
                if progress_cb:
                    progress_cb(0, -1, f'下载失败：HTTP {resp.status_code}')
                return False
            total = int(resp.headers.get('Content-Length', '0') or 0)
            if total <= 0:
                total = -1
            if progress_cb:
                progress_cb(0, total, '开始下载...')
            # 临时文件先写入 .part，完成后重命名
            tmp_path = target_path + '.part'
            downloaded = 0
            last_report = time.time()
            with open(tmp_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    # 节流：每 0.5s 报告一次进度
                    now = time.time()
                    if progress_cb and (now - last_report >= 0.5 or total < 0):
                        if total > 0:
                            pct = downloaded * 100 // total
                            msg = f'下载中 {pct}% ({downloaded // 1024}KB / {total // 1024}KB)'
                        else:
                            msg = f'下载中 ({downloaded // 1024}KB)'
                        progress_cb(downloaded, total, msg)
                        last_report = now
            # 完成重命名
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except OSError:
                    pass
            os.rename(tmp_path, target_path)
            if progress_cb:
                progress_cb(downloaded, total if total > 0 else downloaded, '下载完成')
            return True
    except (requests.RequestException, OSError) as e:
        if progress_cb:
            progress_cb(0, -1, f'下载异常：{e}')
        # 清理 .part 文件
        tmp_path = target_path + '.part'
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


# ============================================================
# SHA-256 完整性校验（P1 修复：下载无校验 → 下载后校验）
# ============================================================

def calculate_sha256(file_path: str) -> Optional[str]:
    """计算文件 SHA-256 十六进制摘要（小写）。失败返回 None。"""
    if not os.path.exists(file_path):
        return None
    try:
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def find_expected_sha256(release: Dict[str, Any], asset_name: str) -> Optional[str]:
    """从 release 信息中提取更新包预期 SHA-256。

    优先从 release notes（body）中解析 `sha256: <hash>` / `SHA-256: <hash>`，
    其次下载配套的 `<asset_name>.sha256` 侧车文件解析（形如 `<hash>  <文件名>`）。
    两者都取不到时返回 None，由 [verify_zip_sha256] 按 fail-closed 拒绝。
    """
    if not release:
        return None
    body = (release.get('body') or '')
    m = re.search(r'(?im)(?:sha-?256\s*[:=]\s*)([0-9a-f]{64})', body)
    if m:
        return m.group(1).lower()
    return _fetch_sidecar_sha256(release, asset_name)


def _fetch_sidecar_sha256(release: Dict[str, Any], asset_name: str) -> Optional[str]:
    """下载配套的 `<asset_name>.sha256` 侧车文件并解析其中的 hash。

    失败（无此附件 / 网络异常 / 内容无 64 位 hex）一律返回 None，交给上层 fail-closed。
    """
    if requests is None or not asset_name:
        return None
    sidecar = f'{asset_name}.sha256'
    url = next(
        (a.get('browser_download_url') for a in (release.get('assets') or [])
         if a.get('name') == sidecar),
        None
    )
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=(15.0, 60.0))
        if resp.status_code != 200:
            return None
        m = re.search(r'[0-9a-f]{64}', resp.text or '', re.I)
        return m.group(0).lower() if m else None
    except Exception:
        return None


def verify_zip_sha256(zip_path: str, expected_sha256: Optional[str]) -> Tuple[bool, str]:
    """校验 zip 的 SHA-256 是否与预期一致。

    返回 (ok, message)。

    fail-closed（2026-08-30 修复）：expected_sha256 为空时**拒绝**安装。
    旧行为"缺 hash 就跳过校验"会让"发布时忘了附 hash"与"发布被投毒"无法区分——
    攻击者只要不提供 hash 即可让完整性校验形同虚设，进而配合解压阶段投递恶意文件。
    """
    if not expected_sha256:
        return False, '更新包未提供 SHA-256，已拒绝安装（请在 Release 中附带 sha256 值或 .sha256 文件）'
    actual = calculate_sha256(zip_path)
    if actual is None:
        return False, '无法计算更新包 SHA-256'
    if actual.lower() == expected_sha256.lower():
        return True, 'SHA-256 校验通过'
    return False, f'SHA-256 校验失败：预期 {expected_sha256}，实际 {actual}'


# ============================================================
# 解压与替换
# ============================================================

def _safe_extract_zip(zf: 'zipfile.ZipFile', dest_root: str) -> None:
    """逐条目安全解压到 dest_root（Zip Slip 防护）。

    拒绝三类危险条目：绝对路径 / 盘符路径（C:...）/ 含 `..` 的路径穿越；
    并对归一化后的落盘路径做目录内包含性校验（realpath + startswith）。

    任一条目非法即抛 ValueError 中止**整个**解压（fail-closed，不做部分解压），
    避免"跳过越界条目后继续安装一个已被投毒的包"。
    """
    root = os.path.realpath(dest_root)
    for info in zf.infolist():
        raw = info.filename.replace('\\', '/')
        parts = [p for p in raw.split('/') if p not in ('', '.')]
        if any(p == '..' for p in parts):
            raise ValueError(f'更新包包含路径穿越条目：{info.filename}')
        # 绝对路径：显式判断前导分隔符（Windows 上 ntpath.isabs('/x') 为 False，
        # 不能只依赖平台语义），另含盘符（C:）与 UNC 前缀
        if raw.startswith('/') or raw.startswith('\\') \
                or re.match(r'^[A-Za-z]:', raw) or os.path.isabs(raw):
            raise ValueError(f'更新包包含绝对路径条目：{info.filename}')
        if not parts:
            continue
        target = os.path.realpath(os.path.join(root, *parts))
        if not (target == root or target.startswith(root + os.sep)):
            raise ValueError(f'更新包条目越界：{info.filename}')
        if info.is_dir():
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(info) as src, open(target, 'wb') as dst:
            shutil.copyfileobj(src, dst)


def extract_to_temp(zip_path: str, target_dir: str) -> Optional[str]:
    """将 zip 解压到临时目录。

    返回: 临时目录路径；失败或包内含非法条目返回 None（并清理残留）
    """
    if not os.path.exists(zip_path):
        return None
    tmp_root = None
    try:
        # 在目标目录的父目录创建临时目录
        parent = os.path.dirname(os.path.abspath(target_dir)) or '.'
        tmp_root = tempfile.mkdtemp(prefix='update_staging_', dir=parent)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            _safe_extract_zip(zf, tmp_root)
        return tmp_root
    except (zipfile.BadZipFile, OSError, ValueError):
        # ValueError：包内含非法/越界条目，已拒绝解压
        if tmp_root:
            shutil.rmtree(tmp_root, ignore_errors=True)
        return None


def _find_staging_subdir(staging_root: str) -> str:
    """在解压目录中查找实际应用根目录。

    zip 包内可能包含一个顶层目录（如 '上门体育教学管理工具/'），
    也可能直接是文件列表。返回包含 app.py 或 .exe 的实际目录。
    """
    # 直接在根目录
    if os.path.exists(os.path.join(staging_root, 'app.py')) or \
       any(f.endswith('.exe') for f in os.listdir(staging_root) if os.path.isfile(os.path.join(staging_root, f))):
        return staging_root
    # 查找一级子目录
    for name in os.listdir(staging_root):
        sub = os.path.join(staging_root, name)
        if os.path.isdir(sub):
            if os.path.exists(os.path.join(sub, 'app.py')) or \
               any(f.endswith('.exe') for f in os.listdir(sub)
                   if os.path.isfile(os.path.join(sub, f))):
                return sub
    return staging_root


def create_restart_bat(exe_path: str, staging_dir: str, log_path: str) -> str:
    """生成 Windows 重启脚本（.bat）。

    脚本流程：
    1. 等待当前 exe 退出（最多 30 秒）
    2. xcopy /E /Y /I /EXCLUDE:... 替换目标目录（排除受保护配置文件）
    3. 启动新 exe
    4. 脚本自删除

    返回: bat 文件路径
    """
    target_dir = os.path.dirname(exe_path)
    exe_name = os.path.basename(exe_path)
    bat_path = os.path.join(tempfile.gettempdir(), 'smty_updater.bat')
    exclude_path = os.path.join(tempfile.gettempdir(), 'smty_exclude.txt')

    # 生成 xcopy 排除规则文件
    write_xcopy_exclude_file(exclude_path)

    bat_content = f'''@echo off
chcp 65001 >nul
echo 正在等待主程序退出...
set /a wait_cnt=0
:wait_loop
tasklist /FI "PID eq %1" 2>nul | find "%1" >nul
if errorlevel 1 goto do_update
set /a wait_cnt+=1
if %wait_cnt% GEQ 30 goto do_update
timeout /t 1 /nobreak >nul
goto wait_loop

:do_update
echo 正在替换文件（保留用户配置）...
xcopy "{staging_dir}\\*" "{target_dir}\\" /E /Y /I /Q /EXCLUDE:{exclude_path} >nul 2>&1
if errorlevel 1 (
    echo 替换失败，详情见日志：{log_path}
    timeout /t 5 /nobreak >nul
    goto cleanup
)

echo 正在重启应用...
start "" "{target_dir}\\{exe_name}"

:cleanup
del "{exclude_path}" 2>nul
(goto) 2>nul & del "%~f0"
'''
    try:
        with open(bat_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(bat_content)
        return bat_path
    except OSError:
        return ''


def _backup_dir(current_dir: str) -> str:
    """返回更新备份目录路径（用于失败回滚）。"""
    return os.path.join(current_dir, '_update_backup')


def apply_update_in_source_mode(staging_dir: str, current_dir: str) -> bool:
    """源码模式：直接覆盖当前目录（不替换运行中的 .py 文件，因为已加载到内存）。

    保护策略：受 PROTECTED_CONFIG_FILES 列表保护的文件不会被覆盖。
    若新版包含同名配置文件，会先以 .new 后缀保留，供用户参考。

    P1 修复：覆盖前先备份旧文件到 _update_backup/，失败时回滚，保留旧版本。
    返回: True 表示成功，需要用户手动重启
    """
    src = _find_staging_subdir(staging_dir)
    backup_dir = _backup_dir(current_dir)
    try:
        # 1. 覆盖前备份将被覆盖的旧条目（供失败回滚）
        if os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)
        os.makedirs(backup_dir, exist_ok=True)
        for name in os.listdir(src):
            d = os.path.join(current_dir, name)
            if not os.path.exists(d):
                continue
            b = os.path.join(backup_dir, name)
            try:
                if os.path.isdir(d):
                    shutil.copytree(d, b, ignore=shutil.ignore_patterns('__pycache__'))
                else:
                    shutil.copy2(d, b)
            except OSError:
                # 单个条目备份失败不阻断整体（回滚时该条目恢复为缺失，属可接受降级）
                pass

        # 2. 覆盖
        for name in os.listdir(src):
            s = os.path.join(src, name)
            d = os.path.join(current_dir, name)
            if os.path.isdir(s):
                # 跳过 __pycache__ 等缓存目录
                if name == '__pycache__':
                    continue
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(s, d)
            else:
                # 检查是否为受保护配置文件
                if is_protected_config_file(d, current_dir):
                    # 用户已有该配置文件 → 跳过覆盖；新版同名文件存为 .new
                    if os.path.exists(d):
                        # 保留新版的默认配置作为参考
                        try:
                            shutil.copy2(s, d + '.new')
                        except OSError:
                            pass
                        continue
                    # 用户没有该配置文件（首次安装）→ 正常写入
                    shutil.copy2(s, d)
                else:
                    shutil.copy2(s, d)
        return True
    except OSError:
        _restore_backup(current_dir)
        return False


def _restore_backup(current_dir: str):
    """更新失败时从 _update_backup/ 恢复旧版本（回滚入口）。"""
    backup_dir = _backup_dir(current_dir)
    if not os.path.isdir(backup_dir):
        return
    try:
        for name in os.listdir(backup_dir):
            b = os.path.join(backup_dir, name)
            d = os.path.join(current_dir, name)
            if os.path.isdir(b):
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(b, d)
            else:
                shutil.copy2(b, d)
    except OSError:
        pass


# ============================================================
# 完整流程
# ============================================================

def check_for_update(repo: str, current_version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """检查是否有新版本（仅查询，不下载）。

    返回:
        dict {'has_update': bool, 'latest_version': str, 'release': dict, 'asset': dict}
        None 表示检查失败（网络异常等）
    """
    if requests is None:
        return None
    cur = current_version or get_current_version()
    release = fetch_latest_release(repo)
    if not release:
        return None
    latest = release.get('tag_name', '')
    has_update = compare_versions(latest, cur) > 0
    asset = find_release_asset(release)
    return {
        'has_update': has_update,
        'current_version': cur,
        'latest_version': latest,
        'release': release,
        'asset': asset,
    }


def perform_update(repo: str,
                   progress_cb: Optional[Callable[[int, int, str], None]] = None,
                   parent_widget=None) -> Tuple[bool, str]:
    """执行完整更新流程：检查 → 下载 → 解压 → 替换 → 提示重启。

    参数:
        repo: GitHub 仓库全名
        progress_cb: (downloaded, total, message) -> None
        parent_widget: 可选父窗口（用于后续弹窗）

    返回:
        (success, message)
        success=True 表示已成功应用更新，需重启
        success=False 表示失败或无需更新
    """
    if requests is None:
        return False, 'requests 库未安装，无法检查更新'

    if progress_cb:
        progress_cb(0, -1, '正在检查新版本...')
    info = check_for_update(repo)
    if not info:
        return False, '无法获取版本信息，请检查网络或仓库配置'
    if not info['has_update']:
        return False, f'当前已是最新版本（{info["current_version"]}）'
    if not info['asset']:
        return False, '未找到可下载的更新包（.zip），请前往 GitHub 手动下载'

    latest = info['latest_version']
    asset = info['asset']
    download_url = asset.get('browser_download_url', '')
    if not download_url:
        return False, '更新包下载地址无效'

    # 下载到临时目录
    if progress_cb:
        progress_cb(0, -1, f'正在下载 v{latest} ...')
    tmp_dir = tempfile.mkdtemp(prefix='update_dl_')
    zip_path = os.path.join(tmp_dir, asset.get('name') or 'update.zip')
    if not download_release_zip(download_url, zip_path, progress_cb=progress_cb):
        _safe_rmtree(tmp_dir)
        return False, '下载更新包失败，请稍后重试'

    # P1 修复：下载后校验 SHA-256，杜绝被篡改的更新包
    expected_sha = find_expected_sha256(info['release'], asset.get('name') or '')
    ok, verify_msg = verify_zip_sha256(zip_path, expected_sha)
    if not ok:
        _safe_rmtree(tmp_dir)
        return False, f'更新包完整性校验失败：{verify_msg}'

    # 解压
    if progress_cb:
        progress_cb(0, -1, '正在解压更新包...')
    if getattr(sys, 'frozen', False):
        # 打包模式：解压到 staging，生成 bat 替换 + 重启
        exe_path = sys.executable
        target_dir = os.path.dirname(exe_path)
        staging_dir = extract_to_temp(zip_path, target_dir)
        if not staging_dir:
            _safe_rmtree(tmp_dir)
            return False, '解压更新包失败（文件损坏，或包内含非法/越界路径条目已被拒绝）'
        log_path = os.path.join(tempfile.gettempdir(), 'smty_update.log')
        bat_path = create_restart_bat(exe_path, staging_dir, log_path)
        if not bat_path:
            _safe_rmtree(tmp_dir)
            return False, '生成重启脚本失败'
        if progress_cb:
            progress_cb(0, -1, '即将重启应用以完成更新...')
        # 启动 bat 脚本（传入当前 PID），然后退出主程序
        try:
            subprocess.Popen(
                ['cmd', '/c', 'start', '/min', bat_path, str(os.getpid())],
                cwd=tempfile.gettempdir(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            )
        except OSError:
            return False, '启动更新脚本失败'
        # 通知调用方退出主程序
        return True, f'更新已下载完成（v{latest}），应用将重启以完成安装'
    else:
        # 源码模式：直接覆盖源码目录
        here = os.path.dirname(os.path.abspath(__file__))
        staging_dir = extract_to_temp(zip_path, here)
        if not staging_dir:
            _safe_rmtree(tmp_dir)
            return False, '解压更新包失败（文件损坏，或包内含非法/越界路径条目已被拒绝）'
        if not apply_update_in_source_mode(staging_dir, here):
            _safe_rmtree(tmp_dir)
            return False, '应用更新失败（文件可能被占用）'
        if progress_cb:
            progress_cb(0, -1, '更新已应用，请手动重启程序')
        return True, f'更新已应用（v{latest}），请手动重启程序'


def _safe_rmtree(path: str):
    """安全删除目录（忽略错误）。"""
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass
