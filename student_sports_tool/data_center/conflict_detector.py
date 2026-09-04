# -*- coding: utf-8 -*-
"""处理器层：数据导入冲突检测（v5 优化4 新增）。

职责：
- 在 do_restore 执行前，预扫描 zip 中的 Android 学员数据
- 与本地档案目录比对，识别同名学员、日期冲突、格式异常等情况
- 输出结构化冲突列表，供 DataConflictResolver 弹窗展示与解决

设计原则：
- 纯逻辑单元，无 UI 依赖，便于单元测试
- 不修改任何文件，仅扫描与比对
- 失败静默降级（Android 数据不存在时返回空列表，不阻塞恢复流程）
"""
import os
import zipfile
from typing import Any, Dict, List, Optional


# 冲突类型枚举（字符串常量，便于 UI 国际化）
CONFLICT_NAME_DUPLICATE = 'name_duplicate'      # 同名学员（本地已有档案）
CONFLICT_LESSON_DATE_OVERLAP = 'lesson_overlap' # 同日课时记录冲突
CONFLICT_PACKAGE_MISMATCH = 'package_mismatch'  # 课时包数据不一致

# 解决策略枚举（DataConflictResolver 返回）
RESOLVE_MERGE = 'merge'           # 合并历史记录（保留双方数据）
RESOLVE_OVERWRITE = 'overwrite'   # 覆盖现有数据（删除本地后再导入）
RESOLVE_RENAME = 'rename'         # 重命名为 xxx_2
RESOLVE_SKIP = 'skip'             # 跳过此条


def detect_conflicts_from_zip(zip_path: str, target_dir: str,
                              progress_cb=None) -> List[Dict[str, Any]]:
    """扫描备份 zip 与本地档案目录，检测潜在冲突。

    参数:
        zip_path: 备份 zip 文件路径
        target_dir: 桌面端档案目录
        progress_cb: 可选回调 (message: str) -> None

    返回: 冲突列表，每项包含：
        {
            'type': 'name_duplicate' | 'lesson_overlap' | 'package_mismatch',
            'student_name': str,           # 学员姓名
            'local_info': str,             # 本地状态描述
            'remote_info': str,            # 远端状态描述
            'suggested_resolution': str,   # 建议解决策略
            'remote_lesson_count': int,    # 远端课时数
            'local_lesson_count': int,     # 本地课时数
        }
    """
    if not os.path.exists(zip_path):
        return []

    conflicts: List[Dict[str, Any]] = []

    # 1. 提取 Android 数据到内存（不写盘）
    if progress_cb:
        progress_cb('正在解析 Android 备份数据...')
    parsed = _parse_android_from_zip(zip_path)
    if not parsed:
        if progress_cb:
            progress_cb('未检测到 Android 数据，跳过冲突检测')
        return []

    remote_students = {s.get('name', '').strip(): s
                       for s in parsed.get('students', [])
                       if s.get('name', '').strip()}
    remote_lessons_by_name = _group_lessons_by_name(parsed.get('lessons', []))
    remote_packages_by_name = {p.get('student_name', '').strip(): p
                               for p in parsed.get('packages', [])
                               if p.get('student_name', '').strip()}

    # 2. 扫描本地档案目录
    if progress_cb:
        progress_cb('正在扫描本地学员档案...')
    local_students = _scan_local_students(target_dir)
    local_lesson_counts = _count_local_lessons(target_dir, local_students)

    # 3. 比对：同名学员冲突
    if progress_cb:
        progress_cb('正在比对学员数据...')
    for name, remote_stu in remote_students.items():
        if name in local_students:
            local_count = local_lesson_counts.get(name, 0)
            remote_count = len(remote_lessons_by_name.get(name, []))

            # 检测课时日期重叠
            overlap_dates = _detect_lesson_date_overlap(
                target_dir, name,
                remote_lessons_by_name.get(name, [])
            )

            if overlap_dates:
                conflicts.append({
                    'type': CONFLICT_LESSON_DATE_OVERLAP,
                    'student_name': name,
                    'local_info': f'本地已有 {local_count} 节课时记录，{len(overlap_dates)} 节与远端日期重叠',
                    'remote_info': f'远端有 {remote_count} 节课时记录',
                    'suggested_resolution': RESOLVE_MERGE,
                    'remote_lesson_count': remote_count,
                    'local_lesson_count': local_count,
                    'overlap_dates': overlap_dates,
                })
            else:
                # 仅同名，无日期重叠
                conflicts.append({
                    'type': CONFLICT_NAME_DUPLICATE,
                    'student_name': name,
                    'local_info': f'本地已有档案（{local_count} 节课时）',
                    'remote_info': f'远端有 {remote_count} 节课时待同步',
                    'suggested_resolution': RESOLVE_MERGE if remote_count > 0 else RESOLVE_SKIP,
                    'remote_lesson_count': remote_count,
                    'local_lesson_count': local_count,
                })

            # 检测课时包数据不一致
            remote_pkg = remote_packages_by_name.get(name)
            if remote_pkg and remote_pkg.get('total') is not None:
                local_pkg_total = _get_local_package_total(target_dir, name)
                if local_pkg_total is not None and remote_pkg['total'] != local_pkg_total:
                    conflicts.append({
                        'type': CONFLICT_PACKAGE_MISMATCH,
                        'student_name': name,
                        'local_info': f'本地课时包总数：{local_pkg_total}',
                        'remote_info': f'远端课时包总数：{remote_pkg["total"]}',
                        'suggested_resolution': RESOLVE_OVERWRITE,
                        'remote_lesson_count': remote_count,
                        'local_lesson_count': local_count,
                    })

    if progress_cb and conflicts:
        progress_cb(f'检测到 {len(conflicts)} 项冲突，等待教练确认')
    elif progress_cb:
        progress_cb('未检测到冲突')

    return conflicts


def _parse_android_from_zip(zip_path: str) -> Optional[Dict]:
    """从 zip 中解析 Android 数据（不写盘）。

    优先使用 export_meta.json，回退 .db。
    """
    try:
        import android_backup_parser as abp
        import tempfile

        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            meta_name = next((n for n in names
                              if os.path.basename(n) == 'export_meta.json'), None)
            db_name = next((n for n in names
                            if n.lower().endswith('.db')
                            and not os.path.basename(n).lower().startswith('sqlite_')), None)

            if meta_name:
                with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    with zf.open(meta_name) as src, open(tmp_path, 'wb') as dst:
                        import shutil
                        shutil.copyfileobj(src, dst)
                    return abp.parse_meta_json(tmp_path)
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

            if db_name:
                with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    with zf.open(db_name) as src, open(tmp_path, 'wb') as dst:
                        import shutil
                        shutil.copyfileobj(src, dst)
                    return abp.parse_db(tmp_path)
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
    except Exception:
        return None

    return None


def _group_lessons_by_name(lessons: List[Dict]) -> Dict[str, List[Dict]]:
    """按学员名聚合课时。"""
    result: Dict[str, List[Dict]] = {}
    for les in lessons:
        name = les.get('student_name', '').strip()
        if name:
            result.setdefault(name, []).append(les)
    return result


def _scan_local_students(target_dir: str) -> Dict[str, str]:
    """扫描本地档案目录，返回 {学员名: 文件路径}。

    去除 .xlsx 扩展名作为学员名；排除课时记录与临时文件。
    """
    result: Dict[str, str] = {}
    if not os.path.isdir(target_dir):
        return result
    try:
        for f in os.listdir(target_dir):
            if not f.lower().endswith('.xlsx'):
                continue
            if f.startswith('~$') or f == '课时记录.xlsx':
                continue
            name = os.path.splitext(f)[0]
            result[name] = os.path.join(target_dir, f)
    except OSError:
        pass
    return result


def _count_local_lessons(target_dir: str, students: Dict[str, str]) -> Dict[str, int]:
    """统计每位学员本地课时数（从 Excel 课时记录读取）。

    优先使用 SQLite 索引（更快），失败回退到 lesson_manager.get_detail。
    """
    result: Dict[str, int] = {}
    if not students:
        return result

    # 优先 SQLite 索引
    try:
        import meta_index_store as mis
        import sqlite3
        if mis.is_index_available(target_dir):
            db_path = mis._get_index_db_path(target_dir)
            with sqlite3.connect(db_path) as conn:
                for name in students.keys():
                    try:
                        cur = conn.execute(
                            'SELECT COUNT(*) FROM lessons WHERE student_name = ?',
                            (name,)
                        )
                        row = cur.fetchone()
                        result[name] = int(row[0]) if row else 0
                    except Exception:
                        result[name] = 0
            return result
    except Exception:
        pass

    # 回退：通过 lesson_manager 读取明细
    try:
        import lesson_manager
        for name in students.keys():
            try:
                records = lesson_manager.get_detail(target_dir, name)
                result[name] = len(records) if records else 0
            except Exception:
                result[name] = 0
    except Exception:
        pass

    # 补全未出现的学员为 0
    for name in students:
        result.setdefault(name, 0)
    return result


def _detect_lesson_date_overlap(target_dir: str, student_name: str,
                                 remote_lessons: List[Dict]) -> List[str]:
    """检测远端课时日期与本地课时日期的重叠。

    返回重叠的日期列表（YYYY-MM-DD 格式）。
    """
    if not remote_lessons:
        return []

    remote_dates = set()
    for les in remote_lessons:
        d = les.get('date')
        if d:
            remote_dates.add(str(d)[:10])

    if not remote_dates:
        return []

    local_dates = set()
    try:
        import lesson_manager
        records = lesson_manager.get_detail(target_dir, student_name)
        for r in records:
            d = r.get('date')
            if d:
                local_dates.add(str(d)[:10])
    except Exception:
        pass

    overlap = sorted(remote_dates & local_dates)
    return overlap


def _get_local_package_total(target_dir: str, student_name: str) -> Optional[int]:
    """读取本地学员课时包总课时。"""
    try:
        import lesson_manager
        summary = lesson_manager.get_lesson_summary(target_dir, student_name)
        if summary:
            return int(summary.get('total') or 0)
    except Exception:
        pass
    return None
