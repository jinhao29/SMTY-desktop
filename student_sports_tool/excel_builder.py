# -*- coding: utf-8 -*-
"""管理层：学员体测档案 Excel 生成与文件管理。

职责：
- 每个学员一个独立 Excel 文件（文件名=学员名）
- 每次测评追加一个工作表（第N次_YYYYMMDD_类型），不覆盖历史
- 维护隐藏的 _meta 工作表存储结构化元数据（JSON）
- 委托 summary_builder 生成「进步对比」汇总表（置顶）
- 还原模板样式（标题/表头/合并/边框）
"""
import os
import json
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Side, Font, PatternFill
from standards import get_primary_standards, get_zhongkao_standards
from scorer import format_value, calc_total
from summary_builder import build_summary_sheet
from file_lock import file_lock, with_retry, atomic_save_workbook

THIN = Side(style='thin', color='888888')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT = Alignment(horizontal='left', vertical='center', wrap_text=True)
TITLE_FILL = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
HEADER_FILL = PatternFill(start_color='DCE6F1', end_color='DCE6F1', fill_type='solid')
SCORE_FILL = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
TITLE_FONT = Font(bold=True, size=12, color='FFFFFF', name='微软雅黑')
HEADER_FONT = Font(bold=True, name='微软雅黑')
NAME_FONT = Font(bold=True, size=14, name='微软雅黑')

# 成绩型档案类型（参与汇总对比）
SCORE_TYPES = ('primary', 'zhongkao', 'zhongkao_old')


def _safe_merge(ws, ranges):
    """安全合并单元格，忽略合并冲突。"""
    for m in ranges:
        try:
            ws.merge_cells(start_row=m[0], start_column=m[1], end_row=m[2], end_column=m[3])
        except Exception:
            pass


def _style_block(ws, r1, c1, r2, c2, fill=None, font=None, align=CENTER):
    """为矩形区域统一设置边框、对齐、填充、字体。"""
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDER
            cell.alignment = align
            if fill:
                cell.fill = fill
            if font:
                cell.font = font


def _record_sheet_name(seq, date, tag):
    """生成测评工作表名：第N次_YYYYMMDD_类型（<=31字符）。"""
    date_compact = (date or '').replace('-', '')[:8]
    base = f"第{seq}次_{date_compact}_{tag}"
    for ch in r'[]*?/\\:':
        base = base.replace(ch, '')
    return base[:31]


def _read_meta(wb):
    """读取隐藏 _meta 工作表，返回元数据 dict。文件无 _meta 时返回空结构。"""
    if '_meta' not in wb.sheetnames:
        return {'info': {}, 'records': []}
    ws = wb['_meta']
    raw = ws.cell(row=1, column=1).value or '{}'
    try:
        meta = json.loads(raw)
        meta.setdefault('info', {})
        meta.setdefault('records', [])
        return meta
    except Exception:
        return {'info': {}, 'records': []}


def _write_meta(wb, meta):
    """写入元数据到隐藏 _meta 工作表（先删旧表再建新表）。"""
    if '_meta' in wb.sheetnames:
        del wb['_meta']
    ws = wb.create_sheet(title='_meta')
    ws.cell(row=1, column=1, value=json.dumps(meta, ensure_ascii=False))
    ws.sheet_state = 'hidden'


def _calc_student_total(student):
    """计算本次测评总分（有效得分平均），无有效成绩返回 None。"""
    records = student.get('records', {})
    scores = [v for v in records.values() if v.get('score') is not None]
    if not scores:
        return None
    return calc_total([{'score': s['score'], 'ok': True} for s in scores])


def _should_hide_grade(student):
    """判断是否隐藏年级信息：年龄 < 7 岁返回 True。"""
    age = student.get('age')
    if age is None:
        return False
    try:
        return int(age) < 7
    except (TypeError, ValueError):
        return False


def _build_primary_sheet(ws, student):
    """生成小学体测档案（含第N次标识）。"""
    grade = student['grade']
    seq = student.get('seq', 1)
    date = student.get('date', '')
    stds = get_primary_standards(grade)
    records = student.get('records', {})
    hide_grade = _should_hide_grade(student)

    ws.column_dimensions['A'].width = 16
    for col in 'BCDEFGHIJ':
        ws.column_dimensions[col].width = 11

    r = 1
    # 7 岁以下标题不显示年级
    if hide_grade:
        title_text = f"{student['name']}  第{seq}次体测档案  {date}"
    else:
        title_text = f"{student['name']}  第{seq}次体测档案（小学{grade}年级）  {date}"
    ws.cell(row=r, column=1, value=title_text)
    _safe_merge(ws, [(r, 1, r, 10)])
    _style_block(ws, r, 1, r, 10, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    r += 2

    # 7 岁以下用「年龄」替代「年级」列
    if hide_grade:
        age_val = student.get('age')
        grade_pair = ('年龄', f"{age_val}岁" if age_val else '')
    else:
        grade_pair = ('年级', f'小学{grade}年级')
    info_pairs = [
        ('姓名', student['name'], '性别', student['gender']),
        ('学校', student.get('school', ''), grade_pair[0], grade_pair[1]),
        ('联系电话', student.get('phone', ''), '测评日期', date),
    ]
    for label1, val1, label2, val2 in info_pairs:
        ws.cell(row=r, column=1, value=label1).font = HEADER_FONT
        ws.cell(row=r, column=2, value=val1)
        ws.cell(row=r, column=5, value=label2).font = HEADER_FONT
        ws.cell(row=r, column=6, value=val2)
        _safe_merge(ws, [(r, 2, r, 4), (r, 6, r, 10)])
        _style_block(ws, r, 1, r, 10)
        r += 1
    r += 1

    headers = ['测试项目', '单位', '满分标准', '及格标准', '实测成绩', '得分', '等级']
    for i, h in enumerate(headers, 1):
        ws.cell(row=r, column=i, value=h)
    _safe_merge(ws, [(r, 3, r, 4), (r, 5, r, 6)])
    _style_block(ws, r, 1, r, 7, fill=HEADER_FILL, font=HEADER_FONT)
    r += 1

    for std in stds:
        full = std.boys_full if student['gender'] == '男' else std.girls_full
        pass_ = std.boys_pass if student['gender'] == '男' else std.girls_pass
        rec = records.get(std.name, {})
        ws.cell(row=r, column=1, value=std.name)
        ws.cell(row=r, column=2, value=std.unit)
        ws.cell(row=r, column=3, value=format_value(full, std.unit))
        ws.cell(row=r, column=5, value=format_value(pass_, std.unit))
        ws.cell(row=r, column=7, value=rec.get('value', ''))
        ws.cell(row=r, column=8, value=rec.get('score', '') if rec.get('score') is not None else '')
        ws.cell(row=r, column=9, value=rec.get('grade', ''))
        _safe_merge(ws, [(r, 3, r, 4), (r, 5, r, 6), (r, 8, r, 8)])
        _style_block(ws, r, 1, r, 9)
        if rec.get('score') is not None:
            ws.cell(row=r, column=8).fill = SCORE_FILL
            ws.cell(row=r, column=9).fill = SCORE_FILL
        r += 1

    scores = [records[s.name] for s in stds
              if s.name in records and records[s.name].get('score') is not None]
    if scores:
        total = calc_total([{'score': s['score']} for s in scores])
        ws.cell(row=r, column=1, value='综合得分').font = HEADER_FONT
        ws.cell(row=r, column=3, value=round(total, 1))
        ws.cell(row=r, column=5, value=student.get('grade_label', ''))
        _safe_merge(ws, [(r, 3, r, 4), (r, 5, r, 9)])
        _style_block(ws, r, 1, r, 9, fill=SCORE_FILL, font=Font(bold=True, name='微软雅黑'))
    r += 2

    ws.cell(row=r, column=1, value='综合评价与提升建议').font = TITLE_FONT
    _safe_merge(ws, [(r, 1, r, 9)])
    _style_block(ws, r, 1, r, 9, fill=TITLE_FILL, align=LEFT)
    r += 1
    ws.cell(row=r, column=1, value=student.get('evaluation', '') or '（请填写综合评价）')
    _safe_merge(ws, [(r, 1, r + 2, 9)])
    _style_block(ws, r, 1, r + 2, 9, align=LEFT)
    ws.row_dimensions[r].height = 30
    ws.freeze_panes = 'A2'


def _build_zhongkao_sheet(ws, student):
    """生成中考档案（含第N次标识）。"""
    seq = student.get('seq', 1)
    date = student.get('date', '')
    stds = get_zhongkao_standards()
    records = student.get('records', {})

    ws.column_dimensions['A'].width = 18
    for col in 'BCDEFGHI':
        ws.column_dimensions[col].width = 12

    r = 1
    ws.cell(row=r, column=1,
            value=f"{student['name']}  第{seq}次中考体育测评档案（{student.get('zk_plan', '2026新方案')}）  {date}")
    _safe_merge(ws, [(r, 1, r, 9)])
    _style_block(ws, r, 1, r, 9, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    r += 2

    info_pairs = [
        ('姓名', student['name'], '性别', student['gender']),
        ('学校', student.get('school', ''), '届别', student.get('zk_plan', '2026新方案')),
        ('联系电话', student.get('phone', ''), '测评日期', date),
    ]
    for label1, val1, label2, val2 in info_pairs:
        ws.cell(row=r, column=1, value=label1).font = HEADER_FONT
        ws.cell(row=r, column=2, value=val1)
        ws.cell(row=r, column=5, value=label2).font = HEADER_FONT
        ws.cell(row=r, column=6, value=val2)
        _safe_merge(ws, [(r, 2, r, 4), (r, 6, r, 9)])
        _style_block(ws, r, 1, r, 9)
        r += 1
    r += 1

    headers = ['测试项目', '单位', '满分标准', '及格标准', '实测成绩', '得分', '等级']
    for i, h in enumerate(headers, 1):
        ws.cell(row=r, column=i, value=h)
    _style_block(ws, r, 1, r, 7, fill=HEADER_FILL, font=HEADER_FONT)
    r += 1

    for std in stds:
        full = std.boys_full if student['gender'] == '男' else std.girls_full
        pass_ = std.boys_pass if student['gender'] == '男' else std.girls_pass
        rec = records.get(std.name, {})
        ws.cell(row=r, column=1, value=std.name)
        ws.cell(row=r, column=2, value=std.unit)
        ws.cell(row=r, column=3, value=format_value(full, std.unit))
        ws.cell(row=r, column=4, value=format_value(pass_, std.unit))
        ws.cell(row=r, column=5, value=rec.get('value', ''))
        ws.cell(row=r, column=6, value=rec.get('score', '') if rec.get('score') is not None else '')
        ws.cell(row=r, column=7, value=rec.get('grade', ''))
        _style_block(ws, r, 1, r, 7)
        if rec.get('score') is not None:
            ws.cell(row=r, column=6).fill = SCORE_FILL
            ws.cell(row=r, column=7).fill = SCORE_FILL
        r += 1

    ws.cell(row=r, column=1,
            value='提示：中考需从一类、二类、三类各选一项，取三项得分之和为总分（满分300）').font = \
        Font(italic=True, color='888888', name='微软雅黑', size=9)
    _safe_merge(ws, [(r, 1, r, 7)])
    _style_block(ws, r, 1, r, 7, align=LEFT)
    ws.freeze_panes = 'A2'


def _build_simple_sheet(ws, student, blocks):
    """生成简单评估表（体态矫正/体重管理，含第N次标识）。"""
    seq = student.get('seq', 1)
    date = student.get('date', '')
    ws.column_dimensions['A'].width = 16
    for col in 'BCDEFGHI':
        ws.column_dimensions[col].width = 12

    r = 1
    ws.cell(row=r, column=1,
            value=f"{student['name']}  第{seq}次{student['sheet_tag']}  {date}")
    _safe_merge(ws, [(r, 1, r, 9)])
    _style_block(ws, r, 1, r, 9, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    r += 2

    info_pairs = [
        ('姓名', student['name'], '性别', student['gender']),
        ('学校', student.get('school', ''), '联系电话', student.get('phone', '')),
        ('测评日期', date, '备注', student.get('note', '')),
    ]
    for label1, val1, label2, val2 in info_pairs:
        ws.cell(row=r, column=1, value=label1).font = HEADER_FONT
        ws.cell(row=r, column=2, value=val1)
        ws.cell(row=r, column=5, value=label2).font = HEADER_FONT
        ws.cell(row=r, column=6, value=val2)
        _safe_merge(ws, [(r, 2, r, 4), (r, 6, r, 9)])
        _style_block(ws, r, 1, r, 9)
        r += 1
    r += 1

    for title, rows in blocks:
        ws.cell(row=r, column=1, value=title).font = TITLE_FONT
        _safe_merge(ws, [(r, 1, r, 9)])
        _style_block(ws, r, 1, r, 9, fill=TITLE_FILL, align=LEFT)
        r += 1
        for label, content in rows:
            ws.cell(row=r, column=1, value=label).font = HEADER_FONT
            ws.cell(row=r, column=2, value=content or '')
            _safe_merge(ws, [(r, 2, r, 9)])
            _style_block(ws, r, 1, r, 9, align=LEFT)
            ws.row_dimensions[r].height = 28
            r += 1
        r += 1
    ws.freeze_panes = 'A2'


def _build_record_sheet(wb, student, seq):
    """创建本次测评工作表并写入数据，返回工作表对象。"""
    sheet_name = _record_sheet_name(seq, student['date'], student['sheet_tag'])
    # 同名（同次同日同类型）已存在则删除重建，避免重名报错
    if sheet_name in wb.sheetnames:
        del wb[sheet_name]
    ws = wb.create_sheet(title=sheet_name)
    student_with_seq = {**student, 'seq': seq}
    ttype = student['table_type']
    if ttype == 'primary':
        _build_primary_sheet(ws, student_with_seq)
    elif ttype == 'zhongkao':
        _build_zhongkao_sheet(ws, student_with_seq)
    elif ttype in ('posture', 'weight'):
        _build_simple_sheet(ws, student_with_seq, student.get('blocks', []))
    return sheet_name


def _make_record_meta(student, seq, sheet_name):
    """从 student 对象提取本次记录的元数据 dict。"""
    ttype = student['table_type']
    scores = {}
    if ttype in SCORE_TYPES:
        for k, v in student.get('records', {}).items():
            scores[k] = {
                'value': v.get('value', ''),
                'score': v.get('score'),
                'grade': v.get('grade', ''),
            }
    return {
        'seq': seq,
        'date': student['date'],
        'type': ttype,
        'tag': student['sheet_tag'],
        'sheet_name': sheet_name,
        'scores': scores,
        'total': _calc_student_total(student) if ttype in SCORE_TYPES else None,
        'evaluation': student.get('evaluation', ''),
    }


def append_record(student, dir_path):
    """将一次测评记录追加到学员档案文件。

    参数:
        student: 学员本次测评数据 dict
        dir_path: 档案目录（每学员一个 .xlsx）

    返回:
        (sheet_name, file_path)

    流程:
        1. 文件路径 = dir_path/学员名.xlsx，不存在则新建
        2. 读取 _meta 元数据，更新基本信息
        3. 计算本次序号，创建「第N次_日期_类型」工作表
        4. 追加本次记录到 _meta.records
        5. 成绩型档案重建「进步对比」汇总表（置顶）
        6. 写回 _meta，保存文件

    并发安全：
        使用 portalocker 文件锁防止多端同时写入导致文件损坏。
        默认超时 5 秒，期间若无法获取锁则抛出 LockTimeoutError。
    """
    os.makedirs(dir_path, exist_ok=True)
    # M5-S1: 调用统一清洗器，替换原仅过滤 / 与 \ 的简陋实现
    try:
        from filename_sanitizer import sanitize_filename
        safe_name = sanitize_filename(student['name'])
    except ImportError:
        safe_name = student['name'].replace('/', '_').replace('\\', '_').strip()
    file_path = os.path.join(dir_path, f"{safe_name}.xlsx")

    def _do_append():
        with file_lock(file_path, timeout=5.0):
            if os.path.exists(file_path):
                wb = load_workbook(file_path)
            else:
                wb = Workbook()
                wb.remove(wb.active)

            meta = _read_meta(wb)
            # 更新基本信息（保留已有值，新值覆盖空值）
            info = meta.setdefault('info', {})
            info['name'] = student['name']
            info['gender'] = student['gender']
            # 年龄字段：填了就更新，没填保留原值
            if student.get('age') is not None:
                info['age'] = student['age']
            if student.get('school'):
                info['school'] = student['school']
            if student.get('phone'):
                info['phone'] = student['phone']
            info.setdefault('school', student.get('school', ''))
            info.setdefault('phone', student.get('phone', ''))
            info.setdefault('age', student.get('age'))
            # 遗传与生活习惯字段（对齐 Android Student v17，身高预测用；填了才覆盖）
            for _k in ('father_height', 'mother_height', 'sleep_hours',
                       'nutrition_score', 'sports_mins'):
                if student.get(_k) is not None:
                    info[_k] = student[_k]

            seq = len(meta.get('records', [])) + 1
            sheet_name = _build_record_sheet(wb, student, seq)

            record = _make_record_meta(student, seq, sheet_name)
            meta.setdefault('records', []).append(record)

            # 成绩型档案重建汇总表（置顶）
            if student['table_type'] in SCORE_TYPES:
                build_summary_sheet(wb, meta)

            _write_meta(wb, meta)
            atomic_save_workbook(wb, file_path)
            return sheet_name, file_path

    return with_retry(_do_append, max_retries=3, retry_interval=1.0)


def read_student_meta(file_path):
    """读取学员档案元数据（基本信息 + 测评历史），文件不存在返回 None。

    并发安全：使用 portalocker 共享锁防止读到正在写入的中间状态。
    """
    if not os.path.exists(file_path):
        return None

    def _do_read():
        with file_lock(file_path, mode='r', timeout=5.0):
            wb = load_workbook(file_path, read_only=True)
            return _read_meta(wb)

    return with_retry(_do_read, max_retries=3, retry_interval=1.0)
