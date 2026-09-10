# -*- coding: utf-8 -*-
"""备份接口：全量导出 JSON / 导入合并（校验模式标识）。

导出格式与桌面端/Android 备份对齐：顶层含 mode 标识 + 各业务表全量数据 + export_version。
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import (execute, query, query_one, now_str,
                      recalc_student_remaining, current_mode)

router = APIRouter(prefix='/api/v1/backup', tags=['backup'])

EXPORT_VERSION = 1

TABLES = ['students', 'coaches', 'lessons', 'lesson_packages', 'checkin_records']


@router.get('/export')
def export_backup(mode: str = Query('', description='模式标识，默认取当前请求数据空间')):
    data = {
        'export_version': EXPORT_VERSION,
        'mode': mode or current_mode(),
        'exported_at': now_str(),
    }
    for t in TABLES:
        if t == 'students':
            data[t] = query("SELECT * FROM students WHERE deleted=0")
        elif t == 'coaches':
            data[t] = query("SELECT * FROM coaches WHERE deleted=0")
        elif t == 'lesson_packages':
            data[t] = query("SELECT * FROM lesson_packages WHERE deleted=0")
        else:
            data[t] = query(f"SELECT * FROM {t}")
    return data


class ImportBody(BaseModel):
    mode: str
    merge: bool = True
    students: list = []
    coaches: list = []
    lessons: list = []
    lesson_packages: list = []
    checkin_records: list = []


@router.post('/import')
def import_backup(body: ImportBody):
    server_mode = current_mode()
    if body.mode != server_mode:
        raise HTTPException(status_code=409,
                            detail=f'模式不匹配：备份为 {body.mode}，当前数据空间为 {server_mode}，拒绝恢复')
    counts = {}
    for key, table, id_col in [
        ('students', 'students', 'id'),
        ('coaches', 'coaches', 'id'),
        ('lessons', 'lessons', 'id'),
        ('lesson_packages', 'lesson_packages', 'id'),
        ('checkin_records', 'checkin_records', 'id'),
    ]:
        n = 0
        for row in (getattr(body, key) or []):
            if not isinstance(row, dict) or id_col not in row:
                continue
            cols = {k: v for k, v in row.items() if k != 'student_name'}
            names = ','.join(cols.keys())
            marks = ','.join('?' * len(cols))
            if body.merge:
                # LWW 合并：updated_at（无则 timestamp）更新或目标不存在才写入
                ts_col = 'timestamp' if table == 'checkin_records' else 'updated_at'
                existing = query_one(f"SELECT {ts_col} AS ts FROM {table} WHERE id=?",
                                     (cols[id_col],))
                if existing and str(existing['ts'] or '') >= str(cols.get(ts_col) or ''):
                    continue
                sql = (f"INSERT INTO {table}({names}) VALUES({marks}) "
                       f"ON CONFLICT(id) DO UPDATE SET " +
                       ','.join(f"{k}=excluded.{k}" for k in cols if k != id_col))
            else:
                sql = f"INSERT OR REPLACE INTO {table}({names}) VALUES({marks})"
            try:
                execute(sql, tuple(cols.values()))
                n += 1
            except Exception:
                continue
        counts[key] = n
    # 恢复后重算学员剩余课时
    for s in query("SELECT id FROM students"):
        recalc_student_remaining(s['id'])
    return {'ok': True, 'imported': counts}
