# -*- coding: utf-8 -*-
"""管理层：课时记录数据读写与文件管理。

职责：
- 维护单独的「课时记录.xlsx」文件（位于档案目录下）
- 管理两个工作表：「明细」（每次上课记录）与「汇总」（每学员总览）
- 提供设置总课时、记录上课、删除记录、查询等接口
- 学员名单从档案目录的 .xlsx 文件自动读取

数据结构：
- 明细表列：序号 | 日期 | 学员 | 课时数 | 训练内容 | 备注
- 汇总表列：学员 | 总课时 | 已上课时 | 剩余课时 | 最近上课 | 备注
"""
import os
from datetime import datetime, date as _date
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Side, Font, PatternFill
from file_lock import file_lock, atomic_save_workbook


LESSON_FILE = '课时记录.xlsx'


def _save_wb(fpath, wb):
    """Save workbook with file lock + atomic replace to prevent corruption."""
    with file_lock(fpath):
        atomic_save_workbook(wb, fpath)


def _load_wb(fpath):
    """Load workbook under file lock：防止读到另一进程写入中的半写文件。

    写路径（set/add/delete/update）与读路径（get_*）统一走这里，
    锁只在 load 期间持有，load 完成即释放，不与 _save_wb 嵌套。
    """
    with file_lock(fpath, mode='r'):
        return load_workbook(fpath)


def _invalidate_meta_index(dir_path: str = ''):
    """通知 data_center 的 SQLite 索引失效（数据修改后必须调用）。

    终极架构：桌面端通过 meta_index_store 维护一份基于 Android 备份的强索引，
    任何修改课时操作（add/set/delete/update）后必须失效索引，
    下次查询时 renewal_coordinator 会自动重建或回退 Excel。

    设计：完全静默，失败不影响业务流程；data_center 模块不存在时直接跳过。
    """
    try:
        from data_center.meta_index_store import invalidate_index
        invalidate_index(dir_path)
    except Exception:
        pass

def _notify_data_changed():
    """本地数据变更后广播（触发手机端自动拉取）；独立进程/模块缺失时静默跳过。"""
    try:
        from data_center.sync_beacon import notify_data_changed
        notify_data_changed()
    except Exception:
        pass


THIN = Side(style='thin', color='888888')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT = Alignment(horizontal='left', vertical='center', wrap_text=True)
HEADER_FILL = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
HEADER_FONT = Font(bold=True, color='FFFFFF', name='微软雅黑')
WARN_FILL = PatternFill(start_color='FCE4E4', end_color='FCE4E4', fill_type='solid')
TOTAL_FILL = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')

DETAIL_HEADERS = ['序号', '日期', '学员', '课时数', '训练内容', '备注']
SUMMARY_HEADERS = ['学员', '总课时', '已上课时', '剩余课时', '最近上课', '备注', '手机已消']

# 非学员数据文件：文件名会被 sync_students 误认为学员名，需排除并清理历史遗留
# （2026-09-06 事故：收费记录.xlsx 落在档案目录后被当成学员「收费记录」双向同步污染两端）
_NON_STUDENT_FILES = {'学员档案.xlsx', '教练档案.xlsx', '课时记录.xlsx', '收费记录.xlsx'}


def _lesson_file_path(dir_path):
    """返回课时记录文件的完整路径。"""
    return os.path.join(dir_path, LESSON_FILE)


def _get_students_from_dir(dir_path):
    """从档案目录扫描学员名单（.xlsx 文件名，排除课时记录自身与临时文件）。

    同时排除主数据文件（学员档案/教练档案）——它们是数据存储文件，
    文件名不是学员名（历史 bug：曾把「学员档案」当成幽灵学员写入汇总表）。
    """
    students = []
    if not os.path.isdir(dir_path):
        return students
    for f in sorted(os.listdir(dir_path)):
        if (f.lower().endswith('.xlsx') and not f.startswith('~$')
                and f != LESSON_FILE and f not in _NON_STUDENT_FILES):
            students.append(f[:-5])
    return students


def _ensure_file(dir_path):
    """确保课时记录文件存在，不存在则创建带表头的空文件。"""
    fpath = _lesson_file_path(dir_path)
    if os.path.exists(fpath):
        return fpath
    wb = Workbook()
    # 明细表
    ws_d = wb.active
    ws_d.title = '明细'
    for i, h in enumerate(DETAIL_HEADERS, 1):
        c = ws_d.cell(row=1, column=i, value=h)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER
    ws_d.column_dimensions['A'].width = 6
    ws_d.column_dimensions['B'].width = 12
    ws_d.column_dimensions['C'].width = 12
    ws_d.column_dimensions['D'].width = 8
    ws_d.column_dimensions['E'].width = 30
    ws_d.column_dimensions['F'].width = 18
    ws_d.freeze_panes = 'A2'
    # 汇总表
    ws_s = wb.create_sheet('汇总')
    for i, h in enumerate(SUMMARY_HEADERS, 1):
        c = ws_s.cell(row=1, column=i, value=h)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER
    ws_s.column_dimensions['A'].width = 14
    ws_s.column_dimensions['B'].width = 10
    ws_s.column_dimensions['C'].width = 10
    ws_s.column_dimensions['D'].width = 10
    ws_s.column_dimensions['E'].width = 12
    ws_s.column_dimensions['F'].width = 18
    ws_s.column_dimensions['G'].width = 10
    ws_s.freeze_panes = 'A2'
    _save_wb(fpath, wb)
    return fpath


def _read_detail(wb):
    """读取明细表，返回记录列表。每条：{seq,date,name,count,content,note,row}。"""
    ws = wb['明细']
    records = []
    for r in range(2, ws.max_row + 1):
        name = ws.cell(row=r, column=3).value
        if not name:
            continue
        records.append({
            'seq': ws.cell(row=r, column=1).value,
            'date': ws.cell(row=r, column=2).value,
            'name': str(name).strip(),
            'count': ws.cell(row=r, column=4).value or 0,
            'content': ws.cell(row=r, column=5).value or '',
            'note': ws.cell(row=r, column=6).value or '',
            'row': r,
        })
    return records


def _read_summary_map(wb):
    """读取汇总表，返回 {学员名: {total, note, row}}。"""
    ws = wb['汇总']
    result = {}
    for r in range(2, ws.max_row + 1):
        name = ws.cell(row=r, column=1).value
        if not name:
            continue
        result[str(name).strip()] = {
            'total': ws.cell(row=r, column=2).value or 0,
            'note': ws.cell(row=r, column=6).value or '',
            'phone_used': _to_int(ws.cell(row=r, column=7).value),
            'row': r,
        }
    return result


def _calc_attended(records, name):
    """从明细记录计算指定学员的已上课时总数。"""
    return sum(rec['count'] for rec in records if rec['name'] == name)


def _to_int(v) -> int:
    """宽松转 int（手机端同步来的值可能是字符串/浮点）。"""
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _norm_date(v):
    """日期归一化：datetime→date，字符串尝试 ISO 解析，失败返回 None。

    明细表日期可能混存 datetime（Excel 单元格）与字符串（同步/手输），
    归一化后才能安全比较与取 max。
    """
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, _date):
        return v
    if isinstance(v, str):
        s = v.strip()[:10].replace('/', '-')
        try:
            return _date.fromisoformat(s)
        except ValueError:
            return None
    return None


def _calc_last_date(records, name):
    """从明细记录获取指定学员最近上课日期（兼容 date/datetime/字符串混存）。"""
    dates = []
    for rec in records:
        if rec['name'] != name or not rec['date']:
            continue
        d = _norm_date(rec['date'])
        if d is not None:
            dates.append(d)
    if not dates:
        return ''
    return max(dates)


def _rebuild_summary(wb, records):
    """根据明细记录与已有汇总表，重建汇总表（保留已设置的总课时与备注）。"""
    old_map = _read_summary_map(wb)
    # 合并学员名单：档案目录学员 + 明细中学员 + 已有汇总学员
    all_names = set(old_map.keys()) | {rec['name'] for rec in records}

    ws = wb['汇总']
    # 清空旧数据（保留表头）
    for r in range(2, ws.max_row + 1):
        for c in range(1, 7):
            ws.cell(row=r, column=c).value = None

    sorted_names = sorted(all_names)
    for i, name in enumerate(sorted_names, start=2):
        total = old_map.get(name, {}).get('total', 0)
        attended = _calc_attended(records, name)
        remaining = total - attended
        last_date = _calc_last_date(records, name)
        note = old_map.get(name, {}).get('note', '')

        ws.cell(row=i, column=1, value=name)
        ws.cell(row=i, column=2, value=total)
        ws.cell(row=i, column=3, value=attended)
        ws.cell(row=i, column=4, value=remaining)
        ws.cell(row=i, column=5, value=last_date)
        ws.cell(row=i, column=6, value=note)
        for c in range(1, 7):
            cell = ws.cell(row=i, column=c)
            cell.border = BORDER
            cell.alignment = CENTER if c != 6 else LEFT
            # 剩余课时 <=0 红色警告，>0 黄色
            if c == 4 and remaining <= 0 and total > 0:
                cell.fill = WARN_FILL
            elif c == 2 and total > 0:
                cell.fill = TOTAL_FILL


def get_summary(dir_path, use_phone_used=True):
    """读取所有学员的课时汇总，返回列表。每条：{name,total,attended,remaining,last_date,note}。

    use_phone_used=True（默认，PC 显示/财务口径）：有效已上 = max(明细推导, 手机已消)，
    与手机端剩余课时一致（手机端存在无课时记录的纯扣课）；
    use_phone_used=False（双端同步导出口径）：仅用明细推导值，避免把 PC 显示值
    回灌手机端造成已用重复折算。
    """
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    records = _read_detail(wb)
    old_map = _read_summary_map(wb)
    all_names = set(old_map.keys()) | {rec['name'] for rec in records}
    result = []
    for name in sorted(all_names):
        total = old_map.get(name, {}).get('total', 0)
        detail_attended = _calc_attended(records, name)
        phone_used = _to_int(old_map.get(name, {}).get('phone_used'))
        attended = max(detail_attended, phone_used) if use_phone_used else detail_attended
        last = _calc_last_date(records, name)
        result.append({
            'name': name,
            'total': total,
            'attended': attended,
            # 与手机端口径一致：剩余不为负（手机端 remainingLessons 同样钳 0）
            'remaining': max(0, total - attended),
            # ISO 字符串（调用方直接进 QTableWidgetItem，date 对象会 TypeError）
            'last_date': last.strftime('%Y-%m-%d') if last else '',
            'note': old_map.get(name, {}).get('note', ''),
        })
    return result


def get_detail(dir_path, name=None):
    """读取课时明细记录。name 指定时只返回该学员的记录。"""
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    records = _read_detail(wb)
    if name:
        records = [r for r in records if r['name'] == name]
    return records


def set_total_lessons(dir_path, name, total):
    """设置/修改某学员的总课时数。学员不存在于汇总表则新增一行。"""
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    ws = wb['汇总']
    # 查找已有行
    target_row = None
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value or '').strip() == name:
            target_row = r
            break
    if target_row is None:
        target_row = ws.max_row + 1 if ws.cell(row=ws.max_row, column=1).value else ws.max_row
        if ws.cell(row=target_row, column=1).value:
            target_row += 1
        ws.cell(row=target_row, column=1, value=name)
    ws.cell(row=target_row, column=2, value=total)
    # 重建汇总以更新剩余课时
    records = _read_detail(wb)
    _rebuild_summary(wb, records)
    _save_wb(fpath, wb)
    _invalidate_meta_index(dir_path)
    _notify_data_changed()
    return True


def set_remaining_lessons(dir_path, name, remaining):
    """设置/修改某学员的剩余课时数。

    实现方式：根据当前已上课时数（明细汇总）反算总课时，
    new_total = attended + remaining，然后写入总课时。
    这样保持数据一致性：明细记录的 attended 不变，total 自动调整。

    参数:
        name: 学员名
        remaining: 剩余课时数（>=0）
    返回: True 成功，False 失败
    """
    if remaining < 0:
        return False
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    # 读取当前已上课时
    records = _read_detail(wb)
    attended = _calc_attended(records, name)
    new_total = attended + remaining
    # 复用 set_total_lessons 的写入逻辑
    ws = wb['汇总']
    target_row = None
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value or '').strip() == name:
            target_row = r
            break
    if target_row is None:
        target_row = ws.max_row + 1 if ws.cell(row=ws.max_row, column=1).value else ws.max_row
        if ws.cell(row=target_row, column=1).value:
            target_row += 1
        ws.cell(row=target_row, column=1, value=name)
    ws.cell(row=target_row, column=2, value=new_total)
    # 重建汇总以更新剩余课时
    _rebuild_summary(wb, records)
    _save_wb(fpath, wb)
    _invalidate_meta_index(dir_path)
    _notify_data_changed()
    return True


def dedup_details(dir_path, progress_cb=None):
    """明细去重（v23.9.2 数据修复）：同（学员,日期,节数）保留最新一条。

    背景：同步键名漂移（旧版导出 note=''/新版 summary）曾使同一批手机课时
    在版本切换后被重复导入（55 组重复，明细翻倍），已上虚高、剩余为负。
    幂等键已同步降级为（学员,日期,节数）防复发，本函数用于清理既有重复。
    返回删除的行数。
    """
    from collections import OrderedDict
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    records = _read_detail(wb)
    groups = OrderedDict()
    for rec in records:
        d = _norm_date(rec.get('date'))
        key = (rec.get('name'), d.isoformat() if d else str(rec.get('date') or ''),
               _to_int(rec.get('count')))
        groups.setdefault(key, []).append(rec)
    rows_to_delete = []
    for key, group in groups.items():
        if len(group) > 1:
            rows_to_delete.extend(g['row'] for g in group[:-1])  # 保留最新
    if not rows_to_delete:
        return 0
    ws = wb['明细']
    for row in sorted(rows_to_delete, reverse=True):
        ws.delete_rows(row)
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=1, value=r - 1)
    records = _read_detail(wb)
    _rebuild_summary(wb, records)
    _save_wb(fpath, wb)
    _invalidate_meta_index(dir_path)
    _notify_data_changed()
    if progress_cb:
        progress_cb(f'明细去重完成：删除 {len(rows_to_delete)} 条重复记录')
    return len(rows_to_delete)


def set_phone_used(dir_path, name, used):
    """写入学员的「手机已消」课时数（手机备份合并时调用，v23.9 双端口径统一）。

    手机端存在无课时记录的纯扣课（直接编辑课时包已用），PC 明细无法体现，
    以独立列记录，get_summary 取 max(明细推导, 手机已消) 保证两端剩余课时一致。
    学员不存在于汇总表时新增一行（与 set_total_lessons 一致）。
    """
    used = _to_int(used)
    if used < 0 or not name:
        return False
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    ws = wb['汇总']
    # 幂等：值未变不写（手机合并每次全量推送，避免无意义写盘与变更广播回环）
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value or '').strip() == name:
            if _to_int(ws.cell(row=r, column=7).value) == used:
                return True
            break
    target_row = None
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value or '').strip() == name:
            target_row = r
            break
    if target_row is None:
        target_row = ws.max_row + 1 if ws.cell(row=ws.max_row, column=1).value else ws.max_row
        if ws.cell(row=target_row, column=1).value:
            target_row += 1
        ws.cell(row=target_row, column=1, value=name)
    ws.cell(row=target_row, column=7, value=used)
    records = _read_detail(wb)
    _rebuild_summary(wb, records)
    _save_wb(fpath, wb)
    _invalidate_meta_index(dir_path)
    _notify_data_changed()
    return True


def get_lesson_summary(dir_path, name):
    """读取指定学员的课时汇总信息。返回 dict 或 None。

    返回: {name, total, attended, remaining, last_date, note}
    """
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    records = _read_detail(wb)
    old_map = _read_summary_map(wb)
    if name not in old_map and not any(r['name'] == name for r in records):
        return None
    total = old_map.get(name, {}).get('total', 0)
    phone_used = _to_int(old_map.get(name, {}).get('phone_used'))
    attended = max(_calc_attended(records, name), phone_used)
    last = _calc_last_date(records, name)
    return {
        'name': name,
        'total': total,
        'attended': attended,
        'remaining': max(0, total - attended),
        'last_date': last.strftime('%Y-%m-%d') if last else '',
        'note': old_map.get(name, {}).get('note', ''),
    }


def add_lesson(dir_path, name, date, count, content='', note=''):
    """记录一次上课（追加到明细表，自动更新汇总）。

    参数:
        name: 学员名
        date: 日期字符串 YYYY-MM-DD
        count: 本次课时数
        content: 训练内容
        note: 备注
    """
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    ws = wb['明细']
    # 计算下一个序号
    next_seq = 1
    if ws.max_row >= 2 and ws.cell(row=ws.max_row, column=1).value:
        next_seq = int(ws.cell(row=ws.max_row, column=1).value or 0) + 1
    new_row = ws.max_row + 1 if ws.cell(row=ws.max_row, column=1).value else ws.max_row
    if ws.cell(row=new_row, column=1).value:
        new_row += 1
    ws.cell(row=new_row, column=1, value=next_seq)
    ws.cell(row=new_row, column=2, value=date)
    ws.cell(row=new_row, column=3, value=name)
    ws.cell(row=new_row, column=4, value=count)
    ws.cell(row=new_row, column=5, value=content)
    ws.cell(row=new_row, column=6, value=note)
    for c in range(1, 7):
        cell = ws.cell(row=new_row, column=c)
        cell.border = BORDER
        cell.alignment = CENTER if c != 5 else LEFT
    # 重建汇总
    records = _read_detail(wb)
    _rebuild_summary(wb, records)
    _save_wb(fpath, wb)
    _invalidate_meta_index(dir_path)
    _notify_data_changed()
    return next_seq


def delete_lesson(dir_path, row_num):
    """删除明细表中指定行的上课记录（自动更新汇总）。"""
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    ws = wb['明细']
    if row_num < 2 or row_num > ws.max_row:
        return False
    ws.delete_rows(row_num)
    # 重新编号序号
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=1, value=r - 1)
    records = _read_detail(wb)
    _rebuild_summary(wb, records)
    _save_wb(fpath, wb)
    _invalidate_meta_index(dir_path)
    _notify_data_changed()
    return True


def update_lesson(dir_path, row_num, date=None, count=None, content=None, note=None):
    """修改明细表中指定行的上课记录字段（仅更新非 None 字段，自动更新汇总）。

    参数:
        row_num: 明细表行号（>=2）
        date: 日期字符串 'YYYY-MM-DD'，None 表示不修改
        count: 课时数，None 表示不修改
        content: 训练内容，None 表示不修改
        note: 备注，None 表示不修改
    返回: True 修改成功，False 行号无效
    """
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    ws = wb['明细']
    if row_num < 2 or row_num > ws.max_row:
        return False
    if date is not None:
        ws.cell(row=row_num, column=2, value=date)
    if count is not None:
        ws.cell(row=row_num, column=4, value=count)
    if content is not None:
        ws.cell(row=row_num, column=5, value=content)
    if note is not None:
        ws.cell(row=row_num, column=6, value=note)
    # 重置样式
    for c in range(1, 7):
        cell = ws.cell(row=row_num, column=c)
        cell.border = BORDER
        cell.alignment = CENTER if c != 5 else LEFT
    # 重建汇总
    records = _read_detail(wb)
    _rebuild_summary(wb, records)
    _save_wb(fpath, wb)
    _invalidate_meta_index(dir_path)
    _notify_data_changed()
    return True


def get_lesson_by_row(dir_path, row_num):
    """按明细表行号获取单条上课记录。返回 dict 或 None。"""
    fpath = _ensure_file(dir_path)
    wb = _load_wb(fpath)
    ws = wb['明细']
    if row_num < 2 or row_num > ws.max_row:
        return None
    name = ws.cell(row=row_num, column=3).value
    if not name:
        return None
    return {
        'seq': ws.cell(row=row_num, column=1).value,
        'date': ws.cell(row=row_num, column=2).value,
        'name': str(name).strip(),
        'count': ws.cell(row=row_num, column=4).value or 0,
        'content': ws.cell(row=row_num, column=5).value or '',
        'note': ws.cell(row=row_num, column=6).value or '',
        'row': row_num,
    }


def sync_students(dir_path):
    """将档案目录中的学员同步到汇总表（新增学员补空行，保留已有数据）。

    同时清理历史遗留：早年版本曾把「学员档案」等主数据文件名误写为学员，
    此处在同步时一并从汇总表移除。
    """
    fpath = _ensure_file(dir_path)
    students = _get_students_from_dir(dir_path)
    wb = _load_wb(fpath)
    existing = _read_summary_map(wb)
    added = 0
    removed = 0
    ws = wb['汇总']
    # 清理历史遗留的幽灵学员（主数据文件名）
    for r in range(2, ws.max_row + 1):
        name_v = str(ws.cell(row=r, column=1).value or '').strip()
        if name_v and f'{name_v}.xlsx' in _NON_STUDENT_FILES:
            for c in range(1, 7):
                ws.cell(row=r, column=c).value = None
            removed += 1
    for s in students:
        if s not in existing:
            new_row = ws.max_row + 1 if ws.cell(row=ws.max_row, column=1).value else ws.max_row
            if ws.cell(row=new_row, column=1).value:
                new_row += 1
            ws.cell(row=new_row, column=1, value=s)
            ws.cell(row=new_row, column=2, value=0)
            ws.cell(row=new_row, column=3, value=0)
            ws.cell(row=new_row, column=4, value=0)
            ws.cell(row=new_row, column=5, value='')
            ws.cell(row=new_row, column=6, value='')
            added += 1
    if added or removed:
        records = _read_detail(wb)
        _rebuild_summary(wb, records)
        _save_wb(fpath, wb)
    return added
