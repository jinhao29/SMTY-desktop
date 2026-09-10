# -*- coding: utf-8 -*-
"""教练接口：CRUD + 排班 + 薪资统计。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from database import execute, query, query_one, now_str

router = APIRouter(prefix='/api/v1/coaches', tags=['coaches'])

ROLE_LABELS = {'fulltime': '全职', 'parttime': '兼职',
               'partner_level1': '一级合伙人', 'partner_level2': '二级合伙人'}


class CoachBody(BaseModel):
    name: str
    phone: str = ''
    role: str = 'parttime'
    superior_id: Optional[int] = None
    status: str = 'active'
    salary_mode: str = 'per_lesson'
    base_salary: float = 0
    lesson_rate: float = 0
    commission_rate: float = 0
    specialties: List[str] = []


def _fetch(coach_id: int):
    row = query_one("SELECT * FROM coaches WHERE id=? AND deleted=0", (coach_id,))
    if not row:
        raise HTTPException(status_code=404, detail='教练不存在')
    return row


@router.get('')
def list_coaches(keyword: str = Query(''), role: str = Query(''), status: str = Query(''),
                 specialty: str = Query(''), page: int = 1, page_size: int = 50):
    where, params = ['deleted=0'], []
    if keyword:
        where.append('(name LIKE ? OR phone LIKE ?)')
        params += [f'%{keyword}%'] * 2
    if role:
        where.append('role=?')
        params.append(role)
    if status:
        where.append('status=?')
        params.append(status)
    if specialty:
        where.append('specialties LIKE ?')
        params.append(f'%{specialty}%')
    cond = ' AND '.join(where)
    total = query_one(f"SELECT COUNT(*) AS c FROM coaches WHERE {cond}", params)['c']
    rows = query(f"SELECT * FROM coaches WHERE {cond} ORDER BY id DESC LIMIT ? OFFSET ?",
                 params + [page_size, (page - 1) * page_size])
    stats = {k: query_one(f"SELECT COUNT(*) AS c FROM coaches WHERE deleted=0 AND role='{k}'")['c']
             for k in ROLE_LABELS}
    stats['total'] = query_one("SELECT COUNT(*) AS c FROM coaches WHERE deleted=0")['c']
    return {'total': total, 'page': page, 'stats': stats, 'list': rows}


@router.get('/{coach_id}')
def get_coach(coach_id: int):
    return _fetch(coach_id)


@router.post('')
def create_coach(body: CoachBody):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail='姓名不能为空')
    cid = execute(
        "INSERT INTO coaches(name,phone,role,superior_id,status,salary_mode,base_salary,"
        "lesson_rate,commission_rate,specialties,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (body.name.strip(), body.phone, body.role, body.superior_id, body.status,
         body.salary_mode, body.base_salary, body.lesson_rate, body.commission_rate,
         __import__('json').dumps(body.specialties, ensure_ascii=False), now_str(), now_str()))
    return {'id': cid}


@router.put('/{coach_id}')
def update_coach(coach_id: int, body: CoachBody):
    _fetch(coach_id)
    execute(
        "UPDATE coaches SET name=?,phone=?,role=?,superior_id=?,status=?,salary_mode=?,"
        "base_salary=?,lesson_rate=?,commission_rate=?,specialties=?,updated_at=? WHERE id=?",
        (body.name.strip(), body.phone, body.role, body.superior_id, body.status,
         body.salary_mode, body.base_salary, body.lesson_rate, body.commission_rate,
         __import__('json').dumps(body.specialties, ensure_ascii=False), now_str(), coach_id))
    return {'ok': True}


@router.delete('/{coach_id}')
def delete_coach(coach_id: int):
    _fetch(coach_id)
    execute("UPDATE coaches SET deleted=1, updated_at=? WHERE id=?", (now_str(), coach_id))
    return {'ok': True}


@router.get('/{coach_id}/schedule')
def coach_schedule(coach_id: int, start: str = Query(''), end: str = Query('')):
    _fetch(coach_id)
    if start and end:
        rows = query("SELECT * FROM lessons WHERE coach_id=? AND date BETWEEN ? AND ? "
                     "ORDER BY date, start_time", (coach_id, start, end))
    else:
        rows = query("SELECT * FROM lessons WHERE coach_id=? ORDER BY date DESC, start_time",
                     (coach_id,))
    return {'list': rows}


@router.get('/{coach_id}/payout')
def coach_payout(coach_id: int):
    """课时统计 + 薪资结算：已上课时 × 课时费 + 底薪分摊。"""
    coach = _fetch(coach_id)
    rows = query("SELECT status FROM lessons WHERE coach_id=?", (coach_id,))
    total_lessons = len(rows)
    signed = sum(1 for r in rows if r['status'] in ('signed_in', 'signed_out'))
    if coach['salary_mode'] == 'fixed':
        payout = coach['base_salary']
    elif coach['salary_mode'] == 'base_plus_commission':
        payout = coach['base_salary'] + signed * coach['lesson_rate'] * (1 + coach['commission_rate'] / 100)
    else:  # per_lesson / dividend 兜底按课时费
        payout = signed * coach['lesson_rate']
    return {'coach': coach, 'total_lessons': total_lessons, 'signed_lessons': signed,
            'payout': round(payout, 2),
            'role_label': ROLE_LABELS.get(coach['role'], coach['role'])}
