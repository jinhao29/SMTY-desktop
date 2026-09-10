# -*- coding: utf-8 -*-
"""学员接口：CRUD + 课时记录 + 签到历史。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from database import execute, query, query_one, now_str, recalc_student_remaining
from deps import get_current_user

# 全路由强制鉴权：未携带有效 token 一律 401。
# 此前仅 auth/ocr 挂了鉴权，其余业务路由裸奔——同网段任何人可直接读写全部学员数据。
router = APIRouter(prefix='/api/v1/students', tags=['students'],
                   dependencies=[Depends(get_current_user)])


class StudentBody(BaseModel):
    name: str
    phone: str = ''
    grade: str = ''
    parent_phone: str = ''
    address: str = ''
    class_group: str = ''
    status: str = 'active'
    expire_date: str = ''


def _fetch(student_id: int):
    row = query_one("SELECT * FROM students WHERE id=? AND deleted=0", (student_id,))
    if not row:
        raise HTTPException(status_code=404, detail='学员不存在')
    return row


@router.get('')
def list_students(
    keyword: str = Query('', description='姓名/手机号搜索'),
    status: str = Query(''),
    class_group: str = Query(''),
    page: int = 1, page_size: int = 50,
):
    where, params = ['deleted=0'], []
    if keyword:
        where.append("(name LIKE ? OR phone LIKE ? OR parent_phone LIKE ?)")
        params += [f'%{keyword}%'] * 3
    if status:
        where.append('status=?')
        params.append(status)
    if class_group:
        where.append('class_group=?')
        params.append(class_group)
    cond = ' AND '.join(where)
    total = query_one(f"SELECT COUNT(*) AS c FROM students WHERE {cond}", params)['c']
    rows = query(f"SELECT * FROM students WHERE {cond} ORDER BY id DESC LIMIT ? OFFSET ?",
                 params + [page_size, (page - 1) * page_size])
    return {'total': total, 'page': page, 'list': rows}


@router.get('/{student_id}')
def get_student(student_id: int):
    return _fetch(student_id)


@router.post('')
def create_student(body: StudentBody):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail='姓名不能为空')
    sid = execute(
        "INSERT INTO students(name,phone,grade,parent_phone,address,class_group,status,"
        "remaining_lessons,expire_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (body.name.strip(), body.phone, body.grade, body.parent_phone, body.address,
         body.class_group, body.status, 0, body.expire_date, now_str(), now_str()))
    return {'id': sid}


@router.put('/{student_id}')
def update_student(student_id: int, body: StudentBody):
    _fetch(student_id)
    execute(
        "UPDATE students SET name=?,phone=?,grade=?,parent_phone=?,address=?,class_group=?,"
        "status=?,expire_date=?,updated_at=? WHERE id=?",
        (body.name.strip(), body.phone, body.grade, body.parent_phone, body.address,
         body.class_group, body.status, body.expire_date, now_str(), student_id))
    return {'ok': True}


@router.delete('/{student_id}')
def delete_student(student_id: int):
    _fetch(student_id)
    execute("UPDATE students SET deleted=1, updated_at=? WHERE id=?", (now_str(), student_id))
    return {'ok': True}


@router.get('/{student_id}/lessons')
def student_lessons(student_id: int):
    """学员课时记录：排课 + 消课明细（明细与桌面端「汇总/明细」口径一致）。"""
    _fetch(student_id)
    rows = query(
        "SELECT l.* FROM lessons l WHERE l.student_ids LIKE ? ORDER BY l.date DESC, l.start_time DESC",
        (f'%{student_id}%',))
    lessons = [r for r in rows if student_id in (r.get('student_ids') or [])]
    packages = query("SELECT * FROM lesson_packages WHERE student_id=? AND deleted=0 "
                     "ORDER BY purchase_date DESC", (student_id,))
    checkins = query("SELECT * FROM checkin_records WHERE student_id=? ORDER BY timestamp DESC",
                     (student_id,))
    return {'lessons': lessons, 'packages': packages, 'checkins': checkins}


@router.get('/{student_id}/checkins')
def student_checkins(student_id: int, date: str = Query('')):
    _fetch(student_id)
    if date:
        rows = query("SELECT * FROM checkin_records WHERE student_id=? AND timestamp LIKE ? "
                     "ORDER BY timestamp DESC", (student_id, f'{date}%'))
    else:
        rows = query("SELECT * FROM checkin_records WHERE student_id=? ORDER BY timestamp DESC",
                     (student_id,))
    return {'list': rows}
