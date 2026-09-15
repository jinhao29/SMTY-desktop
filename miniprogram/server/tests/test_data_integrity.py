# -*- coding: utf-8 -*-
"""数据完整性回归用例。

固化 2026-09-14 全面审查发现的三类**静默数据损坏**：
- 编辑课时包重置剩余课时（改名/改价/改有效期都会触发）
- 课时包转移学员时旧学员汇总不重算
（备注丢失、导入列名注入见后续追加小节）

这些 bug 的共同特征是「界面显示成功、数据已经不对、无提示无异常」——
因此每条都断言**具体数字**，不靠界面反馈。
"""
import pytest


def _mk_student(client, headers, name='学员'):
    r = client.post('/api/v1/students', json={'name': name}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


def _mk_coach(client, headers, name='教练'):
    r = client.post('/api/v1/coaches', json={'name': name}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


def _mk_package(client, headers, sid, total=20, price=2000, paid=-1):
    r = client.post('/api/v1/packages', json={
        'student_id': sid, 'name': '课时包', 'total_lessons': total,
        'price': price, 'paid_amount': paid}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


def _mk_lesson(client, headers, sid, cid, date='2026-09-15'):
    r = client.post('/api/v1/lessons', json={
        'student_ids': [sid], 'coach_id': cid, 'date': date,
        'start_time': '10:00', 'end_time': '11:00'}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


def _pkg(client, headers, pid):
    r = client.get(f'/api/v1/packages/{pid}', headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _student(client, headers, sid):
    r = client.get(f'/api/v1/students/{sid}', headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _put_pkg(client, headers, pid, **overrides):
    """按「前端整体回填表单」的方式提交：除显式覆盖项外原样回传。"""
    cur = _pkg(client, headers, pid)
    body = {k: cur[k] for k in ('student_id', 'name', 'total_lessons',
                                'expire_date', 'purchase_date', 'price', 'paid_amount')}
    body.update(overrides)
    r = client.put(f'/api/v1/packages/{pid}', json=body, headers=headers)
    assert r.status_code == 200, r.text
    return body


# =========================================================================
# 1. 编辑课时包不得重置剩余课时（P0）
# =========================================================================
def test_rename_package_keeps_remaining(client, auth_headers):
    """签到 1 次后改名 → 剩余必须仍是 19，不能回满 20。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    pid = _mk_package(client, auth_headers, sid, total=20)
    lid = _mk_lesson(client, auth_headers, sid, cid)
    r = client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert _pkg(client, auth_headers, pid)['remaining_lessons'] == 19

    _put_pkg(client, auth_headers, pid, name='暑期班20节')

    p = _pkg(client, auth_headers, pid)
    assert p['name'] == '暑期班20节'
    assert p['remaining_lessons'] == 19, '改名不得重置已消耗课时'
    assert _student(client, auth_headers, sid)['remaining_lessons'] == 19, '学员汇总同步失真'


def test_edit_price_and_expiry_keeps_remaining(client, auth_headers):
    """改价格 / 改有效期同样不得动剩余课时。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    pid = _mk_package(client, auth_headers, sid, total=10)
    # 两节不同日期的课（同教练同日同时段会触发排课冲突）
    for d in ('2026-09-15', '2026-09-16'):
        lid = _mk_lesson(client, auth_headers, sid, cid, date=d)
        client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]}, headers=auth_headers)

    _put_pkg(client, auth_headers, pid, price=3600, expire_date='2026-12-31')

    assert _pkg(client, auth_headers, pid)['remaining_lessons'] == 8


def test_grow_total_lessons_adds_remaining(client, auth_headers):
    """加课（总课时 20→25）→ 剩余同步 +5（19→24），而不是回到满额。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    pid = _mk_package(client, auth_headers, sid, total=20)
    lid = _mk_lesson(client, auth_headers, sid, cid)
    client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]}, headers=auth_headers)

    _put_pkg(client, auth_headers, pid, total_lessons=25, price=2500)

    p = _pkg(client, auth_headers, pid)
    assert p['remaining_lessons'] == 24, '加课应补足增量'
    assert _student(client, auth_headers, sid)['remaining_lessons'] == 24


def test_shrink_total_lessons_caps_remaining(client, auth_headers):
    """缩减总课时（20→5，剩余 19）→ 剩余收敛到 5，不得出现 remaining > total。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    pid = _mk_package(client, auth_headers, sid, total=20)
    lid = _mk_lesson(client, auth_headers, sid, cid)
    client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]}, headers=auth_headers)

    _put_pkg(client, auth_headers, pid, total_lessons=5)

    p = _pkg(client, auth_headers, pid)
    assert p['remaining_lessons'] == 5
    assert p['remaining_lessons'] <= p['total_lessons']


# =========================================================================
# 2. 课时包转移学员：两侧汇总都要重算（P1-④）
# =========================================================================
def test_transfer_package_recalcs_both_students(client, auth_headers):
    """包从 A 转给 B：A 汇总减掉、B 汇总加上，不得同时挂在两人头上。"""
    a = _mk_student(client, auth_headers, '甲')
    b = _mk_student(client, auth_headers, '乙')
    pid = _mk_package(client, auth_headers, a, total=20)
    assert _student(client, auth_headers, a)['remaining_lessons'] == 20

    _put_pkg(client, auth_headers, pid, student_id=b)

    assert _student(client, auth_headers, a)['remaining_lessons'] == 0, '旧学员汇总未减'
    assert _student(client, auth_headers, b)['remaining_lessons'] == 20, '新学员汇总未加'


def test_transfer_keeps_consumed_lessons(client, auth_headers):
    """转移时已消耗课时跟着包走（19 而不是 20）。"""
    a = _mk_student(client, auth_headers, '甲')
    b = _mk_student(client, auth_headers, '乙')
    cid = _mk_coach(client, auth_headers)
    pid = _mk_package(client, auth_headers, a, total=20)
    lid = _mk_lesson(client, auth_headers, a, cid)
    client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [a]}, headers=auth_headers)

    _put_pkg(client, auth_headers, pid, student_id=b)

    assert _student(client, auth_headers, b)['remaining_lessons'] == 19
    assert _student(client, auth_headers, a)['remaining_lessons'] == 0
