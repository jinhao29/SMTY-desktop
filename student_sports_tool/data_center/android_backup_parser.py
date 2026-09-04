# -*- coding: utf-8 -*-
"""数据层：Android 端备份解析器。

职责：
- 解析 Android 端导出的 .db（Room SQLite）文件，提取 students / lessons / packages 表
- 解析 export_meta.json 轻量级索引（优先使用）
- 返回结构化数据，交由 backup_coordinator 委托 excel_builder / lesson_manager 写入桌面端 Excel

设计原则：
- 防御式解析：表不存在则跳过，不抛异常
- 列名兼容：Room 默认蛇形命名，同时兼容驼峰
- 不直接写 Excel，仅返回数据，保持单一职责
"""
import os
import json
import shutil
import sqlite3
from typing import Any, Dict, List, Optional


# Android 端核心表名（Room 实体映射）
TABLE_STUDENTS = 'students'
TABLE_LESSONS = 'lessons'
TABLE_PACKAGES = 'lesson_packages'  # Room 默认蛇形
TABLE_PACKAGES_ALT = 'packages'  # 兼容旧版
TABLE_ARCHIVED = 'archived_lessons'


def _connect_db(db_path: str) -> sqlite3.Connection:
    """以只读模式打开 SQLite 数据库。"""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f'数据库文件不存在：{db_path}')
    uri = f'file:{db_path}?mode=ro'
    return sqlite3.connect(uri, uri=True)


def _list_tables(conn: sqlite3.Connection) -> List[str]:
    """返回数据库中所有用户表名。"""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'android_%' AND name NOT LIKE 'room_%'"
    )
    return [row[0] for row in cur.fetchall()]


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """返回指定表的列名列表。"""
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return [row[1] for row in cur.fetchall()]


def _query_all(conn: sqlite3.Connection, table: str) -> List[Dict[str, Any]]:
    """读取整张表，返回字典列表（列名 → 值）。表不存在返回空列表。"""
    cols = _table_columns(conn, table)
    if not cols:
        return []
    cur = conn.execute(f'SELECT * FROM "{table}"')
    rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def _pick(row: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """从字典中按多个候选键取值，第一个命中即返回。"""
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return default


def _normalize_student(row: Dict[str, Any]) -> Dict[str, Any]:
    """归一化 students 表的一行为桌面端学员结构。"""
    return {
        'name': str(_pick(row, 'name', 'student_name', default='')).strip(),
        'age': _pick(row, 'age', 'student_age', default=None),
        'gender': str(_pick(row, 'gender', 'sex', default='男')).strip() or '男',
        'school': str(_pick(row, 'school', default='')).strip(),
        'phone': str(_pick(row, 'phone', 'mobile', 'contact', default='')).strip(),
        'height': _pick(row, 'height', 'latest_height', default=None),
        'weight': _pick(row, 'weight', 'latest_weight', default=None),
        'grade': str(_pick(row, 'grade', 'grade_label', default='')).strip(),
        'note': str(_pick(row, 'note', 'remark', default='')).strip(),
        # 遗传与生活习惯字段（对齐 Android Student 实体 v17，身高预测用）
        'father_height': _pick(row, 'father_height', 'fatherHeight', default=None),
        'mother_height': _pick(row, 'mother_height', 'motherHeight', default=None),
        'sleep_hours': _pick(row, 'avg_sleep_hours', 'avgSleepHours', default=None),
        'nutrition_score': _pick(row, 'nutrition_score', 'nutritionScore', default=None),
        'sports_mins': _pick(row, 'sports_mins_per_week', 'sportsMinsPerWeek', default=None),
        'created_at': _pick(row, 'created_at', 'create_time', default=None),
    }


def _normalize_lesson(row: Dict[str, Any]) -> Dict[str, Any]:
    """归一化 lessons 表的一行为桌面端课时明细结构。"""
    return {
        'student_name': str(_pick(row, 'student_name', 'name', default='')).strip(),
        'date': str(_pick(row, 'date', 'lesson_date', 'check_in_date', default='')).strip(),
        'count': int(_pick(row, 'count', 'lesson_count', 'hours', default=1) or 1),
        'content': str(_pick(row, 'content', 'training_content', default='')).strip(),
        'note': str(_pick(row, 'note', 'remark', default='')).strip(),
        'coach': str(_pick(row, 'coach_name', 'coach', default='')).strip(),
    }


def _normalize_package(row: Dict[str, Any]) -> Dict[str, Any]:
    """归一化 lesson_packages 表的一行为课时包结构。"""
    return {
        'student_name': str(_pick(row, 'student_name', 'name', default='')).strip(),
        'total': int(_pick(row, 'total_lessons', 'total', 'purchased_lessons', default=0) or 0),
        'attended': int(_pick(row, 'attended_lessons', 'used_lessons', 'attended', default=0) or 0),
        'remaining': int(_pick(row, 'remaining_lessons', 'remaining', default=0) or 0),
        'purchase_date': str(_pick(row, 'purchase_date', 'purchaseDate', default='')).strip(),
        'expire_date': str(_pick(row, 'expire_date', 'expireDate', default='')).strip(),
    }


def parse_db(db_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """解析 Android .db 文件，返回 {students, lessons, packages}。

    表缺失时返回空列表，不抛异常。
    """
    result = {'students': [], 'lessons': [], 'packages': []}
    with _connect_db(db_path) as conn:
        tables = set(_list_tables(conn))

        # 学员
        if TABLE_STUDENTS in tables:
            for row in _query_all(conn, TABLE_STUDENTS):
                item = _normalize_student(row)
                if item['name']:
                    result['students'].append(item)

        # 课时明细（合并 lessons 与 archived_lessons，去重按 student_name+date）
        seen_lessons = set()
        for table in (TABLE_LESSONS, TABLE_ARCHIVED):
            if table in tables:
                for row in _query_all(conn, table):
                    item = _normalize_lesson(row)
                    if not item['student_name']:
                        continue
                    key = (item['student_name'], item['date'])
                    if key in seen_lessons:
                        continue
                    seen_lessons.add(key)
                    result['lessons'].append(item)

        # 课时包
        pkg_table = TABLE_PACKAGES if TABLE_PACKAGES in tables else (
            TABLE_PACKAGES_ALT if TABLE_PACKAGES_ALT in tables else None
        )
        if pkg_table:
            for row in _query_all(conn, pkg_table):
                item = _normalize_package(row)
                if item['student_name']:
                    result['packages'].append(item)

    return result


def parse_meta_json(json_path: str) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """解析 export_meta.json，返回 {students, lessons, packages} 或 None。

    Android 端 BackupManager 导出的 meta 结构：
    {
        "students": [{name, age, gender, school, phone, height, weight, grade, note}, ...],
        "lessons": [{student_name, date, count, content, note, coach}, ...],
        "packages": [{student_name, total, attended, remaining, purchase_date, expire_date}, ...],
        "exported_at": "2026-07-26 12:00:00"
    }
    """
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    result = {'students': [], 'lessons': [], 'packages': []}
    for key in result:
        items = data.get(key, [])
        if not isinstance(items, list):
            continue
        normalizer = {
            'students': _normalize_student,
            'lessons': _normalize_lesson,
            'packages': _normalize_package,
        }[key]
        for row in items:
            if not isinstance(row, dict):
                continue
            item = normalizer(row)
            name_key = 'name' if key == 'students' else 'student_name'
            if item.get(name_key):
                result[key].append(item)
    return result


def parse_android_backup(zip_path: str, extract_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    """从 Android 备份 zip 中提取并解析数据。

    优先级：export_meta.json > .db 文件直接解析。

    参数:
        zip_path: Android 备份 zip 路径
        extract_dir: 解压临时目录

    返回:
        {students, lessons, packages}
    """
    import zipfile

    result = {'students': [], 'lessons': [], 'packages': []}
    if not os.path.exists(zip_path):
        return result

    # 解压 zip 中的 Android 数据库与 export_meta.json
    # P0 修复：BackupManager 打包的条目名为 sports_coach_db / sports_coach_db-wal /
    # sports_coach_db-shm（无 .db 后缀），原逻辑只匹配 .db 后缀导致主数据库被丢弃。
    # SQLite WAL 模式需要主 db + wal + shm 三个文件同目录才能正确读取最新数据。
    # P0 修复（Zip Slip）：不再使用 zf.extract(name, extract_dir)，改为按条目 basename
    # 安全写入 extract_dir，杜绝 zip 条目内 "../" 路径穿越把文件写到目录之外。
    db_path = None
    meta_path = None
    android_db_names = ('sports_coach_db', 'sports_coach_db-wal', 'sports_coach_db-shm')
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            base = os.path.basename(os.path.normpath(name))
            lower = base.lower()
            is_android_db = (
                (lower.endswith('.db') and not lower.startswith('sqlite_'))
                or base in android_db_names
            )
            if is_android_db:
                dest = os.path.join(extract_dir, base)
                try:
                    with zf.open(name) as src, open(dest, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                except (OSError, KeyError):
                    continue
                # 仅主数据库文件记入 db_path（wal/shm 仅供 SQLite 恢复时配对）
                if not base.endswith(('-wal', '-shm')):
                    db_path = dest
            elif base == 'export_meta.json':
                dest = os.path.join(extract_dir, base)
                try:
                    with zf.open(name) as src, open(dest, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    meta_path = dest
                except (OSError, KeyError):
                    continue

    # 优先使用 meta.json
    if meta_path and os.path.exists(meta_path):
        parsed = parse_meta_json(meta_path)
        if parsed:
            return parsed

    # 回退到 .db 解析
    if db_path and os.path.exists(db_path):
        try:
            return parse_db(db_path)
        except sqlite3.DatabaseError:
            return result

    return result


def summarize(parsed: Dict[str, List[Dict[str, Any]]]) -> str:
    """生成可读的解析摘要文本，供 UI 进度日志显示。"""
    s = len(parsed.get('students', []))
    l = len(parsed.get('lessons', []))
    p = len(parsed.get('packages', []))
    return f'Android 数据解析完成：学员 {s} 人，课时明细 {l} 条，课时包 {p} 个'
