# -*- coding: utf-8 -*-
"""数据层：汇总数据导出为 Excel。

职责：
- 将所有学员的关键数据汇总为单个 Excel 表
- 每学员一行：姓名/性别/学校/电话/总课时/已上/剩余/最近测评/首次总分/最近总分/进步幅度/状态
- 应用统一的深色表头与斑马纹样式
"""
import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, Font, PatternFill

from excel_builder import read_student_meta
import lesson_manager as lm
from file_lock import file_lock

THIN = Side(style='thin', color='888888')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
HEADER_FILL = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
HEADER_FONT = Font(bold=True, color='FFFFFF', name='微软雅黑')
WARN_FILL = PatternFill(start_color='FCE4E4', end_color='FCE4E4', fill_type='solid')
GOOD_FILL = PatternFill(start_color='E4FCE4', end_color='E4FCE4', fill_type='solid')

HEADERS = [
    '姓名', '性别', '学校', '联系电话',
    '总课时', '已上课时', '剩余课时', '最近上课',
    '测评次数', '首次总分', '最近总分', '进步幅度', '状态',
]


def _calc_progress(records):
    """计算首次与最近总分及进步幅度。

    返回: (首次总分, 最近总分, 进步幅度字符串)
    """
    score_records = [r for r in records if r.get('total') is not None]
    if not score_records:
        return '', '', ''
    first = score_records[0]['total']
    last = score_records[-1]['total']
    diff = round(last - first, 1)
    arrow = f'↑{abs(diff)}' if diff > 0 else (f'↓{abs(diff)}' if diff < 0 else '持平')
    return round(first, 1), round(last, 1), arrow


def _calc_status(remaining, total):
    """计算学员状态标签。"""
    if total <= 0:
        return '未设课时'
    if remaining <= 0:
        return '已超支'
    if remaining <= 5:
        return '需续费'
    return '正常'


def collect_all_students(dir_path):
    """收集档案目录下所有学员的汇总数据。

    返回: list of dict，每学员一条记录。
    """
    students = []
    files = []
    if os.path.isdir(dir_path):
        for f in sorted(os.listdir(dir_path)):
            if f.lower().endswith('.xlsx') and not f.startswith('~$') and f != '课时记录.xlsx':
                files.append(f)

    # 课时汇总
    try:
        lesson_summary = {s['name']: s for s in lm.get_summary(dir_path)}
    except Exception:
        lesson_summary = {}

    for fname in files:
        name = fname[:-5]
        meta = read_student_meta(os.path.join(dir_path, fname))
        if not meta:
            continue
        info = meta.get('info', {})
        records = meta.get('records', [])
        first_total, last_total, progress = _calc_progress(records)

        ls = lesson_summary.get(name, {})
        total = ls.get('total', 0)
        attended = ls.get('attended', 0)
        remaining = ls.get('remaining', 0)
        last_date = ls.get('last_date', '')

        students.append({
            'name': name,
            'gender': info.get('gender', ''),
            'school': info.get('school', ''),
            'phone': info.get('phone', ''),
            'total': total,
            'attended': attended,
            'remaining': remaining,
            'last_date': last_date,
            'test_count': len(records),
            'first_total': first_total,
            'last_total': last_total,
            'progress': progress,
            'status': _calc_status(remaining, total),
        })
    return students


def export_summary_excel(dir_path, output_path):
    """导出所有学员汇总数据为 Excel。"""
    students = collect_all_students(dir_path)
    wb = Workbook()
    ws = wb.active
    ws.title = '学员总览'

    # 表头
    for i, h in enumerate(HEADERS, 1):
        c = ws.cell(row=1, column=i, value=h)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER

    # 数据行
    for r, stu in enumerate(students, start=2):
        values = [
            stu['name'], stu['gender'], stu['school'], stu['phone'],
            stu['total'] or '', stu['attended'], stu['remaining'],
            stu['last_date'], stu['test_count'],
            stu['first_total'], stu['last_total'], stu['progress'], stu['status'],
        ]
        for c, val in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.border = BORDER
            cell.alignment = CENTER
            # 状态列配色
            if c == 13:
                if stu['status'] in ('已超支', '需续费'):
                    cell.fill = WARN_FILL
                elif stu['status'] == '正常':
                    cell.fill = GOOD_FILL

    # 列宽
    widths = [10, 6, 16, 14, 8, 8, 8, 12, 8, 10, 10, 10, 10]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = 'A2'
    with file_lock(output_path):
        wb.save(output_path)
    return len(students)
