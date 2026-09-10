# -*- coding: utf-8 -*-
"""课时包接口：CRUD + 统计。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from database import (execute, query, query_one, now_str, today_str,
                      recalc_student_remaining, package_fee_stats)

router = APIRouter(prefix='/api/v1/packages', tags=['packages'])


class PackageBody(BaseModel):
    student_id: int
    name: str
    total_lessons: int
    expire_date: str = ''
    purchase_date: str = ''
    price: float = 0
    paid_amount: float = -1


def _fetch(pkg_id: int):
    row = query_one("SELECT * FROM lesson_packages WHERE id=? AND deleted=0", (pkg_id,))
    if not row:
        raise HTTPException(status_code=404, detail='课时包不存在')
    return row


def _refresh_status():
    """过期状态刷新：expire_date < 今天 且仍有剩余 → expired。"""
    execute("UPDATE lesson_packages SET status='expired', updated_at=? "
            "WHERE deleted=0 AND status='active' AND expire_date!='' AND expire_date<? "
            "AND remaining_lessons>0", (now_str(), today_str()))


@router.get('')
def list_packages(student_id: int = 0, status: str = Query('')):
    _refresh_status()
    where, params = ['deleted=0'], []
    if student_id:
        where.append('student_id=?')
        params.append(student_id)
    if status:
        where.append('status=?')
        params.append(status)
    rows = query(f"SELECT * FROM lesson_packages WHERE {' AND '.join(where)} "
                 "ORDER BY id DESC", params)
    names = {s['id']: s['name'] for s in query("SELECT id,name FROM students")}
    for r in rows:
        r['student_name'] = names.get(r['student_id'], f"#{r['student_id']}")
    return {'stats': package_fee_stats(), 'list': rows}


@router.get('/stats')
def stats():
    _refresh_status()
    s = package_fee_stats()
    s['student_count'] = query_one(
        "SELECT COUNT(DISTINCT student_id) AS c FROM lesson_packages WHERE deleted=0")['c']
    return s


@router.get('/{pkg_id}')
def get_package(pkg_id: int):
    return _fetch(pkg_id)


@router.post('')
def create_package(body: PackageBody):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail='名称不能为空')
    if body.total_lessons <= 0:
        raise HTTPException(status_code=400, detail='总课时必须大于 0')
    if not query_one("SELECT id FROM students WHERE id=? AND deleted=0", (body.student_id,)):
        raise HTTPException(status_code=404, detail='学员不存在')
    pid = execute(
        "INSERT INTO lesson_packages(student_id,name,total_lessons,remaining_lessons,"
        "expire_date,purchase_date,price,paid_amount,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,'active',?,?)",
        (body.student_id, body.name.strip(), body.total_lessons, body.total_lessons,
         body.expire_date, body.purchase_date or today_str(), body.price,
         body.paid_amount, now_str(), now_str()))
    recalc_student_remaining(body.student_id)
    return {'id': pid}


@router.put('/{pkg_id}')
def update_package(pkg_id: int, body: PackageBody):
    pkg = _fetch(pkg_id)
    execute(
        "UPDATE lesson_packages SET student_id=?,name=?,total_lessons=?,remaining_lessons=?,"
        "expire_date=?,purchase_date=?,price=?,paid_amount=?,updated_at=? WHERE id=?",
        (body.student_id, body.name.strip(), body.total_lessons,
         body.total_lessons, body.expire_date, body.purchase_date or pkg['purchase_date'],
         body.price, body.paid_amount, now_str(), pkg_id))
    recalc_student_remaining(body.student_id)
    return {'ok': True}


@router.delete('/{pkg_id}')
def delete_package(pkg_id: int):
    pkg = _fetch(pkg_id)
    execute("UPDATE lesson_packages SET deleted=1, updated_at=? WHERE id=?", (now_str(), pkg_id))
    recalc_student_remaining(pkg['student_id'])
    return {'ok': True}
