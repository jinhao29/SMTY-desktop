# -*- coding: utf-8 -*-
"""多租户模式配置（阶段一：配置化）。

单一真源：``config/modes.json``；文件缺失或损坏时回退 [BUILTIN_MODES]。
新增机构 = 在 ``modes`` 数组里加一项，**无需改任何代码**。

字段约定（双端共用，Android 阶段二读同名结构）::

    version       int    配置版本
    default_mode  str    默认模式 id（解析失败时的兜底）
    modes[]       每项：
        id            str    稳定标识，人工命名（coaching / club_evolve）
        display_name  str    显示名
        db_name       str    Android 库文件名（桌面端暂不使用，为双端对齐预留）
        archive_dir   str    桌面端档案目录名（位于 ~/Desktop 下）
        enabled       bool   是否在选择页展示
        aliases       dict   历史值 → 本模式 id（如 club → club_evolve）
        可选 UI：window_title / nav_title / tagline / badge / accent / icon

旧值兼容：``aliases`` 让升级后读到旧 ``app_mode.json``（``club``）或旧手机备份
``meta.mode`` 都能正确落位，因此 **数据零迁移**（库名、目录名一律不变）。

校验策略：
- 配置文件**损坏/缺失** → 用内置默认值兜底并记日志（不阻断启动）
- 配置文件**结构合法但重复 id/db_name/archive_dir** → 抛 [ModeConfigError]，
  调用方必须拒绝启动（重复即意味着两个机构会落到同一份数据上）
"""
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

CONFIG_REL_PATH = os.path.join('config', 'modes.json')
ENV_CONFIG_PATH = 'SMTY_MODES_CONFIG'

APP_MODE_FILE = os.path.join(os.path.expanduser('~'), '.shangmentiyu', 'app_mode.json')


class ModeConfigError(Exception):
    """配置结构非法（重复 id / db_name / archive_dir，或 default_mode 失配）。

    调用方（app 启动入口）应当捕获并**拒绝启动**，而不是继续带着错误配置跑。
    """


# ---------------------------------------------------------------------------
# 内置默认配置：与 config/modes.json 内容同源
# （test_mode_config.py 会断言二者规范化后一致，防止双份漂移）
# ---------------------------------------------------------------------------
BUILTIN_MODES = [
    {
        'id': 'coaching',
        'display_name': '上门体育',
        'db_name': 'sports_coach_db',
        'archive_dir': '学员档案',
        'enabled': True,
        'aliases': {'primary': 'coaching', 'coach': 'coaching', '上门体育': 'coaching'},
        'window_title': '上门体育教学管理平台',
        'nav_title': '上门体育',
        'tagline': '学员档案 · 课时排课 · 财务记账 · 数据中心',
        'badge': '常用',
        'accent': '#10B981',
        'icon': 'stopwatch',
    },
    {
        'id': 'club_evolve',
        'display_name': 'EVOLVE 俱乐部',
        'db_name': 'sports_coach_club_db',
        'archive_dir': '学员档案俱乐部',
        'enabled': True,
        'aliases': {'club': 'club_evolve', '俱乐部': 'club_evolve', 'evolve': 'club_evolve'},
        'window_title': '俱乐部管理平台',
        'nav_title': '俱乐部',
        'tagline': 'EVOLVE 进化体育 · 独立数据空间，与上门体育完全隔离',
        'badge': 'NEW',
        'accent': '#047857',
        'icon': 'bolt',
    },
]

BUILTIN_DEFAULT_MODE = 'coaching'

_cache = None


# ---------------------------------------------------------------------------
# 路径与原始读取
# ---------------------------------------------------------------------------

def program_root() -> str:
    """程序根目录（打包后为 exe 所在目录，源码运行时为 student_sports_tool/）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path() -> str:
    """生效的配置文件路径（环境变量优先，便于测试与高级用户覆盖）。"""
    env = os.environ.get(ENV_CONFIG_PATH, '').strip()
    if env:
        return env
    return os.path.join(program_root(), CONFIG_REL_PATH)


def _read_raw():
    """读取并做最粗的 JSON 解析。返回 (data, reason)；失败时 data 为 None。"""
    path = config_path()
    if not os.path.exists(path):
        return None, '配置文件不存在：%s' % path
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        return None, '配置文件无法解析：%s（%s）' % (path, e)
    if not isinstance(data, dict) or not isinstance(data.get('modes'), list) or not data['modes']:
        return None, '配置文件结构非法（缺少非空 modes 数组）：%s' % path
    return data, ''


def _normalize_mode(m):
    """补齐可选字段，保证下游取用不必到处写 .get 兜底。"""
    out = dict(m)
    out['id'] = str(out.get('id') or '').strip()
    out['display_name'] = str(out.get('display_name') or out['id'])
    out['db_name'] = str(out.get('db_name') or '').strip()
    out['archive_dir'] = str(out.get('archive_dir') or '').strip()
    out['enabled'] = bool(out.get('enabled', True))
    aliases = out.get('aliases')
    out['aliases'] = dict(aliases) if isinstance(aliases, dict) else {}
    out.setdefault('window_title', '%s管理平台' % out['display_name'])
    out.setdefault('nav_title', out['display_name'])
    out.setdefault('tagline', '')
    out.setdefault('badge', '')
    out.setdefault('accent', '#FF6B47')
    out.setdefault('icon', 'stopwatch')
    return out


def _make_config(modes, default_mode, version):
    return {
        'version': version,
        'default_mode': default_mode,
        'modes': [_normalize_mode(m) for m in modes],
    }


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def validate(cfg) -> None:
    """结构校验；不合法抛 [ModeConfigError]。"""
    if not isinstance(cfg, dict):
        raise ModeConfigError('配置根节点必须是 JSON 对象')
    modes = cfg.get('modes')
    if not isinstance(modes, list) or not modes:
        raise ModeConfigError('modes 必须是非空数组')

    for key, label in (('id', '模式 id'), ('db_name', '库文件名'), ('archive_dir', '档案目录名')):
        seen = {}
        for i, m in enumerate(modes):
            if not isinstance(m, dict):
                raise ModeConfigError('modes[%d] 必须是对象' % i)
            value = str(m.get(key) or '').strip()
            if not value:
                raise ModeConfigError('modes[%d] 缺少 %s' % (i, key))
            if value in seen:
                raise ModeConfigError(
                    '%s 重复：「%s」（modes[%d] 与 modes[%d] 冲突）'
                    % (label, value, seen[value], i))
            seen[value] = i

    default_mode = cfg.get('default_mode')
    ids = {str(m.get('id')).strip() for m in modes}
    if default_mode and str(default_mode) not in ids:
        raise ModeConfigError(
            'default_mode「%s」不在 modes（可选：%s）' % (default_mode, '、'.join(sorted(ids))))


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------

def reload():
    """清空缓存（配置改动 / 测试切换环境变量后调用）。"""
    global _cache
    _cache = None


def load() -> dict:
    """生效配置（含规范化 modes）。缺失/损坏 → 内置默认；重复项 → 抛异常。"""
    global _cache
    if _cache is not None:
        return _cache

    raw, reason = _read_raw()
    if raw is None:
        logger.warning('mode_config：%s —— 已回退内置默认配置', reason)
        _cache = _make_config(BUILTIN_MODES, BUILTIN_DEFAULT_MODE, 1)
        return _cache

    validate(raw)   # 结构合法但重复/缺失 → 让启动失败，避免带着错配置跑
    default_mode = str(raw.get('default_mode') or raw['modes'][0]['id']).strip()
    try:
        version = int(raw.get('version') or 1)
    except (TypeError, ValueError):
        version = 1
    _cache = _make_config(raw['modes'], default_mode, version)
    return _cache


def validate_or_raise() -> None:
    """启动自检入口：配置不合法时抛 [ModeConfigError]。"""
    load()


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def default_mode() -> str:
    return str(load().get('default_mode') or BUILTIN_DEFAULT_MODE)


def get_all_modes(include_disabled: bool = False):
    """全部模式（默认只返回 enabled 的，供选择页展示）。"""
    modes = load()['modes']
    if include_disabled:
        return list(modes)
    return [m for m in modes if m.get('enabled', True)]


def get_mode(mode_id):
    """按 id 取模式定义；不存在返回 None。"""
    if not mode_id:
        return None
    key = str(mode_id).strip()
    for m in load()['modes']:
        if m['id'] == key:
            return m
    return None


def resolve_alias(value):
    """把历史值/别名解析为模式 id；无法解析返回 None。

    命中顺序：id 精确匹配 → aliases 映射 → display_name 匹配。
    """
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    if get_mode(v):
        return v
    modes = load()['modes']
    for m in modes:
        if v in m['aliases']:
            return m['id']
    for m in modes:
        if v == m['display_name']:
            return m['id']
    return None


def mode_for_archive_dir(archive_dir):
    """档案目录 → 模式 id（按目录 basename 与各模式 archive_dir 比对）。"""
    try:
        name = os.path.basename(os.path.normpath(str(archive_dir or '')))
    except (TypeError, ValueError):
        return None
    if not name:
        return None
    for m in load()['modes']:
        if name == m['archive_dir']:
            return m['id']
    return None


def archive_dir_for(mode_id) -> str:
    """模式对应的档案目录绝对路径（~ / Desktop / <archive_dir>）。"""
    m = get_mode(mode_id) or get_mode(default_mode()) or {}
    name = m.get('archive_dir') or '学员档案'
    return os.path.join(os.path.expanduser('~'), 'Desktop', name)


def ensure_archive_dir(mode_id) -> str:
    """确保档案目录存在并返回其路径。"""
    d = archive_dir_for(mode_id)
    os.makedirs(d, exist_ok=True)
    return d


def db_name_for(mode_id) -> str:
    """模式对应的 Android 库文件名（桌面端暂未使用，为双端对齐预留）。"""
    m = get_mode(mode_id) or {}
    return m.get('db_name') or ''


# ---------------------------------------------------------------------------
# 当前模式（app_mode.json）
# ---------------------------------------------------------------------------

def get_current_mode() -> str:
    """上次使用的模式 id。

    旧值（如 ``club``）经 aliases 解析为新 id；解析失败回退 [default_mode]。
    """
    raw = None
    try:
        with open(APP_MODE_FILE, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            # 兼容键名：mode（现行）/ current_mode（早期约定）
            raw = data.get('mode') or data.get('current_mode')
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        raw = None
    return resolve_alias(raw) or default_mode()


def set_current_mode(mode_id) -> str:
    """写入当前模式（始终写新 id）；返回实际写入值。"""
    mid = resolve_alias(mode_id) or default_mode()
    try:
        os.makedirs(os.path.dirname(APP_MODE_FILE), exist_ok=True)
        with open(APP_MODE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'mode': mid}, f, ensure_ascii=False)
    except OSError as e:
        logger.warning('保存工作模式失败：%s', e)
    return mid


# ---------------------------------------------------------------------------
# 规格别名
# 阶段一接口清单里写的是 load_config / validate_config；
# 本模块内为了简洁叫 load / validate，这里补别名保证两种叫法都能用。
# ---------------------------------------------------------------------------
load_config = load
validate_config = validate
