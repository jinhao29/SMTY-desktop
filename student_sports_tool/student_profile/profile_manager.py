# -*- coding: utf-8 -*-
"""管理层：学员档案增删改查 + 课时联动 + 续费预警。

职责：
1. 协调 profile_storage（档案）与 lesson_manager（课时）两个数据源
2. 合并学员名单：档案中的学员 + 课时记录中的学员
3. 计算续费预警等级（红/黄/正常）
4. 提供搜索、统计接口
"""
import os
import sys

# 确保能导入同级模块和父目录的 lesson_manager
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from bmi_processor import calc_bmi, classify_body_type
from profile_storage import (
    read_all as _read_profiles,
    upsert as _upsert_profile,
    delete as _delete_profile,
    set_active_status as _set_active_status,
    append_body_metric as _append_body_metric,
    get_student_extra as _get_student_extra,
    set_student_extra as _set_student_extra,
    GRADE_OPTIONS,
    grade_short_label,
)
import lesson_manager as lm


def grade_display_label(grade: str, age: int = 0) -> str:
    """根据年级与年龄返回适合显示的短标签。

    - 学龄前或年龄<7：返回空串（不显示年级）
    - 其他：返回 grade_short_label（一年级 / 初一 / 高一 ...）
    """
    if not grade or grade == '学龄前':
        return ''
    if age and age < 7:
        return ''
    return grade_short_label(grade)


def list_students(archive_dir: str, include_inactive: bool = False) -> list:
    """获取完整学员列表（合并档案与课时记录）。

    参数:
        include_inactive: 是否包含已停用学员（默认 False，仅返回启用学员）

    返回字典列表，每条含：
        name, age, height, weight, bmi, body_type, grade, note,
        total, attended, remaining, last_date, warn_level, is_active
    warn_level: 'red' (剩余≤3) / 'yellow' (剩余≤6) / 'normal' / 'unknown'
    """
    if not archive_dir or not os.path.isdir(archive_dir):
        return []
    profiles = _read_profiles(archive_dir)
    # 软删除过滤：默认仅返回 is_active=True 的学员
    if not include_inactive:
        profiles = [p for p in profiles if p.get('is_active', True)]
    profile_map = {p['name']: p for p in profiles}
    # 课时汇总（不受 is_active 影响，仅用于补全信息）
    summaries = lm.get_summary(archive_dir)
    summary_map = {s['name']: s for s in summaries}
    # 合并名单：默认仅展示启用的学员；若启用学员的课时记录存在则一并展示
    # 已停用学员只在 include_inactive=True 时才显示
    if include_inactive:
        all_names = sorted(set(profile_map.keys()) | set(summary_map.keys()))
    else:
        all_names = sorted(profile_map.keys())
    result = []
    for name in all_names:
        p = profile_map.get(name, {})
        s = summary_map.get(name, {})
        remaining = s.get('remaining', 0)
        total = s.get('total', 0)
        # 续费预警等级
        if total <= 0:
            warn = 'unknown'
        elif remaining <= 3:
            warn = 'red'
        elif remaining <= 6:
            warn = 'yellow'
        else:
            warn = 'normal'
        result.append({
            'name': name,
            'age': p.get('age', 0),
            'height': p.get('height'),
            'weight': p.get('weight'),
            'bmi': p.get('bmi', 0),
            'body_type': p.get('body_type', ''),
            'grade': p.get('grade', ''),
            'grade_display': grade_display_label(p.get('grade', ''), p.get('age', 0)),
            'note': p.get('note', ''),
            'gender': p.get('gender', '男'),
            'school': p.get('school', ''),
            'phone': p.get('phone', ''),
            'father_height': p.get('father_height'),
            'mother_height': p.get('mother_height'),
            'sleep_hours': p.get('sleep_hours', 0),
            'nutrition_score': p.get('nutrition_score', 0),
            'sports_mins': p.get('sports_mins', 0),
            'total': total,
            'attended': s.get('attended', 0),
            'remaining': remaining,
            'last_date': s.get('last_date', ''),
            'updated_at': p.get('updated_at'),
            'warn_level': warn,
            'is_active': p.get('is_active', True),
        })
    return result


def save_student(archive_dir: str, name: str, age: int, height,
                 weight, grade: str, note: str = '',
                 gender: str = '男', school: str = '', phone: str = '',
                 father_height=None, mother_height=None,
                 sleep_hours=0, nutrition_score=0, sports_mins=0,
                 updated_at_ms=None) -> dict:
    """新增/更新学员档案，自动计算 BMI 与体型。返回写入的档案字典。

    参数:
        height: 身高(cm)，可为 None 或 0（表示未录入，不计算 BMI）
        weight: 体重(kg)，可为 None 或 0
        grade: 年级；年龄<7 时强制设为 '学龄前'
        gender/school/phone: 对齐 Android 端基本字段
        father_height/mother_height: 父母身高(cm)，身高预测用（None=未录入）
        sleep_hours/nutrition_score/sports_mins: 睡眠(h)/营养评分(1-5)/周运动(min)，身高预测用

    副作用：
        1. 若学员此前被停用（is_active=False），保存时会自动重新启用
        2. 身高体重有效时，自动追加当日体型历史（BodyMetricHistory 对齐）
    """
    # 7岁以下强制学龄前
    if age and age < 7:
        grade = '学龄前'
    # 身高体重可选：未录入时 BMI=0
    h = float(height) if height not in (None, '', 0) else 0.0
    w = float(weight) if weight not in (None, '', 0) else 0.0
    bmi = calc_bmi(h, w) if (h > 0 and w > 0) else 0.0
    body_type = classify_body_type(bmi, age) if bmi > 0 else '未知'
    profile = {
        'name': name.strip(),
        'age': age,
        'height': h if h > 0 else None,
        'weight': w if w > 0 else None,
        'bmi': bmi,
        'body_type': body_type,
        'grade': grade,
        'note': note,
        'gender': gender or '男',
        'school': school,
        'phone': phone,
        'father_height': float(father_height) if father_height not in (None, '', 0) else None,
        'mother_height': float(mother_height) if mother_height not in (None, '', 0) else None,
        'sleep_hours': float(sleep_hours) if sleep_hours else 0,
        'nutrition_score': int(nutrition_score or 0),
        'sports_mins': int(sports_mins or 0),
        # LWW 保留手机端时间戳（None → 存储层取当前时间）
        'updated_at_ms': updated_at_ms,
    }
    _upsert_profile(archive_dir, profile)
    # 若学员曾被停用，重新保存即视为恢复启用
    _set_active_status(archive_dir, name.strip(), True)
    # 体型历史：身高体重有效时追加当日记录（同日重复保存自动去重）
    if h > 0 and w > 0:
        from datetime import date as _date
        try:
            _append_body_metric(archive_dir, name.strip(),
                                _date.today().strftime('%Y-%m-%d'), h, w)
        except Exception:
            pass  # 历史记录失败不阻塞档案保存
    # 同步学员到课时汇总表
    lm.sync_students(archive_dir)
    return profile


def delete_student(archive_dir: str, name: str) -> bool:
    """停用学员档案（软删除）：保留所有数据，仅标记 is_active=False。

    与 Android 端软删除设计对齐，避免课时记录与档案断层。
    """
    return _delete_profile(archive_dir, name)


def reactivate_student(archive_dir: str, name: str) -> bool:
    """恢复已停用学员（is_active=True）。"""
    return _set_active_status(archive_dir, name, True)


def set_student_active(archive_dir: str, name: str, is_active: bool) -> bool:
    """设置学员启用/停用状态的统一接口。"""
    return _set_active_status(archive_dir, name, is_active)


def search(archive_dir: str, keyword: str) -> list:
    """按姓名/年级/学校/电话模糊搜索（对齐 Android FTS 检索范围）。"""
    students = list_students(archive_dir)
    if not keyword:
        return students
    kw = keyword.lower()
    return [s for s in students if
            kw in s['name'].lower()
            or kw in s.get('grade', '').lower()
            or kw in s.get('school', '').lower()
            or kw in s.get('phone', '').lower()]


def get_student_extra(archive_dir: str, name: str, key: str, default=None):
    """读取学员扩展元数据（如膳食方案绑定）。"""
    return _get_student_extra(archive_dir, name, key, default)


def set_student_extra(archive_dir: str, name: str, key: str, value) -> bool:
    """写入学员扩展元数据（如膳食方案绑定）。"""
    return _set_student_extra(archive_dir, name, key, value)


def get_warning_stats(archive_dir: str) -> dict:
    """获取续费预警统计。返回 {red: N, yellow: N, total: N}。"""
    students = list_students(archive_dir)
    red = sum(1 for s in students if s['warn_level'] == 'red')
    yellow = sum(1 for s in students if s['warn_level'] == 'yellow')
    return {'red': red, 'yellow': yellow, 'total': len(students)}


def get_grades() -> list:
    """返回年级选项列表。"""
    return GRADE_OPTIONS


# ==================== 手机推送 LWW 合并（v23.2 双端同步） ====================

# Android 端年级编码（Standards.GRADE_OPTIONS）→ PC 端完整年级名
_ANDROID_GRADE_LABELS = {
    '0': '学龄前', '1': '小学一年级', '2': '小学二年级', '3': '小学三年级',
    '4': '小学四年级', '5': '小学五年级', '6': '小学六年级',
    '7': '初中一年级', '8': '初中二年级', '9': '初中三年级',
    '10': '高中一年级', '11': '高中二年级', '12': '高中三年级',
    '13': '中考',
}


def _to_ms(v):
    """宽松毫秒时间戳转换；无效返回 0。"""
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def merge_student_from_phone(archive_dir: str, s: dict) -> str:
    """手机→PC 推送方向的档案 LWW 合并。

    规则（与 双端同步协议.md §4 一致）：
    - 花名册无此学员：用手机端数据建档（需至少有一项有效资料），年级编码转 PC 标签
    - 花名册已有：仅当手机端 updated_at（毫秒）比 PC 记录更新时，刷新
      身高/体重/BMI/体型/年龄/性别/学校/电话/遗传与生活字段；
      年级与备注保留 PC 现值（两端表示不同，不做覆盖）
    - 手机端无时间戳或时间戳较旧：跳过

    返回: 'updated' / 'created' / 'skipped'
    """
    name = (s.get('name') or '').strip()
    if not name:
        return 'skipped'
    phone_ts = _to_ms(s.get('updated_at'))
    students = {p['name']: p for p in _read_profiles(archive_dir)}
    existing = students.get(name)

    if existing is not None:
        pc_ts = _to_ms(existing.get('updated_at'))
        if phone_ts <= 0 or phone_ts <= pc_ts:
            return 'skipped'

    def _pick(key, valid=None, default=None):
        """手机值优先（需通过 valid 校验），否则保留 PC 现值。"""
        v = s.get(key)
        if v not in (None, '', 0) and (valid is None or valid(v)):
            return v
        if existing is not None:
            e = existing.get(key)
            if e not in (None, '', 0):
                return e
        return default

    height = _pick('height', valid=lambda v: float(v) > 0)
    weight = _pick('weight', valid=lambda v: float(v) > 0)

    # 建档场景：手机端无任何有效资料时不产生空档案
    if existing is None and all(
        s.get(k) in (None, '', 0) for k in
        ('height', 'weight', 'age', 'grade', 'school', 'phone')
    ):
        return 'skipped'

    grade = s.get('grade')
    if existing is not None:
        grade = existing.get('grade', '')  # 年级两端表示不同，保留 PC 现值
    elif grade in _ANDROID_GRADE_LABELS:
        grade = _ANDROID_GRADE_LABELS[grade]

    save_student(
        archive_dir,
        name=name,
        age=int(_pick('age', valid=lambda v: int(v) > 0, default=0) or 0),
        height=height,
        weight=weight,
        grade=grade or ('学龄前' if int(_pick('age', default=0) or 0) < 7 else ''),
        note=(existing or {}).get('note', '') if existing else (s.get('note') or ''),
        gender=_pick('gender', default='男') or '男',
        school=_pick('school', default=''),
        phone=_pick('phone', default=''),
        father_height=_pick('father_height', valid=lambda v: float(v) > 0),
        mother_height=_pick('mother_height', valid=lambda v: float(v) > 0),
        sleep_hours=_pick('sleep_hours', valid=lambda v: float(v) > 0, default=0) or 0,
        nutrition_score=_pick('nutrition_score', valid=lambda v: int(v) > 0, default=0) or 0,
        sports_mins=_pick('sports_mins', valid=lambda v: int(v) > 0, default=0) or 0,
        updated_at_ms=phone_ts or None,
    )
    return 'created' if existing is None else 'updated'
