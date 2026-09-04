# -*- coding: utf-8 -*-
"""处理器层：训练达成率偏差分析（v5 优化5 新增）。

职责：
- 从 Android 备份 zip 中读取 Schedule 表（排课计划）
- 与本地 lesson_manager 的 Lesson（实际签退记录）比对
- 计算月度训练达成率：计划排课数 / 实际签到数 / 缺勤数
- 输出结构化分析结果，供图表 UI 展示

设计原则：
- 纯逻辑单元，无 UI 依赖
- 仅读取，不修改任何文件
- 失败静默降级（无 Schedule 表时返回空结果）
- 支持指定月份范围，默认本月
"""
import os
import sqlite3
import zipfile
import tempfile
import shutil
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple


def analyze_schedule_lesson_deviation(
    zip_path: str,
    target_dir: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    progress_cb=None
) -> Dict[str, Any]:
    """分析排课计划与实际签退记录的偏差（v5 优化5 核心）。

    参数:
        zip_path: Android 备份 zip 路径（用于读取 schedules 表）
        target_dir: 桌面端档案目录（用于读取本地 lesson 记录）
        year: 指定年份（默认本年）
        month: 指定月份（默认本月）
        progress_cb: 可选回调

    返回:
        {
            'period': 'YYYY-MM',
            'planned_count': int,           # 计划排课数
            'actual_count': int,            # 实际签到数
            'absent_count': int,            # 缺勤数 = planned - actual
            'achievement_rate': float,      # 达成率 (0.0 - 1.0)
            'per_student': [                # 按学员明细
                {
                    'student_name': str,
                    'planned': int,
                    'actual': int,
                    'absent': int,
                    'rate': float,
                }
            ],
            'per_day': [                    # 按日期明细（仅本月）
                {
                    'date': 'YYYY-MM-DD',
                    'planned': int,
                    'actual': int,
                }
            ],
            'absent_dates': [               # 缺勤日期列表
                {'student_name': str, 'date': str, 'planned_content': str}
            ],
            'has_schedule_data': bool,      # 是否读到 schedules 表
        }
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    period = f'{year:04d}-{month:02d}'

    if progress_cb:
        progress_cb(f'正在分析 {period} 训练达成率...')

    # 1. 从 zip 读取 schedules 表
    schedules = _read_schedules_from_zip(zip_path, progress_cb)
    has_schedule_data = len(schedules) > 0

    if progress_cb:
        progress_cb(f'读取到 {len(schedules)} 条排课计划')

    # 2. 读取本地 lesson 明细
    local_lessons = _read_local_lessons(target_dir, year, month, progress_cb)
    if progress_cb:
        progress_cb(f'读取到 {len(local_lessons)} 条本地课时记录')

    # 3. 计算 plan: 将 schedules 展开为月度每日计划
    planned_per_day = _expand_schedules_to_month(schedules, year, month)
    planned_count = sum(len(items) for items in planned_per_day.values())

    # 4. 计算 actual: 按日期分组 local_lessons
    actual_per_day: Dict[str, List[Dict]] = {}
    for les in local_lessons:
        d = str(les.get('date') or '')[:10]
        if d:
            actual_per_day.setdefault(d, []).append(les)
    actual_count = len(local_lessons)

    # 5. 按学员维度聚合
    per_student = _aggregate_per_student(schedules, local_lessons, year, month)

    # 6. 按日期维度聚合（仅本月有计划的天）
    per_day = []
    absent_dates = []
    for d in sorted(planned_per_day.keys()):
        planned_items = planned_per_day[d]
        actual_items = actual_per_day.get(d, [])
        planned_n = len(planned_items)
        actual_n = len(actual_items)
        per_day.append({
            'date': d,
            'planned': planned_n,
            'actual': actual_n,
        })
        # 缺勤检测：计划了但未签到（按学员粒度）
        actual_students = {a.get('student_name', '').strip() for a in actual_items}
        for p in planned_items:
            stu = p.get('student_name', '').strip()
            if stu and stu not in actual_students:
                absent_dates.append({
                    'student_name': stu,
                    'date': d,
                    'planned_content': p.get('content', '')[:60],
                })

    absent_count = max(0, planned_count - actual_count)
    rate = (actual_count / planned_count) if planned_count > 0 else 0.0

    if progress_cb:
        progress_cb(
            f'分析完成：计划 {planned_count} 节，实际 {actual_count} 节，'
            f'达成率 {rate * 100:.1f}%'
        )

    return {
        'period': period,
        'planned_count': planned_count,
        'actual_count': actual_count,
        'absent_count': absent_count,
        'achievement_rate': rate,
        'per_student': per_student,
        'per_day': per_day,
        'absent_dates': absent_dates,
        'has_schedule_data': has_schedule_data,
    }


def _read_schedules_from_zip(zip_path: str, progress_cb=None) -> List[Dict[str, Any]]:
    """从 Android 备份 zip 中提取 schedules 表数据。

    流程：
    1. 在 zip 中查找 .db 文件
    2. 解压到临时目录
    3. 查询 schedules 表（若不存在返回空列表）
    4. 清理临时文件
    """
    if not zip_path or not os.path.exists(zip_path):
        return []

    tmp_dir = tempfile.mkdtemp(prefix='sched_analyze_')
    tmp_db = os.path.join(tmp_dir, 'android.db')
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            db_name = next((n for n in zf.namelist()
                            if n.lower().endswith('.db')
                            and not os.path.basename(n).lower().startswith('sqlite_')), None)
            if not db_name:
                return []
            with zf.open(db_name) as src, open(tmp_db, 'wb') as dst:
                shutil.copyfileobj(src, dst)

        schedules: List[Dict[str, Any]] = []
        with sqlite3.connect(tmp_db) as conn:
            conn.row_factory = sqlite3.Row
            # 检查表是否存在
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schedules'"
            )
            if cur.fetchone() is None:
                return []

            cur = conn.execute('SELECT * FROM schedules')
            cols = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                schedules.append({cols[i]: row[i] for i in range(len(cols))})
        return schedules
    except Exception:
        return []
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def _read_local_lessons(target_dir: str, year: int, month: int,
                        progress_cb=None) -> List[Dict[str, Any]]:
    """读取本地指定月份的 lesson 明细。

    优先使用 SQLite 索引，回退到 lesson_manager.get_detail。
    """
    period_prefix = f'{year:04d}-{month:02d}'

    # 优先 SQLite 索引
    try:
        import meta_index_store as mis
        if mis.is_index_available(target_dir):
            db_path = mis._get_index_db_path(target_dir)
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT student_name, date, count, content, note, coach "
                    "FROM lessons WHERE date LIKE ?",
                    (f'{period_prefix}%',)
                )
                return [dict(row) for row in cur.fetchall()]
    except Exception:
        pass

    # 回退：通过 lesson_manager 读取全部明细后过滤
    try:
        import lesson_manager
        records = lesson_manager.get_detail(target_dir)
        if not records:
            return []
        result = []
        for r in records:
            d = str(r.get('date') or '')[:10]
            if d.startswith(period_prefix):
                result.append({
                    'student_name': r.get('name', ''),
                    'date': d,
                    'count': r.get('count', 1),
                    'content': r.get('content', ''),
                    'note': r.get('note', ''),
                    'coach': r.get('coach', ''),
                })
        return result
    except Exception:
        return []


def _expand_schedules_to_month(schedules: List[Dict[str, Any]],
                                year: int, month: int) -> Dict[str, List[Dict]]:
    """将周期性排课计划展开为月度每日计划。

    逻辑：
    - 仅处理 isActive=true 的排课
    - 按startDate/endDate 限定生效区间
    - 按 dayOfWeek 在指定月份内生成每日计划
    - 长期排课（isLongTerm=true）会在该月每周对应日生成记录

    返回: {'YYYY-MM-DD': [{student_name, content, coach, ...}]}
    """
    result: Dict[str, List[Dict]] = {}

    # 计算月份起止日期
    try:
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)
    except Exception:
        return result

    for sch in schedules:
        # 仅处理启用中的排课
        if not sch.get('isActive', True):
            continue

        # 生效区间检查
        try:
            start_date_str = str(sch.get('startDate') or '')[:10]
            end_date_str = str(sch.get('endDate') or '')[:10]
            if start_date_str:
                sd = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                if sd > month_end:
                    continue
                effective_start = max(sd, month_start)
            else:
                effective_start = month_start

            if end_date_str:
                ed = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                if ed < month_start:
                    continue
                effective_end = min(ed, month_end)
            else:
                effective_end = month_end
        except Exception:
            effective_start = month_start
            effective_end = month_end

        # 周几（1=周一 ... 7=周日）
        try:
            dow = int(sch.get('dayOfWeek', 0))
        except (ValueError, TypeError):
            continue
        if dow < 1 or dow > 7:
            continue

        # 在生效区间内查找匹配该 dayOfWeek 的日期
        d = effective_start
        while d <= effective_end:
            # Python weekday(): 0=周一 ... 6=周日；输入 dow 1=周一
            if d.weekday() + 1 == dow:
                date_str = d.strftime('%Y-%m-%d')
                result.setdefault(date_str, []).append({
                    'student_name': sch.get('studentName', ''),
                    'content': sch.get('content', ''),
                    'coach': sch.get('coachName', ''),
                    'start_time': sch.get('startTime', ''),
                    'lesson_type': sch.get('lessonType', ''),
                    'location': sch.get('location', ''),
                })
            # 下一天
            from datetime import timedelta
            d = d + timedelta(days=1)

    return result


def _aggregate_per_student(schedules: List[Dict[str, Any]],
                            local_lessons: List[Dict[str, Any]],
                            year: int, month: int) -> List[Dict[str, Any]]:
    """按学员维度聚合计划数与实际数。"""
    # 展开计划
    planned_per_day = _expand_schedules_to_month(schedules, year, month)

    # 按学员聚合计划数
    planned_by_student: Dict[str, int] = {}
    for day_items in planned_per_day.values():
        for item in day_items:
            name = item.get('student_name', '').strip()
            if name:
                planned_by_student[name] = planned_by_student.get(name, 0) + 1

    # 按学员聚合计划数
    actual_by_student: Dict[str, int] = {}
    for les in local_lessons:
        name = (les.get('student_name') or '').strip()
        if name:
            actual_by_student[name] = actual_by_student.get(name, 0) + 1

    # 合并学员集合
    all_students = set(planned_by_student.keys()) | set(actual_by_student.keys())

    result = []
    for name in sorted(all_students):
        planned = planned_by_student.get(name, 0)
        actual = actual_by_student.get(name, 0)
        absent = max(0, planned - actual)
        rate = (actual / planned) if planned > 0 else 0.0
        result.append({
            'student_name': name,
            'planned': planned,
            'actual': actual,
            'absent': absent,
            'rate': rate,
        })
    return result
