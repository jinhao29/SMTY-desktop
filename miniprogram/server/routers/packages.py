# -*- coding: utf-8 -*-
"""课时包接口：CRUD + 统计 + 续费提醒。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from database import (execute, query, query_one, now_str, today_str,
                      recalc_student_remaining, package_fee_stats)
from deps import get_current_user

# 续费提醒阈值：与 Android RenewalThresholds 同源（勿自创），原因优先级与
# OperationRepository.getRenewalAlerts 一致：已用完 > 已过期 > 剩余不足 > 即将过期
RENEWAL_LOW_BALANCE = 3        # 剩余 1..3 = 余额不足
RENEWAL_NEAR_EXPIRY_DAYS = 30  # 0..30 天内到期 = 即将过期

router = APIRouter(prefix='/api/v1/packages', tags=['packages'],
                   dependencies=[Depends(get_current_user)])


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


def _renewal_reason(remaining: int, expire_date: str, today: str):
    """与 Android OperationRepository.getRenewalAlerts 同源的原因判定。

    返回 None = 不需要提醒。优先级：已用完 > 已过期 > 剩余不足 > 即将过期。
    不看 status 字段（refresh 时机两套，以事实数据为准）。
    """
    if remaining == 0:
        return '已用完', -1
    if expire_date and expire_date < today:
        return '已过期', -1
    if 1 <= remaining <= RENEWAL_LOW_BALANCE:
        return '剩余不足', -1
    if expire_date:
        try:
            dte = (date.fromisoformat(expire_date) - date.fromisoformat(today)).days
            if 0 <= dte <= RENEWAL_NEAR_EXPIRY_DAYS:
                return '即将过期', dte
        except ValueError:
            pass
    return None, -1


@router.get('/renewal-alerts')
def renewal_alerts():
    """续费 / 到期提醒名单（纯查询，不改任何数据、不动备份格式）。"""
    _refresh_status()
    rows = query(
        "SELECT p.id, p.student_id, p.name AS package_name, p.total_lessons, "
        "p.remaining_lessons, p.expire_date, s.name AS student_name "
        "FROM lesson_packages p LEFT JOIN students s ON s.id=p.student_id AND s.deleted=0 "
        "WHERE p.deleted=0")
    today = today_str()
    out = []
    for r in rows:
        reason, dte = _renewal_reason(r['remaining_lessons'], r['expire_date'], today)
        if not reason:
            continue
        out.append({
            'student_id': r['student_id'],
            'student_name': r['student_name'] or f"#{r['student_id']}",
            'package_id': r['id'], 'package_name': r['package_name'],
            'remaining_lessons': r['remaining_lessons'],
            'expire_date': r['expire_date'] or '',
            'days_to_expire': dte if reason == '即将过期' else (-1 if reason == '已过期' else -1),
            'reason': reason,
        })
    # 已过期最先；即将过期按天数升序；无期限的（已用完/剩余不足）殿后，再按剩余课时升序
    def _sort_key(x):
        if x['reason'] == '已过期':
            return (0, 0, x['remaining_lessons'])
        if x['days_to_expire'] >= 0:
            return (1, x['days_to_expire'], x['remaining_lessons'])
        return (2, 0, x['remaining_lessons'])

    out.sort(key=_sort_key)
    return {'count': len(out), 'list': out}


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
    # 剩余课时与总课时解耦：编辑（改名/改价/改有效期）不得重置已消耗课时，
    # 否则「改个包名 → 已消课时全部复活」是静默的数据损坏。
    # 仅当总课时增加时同步补足剩余（加课场景）；总课时减少时上限收敛到新总数，
    # 避免 remaining > total 这种自相矛盾的状态。
    remaining = min(pkg['remaining_lessons'] + max(0, body.total_lessons - pkg['total_lessons']),
                    body.total_lessons)
    old_student_id = pkg['student_id']
    execute(
        "UPDATE lesson_packages SET student_id=?,name=?,total_lessons=?,remaining_lessons=?,"
        "expire_date=?,purchase_date=?,price=?,paid_amount=?,updated_at=? WHERE id=?",
        (body.student_id, body.name.strip(), body.total_lessons,
         remaining, body.expire_date, body.purchase_date or pkg['purchase_date'],
         body.price, body.paid_amount, now_str(), pkg_id))
    # 换学员时旧学员的汇总同样要重算，否则那份课时会同时挂在两个人头上
    if old_student_id != body.student_id:
        recalc_student_remaining(old_student_id)
    recalc_student_remaining(body.student_id)
    return {'ok': True}


@router.delete('/{pkg_id}')
def delete_package(pkg_id: int):
    pkg = _fetch(pkg_id)
    execute("UPDATE lesson_packages SET deleted=1, updated_at=? WHERE id=?", (now_str(), pkg_id))
    recalc_student_remaining(pkg['student_id'])
    return {'ok': True}
