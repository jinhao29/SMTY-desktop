# -*- coding: utf-8 -*-
"""多租户模式配置测试（阶段一：配置化）。

覆盖：
1. 加载：正常 / 文件缺失兜底 / 文件损坏兜底
2. 别名解析：旧值 club → club_evolve
3. 目录与库名解析：各模式档案目录正确
4. 校验：重复 id / db_name / archive_dir 被拒，default_mode 失配被拒
5. 当前模式读写与旧值兼容
6. 过渡开关 use_config=0 时退回旧硬编码行为
7. ★ 新增机构零代码：只加一段配置即可被正确解析
"""
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'data_center'))

import mode_config as mc  # noqa: E402

SHIPPED_CONFIG = os.path.join(_ROOT, 'config', 'modes.json')

SAMPLE_MODES = [
    {
        'id': 'coaching',
        'display_name': '上门体育',
        'db_name': 'sports_coach_db',
        'archive_dir': '学员档案',
        'enabled': True,
        'aliases': {'primary': 'coaching'},
    },
    {
        'id': 'club_evolve',
        'display_name': 'EVOLVE 俱乐部',
        'db_name': 'sports_coach_club_db',
        'archive_dir': '学员档案俱乐部',
        'enabled': True,
        'aliases': {'club': 'club_evolve'},
    },
]


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """每个用例都在干净环境下跑：无环境变量覆盖 + 清空缓存。"""
    monkeypatch.delenv(mc.ENV_CONFIG_PATH, raising=False)
    monkeypatch.delenv(mc.ENV_USE_CONFIG, raising=False)
    mc.reload()
    yield
    mc.reload()


def _write_config(tmp_path, payload, name='modes.json'):
    path = tmp_path / name
    if isinstance(payload, str):
        path.write_text(payload, encoding='utf-8')
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return str(path)


def _use(monkeypatch, path):
    monkeypatch.setenv(mc.ENV_CONFIG_PATH, str(path))
    mc.reload()


# ---------------------------------------------------------------------------
# 1. 加载：正常 / 缺失 / 损坏
# ---------------------------------------------------------------------------

def test_loads_shipped_config(monkeypatch):
    _use(monkeypatch, SHIPPED_CONFIG)
    cfg = mc.load()
    assert cfg['version'] >= 1
    assert cfg['default_mode'] == 'coaching'
    assert [m['id'] for m in mc.get_all_modes()] == ['coaching', 'club_evolve']


def test_missing_file_falls_back_to_builtin(monkeypatch, tmp_path):
    _use(monkeypatch, tmp_path / 'does_not_exist.json')
    assert [m['id'] for m in mc.get_all_modes()] == ['coaching', 'club_evolve']
    assert mc.default_mode() == 'coaching'


def test_corrupted_file_falls_back_to_builtin(monkeypatch, tmp_path):
    _use(monkeypatch, _write_config(tmp_path, '{ this is not json'))
    assert [m['id'] for m in mc.get_all_modes()] == ['coaching', 'club_evolve']


def test_structurally_invalid_file_falls_back(monkeypatch, tmp_path):
    """缺 modes 数组 → 视为损坏，回退内置（而不是崩溃）"""
    _use(monkeypatch, _write_config(tmp_path, {'version': 1}))
    assert len(mc.get_all_modes()) == 2


def test_shipped_config_matches_builtin(monkeypatch):
    """config/modes.json 与内置默认必须同源，防止两份清单各自漂移。"""
    if not os.path.exists(SHIPPED_CONFIG):
        pytest.skip('未找到 config/modes.json')
    _use(monkeypatch, SHIPPED_CONFIG)
    shipped = [(m['id'], m['display_name'], m['db_name'], m['archive_dir'])
               for m in mc.get_all_modes()]
    builtin = [(m['id'], m['display_name'], m['db_name'], m['archive_dir'])
               for m in mc.BUILTIN_MODES]
    assert shipped == builtin


# ---------------------------------------------------------------------------
# 2. 别名解析
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('value,expected', [
    ('coaching', 'coaching'),
    ('club_evolve', 'club_evolve'),
    ('club', 'club_evolve'),          # 旧值 → 新 id
    ('primary', 'coaching'),          # 旧值 → 新 id
    ('coach', 'coaching'),
    ('EVOLVE 俱乐部', 'club_evolve'),  # display_name 命中
    ('不存在的模式', None),
    ('', None),
    (None, None),
])
def test_resolve_alias(value, expected):
    assert mc.resolve_alias(value) == expected


# ---------------------------------------------------------------------------
# 3. 目录 / 库名解析
# ---------------------------------------------------------------------------

def test_archive_dir_per_mode():
    assert mc.archive_dir_for('coaching').endswith(os.path.join('Desktop', '学员档案'))
    assert mc.archive_dir_for('club_evolve').endswith(os.path.join('Desktop', '学员档案俱乐部'))
    # 未知模式回退 default_mode 的目录（不抛异常）
    assert mc.archive_dir_for('nope').endswith(os.path.join('Desktop', '学员档案'))


def test_db_name_per_mode():
    assert mc.db_name_for('coaching') == 'sports_coach_db'
    assert mc.db_name_for('club_evolve') == 'sports_coach_club_db'


@pytest.mark.parametrize('path,expected', [
    (r'C:/Users/x/Desktop/学员档案', 'coaching'),
    (r'C:/Users/x/Desktop/学员档案俱乐部', 'club_evolve'),
    (r'C:/Users/x/Desktop/学员档案/', 'coaching'),
    (r'C:/Users/x/Desktop/别的目录', None),
    ('', None),
])
def test_mode_for_archive_dir(path, expected):
    assert mc.mode_for_archive_dir(path) == expected


# ---------------------------------------------------------------------------
# 4. 校验：重复项必须拒绝启动
# ---------------------------------------------------------------------------

def _dup(field, value):
    modes = [dict(SAMPLE_MODES[0]), dict(SAMPLE_MODES[1])]
    modes[1][field] = value
    return {'version': 1, 'default_mode': 'coaching', 'modes': modes}


@pytest.mark.parametrize('field,value', [
    ('id', 'coaching'),
    ('db_name', 'sports_coach_db'),
    ('archive_dir', '学员档案'),
])
def test_duplicate_fields_are_rejected(monkeypatch, tmp_path, field, value):
    """重复 = 两个机构落到同一份数据，必须拒绝启动（抛 ModeConfigError）。"""
    _use(monkeypatch, _write_config(tmp_path, _dup(field, value)))
    with pytest.raises(mc.ModeConfigError):
        mc.load()


def test_default_mode_must_exist(monkeypatch, tmp_path):
    _use(monkeypatch, _write_config(tmp_path, {
        'version': 1, 'default_mode': 'ghost', 'modes': SAMPLE_MODES}))
    with pytest.raises(mc.ModeConfigError):
        mc.load()


def test_missing_required_field_rejected(monkeypatch, tmp_path):
    bad = [dict(SAMPLE_MODES[0])]
    del bad[0]['archive_dir']
    _use(monkeypatch, _write_config(tmp_path, {'version': 1, 'modes': bad}))
    with pytest.raises(mc.ModeConfigError):
        mc.load()


def test_validate_or_raise_passes_for_shipped_config(monkeypatch):
    _use(monkeypatch, SHIPPED_CONFIG)
    mc.validate_or_raise()   # 不抛即通过


# ---------------------------------------------------------------------------
# 5. 当前模式读写（含旧值兼容）
# ---------------------------------------------------------------------------

def test_current_mode_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, 'APP_MODE_FILE', str(tmp_path / 'app_mode.json'))
    mc.set_current_mode('club_evolve')
    assert mc.get_current_mode() == 'club_evolve'
    # 写入的永远是解析后的新 id
    with open(mc.APP_MODE_FILE, encoding='utf-8') as f:
        assert json.load(f)['mode'] == 'club_evolve'


def test_current_mode_legacy_value_migrated(monkeypatch, tmp_path):
    """升级后 app_mode.json 里还是旧值 'club' —— 必须解析到 club_evolve。"""
    path = tmp_path / 'app_mode.json'
    monkeypatch.setattr(mc, 'APP_MODE_FILE', str(path))
    path.write_text(json.dumps({'mode': 'club'}), encoding='utf-8')
    assert mc.get_current_mode() == 'club_evolve'


def test_current_mode_accepts_early_key_name(monkeypatch, tmp_path):
    """早期约定键名 current_mode 也要认。"""
    path = tmp_path / 'app_mode.json'
    monkeypatch.setattr(mc, 'APP_MODE_FILE', str(path))
    path.write_text(json.dumps({'current_mode': 'club'}), encoding='utf-8')
    assert mc.get_current_mode() == 'club_evolve'


def test_current_mode_unknown_falls_back_to_default(monkeypatch, tmp_path):
    path = tmp_path / 'app_mode.json'
    monkeypatch.setattr(mc, 'APP_MODE_FILE', str(path))
    path.write_text(json.dumps({'mode': 'garbage'}), encoding='utf-8')
    assert mc.get_current_mode() == 'coaching'


def test_current_mode_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, 'APP_MODE_FILE', str(tmp_path / 'nope.json'))
    assert mc.get_current_mode() == 'coaching'


# ---------------------------------------------------------------------------
# 6. 过渡开关：use_config=0 退回旧硬编码行为
# ---------------------------------------------------------------------------

def test_use_config_off_uses_legacy_modes(monkeypatch):
    monkeypatch.setenv(mc.ENV_USE_CONFIG, '0')
    mc.reload()
    assert mc.use_config() is False
    assert [m['id'] for m in mc.get_all_modes()] == ['coaching', 'club']
    # legacy 下不做别名映射（旧逻辑原样）
    assert mc.resolve_alias('club') == 'club'
    assert mc.archive_dir_for('club').endswith('学员档案俱乐部')
    assert mc.get_current_mode() in ('coaching', 'club')


def test_use_config_env_beats_file(monkeypatch, tmp_path):
    _use(monkeypatch, _write_config(tmp_path, {
        'version': 1, 'use_config': True, 'modes': SAMPLE_MODES}))
    monkeypatch.setenv(mc.ENV_USE_CONFIG, '0')
    mc.reload()
    assert mc.use_config() is False


def test_file_switch_disables_config(monkeypatch, tmp_path):
    _use(monkeypatch, _write_config(tmp_path, {
        'version': 1, 'use_config': False, 'modes': SAMPLE_MODES}))
    assert mc.use_config() is False
    assert [m['id'] for m in mc.get_all_modes()] == ['coaching', 'club']


# ---------------------------------------------------------------------------
# 7. ★ 新增机构零代码（阶段一核心目标）
# ---------------------------------------------------------------------------

def test_new_tenant_requires_no_code_change(monkeypatch, tmp_path):
    """只往 modes 加一项，目录解析 / 别名 / 库名全部自动生效。"""
    new_mode = {
        'id': 'club_beta',
        'display_name': 'BETA 俱乐部',
        'db_name': 'sports_coach_beta_db',
        'archive_dir': '学员档案Beta',
        'enabled': True,
        'aliases': {'beta': 'club_beta'},
    }
    _use(monkeypatch, _write_config(tmp_path, {
        'version': 1, 'default_mode': 'coaching',
        'modes': SAMPLE_MODES + [new_mode]}))

    assert mc.resolve_alias('beta') == 'club_beta'
    assert mc.mode_for_archive_dir(r'C:/Users/x/Desktop/学员档案Beta') == 'club_beta'
    assert mc.archive_dir_for('club_beta').endswith('学员档案Beta')
    assert mc.db_name_for('club_beta') == 'sports_coach_beta_db'
    assert 'club_beta' in [m['id'] for m in mc.get_all_modes()]


def test_disabled_mode_hidden_from_selector(monkeypatch, tmp_path):
    modes = [dict(SAMPLE_MODES[0]), dict(SAMPLE_MODES[1])]
    modes[1]['enabled'] = False
    _use(monkeypatch, _write_config(tmp_path, {
        'version': 1, 'default_mode': 'coaching', 'modes': modes}))
    assert [m['id'] for m in mc.get_all_modes()] == ['coaching']
    assert [m['id'] for m in mc.get_all_modes(include_disabled=True)] == \
        ['coaching', 'club_evolve']


# ---------------------------------------------------------------------------
# 8. 阶段一规格点名的接口必须齐备（防改名/漏实现）
# ---------------------------------------------------------------------------

def test_spec_interface_names_available(monkeypatch):
    """load_config / validate_config / get_mode / ... 全部可调用且语义正确。"""
    _use(monkeypatch, SHIPPED_CONFIG)

    cfg = mc.load_config()                       # 规格名（= load）
    assert cfg['default_mode'] == 'coaching'
    assert cfg['version'] >= 1

    mc.validate_config(cfg)                      # 规格名（= validate），不抛即通过

    for name in ('get_mode', 'get_all_modes', 'resolve_alias',
                 'get_current_mode', 'set_current_mode'):
        assert callable(getattr(mc, name)), '缺少规格接口：%s' % name

    assert mc.get_mode('club_evolve')['db_name'] == 'sports_coach_club_db'
    assert mc.get_mode('不存在的模式') is None
    assert [m['id'] for m in mc.get_all_modes()] == ['coaching', 'club_evolve']
    assert mc.resolve_alias('club') == 'club_evolve'


def test_use_config_flag_exposed(monkeypatch):
    """use_config 开关必须可查询（阶段一要求保留一个版本）。"""
    _use(monkeypatch, SHIPPED_CONFIG)
    assert mc.use_config() is True
    monkeypatch.setenv(mc.ENV_USE_CONFIG, 'false')
    mc.reload()
    assert mc.use_config() is False
