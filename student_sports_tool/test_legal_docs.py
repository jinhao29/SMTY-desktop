# -*- coding: utf-8 -*-
"""合规交付物完整性：桌面端 legal/ 与 Android assets/legal/ 必须同源同内容。

背景
----
2026-09-12 审查确认：全仓无隐私政策 / 用户协议 / 注销权入口，
而本产品处理的是不满十四周岁未成年人的个人信息，属阻断商业化的 P0 合规硬伤。
补齐文本后，用本测试防止后续被误删、或双端文本各自漂移。

双端同一份文本是刻意的：运营主体、收集范围、存储方式对两个客户端是同一套事实，
分叉维护必然导致某端条款与实际行为不符。
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

PC_LEGAL = os.path.join(_ROOT, 'legal')
KT_LEGAL = os.path.join(_ROOT, '..', 'android_app', 'app', 'src', 'main',
                        'assets', 'legal')

DOCS = {
    'user_agreement.txt': ('数据归属', '免责声明', '联系方式'),
    'privacy_policy.txt': ('未成年人', '加密', '删除', '联系方式'),
}


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


@pytest.mark.parametrize('fname', list(DOCS))
def test_pc_legal_docs_exist_and_nonempty(fname):
    path = os.path.join(PC_LEGAL, fname)
    assert os.path.exists(path), f'桌面端合规文件缺失：{path}'
    content = _read(path)
    assert len(content) > 500, f'{fname} 内容过短（{len(content)} 字符），疑似占位'


@pytest.mark.parametrize('fname,clauses', list(DOCS.items()))
def test_pc_legal_docs_cover_key_clauses(fname, clauses):
    content = _read(os.path.join(PC_LEGAL, fname))
    missing = [c for c in clauses if c not in content]
    assert not missing, f'{fname} 缺少关键条款：{missing}'


@pytest.mark.parametrize('fname', list(DOCS))
def test_android_assets_match_pc_legal(fname):
    """双端文本必须逐字节一致（避免只改一端的静默漂移）。"""
    kt_path = os.path.join(KT_LEGAL, fname)
    if not os.path.exists(kt_path):
        pytest.skip('未找到 Android assets/legal（分发环境无源码），跳过同源比对')
    assert _read(kt_path) == _read(os.path.join(PC_LEGAL, fname)), (
        f'{fname} 双端内容不一致 —— 请同步 android_app/app/src/main/assets/legal/ '
        f'与 student_sports_tool/legal/')


def test_placeholders_are_marked_for_review():
    """运营主体/联系方式等未定项必须以【】占位，避免"看起来已定稿"被直接对外。"""
    for fname in DOCS:
        content = _read(os.path.join(PC_LEGAL, fname))
        assert '【' in content, f'{fname} 未标注待确认占位项（【…】）'


def test_release_package_includes_legal():
    """发版脚本必须把 legal/ 显式打进安装包（缺了等于合规文件没送达客户）。"""
    src = _read(os.path.join(_ROOT, 'make_release.py'))
    assert 'legal' in src, 'make_release.py 未处理 legal/ 目录'
    for fname in DOCS:
        assert fname in src, f'make_release.py 未校验 {fname}'
