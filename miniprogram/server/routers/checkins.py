# -*- coding: utf-8 -*-
"""签到接口：批量签到/签退 + 历史 + 未签退提醒。

签到时扣减学员有效课时包（优先最早到期的包），口径与桌面端「记录上课」一致。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from database import (execute, query, query_one, now_str, today_str,
                      recalc_student_remaining)
from deps import get_current_user

router = APIRouter(prefix='/api/v1', tags=['checkins'],
                   dependencies=[Depends(get_current_user)])


class CheckinBody(BaseModel):
    student_ids: List[int]
    note: str = ''


def _deduct_lesson(student_id: int):
    """按最早到期优先扣课时；扣完的包标记 exhausted。"""
    pkgs = query("SELECT * FROM lesson_packages WHERE student_id=? AND deleted=0 "
                 "AND status='active' AND remaining_lessons>0 "
                 "ORDER BY (expire_date='') ASC, expire_date ASC, id ASC",
                 (student_id,))
    if not pkgs:
        return
    pkg = pkgs[0]
    remaining = pkg['remaining_lessons'] - 1
    status = 'exhausted' if remaining <= 0 else 'active'
    execute("UPDATE lesson_packages SET remaining_lessons=?, status=?, updated_at=? WHERE id=?",
            (max(remaining, 0), status, now_str(), pkg['id']))
    recalc_student_remaining(student_id)


def _do_check(lesson_id: int, body: CheckinBody, check_type: str):
    lesson = query_one("SELECT * FROM lessons WHERE id=?", (lesson_id,))
    if not lesson:
        raise HTTPException(status_code=404, detail='排课不存在')
    valid_ids = set(lesson.get('student_ids') or [])
    results = []
    ts = now_str()
    for sid in body.student_ids:
        if valid_ids and sid not in valid_ids:
            results.append({'student_id': sid, 'ok': False, 'reason': '不在该课名单中'})
            continue
        dup = query_one("SELECT id FROM checkin_records WHERE lesson_id=? AND student_id=? AND type=?",
                        (lesson_id, sid, check_type))
        if dup:
            results.append({'student_id': sid, 'ok': False, 'reason': '已操作过'})
            continue
        execute("INSERT INTO checkin_records(student_id,lesson_id,type,timestamp,note) "
                "VALUES(?,?,?,?,?)", (sid, lesson_id, check_type, ts, body.note))
        if check_type == 'check_in':
            _deduct_lesson(sid)
        results.append({'student_id': sid, 'ok': True})
    if body.student_ids and all(r['ok'] for r in results):
        new_status = 'signed_in' if check_type == 'check_in' else 'signed_out'
        execute("UPDATE lessons SET status=?, updated_at=? WHERE id=?",
                (new_status, ts, lesson_id))
    return {'results': results, 'lesson_status': query_one(
        "SELECT status FROM lessons WHERE id=?", (lesson_id,))['status']}


@router.post('/checkin/{lesson_id}')
def checkin(lesson_id: int, body: CheckinBody):
    return _do_check(lesson_id, body, 'check_in')


@router.post('/checkout/{lesson_id}')
def checkout(lesson_id: int, body: CheckinBody):
    return _do_check(lesson_id, body, 'check_out')


@router.get('/checkins')
def checkin_history(date: str = Query(''), student_id: int = 0,
                    lesson_id: int = 0, type: str = Query('')):
    where, params = ['1=1'], []
    if date:
        where.append('timestamp LIKE ?')
        params.append(f'{date}%')
    if student_id:
        where.append('student_id=?')
        params.append(student_id)
    if lesson_id:
        where.append('lesson_id=?')
        params.append(lesson_id)
    if type:
        where.append('type=?')
        params.append(type)
    rows = query(f"SELECT * FROM checkin_records WHERE {' AND '.join(where)} "
                 "ORDER BY timestamp DESC LIMIT 500", params)
    # 附学员名
    names = {s['id']: s['name'] for s in query("SELECT id,name FROM students")}
    for r in rows:
        r['student_name'] = names.get(r['student_id'], f"#{r['student_id']}")
    return {'list': rows}


@router.get('/checkins/pending')
def pending_checkout(date: str = Query('')):
    """未签退提醒：指定日期（默认今天之前）已签到未签退的 学员×课程。"""
    before = date or today_str()
    rows = query(
        "SELECT c.student_id, c.lesson_id, MIN(c.timestamp) AS checkin_time, "
        "l.date, l.start_time, l.end_time, l.type, l.location "
        "FROM checkin_records c JOIN lessons l ON l.id=c.lesson_id "
        "WHERE c.type='check_in' AND l.date<=? AND NOT EXISTS ("
        "  SELECT 1 FROM checkin_records o WHERE o.lesson_id=c.lesson_id "
        "  AND o.student_id=c.student_id AND o.type='check_out') "
        "GROUP BY c.student_id, c.lesson_id ORDER BY l.date DESC, l.start_time",
        (before,))
    names = {s['id']: s['name'] for s in query("SELECT id,name FROM students")}
    for r in rows:
        r['student_name'] = names.get(r['student_id'], f"#{r['student_id']}")
    return {'list': rows}


@router.get('/checkins/today')
def today_pending_list():
    """今日待签到列表（含小班课聚合所需课程信息）。"""
    today = today_str()
    rows = query("SELECT * FROM lessons WHERE date=? ORDER BY start_time", (today,))
    names = {s['id']: s['name'] for s in query("SELECT id,name FROM students")}
    out = []
    for lesson in rows:
        sids = lesson.get('student_ids') or []
        checked = {r['student_id'] for r in query(
            "SELECT student_id FROM checkin_records WHERE lesson_id=? AND type='check_in'",
            (lesson['id'],))}
        checked_out = {r['student_id'] for r in query(
            "SELECT student_id FROM checkin_records WHERE lesson_id=? AND type='check_out'",
            (lesson['id'],))}
        out.append({
            **lesson,
            'students': [{'id': i, 'name': names.get(i, f'#{i}'),
                          'checked_in': i in checked, 'checked_out': i in checked_out}
                         for i in sids],
        })
    return {'date': today, 'list': out}
