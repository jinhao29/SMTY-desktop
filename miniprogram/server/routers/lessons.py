# -*- coding: utf-8 -*-
"""排课接口：CRUD + 周课表 + 今日概览。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from database import execute, query, query_one, now_str, today_str
from deps import get_current_user

router = APIRouter(prefix='/api/v1/lessons', tags=['lessons'],
                   dependencies=[Depends(get_current_user)])


class LessonBody(BaseModel):
    student_ids: List[int]
    coach_id: int
    date: str
    start_time: str
    end_time: str
    type: str = 'private'
    location: str = ''
    note: str = ''


def _fetch(lesson_id: int):
    row = query_one("SELECT * FROM lessons WHERE id=?", (lesson_id,))
    if not row:
        raise HTTPException(status_code=404, detail='排课不存在')
    return row


@router.get('')
def list_lessons(date_from: str = Query(''), date_to: str = Query(''),
                 coach_id: int = 0, student_id: int = 0):
    where, params = ['1=1'], []
    if date_from:
        where.append('date>=?')
        params.append(date_from)
    if date_to:
        where.append('date<=?')
        params.append(date_to)
    if coach_id:
        where.append('coach_id=?')
        params.append(coach_id)
    rows = query(f"SELECT * FROM lessons WHERE {' AND '.join(where)} ORDER BY date, start_time",
                 params)
    if student_id:
        rows = [r for r in rows if student_id in (r.get('student_ids') or [])]
    return {'list': rows}


@router.get('/today')
def today_overview():
    """首页今日概览：排课数/已签到/未签到/总学员数 + 今日课程列表。"""
    today = today_str()
    rows = query("SELECT * FROM lessons WHERE date=? ORDER BY start_time", (today,))
    signed = sum(1 for r in rows if r['status'] in ('signed_in', 'signed_out'))
    total_students = query_one("SELECT COUNT(*) AS c FROM students WHERE deleted=0 AND status='active'")['c']
    return {'date': today, 'lesson_count': len(rows), 'signed_count': signed,
            'pending_count': len(rows) - signed, 'student_count': total_students,
            'lessons': rows}


@router.get('/week')
def week_schedule(start: str = Query(..., description='周一日期 YYYY-MM-DD'),
                  end: str = Query(..., description='周日日期 YYYY-MM-DD')):
    rows = query("SELECT * FROM lessons WHERE date BETWEEN ? AND ? ORDER BY date, start_time",
                 (start, end))
    return {'start': start, 'end': end, 'list': rows}


@router.get('/{lesson_id}')
def get_lesson(lesson_id: int):
    lesson = _fetch(lesson_id)
    students = []
    for sid in (lesson.get('student_ids') or []):
        s = query_one("SELECT id,name,grade,remaining_lessons FROM students WHERE id=? AND deleted=0", (sid,))
        if s:
            students.append(s)
    lesson['students'] = students
    return lesson


@router.post('')
def create_lesson(body: LessonBody):
    if not body.student_ids:
        raise HTTPException(status_code=400, detail='至少选择一名学员')
    if not body.date or not body.start_time:
        raise HTTPException(status_code=400, detail='日期与开始时间必填')
    # 冲突检测：同一教练同时段已有排课（不论状态）
    conflict = query_one(
        "SELECT id FROM lessons WHERE coach_id=? AND date=? "
        "AND NOT(end_time<=? OR start_time>=?)",
        (body.coach_id, body.date, body.start_time, body.end_time))
    if conflict:
        raise HTTPException(status_code=409, detail='该教练此时段已有排课')
    lid = execute(
        "INSERT INTO lessons(student_ids,coach_id,date,start_time,end_time,type,location,"
        "status,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'pending',?,?,?)",
        (__import__('json').dumps(body.student_ids), body.coach_id, body.date,
         body.start_time, body.end_time, body.type, body.location, body.note,
         now_str(), now_str()))
    return {'id': lid}


@router.put('/{lesson_id}')
def update_lesson(lesson_id: int, body: LessonBody):
    _fetch(lesson_id)
    execute(
        "UPDATE lessons SET student_ids=?,coach_id=?,date=?,start_time=?,end_time=?,type=?,"
        "location=?,note=?,updated_at=? WHERE id=?",
        (__import__('json').dumps(body.student_ids), body.coach_id, body.date,
         body.start_time, body.end_time, body.type, body.location, body.note,
         now_str(), lesson_id))
    return {'ok': True}


@router.delete('/{lesson_id}')
def delete_lesson(lesson_id: int):
    _fetch(lesson_id)
    if query_one("SELECT id FROM checkin_records WHERE lesson_id=? LIMIT 1", (lesson_id,)):
        raise HTTPException(status_code=409, detail='已有签到记录，不可删除')
    execute("DELETE FROM lessons WHERE id=?", (lesson_id,))
    return {'ok': True}
