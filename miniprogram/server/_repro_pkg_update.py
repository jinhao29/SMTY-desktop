# -*- coding: utf-8 -*-
"""P0 复现/验收脚本：PUT /packages/{id} 是否把 remaining_lessons 重置为 total_lessons。

手工整链路验收用（等价用例已固化在 tests/test_data_integrity.py）。
期望输出：签到一次后 19/20 → 仅改名保存后仍是 19/20 → 加课 20→25 后 24/25 → PASS。
"""
import os
import sys
import tempfile

os.environ.setdefault('MP_SECRET', 'repro-secret-0123456789abcdef')
os.environ.setdefault('MP_MODE', 'shangmen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database  # noqa: E402
database.DATA_DIR = tempfile.mkdtemp(prefix='mp_repro_')

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from passlib_lite import issue_token  # noqa: E402

with TestClient(main.app) as c:
    conn = database.get_conn_for_mode('shangmen')
    conn.execute(
        "INSERT INTO users(phone,password_hash,name,role,created_at,updated_at) "
        "VALUES('13800000000','x','t','coach','2026-01-01','2026-01-01')")
    conn.commit()
    uid = conn.execute("SELECT id FROM users WHERE phone='13800000000'").fetchone()[0]
    h = {'Authorization': 'Bearer ' + issue_token(uid, '13800000000')}

    sid = c.post('/api/v1/students', json={'name': '小明'}, headers=h).json()['id']
    pid = c.post('/api/v1/packages', json={
        'student_id': sid, 'name': '20课时包', 'total_lessons': 20, 'price': 2000,
    }, headers=h).json()['id']
    lid = c.post('/api/v1/lessons', json={
        'student_ids': [sid], 'coach_id': 1, 'date': '2026-09-14',
        'start_time': '10:00', 'end_time': '11:00'}, headers=h).json()['id']
    c.post(f'/api/v1/checkin/{lid}', json={'student_ids': [sid]}, headers=h)

    before = c.get(f'/api/v1/packages/{pid}', headers=h).json()
    print(f"签到一次后: remaining={before['remaining_lessons']}/{before['total_lessons']}")

    # 教练只是改个名字
    c.put(f'/api/v1/packages/{pid}', headers=h, json={
        'student_id': sid, 'name': '20课时包(改名)', 'total_lessons': 20, 'price': 2000,
        'paid_amount': -1, 'expire_date': '', 'purchase_date': ''})

    after = c.get(f'/api/v1/packages/{pid}', headers=h).json()
    stu = c.get(f'/api/v1/students/{sid}', headers=h).json()
    print(f"仅改名保存后: remaining={after['remaining_lessons']}/{after['total_lessons']}"
          f"  学员剩余课时={stu['remaining_lessons']}")

    ok = (after['remaining_lessons'] == before['remaining_lessons'] == 19
          and stu['remaining_lessons'] == 19)

    # 加课场景：总课时 20→25，剩余应同步 +5（19→24），不是回到满额
    c.put(f'/api/v1/packages/{pid}', headers=h, json={
        'student_id': sid, 'name': '包', 'total_lessons': 25, 'price': 2500,
        'paid_amount': -1, 'expire_date': '', 'purchase_date': ''})
    grown = c.get(f'/api/v1/packages/{pid}', headers=h).json()
    print(f"总课时 20→25 后: remaining={grown['remaining_lessons']}/{grown['total_lessons']}"
          f"（期望 24/25）")
    ok = ok and grown['remaining_lessons'] == 24

    print(">>> PASS：编辑不再重置已消耗课时（改名前 19 / 改名后 "
          f"{after['remaining_lessons']}）" if ok else ">>> FAIL：仍有课时被重置")
