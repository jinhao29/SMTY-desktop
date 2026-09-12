# -*- coding: utf-8 -*-
"""跨端一致性测试：续费预警阈值 ↔ Android data/model/RenewalThresholds.kt。

背景
----
双端各自硬编码续费阈值，曾漂移为「Android 剩余≤3 / PC 默认≤5」，
同一学员在两端"是否需要续费"的判定不同。现两端均以命名常量表达，
本测试解析 Android 源码做锚定，**任一端改动未同步即失败**。

已知分级差异（有意保留，非漂移）
--------------------------------
- PC 有三级：critical（剩余≤CRITICAL_REMAINING 或超支）/ warning（≤阈值）/ normal
- Android 只有 isLowBalance（剩余 1..LOW_BALANCE_REMAINING）与 isExhausted（==0），无 critical 级
  两者对"0 节"的归类不同（PC→critical，Android→exhausted），但**触发提醒的阈值一致**。
"""
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'data_center'))

from renewal_processor import (  # noqa: E402
    DEFAULT_RENEWAL_THRESHOLD, DEFAULT_INACTIVE_DAYS, CRITICAL_REMAINING,
    calc_urgency, is_inactive, WARNING, NORMAL, CRITICAL, UNKNOWN,
)

ROOT = _ROOT
KT_RENEWAL = os.path.join(
    ROOT, '..', 'android_app', 'data', 'src', 'main', 'java',
    'com', 'shangmentiyu', 'sportscoach', 'data', 'model', 'RenewalThresholds.kt')

pytestmark = pytest.mark.skipif(
    not os.path.exists(KT_RENEWAL),
    reason='未找到 Android 端 RenewalThresholds.kt（分发环境无源码），跳过跨端比对')


def _kt_const(name):
    with open(KT_RENEWAL, encoding='utf-8') as f:
        src = f.read()
    m = re.search(rf'const val {name}\s*=\s*(\d+)', src)
    assert m, f'RenewalThresholds.kt 未找到常量 {name}'
    return int(m.group(1))


def test_low_balance_threshold_matches_android():
    """续费阈值：双端必须一致（这是曾经的漂移点）。"""
    assert _kt_const('LOW_BALANCE_REMAINING') == DEFAULT_RENEWAL_THRESHOLD, (
        f'续费阈值漂移：Android={_kt_const("LOW_BALANCE_REMAINING")} '
        f'PC={DEFAULT_RENEWAL_THRESHOLD}')


def test_near_expiry_days_is_sane():
    """Android 侧重置的临期天数（PC 尚未实现该维度预警，仅做合理性约束）。"""
    assert 1 <= _kt_const('NEAR_EXPIRY_DAYS') <= 90


@pytest.mark.parametrize('remaining,expected', [
    (0, CRITICAL),
    (CRITICAL_REMAINING, CRITICAL),
    (CRITICAL_REMAINING + 1, WARNING),
    (DEFAULT_RENEWAL_THRESHOLD, WARNING),
    (DEFAULT_RENEWAL_THRESHOLD + 1, NORMAL),
    (99, NORMAL),
])
def test_urgency_boundaries(remaining, expected):
    assert calc_urgency(remaining, 100) == expected


def test_urgency_unknown_when_no_total():
    assert calc_urgency(5, 0) == UNKNOWN


def test_urgency_respects_custom_threshold():
    """教练在「高级配置」里覆盖后的阈值必须生效。"""
    assert calc_urgency(8, 100, threshold=10) == WARNING
    assert calc_urgency(11, 100, threshold=10) == NORMAL


def test_inactive_boundaries():
    assert is_inactive(DEFAULT_INACTIVE_DAYS) is True
    assert is_inactive(DEFAULT_INACTIVE_DAYS - 1) is False
    assert is_inactive(-1) is False          # 无上课记录
