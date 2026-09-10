# -*- coding: utf-8 -*-
"""SQLite 数据层：表结构与 Android Room 实体对齐。

单文件数据库（server_data/miniprogram.db），标准库 sqlite3，无 ORM 依赖。
业务规则与桌面端 fee_manager 口径保持一致：
- 应收 = 总课时 × 单价；实收 = paid_amount（-1 视同已付清）；待收 = 应收 - 实收
"""
import json
import os
import sqlite3
import threading
import time
import contextvars
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'server_data')

# 数据空间按模式隔离：每模式独立库文件（与 PC 端 mode_guard 思路一致）
DEFAULT_MODE = os.environ.get('MP_MODE', 'shangmen')
VALID_MODES = ('shangmen', 'club')

# 请求级模式覆盖（中间件/依赖从 X-MP-Mode header 写入）
_mode_ctx = contextvars.ContextVar('mp_mode', default=None)

_local = threading.local()


def now_str() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def current_mode() -> str:
    m = _mode_ctx.get() or DEFAULT_MODE
    return m if m in VALID_MODES else 'shangmen'


def _db_path(mode: str) -> str:
    return os.path.join(DATA_DIR, f'miniprogram_{mode}.db')


def get_conn() -> sqlite3.Connection:
    conns = getattr(_local, 'conns', None)
    if conns is None:
        conns = _local.conns = {}
    mode = current_mode()
    conn = conns.get(mode)
    if conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(_db_path(mode), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        conns[mode] = conn
        _ensure_schema(conn)
    return conn


def _ensure_schema(conn):
    """幂等建表 + 管理员账号播种（每个模式库独立初始化）。

    不再播种 13800000000/123456 这类公开默认口令——源码可见即等于没有密码。
    管理员账号只在显式提供 MP_ADMIN_PHONE + MP_ADMIN_PASSWORD 时创建；
    两者缺失则库内无任何账号，需先配置环境变量再启动。
    """
    conn.executescript(SCHEMA)
    phone = (os.environ.get('MP_ADMIN_PHONE') or '').strip()
    password = os.environ.get('MP_ADMIN_PASSWORD') or ''
    if not phone or not password:
        conn.commit()
        return
    if len(password) < 8:
        raise RuntimeError('MP_ADMIN_PASSWORD 至少 8 位，拒绝播种弱口令管理员账号。')
    from passlib_lite import hash_password
    row = conn.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
    if not row:
        name = (os.environ.get('MP_ADMIN_NAME') or '管理员').strip() or '管理员'
        conn.execute(
            "INSERT INTO users(phone,password_hash,name,role,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (phone, hash_password(password), name, 'coach', now_str(), now_str()))
    conn.commit()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'coach',
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    grade TEXT DEFAULT '',
    parent_phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    class_group TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    remaining_lessons INTEGER NOT NULL DEFAULT 0,
    expire_date TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coaches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    role TEXT NOT NULL DEFAULT 'parttime',
    superior_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    salary_mode TEXT NOT NULL DEFAULT 'per_lesson',
    base_salary REAL NOT NULL DEFAULT 0,
    lesson_rate REAL NOT NULL DEFAULT 0,
    commission_rate REAL NOT NULL DEFAULT 0,
    specialties TEXT DEFAULT '[]',
    created_at TEXT, updated_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_ids TEXT NOT NULL DEFAULT '[]',
    coach_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'private',
    location TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS lesson_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    total_lessons INTEGER NOT NULL,
    remaining_lessons INTEGER NOT NULL,
    expire_date TEXT DEFAULT '',
    purchase_date TEXT DEFAULT '',
    price REAL NOT NULL DEFAULT 0,
    paid_amount REAL NOT NULL DEFAULT -1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT, updated_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checkin_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    lesson_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    note TEXT DEFAULT ''
);
"""


def init_db():
    """初始化所有模式库（幂等）。"""
    for m in VALID_MODES:
        _mode_ctx.set(m)
        _ensure_schema(get_conn())


def row_to_dict(row) -> dict:
    d = dict(row)
    for key in ('student_ids', 'specialties'):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key] or '[]')
            except (ValueError, TypeError):
                d[key] = []
    return d


def query(sql: str, params=()) -> list:
    return [row_to_dict(r) for r in get_conn().execute(sql, params).fetchall()]


def query_one(sql: str, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=()) -> int:
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def touch(table: str, row_id: int):
    execute(f"UPDATE {table} SET updated_at=? WHERE id=?", (now_str(), row_id))


def recalc_student_remaining(student_id: int):
    """学员剩余课时 = 有效课时包 remaining 之和（与桌面端汇总口径一致）。"""
    rows = query(
        "SELECT COALESCE(SUM(remaining_lessons),0) AS s FROM lesson_packages "
        "WHERE student_id=? AND deleted=0 AND status='active'", (student_id,))
    total = rows[0]['s'] if rows else 0
    execute("UPDATE students SET remaining_lessons=?, updated_at=? WHERE id=?",
            (total, now_str(), student_id))


def package_fee_stats() -> dict:
    """费用统计（fee_manager 口径）：应收/实收/待收。"""
    rows = query("SELECT total_lessons, remaining_lessons, price, paid_amount, status "
                 "FROM lesson_packages WHERE deleted=0")
    total_lessons = sum(r['total_lessons'] for r in rows)
    consumed = sum(r['total_lessons'] - r['remaining_lessons'] for r in rows)
    remaining = sum(r['remaining_lessons'] for r in rows)
    receivable = 0.0
    received = 0.0
    for r in rows:
        unit = (r['price'] / r['total_lessons']) if r['total_lessons'] else 0
        receivable += r['total_lessons'] * unit
        received += r['price'] if r['paid_amount'] == -1 else (r['paid_amount'] or 0)
    return {
        'total_lessons': total_lessons, 'consumed_lessons': consumed,
        'remaining_lessons': remaining, 'student_count': len({r.get('student_id') for r in rows}) if False else None,
        'total_receivable': round(receivable, 2), 'total_received': round(received, 2),
        'total_pending': round(receivable - received, 2),
    }
