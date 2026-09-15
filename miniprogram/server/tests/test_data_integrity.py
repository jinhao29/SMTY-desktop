# -*- coding: utf-8 -*-
"""数据完整性回归用例。

固化 2026-09-14 全面审查发现的**静默数据损坏**：
- 编辑课时包重置剩余课时（改名/改价/改有效期都会触发）
- 课时包转移学员时旧学员汇总不重算
- 学员备注只进本机不进库（服务器模式填了等于没填）
- 备份导入的列名来自请求 JSON（注入面）

这些 bug 的共同特征是「界面显示成功、数据已经不对、无提示无异常」——
因此每条都断言**具体数字或具体值**，不靠界面反馈。
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


def _mk_package(client, headers, sid, total=20, price=2000, paid=-1, **kw):
    r = client.post('/api/v1/packages', json={
        'student_id': sid, 'name': '课时包', 'total_lessons': total,
        'price': price, 'paid_amount': paid, **kw}, headers=headers)
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


# =========================================================================
# 3. 学员备注：服务器模式必须真存下来（P1-②）
# =========================================================================
def test_student_note_persists(client, auth_headers):
    """建号时写的备注能回读，改号时改的备注也能回读。"""
    note = '暑期班，家长要求 18:00 前结束'
    r = client.post('/api/v1/students', json={'name': '小明', 'note': note}, headers=auth_headers)
    assert r.status_code == 200, r.text
    sid = r.json()['id']
    assert _student(client, auth_headers, sid)['note'] == note, '新建时备注丢失'

    client.put(f'/api/v1/students/{sid}',
               json={'name': '小明', 'note': '已结课'}, headers=auth_headers)
    assert _student(client, auth_headers, sid)['note'] == '已结课', '编辑时备注丢失'


def test_student_note_defaults_empty(client, auth_headers):
    """不传备注时存空串，不是 None（前端 v-model 直接绑）"""
    sid = _mk_student(client, auth_headers, '无备注学员')
    assert _student(client, auth_headers, sid)['note'] == ''


def test_legacy_db_migration_adds_note(tmp_path):
    """老库（students 无 note 列）升级：补列、旧数据保留、重复执行不报错。"""
    import sqlite3

    import database

    conn = sqlite3.connect(str(tmp_path / 'legacy.db'))
    conn.executescript("""
        CREATE TABLE students (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            phone TEXT DEFAULT '', grade TEXT DEFAULT '', parent_phone TEXT DEFAULT '',
            address TEXT DEFAULT '', class_group TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active', remaining_lessons INTEGER NOT NULL DEFAULT 0,
            expire_date TEXT DEFAULT '', created_at TEXT, updated_at TEXT,
            deleted INTEGER NOT NULL DEFAULT 0);
        INSERT INTO students(name) VALUES('老学员');
    """)
    conn.commit()

    database._migrate(conn)
    cols = {r[1] for r in conn.execute('PRAGMA table_info(students)')}
    assert 'note' in cols, '迁移未补 note 列'
    row = conn.execute('SELECT name, note FROM students').fetchone()
    assert row[0] == '老学员', '迁移不得动既有数据'
    assert row[1] == '', '既有行补列后应为空串'

    database._migrate(conn)  # 幂等：第二次不得抛 duplicate column
    conn.close()


# =========================================================================
# 4. 备份导入：列名必须过白名单（P1-①）
# =========================================================================
def _import(client, headers, **tables):
    body = {'mode': 'shangmen', 'merge': True, **tables}
    return client.post('/api/v1/backup/import', json=body, headers=headers)


def test_import_accepts_known_columns(client, auth_headers):
    """合法备份正常导入（含 note 这类业务列）。"""
    r = _import(client, auth_headers, students=[
        {'id': 1, 'name': '导入学员', 'note': '来自备份', 'deleted': 0,
         'created_at': '2026-01-01 00:00:00', 'updated_at': '2026-01-01 00:00:00'}])
    assert r.status_code == 200, r.text
    assert r.json()['imported']['students'] == 1
    assert _student(client, auth_headers, 1)['note'] == '来自备份'


def test_import_ignores_display_field(client, auth_headers):
    """导出/接口附带的 student_name 不是表列，应忽略而不是拒绝。"""
    _mk_student(client, auth_headers, '甲')
    r = _import(client, auth_headers, lesson_packages=[
        {'id': 1, 'student_id': 1, 'name': '包', 'total_lessons': 10,
         'remaining_lessons': 10, 'price': 0, 'paid_amount': -1, 'status': 'active',
         'student_name': '甲'}])
    assert r.status_code == 200, r.text


def test_import_rejects_unknown_column(client, auth_headers):
    """未知列名（含注入尝试）一律 400。"""
    r = _import(client, auth_headers, students=[
        {'id': 1, 'name': '甲', "name) VALUES('x'); --": 'y'}])
    assert r.status_code == 400, r.text
    assert '未知列' in r.json()['detail']


def test_import_rejection_leaves_no_partial_write(client, auth_headers):
    """拒绝时一条都不落库——合法行排在前也不得先写进去。"""
    r = _import(client, auth_headers, students=[
        {'id': 1, 'name': '甲', 'deleted': 0},
        {'id': 2, 'name': '乙', 'evil': 1}])
    assert r.status_code == 400
    assert client.get('/api/v1/students', headers=auth_headers).json()['total'] == 0, \
        '被拒的导入不得留下前半份数据'


# =========================================================================
# 5. 超课时签到：允许签到，但必须明确回报（P2：不能静默不扣课）
# =========================================================================
def test_checkin_without_package_is_allowed_but_flagged(client, auth_headers):
    """一张课时包都没有 → 签到仍成功（现场不能白上课），但 overdue 必须回报。"""
    sid = _mk_student(client, auth_headers, '无包学员')
    cid = _mk_coach(client, auth_headers)
    lid = _mk_lesson(client, auth_headers, sid, cid)

    d = client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]},
                    headers=auth_headers).json()
    assert d['results'][0]['ok'] is True, '不得阻断现场签到'
    assert d['overdue'] == [{'student_id': sid, 'reason': 'no_package'}]
    assert _student(client, auth_headers, sid)['remaining_lessons'] == 0, '不得扣成负数'


def test_checkin_over_quota_is_flagged_not_negative(client, auth_headers):
    """1 课时包连签两节：第二次标记超额，课时保持 0 不为负。"""
    sid = _mk_student(client, auth_headers, '剩1课时')
    cid = _mk_coach(client, auth_headers)
    pid = _mk_package(client, auth_headers, sid, total=1, price=100)
    l1 = _mk_lesson(client, auth_headers, sid, cid, date='2026-09-21')
    l2 = _mk_lesson(client, auth_headers, sid, cid, date='2026-09-22')

    d1 = client.post(f'/api/v1/checkin/{l1}', json={'student_ids': [sid]},
                     headers=auth_headers).json()
    assert d1['overdue'] == [], '正常扣课不应报超额'
    assert _pkg(client, auth_headers, pid)['remaining_lessons'] == 0

    d2 = client.post(f'/api/v1/checkin/{l2}', json={'student_ids': [sid]},
                     headers=auth_headers).json()
    assert d2['results'][0]['ok'] is True
    assert d2['overdue'] == [{'student_id': sid, 'reason': 'no_active_package'}], \
        '已耗尽的包也算「没有可扣的课时」，必须回报'
    assert _pkg(client, auth_headers, pid)['remaining_lessons'] == 0, '不得扣成负数'
    assert _student(client, auth_headers, sid)['remaining_lessons'] == 0
    assert len(client.get(f'/api/v1/checkins?student_id={sid}',
                          headers=auth_headers).json()['list']) == 2, '两节课都要留痕'


def test_expired_package_checkin_is_flagged(client, auth_headers):
    """过期包有余量但不可扣 → 签到成功且余量不动，同时明确回报。"""
    sid = _mk_student(client, auth_headers, '过期包学员')
    cid = _mk_coach(client, auth_headers)
    pid = _mk_package(client, auth_headers, sid, total=10, price=1000,
                      expire_date='2026-01-01')
    client.get('/api/v1/packages', headers=auth_headers)  # 触发过期状态刷新
    assert _pkg(client, auth_headers, pid)['status'] == 'expired'

    lid = _mk_lesson(client, auth_headers, sid, cid, date='2026-09-23')
    d = client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]},
                    headers=auth_headers).json()
    assert d['overdue'] == [{'student_id': sid, 'reason': 'no_active_package'}], \
        '过期包不可扣，教练必须看得见'
    assert _pkg(client, auth_headers, pid)['remaining_lessons'] == 10, '过期包余量不应被动'


def test_checkout_never_flags_overdue(client, auth_headers):
    """签退不涉及扣课，不得报超额（否则天天误报）。"""
    sid = _mk_student(client, auth_headers, '甲')
    cid = _mk_coach(client, auth_headers)
    lid = _mk_lesson(client, auth_headers, sid, cid)
    client.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]}, headers=auth_headers)

    d = client.post(f'/api/v1/checkout/{lid}', json={'student_ids': [sid]},
                    headers=auth_headers).json()
    assert d['overdue'] == []
