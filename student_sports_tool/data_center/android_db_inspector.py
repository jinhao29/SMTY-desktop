# -*- coding: utf-8 -*-
"""处理器层：Android SQLite 数据库深度读取与质量检查。

职责（第3轮新增）：
- 补全 [android_backup_parser] 未覆盖的高级能力：schema 版本检测、完整性校验、
  全表清单枚举、备份内照片文件清单、数据质量自检
- 不重复 [android_backup_parser.parse_db] 的基础解析逻辑，仅做增强读取
- 输出结构化报告，供桌面端 UI 显示「备份健康度」面板

设计原则：
- 只读：所有 SQLite 操作使用 mode=ro，绝不修改源文件
- 防御式：表/列缺失时跳过，不抛异常，返回空结果
- 单一职责：仅做读取与检查，不写 Excel / 不调用 UI
- 性能：单次连接完成所有查询，避免反复打开数据库

调用入口：
- [inspect_db] - 完整数据库体检（schema 版本 + 完整性 + 全表清单 + 行数）
- [enumerate_photos_in_backup] - 备份 zip 内签到照片清单
- [check_data_quality] - 学员/课时/课时包交叉一致性检查
"""
import os
import zipfile
import sqlite3
from typing import Any, Dict, List, Optional


# Android 端 Room 数据库的预期 schema 版本（与 AppDatabase.kt 中 DATABASE_VERSION 一致）
# 注意：每次 Android 端升级数据库版本时，桌面端需同步更新此常量以做兼容性提示
EXPECTED_SCHEMA_VERSION = 24


def _connect_db(db_path: str) -> sqlite3.Connection:
    """以只读模式打开 SQLite 数据库（与 [android_backup_parser._connect_db] 一致）。"""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f'数据库文件不存在：{db_path}')
    uri = f'file:{db_path}?mode=ro'
    return sqlite3.connect(uri, uri=True)


def inspect_db(db_path: str) -> Dict[str, Any]:
    """对 Android .db 文件做完整体检。

    返回结构：
    ```
    {
        'db_path': '/path/to/sports_coach_db',
        'file_size_bytes': 102400,
        'schema_version': 24,
        'expected_version': 24,
        'version_match': True,
        'integrity': 'ok',                  # ok / error / unknown
        'tables': [
            {'name': 'students', 'row_count': 35, 'columns': ['id', 'name', ...]},
            ...
        ],
        'total_rows': 150,
    }
    ```
    """
    result: Dict[str, Any] = {
        'db_path': db_path,
        'file_size_bytes': 0,
        'schema_version': 0,
        'expected_version': EXPECTED_SCHEMA_VERSION,
        'version_match': False,
        'integrity': 'unknown',
        'tables': [],
        'total_rows': 0,
    }
    if not os.path.exists(db_path):
        return result
    result['file_size_bytes'] = os.path.getsize(db_path)

    try:
        with _connect_db(db_path) as conn:
            # 1. Schema 版本
            result['schema_version'] = _read_schema_version(conn)
            result['version_match'] = (result['schema_version'] == EXPECTED_SCHEMA_VERSION)

            # 2. 完整性校验
            result['integrity'] = _check_integrity(conn)

            # 3. 全表清单 + 行数 + 列名
            total_rows = 0
            for table in _list_tables(conn):
                cols = _table_columns(conn, table)
                row_count = _table_row_count(conn, table)
                result['tables'].append({
                    'name': table,
                    'row_count': row_count,
                    'columns': cols,
                })
                total_rows += row_count
            result['total_rows'] = total_rows
    except sqlite3.DatabaseError:
        result['integrity'] = 'error'
    return result


def enumerate_photos_in_backup(zip_path: str) -> List[Dict[str, str]]:
    """枚举 Android 备份 zip 内的签到照片文件清单。

    返回结构：
    ```
    [
        {'entry_name': 'SignPhotos/photo_xxx.enc.jpg', 'size': 10240},
        ...
    ]
    ```

    用于：
    - 桌面端报告生成时按需提取特定学员的照片
    - 数据健康度面板显示「备份内照片数」
    - 与 .db 中 lesson.photoPath 做匹配，识别孤立照片
    """
    photos: List[Dict[str, str]] = []
    if not os.path.exists(zip_path):
        return photos
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace('\\', '/')
                # 兼容不同版本的照片目录名：SignPhotos / sign_photos
                lower = name.lower()
                if 'signphotos/' in lower or 'sign_photos/' in lower:
                    photos.append({
                        'entry_name': name,
                        'size': info.file_size,
                    })
    except (zipfile.BadZipFile, OSError):
        pass
    return photos


def check_data_quality(parsed: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """对 [android_backup_parser.parse_db] 的输出做数据质量检查。

    检查项：
    - 孤立课时：lessons 中的 student_name 不在 students 列表中
    - 课时包余额异常：packages 中 remaining < 0 或 remaining > total
    - 课时日期格式错误：date 不符合 YYYY-MM-DD
    - 重复学员：students 列表中存在同名学员

    返回：
    ```
    {
        'orphan_lesson_count': 2,
        'orphan_lesson_samples': ['张三 2026-07-15', ...],
        'invalid_balance_count': 1,
        'invalid_date_count': 0,
        'duplicate_student_count': 0,
        'overall_status': 'warning',   # ok / warning / error
    }
    ```
    """
    students = parsed.get('students', [])
    lessons = parsed.get('lessons', [])
    packages = parsed.get('packages', [])

    student_names = {s.get('name', '').strip() for s in students if s.get('name')}

    # 1. 孤立课时
    orphan_lessons: List[str] = []
    for lesson in lessons:
        name = lesson.get('student_name', '').strip()
        date = lesson.get('date', '').strip()
        if name and name not in student_names:
            orphan_lessons.append(f'{name} {date}'.strip())
    orphan_samples = orphan_lessons[:5]

    # 2. 课时包余额异常
    invalid_balance = 0
    for pkg in packages:
        total = pkg.get('total', 0) or 0
        remaining = pkg.get('remaining', 0) or 0
        if remaining < 0 or remaining > total:
            invalid_balance += 1

    # 3. 课时日期格式
    invalid_date = 0
    for lesson in lessons:
        date = lesson.get('date', '').strip()
        if date and not _is_valid_date(date):
            invalid_date += 1

    # 4. 重复学员
    name_list = [s.get('name', '').strip() for s in students if s.get('name')]
    duplicates = len(name_list) - len(set(name_list))

    # 综合状态
    if orphan_lessons or invalid_balance or invalid_date:
        status = 'warning'
    elif duplicates > 0:
        status = 'warning'
    else:
        status = 'ok'

    return {
        'orphan_lesson_count': len(orphan_lessons),
        'orphan_lesson_samples': orphan_samples,
        'invalid_balance_count': invalid_balance,
        'invalid_date_count': invalid_date,
        'duplicate_student_count': duplicates,
        'overall_status': status,
    }


# ============================================================
# 内部工具方法
# ============================================================

def _read_schema_version(conn: sqlite3.Connection) -> int:
    """读取 SQLite 的 PRAGMA user_version（Room 用于跟踪 schema 版本）。"""
    try:
        cur = conn.execute('PRAGMA user_version')
        return int(cur.fetchone()[0] or 0)
    except sqlite3.DatabaseError:
        return 0


def _check_integrity(conn: sqlite3.Connection) -> str:
    """执行 PRAGMA integrity_check，返回 'ok' / 'error' / 'unknown'。"""
    try:
        cur = conn.execute('PRAGMA integrity_check')
        row = cur.fetchone()
        return 'ok' if row and row[0] == 'ok' else 'error'
    except sqlite3.DatabaseError:
        return 'error'


def _list_tables(conn: sqlite3.Connection) -> List[str]:
    """返回数据库中所有用户表名（与 [android_backup_parser._list_tables] 一致）。"""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' "
        "AND name NOT LIKE 'android_%' "
        "AND name NOT LIKE 'room_%'"
    )
    return [row[0] for row in cur.fetchall()]


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """返回指定表的列名列表。"""
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return [row[1] for row in cur.fetchall()]


def _table_row_count(conn: sqlite3.Connection, table: str) -> int:
    """返回指定表的行数。失败返回 0。"""
    try:
        cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
        return int(cur.fetchone()[0] or 0)
    except sqlite3.DatabaseError:
        return 0


def _is_valid_date(date_str: str) -> bool:
    """简单校验日期格式是否为 YYYY-MM-DD。"""
    if len(date_str) != 10:
        return False
    parts = date_str.split('-')
    if len(parts) != 3:
        return False
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31
    except ValueError:
        return False


def build_inspector_summary(inspect_result: Dict[str, Any],
                            quality_result: Dict[str, Any]) -> str:
    """生成体检 + 质量检查的可读摘要文本，供 UI 显示。"""
    lines = []
    lines.append('=== 数据库体检 ===')
    lines.append(f"• 文件大小：{_format_size(inspect_result.get('file_size_bytes', 0))}")
    lines.append(f"• Schema 版本：{inspect_result.get('schema_version', 0)}"
                 f" / 期望 {inspect_result.get('expected_version', 0)}"
                 f"{' ✓' if inspect_result.get('version_match') else ' ⚠ 不匹配'}")
    lines.append(f"• 完整性校验：{inspect_result.get('integrity', 'unknown')}")
    lines.append(f"• 表数量：{len(inspect_result.get('tables', []))}")
    lines.append(f"• 总记录数：{inspect_result.get('total_rows', 0)}")
    lines.append('')
    lines.append('=== 数据质量 ===')
    status = quality_result.get('overall_status', 'unknown')
    lines.append(f"• 综合状态：{status}")
    lines.append(f"• 孤立课时（无对应学员）：{quality_result.get('orphan_lesson_count', 0)}")
    lines.append(f"• 课时包余额异常：{quality_result.get('invalid_balance_count', 0)}")
    lines.append(f"• 课时日期格式错误：{quality_result.get('invalid_date_count', 0)}")
    lines.append(f"• 重复学员：{quality_result.get('duplicate_student_count', 0)}")
    return '\n'.join(lines)


def _format_size(size_bytes: int) -> str:
    """字节数转人类可读字符串。"""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    if size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    if size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / 1024 / 1024:.1f} MB'
    return f'{size_bytes / 1024 / 1024 / 1024:.2f} GB'
