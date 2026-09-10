# -*- coding: utf-8 -*-
"""业务逻辑回归用例。

固化 2026-09-10 接口连通性验证中确认过的行为，防止后续重构破坏：
- 费用口径（与桌面端 fee_manager 一致）
- 签到扣课时
- 模式隔离
- 备份 meta.mode 标识
- 排课冲突检测
- 有签到记录的课程禁止删除
"""
import pytest


def _mk_student(client, headers, name='测试学员', **kw):
    body = {'name': name, **kw}
    r = client.post('/api/v1/students', json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


def _mk_coach(client, headers, name='测试教练', **kw):
    body = {'name': name, **kw}
    r = client.post('/api/v1/coaches', json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


def _mk_package(client, headers, sid, total=10, price=2000, paid=1200, **kw):
    body = {'student_id': sid, 'name': '课时包', 'total_lessons': total,
            'price': price, 'paid_amount': paid, **kw}
    r = client.post('/api/v1/packages', json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


def _mk_lesson(client, headers, sid, cid, date='2026-09-15',
               start='10:00', end='11:00', **kw):
    body = {'student_ids': [sid], 'coach_id': cid, 'date': date,
            'start_time': start, 'end_time': end, **kw}
    r = client.post('/api/v1/lessons', json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


# =========================================================================
# 1. 费用口径：单价 = 实收 ÷ 已购课时；应收 / 实收 / 待收
# =========================================================================
def test_fee_stats_basic(client, auth_headers):
    """2000 ÷ 10 = 200 单价 → 应收 2000 / 实收 1200 / 待收 800。"""
    sid = _mk_student(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=10, price=2000, paid=1200)

    r = client.get('/api/v1/packages/stats', headers=auth_headers)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s['total_lessons'] == 10
    assert s['remaining_lessons'] == 10
    assert s['consumed_lessons'] == 0
    assert s['total_receivable'] == 2000.0
    assert s['total_received'] == 1200.0
    assert s['total_pending'] == 800.0
    assert s['student_count'] == 1


def test_fee_paid_amount_minus_one_means_paid_in_full(client, auth_headers):
    """paid_amount = -1 视同已付清（与桌面端口径一致）。"""
    sid = _mk_student(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=5, price=1000, paid=-1)

    s = client.get('/api/v1/packages/stats', headers=auth_headers).json()
    assert s['total_receivable'] == 1000.0
    assert s['total_received'] == 1000.0, 'paid_amount=-1 应视同付清'
    assert s['total_pending'] == 0.0


def test_fee_stats_empty_db(client, auth_headers):
    """空库统计应全 0，不报错。"""
    s = client.get('/api/v1/packages/stats', headers=auth_headers).json()
    assert s['total_receivable'] == 0.0
    assert s['total_received'] == 0.0
    assert s['total_pending'] == 0.0
    assert s['total_lessons'] == 0


def test_student_remaining_synced_from_packages(client, auth_headers):
    """学员剩余课时 = 有效课时包 remaining 之和。"""
    sid = _mk_student(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=10)
    _mk_package(client, auth_headers, sid, total=5)

    stu = client.get(f'/api/v1/students/{sid}', headers=auth_headers).json()
    assert stu['remaining_lessons'] == 15, '两包合计应同步到学员 remaining_lessons'


# =========================================================================
# 2. 签到扣课时：10 → 9
# =========================================================================
def test_checkin_deducts_one_lesson(client, auth_headers):
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=10)
    lid = _mk_lesson(client, auth_headers, sid, cid)

    before = client.get(f'/api/v1/students/{sid}', headers=auth_headers).json()
    assert before['remaining_lessons'] == 10

    r = client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]},
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['lesson_status'] == 'signed_in'
    assert body['results'][0]['ok'] is True

    after = client.get(f'/api/v1/students/{sid}', headers=auth_headers).json()
    assert after['remaining_lessons'] == 9, f'扣课时后应为 9，实际 {after["remaining_lessons"]}'

    pkg = client.get('/api/v1/packages', headers=auth_headers).json()['list'][0]
    assert pkg['remaining_lessons'] == 9


def test_checkin_duplicate_rejected(client, auth_headers):
    """重复签到同一课应被拒绝，且不重复扣课时。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=10)
    lid = _mk_lesson(client, auth_headers, sid, cid)

    client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]},
                headers=auth_headers)
    r2 = client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]},
                     headers=auth_headers)
    assert r2.json()['results'][0]['ok'] is False
    assert '已操作过' in r2.json()['results'][0]['reason']

    after = client.get(f'/api/v1/students/{sid}', headers=auth_headers).json()
    assert after['remaining_lessons'] == 9, '重复签到不应二次扣课时'


def test_checkin_student_not_in_lesson_rejected(client, auth_headers):
    """不在该课名单中的学员不能被签到。"""
    sid1 = _mk_student(client, auth_headers, name='在课学员')
    sid2 = _mk_student(client, auth_headers, name='无关学员')
    cid = _mk_coach(client, auth_headers)
    _mk_package(client, auth_headers, sid2, total=10)
    lid = _mk_lesson(client, auth_headers, sid1, cid)

    r = client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid2]},
                    headers=auth_headers)
    assert r.json()['results'][0]['ok'] is False
    assert '不在该课名单中' in r.json()['results'][0]['reason']


def test_checkin_marking_package_exhausted(client, auth_headers):
    """扣到 0 时课时包应转为 exhausted 状态。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=1)
    lid = _mk_lesson(client, auth_headers, sid, cid)

    client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]},
                headers=auth_headers)
    pkg = client.get('/api/v1/packages', headers=auth_headers).json()['list'][0]
    assert pkg['status'] == 'exhausted'
    assert pkg['remaining_lessons'] == 0


# =========================================================================
# 3. 模式隔离：shangmen 与 club 数据互不可见
# =========================================================================
def test_mode_isolation(client, auth_headers):
    """在 shangmen 建学员，club 空间不应看到。"""
    _mk_student(client, auth_headers, name='上门模式学员')

    shangmen = client.get('/api/v1/students', headers=auth_headers).json()
    assert shangmen['total'] == 1

    club_headers = dict(auth_headers)
    club_headers['X-MP-Mode'] = 'club'
    club = client.get('/api/v1/students', headers=club_headers).json()
    assert club['total'] == 0, f'club 空间不应看到 shangmen 数据，实际 {club["total"]}'


def test_mode_isolation_reverse(client, auth_headers):
    """反向：club 建的学员，shangmen 不应看到。"""
    club_headers = dict(auth_headers)
    club_headers['X-MP-Mode'] = 'club'
    _mk_student(client, club_headers, name='俱乐部学员')

    assert client.get('/api/v1/students', headers=club_headers).json()['total'] == 1
    assert client.get('/api/v1/students', headers=auth_headers).json()['total'] == 0


@pytest.mark.parametrize('bad_mode', ['__bogus__', '', 'CLUB', 'unknown'],
                         ids=['bogus', 'empty', 'uppercase', 'unknown'])
def test_invalid_mode_falls_back_to_default(client, auth_headers, bad_mode):
    """非法模式标识应回落默认（shangmen），不能报错或串库。"""
    h = dict(auth_headers)
    h['X-MP-Mode'] = bad_mode
    r = client.get('/api/v1/students', headers=h)
    assert r.status_code == 200, f'非法 mode={bad_mode!r} 应回落而非报错'


# =========================================================================
# 4. 备份 meta.mode 标识正确
# =========================================================================
def test_backup_export_mode_identifier(client, auth_headers):
    """导出必须带 mode 标识 + export_version，供跨端/跨空间校验。"""
    _mk_student(client, auth_headers, name='备份测试学员')

    data = client.get('/api/v1/backup/export', headers=auth_headers).json()
    assert data['mode'] == 'shangmen'
    assert data['export_version'] == 1
    assert 'exported_at' in data
    # 各业务表齐全
    for t in ('students', 'coaches', 'lessons', 'lesson_packages', 'checkin_records'):
        assert t in data, f'导出缺少表 {t}'
    assert len(data['students']) == 1
    # 软删除的行不应出现
    assert all(s.get('deleted', 0) == 0 for s in data['students'])


def test_backup_export_mode_follows_header(client, auth_headers):
    """club 空间导出应带 mode=club。"""
    h = dict(auth_headers)
    h['X-MP-Mode'] = 'club'
    data = client.get('/api/v1/backup/export', headers=h).json()
    assert data['mode'] == 'club'


def test_backup_import_mode_mismatch_rejected(client, auth_headers):
    """导入 mode 与当前空间不符应 409（防跨模式恢复）。"""
    r = client.post('/api/v1/backup/import',
                    json={'mode': 'club', 'students': []}, headers=auth_headers)
    assert r.status_code == 409, f'模式不匹配应 409，实际 {r.status_code}'
    assert '模式不匹配' in r.json()['detail']


def test_backup_export_excludes_soft_deleted(client, auth_headers):
    """软删除的学员不应出现在导出中。"""
    sid = _mk_student(client, auth_headers, name='待删学员')
    assert len(client.get('/api/v1/backup/export',
                          headers=auth_headers).json()['students']) == 1
    client.delete(f'/api/v1/students/{sid}', headers=auth_headers)
    assert len(client.get('/api/v1/backup/export',
                          headers=auth_headers).json()['students']) == 0


# =========================================================================
# 5. 排课冲突检测
# =========================================================================
def test_lesson_conflict_same_coach_overlapping(client, auth_headers):
    """同一教练时段重叠 → 409。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    _mk_lesson(client, auth_headers, sid, cid,
               date='2026-10-01', start='09:00', end='10:00')

    r = client.post('/api/v1/lessons',
                    json={'student_ids': [sid], 'coach_id': cid, 'date': '2026-10-01',
                          'start_time': '09:30', 'end_time': '10:30'},
                    headers=auth_headers)
    assert r.status_code == 409, f'重叠时段应 409，实际 {r.status_code}'
    assert '已有排课' in r.json()['detail']


def test_lesson_no_conflict_adjacent_times(client, auth_headers):
    """首尾相接（10:00 结束 / 10:00 开始）不算冲突。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    _mk_lesson(client, auth_headers, sid, cid,
               date='2026-10-02', start='09:00', end='10:00')

    r = client.post('/api/v1/lessons',
                    json={'student_ids': [sid], 'coach_id': cid, 'date': '2026-10-02',
                          'start_time': '10:00', 'end_time': '11:00'},
                    headers=auth_headers)
    assert r.status_code == 200, f'相邻时段不应冲突，实际 {r.status_code} {r.text}'


def test_lesson_no_conflict_different_coach(client, auth_headers):
    """不同教练同一时段不算冲突。"""
    sid = _mk_student(client, auth_headers)
    c1 = _mk_coach(client, auth_headers, name='教练A')
    c2 = _mk_coach(client, auth_headers, name='教练B')
    _mk_lesson(client, auth_headers, sid, c1,
               date='2026-10-03', start='09:00', end='10:00')

    r = client.post('/api/v1/lessons',
                    json={'student_ids': [sid], 'coach_id': c2, 'date': '2026-10-03',
                          'start_time': '09:00', 'end_time': '10:00'},
                    headers=auth_headers)
    assert r.status_code == 200, '不同教练同时段不应冲突'


def test_lesson_requires_student(client, auth_headers):
    cid = _mk_coach(client, auth_headers)
    r = client.post('/api/v1/lessons',
                    json={'student_ids': [], 'coach_id': cid, 'date': '2026-10-04',
                          'start_time': '09:00', 'end_time': '10:00'},
                    headers=auth_headers)
    assert r.status_code == 400
    assert '至少选择一名学员' in r.json()['detail']


# =========================================================================
# 6. 有签到记录的课程禁止删除
# =========================================================================
def test_lesson_with_checkin_cannot_be_deleted(client, auth_headers):
    """已有签到记录的排课不可删除（防丢上课凭证）。"""
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=10)
    lid = _mk_lesson(client, auth_headers, sid, cid)

    r = client.delete(f'/api/v1/lessons/{lid}', headers=auth_headers)
    assert r.status_code == 200, '无签到时应可删'

    lid2 = _mk_lesson(client, auth_headers, sid, cid,
                      date='2026-09-16', start='14:00', end='15:00')
    client.post(f'/api/v1/checkin/{lid2}', json={'student_ids': [sid]},
                headers=auth_headers)

    r2 = client.delete(f'/api/v1/lessons/{lid2}', headers=auth_headers)
    assert r2.status_code == 409, f'有签到记录应禁删，实际 {r2.status_code}'
    assert '签到记录' in r2.json()['detail']


# =========================================================================
# 7. 其他已验证行为
# =========================================================================
def test_student_crud_roundtrip(client, auth_headers):
    sid = _mk_student(client, auth_headers, name='原名', grade='初一')
    r = client.put(f'/api/v1/students/{sid}',
                   json={'name': '改名后', 'grade': '初二', 'class_group': 'A班'},
                   headers=auth_headers)
    assert r.status_code == 200
    got = client.get(f'/api/v1/students/{sid}', headers=auth_headers).json()
    assert got['name'] == '改名后'
    assert got['grade'] == '初二'
    assert got['class_group'] == 'A班'


def test_student_empty_name_rejected(client, auth_headers):
    r = client.post('/api/v1/students', json={'name': '   '}, headers=auth_headers)
    assert r.status_code == 400
    assert '姓名不能为空' in r.json()['detail']


def test_package_total_lessons_must_be_positive(client, auth_headers):
    sid = _mk_student(client, auth_headers)
    for bad in (0, -1):
        r = client.post('/api/v1/packages',
                        json={'student_id': sid, 'name': 'x', 'total_lessons': bad},
                        headers=auth_headers)
        assert r.status_code == 400, f'total_lessons={bad} 应 400'
        assert '总课时必须大于 0' in r.json()['detail']


def test_package_requires_existing_student(client, auth_headers):
    r = client.post('/api/v1/packages',
                    json={'student_id': 999999, 'name': 'x', 'total_lessons': 5},
                    headers=auth_headers)
    assert r.status_code == 404


def test_soft_delete_hides_from_list(client, auth_headers):
    sid = _mk_student(client, auth_headers, name='待删')
    assert client.get('/api/v1/students', headers=auth_headers).json()['total'] == 1
    client.delete(f'/api/v1/students/{sid}', headers=auth_headers)
    assert client.get('/api/v1/students', headers=auth_headers).json()['total'] == 0
    # 详情也应 404
    assert client.get(f'/api/v1/students/{sid}',
                      headers=auth_headers).status_code == 404


def test_student_keyword_search(client, auth_headers):
    _mk_student(client, auth_headers, name='张三', phone='13900001111')
    _mk_student(client, auth_headers, name='李四', phone='13900002222')

    r = client.get('/api/v1/students?keyword=张三', headers=auth_headers).json()
    assert r['total'] == 1
    r2 = client.get('/api/v1/students?keyword=13900002222', headers=auth_headers).json()
    assert r2['total'] == 1
    assert r2['list'][0]['name'] == '李四'


def test_today_overview_shape(client, auth_headers):
    """今日概览返回结构稳定（首页依赖）。"""
    d = client.get('/api/v1/lessons/today', headers=auth_headers).json()
    for k in ('date', 'lesson_count', 'signed_count', 'pending_count',
              'student_count', 'lessons'):
        assert k in d, f'今日概览缺少字段 {k}'


def test_week_schedule_range(client, auth_headers):
    sid = _mk_student(client, auth_headers)
    cid = _mk_coach(client, auth_headers)
    _mk_lesson(client, auth_headers, sid, cid, date='2026-09-15')

    d = client.get('/api/v1/lessons/week?start=2026-09-14&end=2026-09-20',
                   headers=auth_headers).json()
    assert d['start'] == '2026-09-14'
    assert d['end'] == '2026-09-20'
    assert len(d['list']) == 1

    # 区间外应为空
    d2 = client.get('/api/v1/lessons/week?start=2026-10-01&end=2026-10-07',
                    headers=auth_headers).json()
    assert len(d2['list']) == 0


def test_checkin_history_includes_student_name(client, auth_headers):
    """签到历史应附带 student_name（前端直接展示）。"""
    sid = _mk_student(client, auth_headers, name='签到学员')
    cid = _mk_coach(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=5)
    lid = _mk_lesson(client, auth_headers, sid, cid)
    client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]},
                headers=auth_headers)

    h = client.get('/api/v1/checkins', headers=auth_headers).json()['list']
    assert len(h) == 1
    assert h[0]['student_name'] == '签到学员'


def test_package_list_includes_student_name(client, auth_headers):
    sid = _mk_student(client, auth_headers, name='包学员')
    _mk_package(client, auth_headers, sid, total=5)

    lst = client.get('/api/v1/packages', headers=auth_headers).json()['list']
    assert lst[0]['student_name'] == '包学员'


def test_coach_payout_calculation(client, auth_headers):
    """per_lesson 模式：已上课时 × 课时费。"""
    cid = _mk_coach(client, auth_headers, role='parttime',
                    salary_mode='per_lesson', lesson_rate=200)
    sid = _mk_student(client, auth_headers)
    _mk_package(client, auth_headers, sid, total=5)
    lid = _mk_lesson(client, auth_headers, sid, cid)
    client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]},
                headers=auth_headers)

    p = client.get(f'/api/v1/coaches/{cid}/payout', headers=auth_headers).json()
    assert p['total_lessons'] == 1
    assert p['signed_lessons'] == 1
    assert p['payout'] == 200.0, f'课时费应 200，实际 {p["payout"]}'
