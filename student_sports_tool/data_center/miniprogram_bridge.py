# -*- coding: utf-8 -*-
"""数据层：小程序 ↔ 桌面端数据桥（阶段五互通）。

协议（与 miniprogram/src/utils/local-store.js 的 exportBackup/importBackup 严格对齐，
跨端字段锚定测试见 test_miniprogram_parity.py）：

- 导出：桌面端学员档案 + 课时汇总 → 小程序备份 JSON（backup_{mode}_{日期}.json）
  students 表逐字段映射；coaches/lessons/lesson_packages/checkin_records 置空数组
  （小程序导入端对空表为 no-op，不破坏其本地已有数据）
- 导入：小程序备份 JSON → 桌面端
  - students 非软删行 → profile_storage.upsert（姓名主键，已存在则更新）
  - remaining_lessons → lesson_manager.set_remaining_lessons（反算总课时保持一致性）
  - coaches/lessons/checkins：桌面端无对应实体，跳过并计入报告

日期格式：小程序全表 created_at/updated_at 为 "YYYY-MM-DD HH:mm:ss" 字符串，
毫秒时间戳仅用于桌面端 _meta LWW，导入时做单向转换。
"""
import json
import os
from datetime import datetime


def _stamp() -> str:
    """小程序时间戳格式（YYYY-MM-DD HH:mm:ss）。"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _to_ms(date_str: str) -> int:
    """小程序秒级字符串 → 毫秒；解析失败返回 0（upsert 会回退当前时间）。"""
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d %H:%M:%S')
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return 0


def load_payload(json_path: str) -> dict:
    """读取并校验小程序备份 JSON 的顶层结构。

    与 local-store.importBackup 的期望一致：mode 必填，五表为数组。
    抛 ValueError（用户可见）或 FileNotFoundError。
    """
    json_path = os.path.normpath(json_path)
    if not os.path.exists(json_path):
        raise FileNotFoundError(f'导入文件不存在：{json_path}')
    with open(json_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError('文件不是有效的小程序备份 JSON（顶层必须是对象）')
    if int(payload.get('export_version') or 0) != 1:
        raise ValueError(f'不支持的备份版本：{payload.get("export_version")}（期望 1）')
    if not str(payload.get('mode') or '').strip():
        raise ValueError('备份缺少 mode 字段，无法确认目标模式')
    return payload


def export_miniprogram_backup(dir_path: str, mode: str, output_path: str,
                              progress_cb=None) -> dict:
    """导出小程序可导入的备份 JSON。

    返回 {'path': 输出路径, 'students': 导出学员数}
    """
    from student_profile import profile_storage
    from lesson_manager import get_summary

    dir_path = os.path.normpath(dir_path)
    mode = str(mode or '').strip()
    if not mode:
        raise ValueError('必须指定导出模式（shangmen / club）')

    students = profile_storage.read_all(dir_path)
    summary = {row['name']: row for row in get_summary(dir_path)}

    rows = []
    for i, stu in enumerate(students, start=1):
        name = stu['name']
        rows.append({
            'id': i,
            'name': name,
            'phone': stu.get('phone') or '',
            'parent_phone': '',           # 桌面端无家长电话独立字段
            'grade': stu.get('grade') or '',
            'class_group': '',            # club 模式班级标签，桌面端无
            'address': '',                # 桌面端无地址字段
            'status': 'active' if stu.get('is_active', True) else 'inactive',
            'expire_date': '',
            'note': stu.get('note') or '',
            'remaining_lessons': int(summary.get(name, {}).get('remaining', 0)),
            'created_at': _stamp(),
            'updated_at': _stamp(),
            'deleted': 0,
        })
        if progress_cb and i % 20 == 0:
            progress_cb(f'已导出 {i}/{len(students)} 位学员')

    payload = {
        'export_version': 1,
        'mode': mode,
        'exported_at': _stamp(),
        'students': rows,
        'coaches': [],            # 桌面端无教练实体；空表在小程序导入端为 no-op
        'lessons': [],
        'lesson_packages': [],
        'checkin_records': [],
    }

    output_path = os.path.normpath(output_path)
    if not output_path.lower().endswith('.json'):
        output_path += '.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if progress_cb:
        progress_cb(f'导出完成：{len(rows)} 位学员 → {output_path}')
    return {'path': output_path, 'students': len(rows)}


def import_miniprogram_backup(json_path: str, dir_path: str,
                              progress_cb=None) -> dict:
    """导入小程序备份 JSON 到桌面端（学员档案 + 剩余课时）。

    返回 {'created': 新建数, 'updated': 更新数, 'skipped_deleted': 软删跳过数,
          'lessons_applied': 写入剩余课时数, 'skipped_tables': 跳过的表}
    """
    from student_profile import profile_storage
    from lesson_manager import set_remaining_lessons

    payload = load_payload(json_path)
    dir_path = os.path.normpath(dir_path)
    if progress_cb:
        progress_cb(f'导入小程序数据（模式 {payload["mode"]}）...')

    existing = {stu['name'] for stu in profile_storage.read_all(dir_path)}
    created = updated = skipped_deleted = lessons_applied = 0

    for row in payload.get('students') or []:
        name = str(row.get('name') or '').strip()
        if not name:
            continue
        if row.get('deleted'):
            skipped_deleted += 1
            continue
        profile = {
            'name': name,
            'grade': str(row.get('grade') or ''),
            'note': str(row.get('note') or ''),
            # 小程序 phone=学员手机、parent_phone=家长联系方式；桌面端只有"电话"一列，
            # 家长联系方式优先（体测场景主要联系家长）
            'phone': str(row.get('parent_phone') or row.get('phone') or ''),
            'updated_at_ms': _to_ms(row.get('updated_at')),
        }
        profile_storage.upsert(dir_path, profile)
        if name in existing:
            updated += 1
            if progress_cb:
                progress_cb(f'更新学员：{name}')
        else:
            created += 1
            existing.add(name)
            if progress_cb:
                progress_cb(f'新建学员：{name}')
        remaining = row.get('remaining_lessons')
        try:
            remaining = int(remaining)
        except (TypeError, ValueError):
            remaining = None
        if remaining is not None and remaining >= 0:
            if set_remaining_lessons(dir_path, name, remaining):
                lessons_applied += 1

    skipped_tables = [t for t in ('coaches', 'lessons', 'checkin_records')
                      if payload.get(t)]
    if skipped_tables and progress_cb:
        progress_cb(f'跳过桌面端无对应实体的表：{", ".join(skipped_tables)}')
    return {
        'created': created,
        'updated': updated,
        'skipped_deleted': skipped_deleted,
        'lessons_applied': lessons_applied,
        'skipped_tables': skipped_tables,
    }
