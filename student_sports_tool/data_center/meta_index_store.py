# -*- coding: utf-8 -*-
"""数据层：Android export_meta.json 本地 SQLite 强索引（性能加速层）。

职责：
- 在桌面端主程序根目录下维护 meta_index.db SQLite 数据库
- 存储从 Android 备份解析出的 students / lessons / packages 三张表
- 提供 O(1) 查询接口，避免每次扫描几十个 Excel 文件
- 索引失效机制：检测档案目录变化或显式调用 invalidate_index 后自动重建

设计原则：
- 索引仅为查询加速层，源数据仍以 Excel 为准
- 任何修改操作（add_lesson, set_total_lessons 等）必须显式失效索引
- 失败时优雅降级到 Excel 直读
- 单一职责：仅负责索引 CRUD，不包含业务逻辑
"""
import os
import sqlite3
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional


# 索引数据库文件名（位于桌面端主程序根目录）
INDEX_DB_FILENAME = 'meta_index.db'

# 索引版本号（用于后续 schema 升级）
INDEX_VERSION = 1


def _get_index_db_path(dir_path: str = '') -> str:
    """返回索引数据库路径。

    - dir_path 非空：`<dir>/.cache/meta_index.db`（每档案目录独立索引，杜绝跨目录串档）
    - dir_path 为空：桌面端主程序根目录 meta_index.db（向后兼容旧调用）

    定位逻辑（dir_path 为空时）：本文件位于 student_sports_tool/data_center/，
    上溯一层即为主程序根目录。
    """
    if dir_path:
        return os.path.join(dir_path, '.cache', INDEX_DB_FILENAME)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, INDEX_DB_FILENAME)


def _connect(dir_path: str = '') -> sqlite3.Connection:
    """打开索引数据库连接，启用 WAL 模式以支持并发读。"""
    db_path = _get_index_db_path(dir_path)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def _init_schema(conn: sqlite3.Connection):
    """初始化 schema（IF NOT EXISTS，幂等）。"""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS students (
            name TEXT PRIMARY KEY,
            age INTEGER,
            gender TEXT,
            school TEXT,
            phone TEXT,
            height REAL,
            weight REAL,
            grade TEXT,
            note TEXT,
            created_at TEXT,
            source TEXT
        );
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            date TEXT,
            count INTEGER DEFAULT 1,
            content TEXT,
            note TEXT,
            coach TEXT,
            UNIQUE(student_name, date, content, note)
        );
        CREATE TABLE IF NOT EXISTS packages (
            student_name TEXT PRIMARY KEY,
            total INTEGER DEFAULT 0,
            attended INTEGER DEFAULT 0,
            remaining INTEGER DEFAULT 0,
            purchase_date TEXT,
            expire_date TEXT
        );
        CREATE TABLE IF NOT EXISTS index_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_lessons_student ON lessons(student_name);
        CREATE INDEX IF NOT EXISTS idx_lessons_date ON lessons(date);
    ''')


def rebuild_index_from_parsed(parsed: Dict[str, List[Dict[str, Any]]], dir_path: str = '') -> int:
    """从 Android 解析结果重建索引（全量替换）。

    参数:
        parsed: android_backup_parser.parse_db / parse_meta_json 返回的结构
            {students: [...], lessons: [...], packages: [...]}
        dir_path: 档案目录；非空时索引写入该目录独立 .cache/meta_index.db，
            为空时写入全局根目录索引（兼容旧调用）

    返回: 索引的学员数量

    异常: 静默捕获，仅返回 0 表示失败（索引不可用不应阻塞主流程）
    """
    try:
        with _connect(dir_path) as conn:
            _init_schema(conn)
            # 全量清空旧索引
            conn.executescript('''
                DELETE FROM students;
                DELETE FROM lessons;
                DELETE FROM packages;
            ''')
            # 写入 students
            for stu in parsed.get('students', []):
                name = (stu.get('name') or '').strip()
                if not name:
                    continue
                conn.execute('''
                    INSERT OR REPLACE INTO students
                    (name, age, gender, school, phone, height, weight, grade, note, created_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'android')
                ''', (
                    name,
                    stu.get('age'),
                    stu.get('gender') or '男',
                    stu.get('school') or '',
                    stu.get('phone') or '',
                    stu.get('height'),
                    stu.get('weight'),
                    stu.get('grade') or '',
                    stu.get('note') or '',
                    stu.get('created_at'),
                ))
            # 写入 lessons
            for les in parsed.get('lessons', []):
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO lessons
                        (student_name, date, count, content, note, coach)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        (les.get('student_name') or '').strip(),
                        les.get('date') or '',
                        int(les.get('count') or 1),
                        les.get('content') or '',
                        les.get('note') or '',
                        les.get('coach') or '',
                    ))
                except sqlite3.IntegrityError:
                    continue
            # 写入 packages
            for pkg in parsed.get('packages', []):
                name = (pkg.get('student_name') or '').strip()
                if not name:
                    continue
                conn.execute('''
                    INSERT OR REPLACE INTO packages
                    (student_name, total, attended, remaining, purchase_date, expire_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    name,
                    int(pkg.get('total') or 0),
                    int(pkg.get('attended') or 0),
                    int(pkg.get('remaining') or 0),
                    pkg.get('purchase_date') or '',
                    pkg.get('expire_date') or '',
                ))
            # 更新 meta
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('last_rebuild', ?)",
                (now,)
            )
            conn.execute(
                "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('version', ?)",
                (str(INDEX_VERSION),)
            )
            # 清除脏标记
            conn.execute("DELETE FROM index_meta WHERE key='dirty'")
            return len(parsed.get('students', []))
    except sqlite3.Error:
        return 0


def is_index_available(dir_path: str = '') -> bool:
    """索引是否可用（数据库文件存在且 last_rebuild 不为空）。"""
    db_path = _get_index_db_path(dir_path)
    if not os.path.exists(db_path):
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT value FROM index_meta WHERE key='last_rebuild'")
            row = cur.fetchone()
            return row is not None
    except sqlite3.Error:
        return False


def get_last_rebuild_time(dir_path: str = '') -> Optional[str]:
    """返回上次重建时间，便于 UI 显示。"""
    db_path = _get_index_db_path(dir_path)
    if not os.path.exists(db_path):
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT value FROM index_meta WHERE key='last_rebuild'")
            row = cur.fetchone()
            return row[0] if row else None
    except sqlite3.Error:
        return None


def query_all_students_summary(dir_path: str = '') -> List[Dict[str, Any]]:
    """查询所有学员汇总（联合 students + packages + 最近上课日期）。

    返回结构兼容 lesson_manager.get_summary() 输出：
        [{name, total, attended, remaining, last_date, note, ...}]
    """
    db_path = _get_index_db_path(dir_path)
    if not os.path.exists(db_path):
        return []
    try:
        with _connect(dir_path) as conn:
            _init_schema(conn)
            cur = conn.execute('''
                SELECT
                    s.name AS name,
                    s.age AS age,
                    s.gender AS gender,
                    s.school AS school,
                    s.phone AS phone,
                    s.grade AS grade,
                    COALESCE(p.total, 0) AS total,
                    COALESCE(p.attended, 0) AS attended,
                    COALESCE(p.remaining, 0) AS remaining,
                    COALESCE(p.purchase_date, '') AS purchase_date,
                    COALESCE(p.expire_date, '') AS expire_date,
                    (SELECT MAX(date) FROM lessons l WHERE l.student_name = s.name) AS last_date,
                    s.note AS note
                FROM students s
                LEFT JOIN packages p ON p.student_name = s.name
                ORDER BY s.name
            ''')
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error:
        return []


def query_student_lessons(name: str, dir_path: str = '') -> List[Dict[str, Any]]:
    """查询指定学员的所有课时明细。"""
    db_path = _get_index_db_path(dir_path)
    if not os.path.exists(db_path):
        return []
    try:
        with _connect(dir_path) as conn:
            _init_schema(conn)
            cur = conn.execute(
                'SELECT student_name, date, count, content, note, coach '
                'FROM lessons WHERE student_name = ? ORDER BY date DESC',
                (name,)
            )
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error:
        return []


def search_students(keyword: str, limit: int = 50, dir_path: str = '') -> List[Dict[str, Any]]:
    """按关键字搜索学员（name / school / phone 模糊匹配）。"""
    db_path = _get_index_db_path(dir_path)
    if not os.path.exists(db_path):
        return []
    try:
        with _connect(dir_path) as conn:
            _init_schema(conn)
            like = f'%{keyword}%'
            cur = conn.execute('''
                SELECT * FROM students
                WHERE name LIKE ? OR school LIKE ? OR phone LIKE ?
                ORDER BY name LIMIT ?
            ''', (like, like, like, limit))
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error:
        return []


def invalidate_index(dir_path: str = ''):
    """标记索引为脏（需要重建，但保留数据供降级查询）。

    触发时机：lesson_manager 修改课时、Excel 直接编辑等
    设计：仅写入 dirty='1' 标记，不删除数据。下次查询时可选择降级到 Excel 或立即重建。
    """
    db_path = _get_index_db_path(dir_path)
    if not os.path.exists(db_path):
        return
    try:
        with sqlite3.connect(db_path) as conn:
            _init_schema(conn)
            conn.execute(
                "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('dirty', '1')"
            )
    except sqlite3.Error:
        pass


def is_dirty(dir_path: str = '') -> bool:
    """索引是否标记为脏（需要重建）。"""
    db_path = _get_index_db_path(dir_path)
    if not os.path.exists(db_path):
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT value FROM index_meta WHERE key='dirty'")
            row = cur.fetchone()
            return row is not None and row[0] == '1'
    except sqlite3.Error:
        return False


def clear_dirty(dir_path: str = ''):
    """清除脏标记。"""
    db_path = _get_index_db_path(dir_path)
    if not os.path.exists(db_path):
        return
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM index_meta WHERE key='dirty'")
    except sqlite3.Error:
        pass


def rebuild_index_from_dir(dir_path: str, force: bool = False) -> int:
    """从档案目录扫描重建索引（降级方案：扫描所有 Excel 文件）。

    参数:
        dir_path: 档案目录
        force: True 强制重建（即使未标记为 dirty）

    返回: 索引的学员数量
    """
    if not force and not is_dirty(dir_path):
        # 索引仍然有效，无需重建
        return len(query_all_students_summary(dir_path))

    # 延迟导入避免循环依赖
    import lesson_manager as lm
    from excel_builder import read_student_meta

    parsed = {'students': [], 'lessons': [], 'packages': []}
    if os.path.isdir(dir_path):
        # 学员基本信息从 _meta 读
        for fname in sorted(os.listdir(dir_path)):
            if not (fname.lower().endswith('.xlsx') and not fname.startswith('~$')):
                continue
            if fname == '课时记录.xlsx':
                continue
            full_path = os.path.join(dir_path, fname)
            meta = read_student_meta(full_path)
            if not meta:
                continue
            info = meta.get('info', {})
            name = (info.get('name') or fname[:-5]).strip()
            if not name:
                continue
            parsed['students'].append({
                'name': name,
                'gender': info.get('gender', '男'),
                'school': info.get('school', ''),
                'phone': info.get('phone', ''),
                'grade': info.get('grade', ''),
                'note': info.get('note', ''),
            })

        # 课时汇总从 lesson_manager 读
        try:
            summary = lm.get_summary(dir_path)
            for s in summary:
                parsed['packages'].append({
                    'student_name': s.get('name', ''),
                    'total': s.get('total', 0),
                    'attended': s.get('attended', 0),
                    'remaining': s.get('remaining', 0),
                })
        except Exception:
            logging.exception('索引重建读取课时汇总失败')

        # 课时明细从 lesson_manager 读
        try:
            detail = lm.get_detail(dir_path)
            for d in detail:
                parsed['lessons'].append({
                    'student_name': d.get('name', ''),
                    'date': d.get('date', ''),
                    'count': d.get('count', 1),
                    'content': d.get('content', ''),
                    'note': d.get('note', ''),
                    'coach': d.get('coach', ''),
                })
        except Exception:
            logging.exception('索引重建读取课时明细失败')

    count = rebuild_index_from_parsed(parsed, dir_path)
    return count


def drop_index(dir_path: str = ''):
    """删除索引文件（卸载/重置用）。"""
    db_path = _get_index_db_path(dir_path)
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        # 同时清理 WAL/SHM 临时文件
        for ext in ('-wal', '-shm'):
            side = db_path + ext
            if os.path.exists(side):
                os.remove(side)
    except OSError:
        pass
