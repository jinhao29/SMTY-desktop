# -*- coding: utf-8 -*-
"""备份导入的「没进多少」必须被记账（静默型问题）。

用户导入自己的备份时，最怕的不是报错，是**部分行悄悄没进去而界面说成功**：
之后按备份里有的数据去对账，账对不上却查不出是哪一次出的问题。
因此导入接口必须如实回报 成功 / 跳过 / 失败 三类计数与原因。

列名白名单（拒绝非法列）见 test_data_integrity.py。
"""
import pytest


def _import(client, headers, **tables):
    body = {'mode': 'shangmen', 'merge': True, **tables}
    return client.post('/api/v1/backup/import', json=body, headers=headers)


def _student(client, headers, sid):
    r = client.get(f'/api/v1/students/{sid}', headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_import_reports_skipped_rows(client, auth_headers):
    """好行进得去；坏行被记下并分类，不再静默丢弃。"""
    r = _import(client, auth_headers, students=[
        {'id': 1, 'name': '甲', 'deleted': 0},   # 正常
        'not-a-dict',                            # 格式错
        {'name': '没有 id'},                      # 缺主键
        {'id': 4},                               # 写入失败（name NOT NULL）
    ])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['imported']['students'] == 1
    assert d['skipped']['students'] == 3, '跳过数必须如实回报'
    reasons = d['skipped_details']['students']['reasons']
    assert any('格式错' in k for k in reasons), reasons
    assert any('缺字段' in k for k in reasons), reasons
    assert any('写入失败' in k for k in reasons), reasons
    assert d['skipped_details']['students']['samples'], '应给出可核对的样例'
    # 好行确实落库了，坏行没有
    assert client.get('/api/v1/students', headers=auth_headers).json()['total'] == 1


def test_import_reports_lww_skip(client, auth_headers):
    """LWW 未覆盖也是「没导入」，同样要出现在回报里。"""
    _import(client, auth_headers, students=[
        {'id': 1, 'name': '新版本', 'updated_at': '2026-05-05 00:00:00'}])
    r = _import(client, auth_headers, students=[
        {'id': 1, 'name': '旧版本', 'updated_at': '2026-01-01 00:00:00'}])
    d = r.json()
    assert d['imported']['students'] == 0
    assert d['skipped']['students'] == 1
    assert any('LWW' in k for k in d['skipped_details']['students']['reasons'])
    assert _student(client, auth_headers, 1)['name'] == '新版本', '旧版本不得覆盖'


def test_import_clean_backup_reports_zero_skipped(client, auth_headers):
    """干净备份：skipped 全 0、无 details（正常路径不产生噪音）。"""
    r = _import(client, auth_headers, students=[{'id': 1, 'name': '甲', 'deleted': 0}])
    d = r.json()
    assert d['skipped']['students'] == 0
    assert d['skipped_details'] == {}


# ---------------------------------------------------------------------------
# 以下为 2026-09-15 独立复核补测（不改实现，只补未覆盖的边界）
# ---------------------------------------------------------------------------
def test_skipped_counted_per_table(client, auth_headers):
    """跳过必须按表分组：一张表的坏行不能算到另一张头上。"""
    r = _import(client, auth_headers,
                students=[{'id': 1, 'name': '甲'}, 'bad', {'name': '缺 id'}],
                coaches=[{'id': 1, 'name': '教练'}, {'name': '缺 id'}])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['imported']['students'] == 1
    assert d['skipped']['students'] == 2
    assert d['imported']['coaches'] == 1
    assert d['skipped']['coaches'] == 1
    assert set(d['skipped_details']) == {'students', 'coaches'}, d['skipped_details']
    assert d['skipped']['lessons'] == 0, '未涉及的表也要有 0 计数，便于前端统一渲染'


def test_samples_capped_at_three(client, auth_headers):
    """样例最多 3 条（免得一个坏备份把弹窗撑爆），但计数必须是全量。"""
    d = _import(client, auth_headers,
                students=[{'name': f'缺 id {i}'} for i in range(5)]).json()
    assert d['skipped']['students'] == 5, '计数必须是全量，不能跟着样例一起截断'
    assert len(d['skipped_details']['students']['samples']) == 3, '样例应封顶 3 条'


def test_column_rejection_preempts_row_report(client, auth_headers):
    """列级拒绝是整体 400：既不写入好行，也不给「跳过报告」来掩盖它。

    这是列级（ba51394）与行级（本文件）两层的关系证明：
    非法列必须在写入前整体拒绝，而不是降级成一条「跳过」混在明细里。
    """
    r = _import(client, auth_headers, students=[
        {'id': 1, 'name': '甲'},               # 好行——但整体拒绝时也不许进
        {'id': 2, 'name': '乙', 'evil': 1},    # 非法列
    ])
    assert r.status_code == 400, r.text
    assert '未知列' in r.json()['detail']
    assert client.get('/api/v1/students', headers=auth_headers).json()['total'] == 0, \
        '整体拒绝不得留下半份写入'
