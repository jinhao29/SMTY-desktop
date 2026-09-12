# -*- coding: utf-8 -*-
"""跨端模式配置锚定（阶段三）：PC 与 Android 的 modes.json 必须字段级一致。

背景：阶段一/二把两端的模式清单收敛为各自一份配置——
- PC      student_sports_tool/config/modes.json（运行时读取）
- Android android_app/app/src/main/assets/config/modes.json（随 APK 固化）

安全关键字段（id / db_name / archive_dir / aliases）双端不一致的直接后果：
备份防串库校验（mode_guard.check_backup_mode ↔ ModeManager.isSameMode）失配，
任一端"新增机构"后另一端无法识别，轻则同步被拒，重则串库。

比对策略：核心字段**强一致**；UI 装饰字段（tagline/badge/icon/accent 等）
允许两端按需分化（Android 的 Material 图标与 PC 自绘图标本就不同），不比对。
"""
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

PC_CONFIG = os.path.join(_ROOT, 'config', 'modes.json')
KT_CONFIG = os.path.join(
    _ROOT, '..', 'android_app', 'app', 'src', 'main', 'assets', 'config', 'modes.json')

pytestmark = pytest.mark.skipif(
    not os.path.exists(KT_CONFIG),
    reason='未找到 Android assets/config/modes.json（分发环境无源码），跳过跨端比对')


def _load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope='module')
def configs():
    return _load(PC_CONFIG), _load(KT_CONFIG)


def test_meta_fields_match(configs):
    """version / default_mode / use_config 双端一致。"""
    pc, kt = configs
    for key in ('version', 'default_mode', 'use_config'):
        assert pc[key] == kt[key], (
            f'配置字段「{key}」双端不一致：PC={pc.get(key)!r} Android={kt.get(key)!r}')


def test_mode_count_and_order_match(configs):
    """模式数量与 id 顺序一致（顺序影响 UI 卡片展示次序）。"""
    pc, kt = configs
    assert len(pc['modes']) == len(kt['modes'])
    assert [m['id'] for m in pc['modes']] == [m['id'] for m in kt['modes']], (
        f"模式 id 列表不一致：PC={[m['id'] for m in pc['modes']]} "
        f"Android={[m['id'] for m in kt['modes']]}")


def test_security_critical_fields_match(configs):
    """★ 每个模式的安全关键字段逐项一致（防串库校验的根基）。"""
    pc, kt = configs
    for pm, km in zip(pc['modes'], kt['modes']):
        for field in ('id', 'display_name', 'db_name', 'archive_dir', 'enabled'):
            assert pm.get(field) == km.get(field), (
                f"模式「{pm.get('id')}」字段 {field} 双端不一致："
                f"PC={pm.get(field)!r} Android={km.get(field)!r}")
        assert pm.get('aliases', {}) == km.get('aliases', {}), (
            f"模式「{pm.get('id')}」aliases 双端不一致："
            f"PC={pm.get('aliases')} Android={km.get('aliases')}——"
            f"旧值映射缺一侧会导致升级用户数据丢失或误拒")


def test_required_schema_fields_present(configs):
    """PC 配置自身的 schema 完整性（id/db_name/archive_dir 非空）。"""
    pc, _ = configs
    for m in pc['modes']:
        for field in ('id', 'db_name', 'archive_dir'):
            assert str(m.get(field) or '').strip(), (
                f"模式缺少 {field}：{m}")
