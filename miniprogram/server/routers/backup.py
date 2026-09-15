# -*- coding: utf-8 -*-
"""备份接口：全量导出 JSON / 导入合并（校验模式标识）。

导出格式与桌面端/Android 备份对齐：顶层含 mode 标识 + 各业务表全量数据 + export_version。
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import (execute, query, query_one, now_str, get_conn,
                      recalc_student_remaining, current_mode)
from deps import get_current_user

router = APIRouter(prefix='/api/v1/backup', tags=['backup'],
                   dependencies=[Depends(get_current_user)])

EXPORT_VERSION = 1

TABLES = ['students', 'coaches', 'lessons', 'lesson_packages', 'checkin_records']

# 接口/导出附带的展示字段（不是表列），导入时明确忽略而非当未知列拒绝
IGNORED_KEYS = {'student_name'}

# 导入涉及的表：(请求字段名, 表名, 主键列)
IMPORT_TABLES = [
    ('students', 'students', 'id'),
    ('coaches', 'coaches', 'id'),
    ('lessons', 'lessons', 'id'),
    ('lesson_packages', 'lesson_packages', 'id'),
    ('checkin_records', 'checkin_records', 'id'),
]


def _table_columns(table: str) -> set:
    """表实际列名白名单（来自 schema，不来自请求）。

    备份 JSON 的 key 会被拼进 INSERT 的列名，必须只允许库里真实存在的列通过；
    表名来自本模块常量，不受请求控制。
    """
    return {r[1] for r in get_conn().execute(f'PRAGMA table_info({table})')}


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
    # 全量列名预检：任何非法列名都在写入前拒绝，避免留下半份导入结果
    for key, table, id_col in IMPORT_TABLES:
        allowed = _table_columns(table)
        for row in (getattr(body, key) or []):
            if not isinstance(row, dict):
                continue
            unknown = set(row) - allowed - IGNORED_KEYS
            if unknown:
                raise HTTPException(
                    status_code=400,
                    detail=f'{table} 备份含未知列：{"、".join(sorted(unknown))}，拒绝导入')
    # 逐行导入并全程记账：跳过多少、为什么跳过都要回报给调用方，绝不静默丢弃
    stats = {}
    for key, table, id_col in IMPORT_TABLES:
        st = {'imported': 0, 'skipped': 0, 'reasons': {}, 'samples': []}
        stats[key] = st

        def _skip(reason: str, row=None, _st=st, _samples_limit=3):
            _st['skipped'] += 1
            _st['reasons'][reason] = _st['reasons'].get(reason, 0) + 1
            if len(_st['samples']) < _samples_limit and isinstance(row, dict):
                brief = ','.join(f'{k}={row[k]}' for k in list(row)[:3])
                _st['samples'].append(f'{brief} → {reason}')

        for row in (getattr(body, key) or []):
            if not isinstance(row, dict):
                _skip('格式错：不是对象', row)
                continue
            if row.get(id_col) is None:
                _skip('缺字段：没有主键 id', row)
                continue
            cols = {k: v for k, v in row.items() if k not in IGNORED_KEYS}
            names = ','.join(cols.keys())
            marks = ','.join('?' * len(cols))
            if body.merge:
                # LWW 合并：updated_at（无则 timestamp）更新或目标不存在才写入
                ts_col = 'timestamp' if table == 'checkin_records' else 'updated_at'
                existing = query_one(f"SELECT {ts_col} AS ts FROM {table} WHERE id=?",
                                     (cols[id_col],))
                if existing and str(existing['ts'] or '') >= str(cols.get(ts_col) or ''):
                    _skip('已有更新版本，按 LWW 未覆盖', row)
                    continue
                sql = (f"INSERT INTO {table}({names}) VALUES({marks}) "
                       f"ON CONFLICT(id) DO UPDATE SET " +
                       ','.join(f"{k}=excluded.{k}" for k in cols if k != id_col))
            else:
                sql = f"INSERT OR REPLACE INTO {table}({names}) VALUES({marks})"
            try:
                execute(sql, tuple(cols.values()))
                st['imported'] += 1
            except Exception as exc:
                # 类型不符 / 约束冲突等：记下异常类型与首行信息，不再无声吞掉
                detail = f'{type(exc).__name__}: {str(exc)[:60]}'
                _skip(f'写入失败：{detail}', row)
    # 恢复后重算学员剩余课时
    for s in query("SELECT id FROM students"):
        recalc_student_remaining(s['id'])
    return {
        'ok': True,
        'imported': {k: v['imported'] for k, v in stats.items()},
        'skipped': {k: v['skipped'] for k, v in stats.items()},
        'skipped_details': {k: {'reasons': v['reasons'], 'samples': v['samples']}
                            for k, v in stats.items() if v['skipped']},
    }
