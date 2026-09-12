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
import logging
import shutil
import sqlite3
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)

# ===== v1.0.3 备份加密：与 Android BackupCrypto.kt 严格对齐 =====
# 加密载荷格式：[魔数 SMTB 4B][GCM IV 12B][密文+GCM 标签 16B]
# 密钥派生：PBKDF2WithHmacSHA256(passphrase, salt, iterations, 256bit) -> AES-256
_BACKUP_MAGIC = b'SMTB'
_GCM_IV_LEN = 12
_GCM_TAG_BITS = 128
_DEFAULT_ITERATIONS = 600000


def is_encrypted_payload(data: bytes) -> bool:
    """判定字节流是否为 Android 备份加密载荷（仅查魔数）。"""
    return len(data) >= len(_BACKUP_MAGIC) and data[:len(_BACKUP_MAGIC)] == _BACKUP_MAGIC


def _derive_backup_key(passphrase: str, salt_hex: str, iterations: int):
    """由口令 + 盐派生 AES-256 密钥（PBKDF2-HMAC-SHA256）。"""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    salt = bytes.fromhex(salt_hex)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=max(1, int(iterations)))
    return kdf.derive(passphrase.encode('utf-8'))


def _decrypt_payload(data: bytes, key) -> Optional[bytes]:
    """解密备份载荷；魔数不符或密钥错误返回 None。"""
    if not is_encrypted_payload(data):
        return None
    if len(data) < len(_BACKUP_MAGIC) + _GCM_IV_LEN + 16:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        iv = data[len(_BACKUP_MAGIC):len(_BACKUP_MAGIC) + _GCM_IV_LEN]
        ciphertext = data[len(_BACKUP_MAGIC) + _GCM_IV_LEN:]
        return AESGCM(key).decrypt(iv, ciphertext, None)
    except Exception:
        # 口令错误 / 密文被篡改 / 格式损坏统一返回 None
        return None


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


def is_sqlcipher_db(db_path: str) -> bool:
    """判断文件是否为 SQLCipher 加密库（v1.0.5 起 Android 端加密）。

    SQLCipher 加密后文件头是随机盐，**不是** 明文 SQLite 的 "SQLite format 3\\x00"。
    标准库 sqlite3 打不开加密库，会抛 DatabaseError("file is not a database")，
    必须提前识别并给出可读提示，而不是让上层误报"数据库损坏"。
    """
    try:
        with open(db_path, 'rb') as f:
            header = f.read(16)
    except OSError:
        return False
    if len(header) < 16:
        return False
    return header[:15] != b'SQLite format 3'


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
        'height': _pick(row, 'height', 'latest_height', 'heightCm', default=None),
        'weight': _pick(row, 'weight', 'latest_weight', 'weightKg', default=None),
        'grade': str(_pick(row, 'grade', 'grade_label', default='')).strip(),
        'note': str(_pick(row, 'note', 'remark', default='')).strip(),
        # 遗传与生活习惯字段（对齐 Android Student 实体 v17，身高预测用）
        'father_height': _pick(row, 'father_height', 'fatherHeight', default=None),
        'mother_height': _pick(row, 'mother_height', 'motherHeight', default=None),
        'sleep_hours': _pick(row, 'avg_sleep_hours', 'avgSleepHours', default=None),
        'nutrition_score': _pick(row, 'nutrition_score', 'nutritionScore', default=None),
        'sports_mins': _pick(row, 'sports_mins_per_week', 'sportsMinsPerWeek', default=None),
        # 毫秒级更新时间（v23 双端同步 LWW 判新）
        'updated_at': _pick(row, 'updated_at', 'updatedAt', default=None),
        'created_at': _pick(row, 'created_at', 'create_time', default=None),
    }


def _normalize_lesson(row: Dict[str, Any]) -> Dict[str, Any]:
    """归一化 lessons 表的一行为桌面端课时明细结构。"""
    return {
        # 2026-09-06：BackupManager 实际导出为驼峰键（studentName/summary）——
        # 此前只认蛇形键，真机备份的课时明细在 PC 端整包被丢（测试夹具用蛇形键未暴露）
        'student_name': str(_pick(row, 'student_name', 'studentName', 'name', default='')).strip(),
        'date': str(_pick(row, 'date', 'lesson_date', 'check_in_date', default='')).strip(),
        'count': int(_pick(row, 'count', 'lesson_count', 'hours', default=1) or 1),
        'content': str(_pick(row, 'content', 'training_content', default='')).strip(),
        'note': str(_pick(row, 'note', 'remark', 'summary', default='')).strip(),
        'coach': str(_pick(row, 'coach_name', 'coachName', 'coach', default='')).strip(),
    }


def _normalize_package(row: Dict[str, Any]) -> Dict[str, Any]:
    """归一化 lesson_packages 表的一行为课时包结构。"""
    return {
        # 2026-09-06：补驼峰键回退——真机 BackupManager 导出 studentName/totalLessons/
        # usedLessons/purchaseDate/expireDate，此前只认蛇形键导致真机课时包整包被丢
        # （PC 总课时从不随手机购买更新、手机已消列永不写入的根源）
        'student_name': str(_pick(row, 'student_name', 'studentName', 'name', default='')).strip(),
        # 课时包名称（幂等收费镜像的备注键；与 student_name 的回退顺序区分开）
        'pkg_name': str(_pick(row, 'pkg_name', 'package_name', 'name', default='')).strip(),
        'total': int(_pick(row, 'total_lessons', 'total', 'purchased_lessons', 'totalLessons', default=0) or 0),
        'attended': int(_pick(row, 'attended_lessons', 'used_lessons', 'attended', 'usedLessons', default=0) or 0),
        'remaining': int(_pick(row, 'remaining_lessons', 'remaining', 'remainingLessons', default=0) or 0),
        'price': float(_pick(row, 'price', 'package_price', default=0) or 0),
        'paid_amount': float(_pick(row, 'paid_amount', 'paidAmount', default=-1)),
        'purchase_date': str(_pick(row, 'purchase_date', 'purchaseDate', default='')).strip(),
        'expire_date': str(_pick(row, 'expire_date', 'expireDate', default='')).strip(),
        # 状态（活跃/已用完/已过期/已退费）：已退费包不计入 PC 已购总课时
        'status': str(_pick(row, 'status', default='活跃') or '活跃').strip(),
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


def parse_android_backup(zip_path: str, extract_dir: str,
                        passphrase: str = '') -> Dict[str, List[Dict[str, Any]]]:
    """从 Android 备份 zip 中提取并解析数据。

    优先级：export_meta.json > .db 文件直接解析。

    参数:
        zip_path: Android 备份 zip 路径
        extract_dir: 解压临时目录
        passphrase: 备份口令（用户私钥种子）。v1.0.3 起 Android 端支持加密备份，
                    加密包内含 backup_manifest.json 标记 + 盐与迭代次数。
                    留空时：备份未加密则正常解析；备份已加密则返回空结果并记录警告
                    （绝不把密文当数据库解析，否则会误报"数据库损坏"）。

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

    # v1.0.3：先探测是否为加密备份，取得解密密钥
    crypto_key = None
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'backup_manifest.json' in zf.namelist():
                manifest = json.loads(zf.read('backup_manifest.json').decode('utf-8'))
                if manifest.get('encrypted'):
                    if not (passphrase or '').strip():
                        logging.getLogger(__name__).warning(
                            '备份 %s 已加密但未提供口令，跳过解析（请在界面填写用户私钥）',
                            os.path.basename(zip_path))
                        return result
                    crypto_key = _derive_backup_key(
                        passphrase, manifest.get('salt', ''),
                        int(manifest.get('iterations', 600000)))
    except (zipfile.BadZipFile, OSError, ValueError, KeyError) as e:
        logging.getLogger(__name__).warning('读取备份清单失败，按未加密处理：%s', e)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            base = os.path.basename(os.path.normpath(name))
            lower = base.lower()
            is_android_db = (
                (lower.endswith('.db') and not lower.startswith('sqlite_'))
                or base in android_db_names
            )
            if is_android_db or base == 'export_meta.json':
                dest = os.path.join(extract_dir, base)
                try:
                    with zf.open(name) as src:
                        payload = src.read()
                    # 加密备份：逐条目按魔数判定并解密
                    if crypto_key is not None and is_encrypted_payload(payload):
                        decrypted = _decrypt_payload(payload, crypto_key)
                        if decrypted is None:
                            logging.getLogger(__name__).warning(
                                '备份条目 %s 解密失败（口令不匹配或文件损坏），已跳过', base)
                            continue
                        payload = decrypted
                    with open(dest, 'wb') as dst:
                        dst.write(payload)
                except (OSError, KeyError):
                    continue
                # 仅主数据库文件记入 db_path（wal/shm 仅供 SQLite 恢复时配对）
                if is_android_db and not base.endswith(('-wal', '-shm')):
                    db_path = dest
                elif base == 'export_meta.json':
                    meta_path = dest

    # 优先使用 meta.json
    if meta_path and os.path.exists(meta_path):
        parsed = parse_meta_json(meta_path)
        if parsed:
            return parsed

    # 回退到 .db 解析
    if db_path and os.path.exists(db_path):
        # v1.0.5：Android 端数据库已由 SQLCipher 加密，PC 标准库 sqlite3 无法打开。
        # 该情况下 export_meta.json 是唯一通道（Android 端默认会生成），
        # 明确记录原因而不是让 sqlite3 抛出 "file is not a database" 被误读为数据损坏。
        if is_sqlcipher_db(db_path):
            logging.getLogger(__name__).warning(
                '备份内数据库为 SQLCipher 加密格式，PC 端无法直接解析；'
                '请确保备份包含 export_meta.json（Android 端默认生成）')
            return result
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
