# -*- coding: utf-8 -*-
"""数据层：PC→手机 学员汇总同步包（Excel）生成。

用途：
- 局域网/USB 双端同步的「PC→手机」方向：PC 端把学员汇总导出为 Excel，
  手机端（LanSyncManager.pullStudents）拉取后经 ExcelSync.importStudentsFromTabularExcel
  智能表头映射导入合并（同名默认 UPDATE_PART 更新身体形态）。

列集合约定（与 Android ExcelSync.buildColumnMapping 严格对齐，勿随意增列）：
    姓名 | 性别 | 年龄 | 年级 | 学校 | 电话 | 身高(cm) | 体重(kg) | 备注
- 每个表头必须命中 ExcelSync 智能映射的唯一 key
- ⚠️ 禁止加入「父身高」「母身高」等含"高/重"字样的列——会被误映射为身高/体重
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from file_lock import file_lock, atomic_save_workbook


def _import_profile_manager():
    """导入 profile_manager（兼容主程序扁平导入与独立进程两种运行环境）。"""
    try:
        import profile_manager  # noqa: F401
        return profile_manager
    except ImportError:
        pass
    sub = os.path.join(_PARENT, 'student_profile')
    if sub not in sys.path:
        sys.path.insert(0, sub)
    import profile_manager
    return profile_manager

# 与 ExcelSync.buildColumnMapping 一一对应的列（顺序即输出顺序）
# 「数据更新时间」= PC 端毫秒时间戳，手机端据此做 LWW（新者胜），勿改列名关键字
SYNC_HEADERS = ['姓名', '性别', '年龄', '年级', '学校', '电话',
                '身高(cm)', '体重(kg)', '数据更新时间', '备注']

THIN = Side(style='thin', color='888888')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center')
HEADER_FILL = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
HEADER_FONT = Font(bold=True, color='FFFFFF', name='微软雅黑')


def _import_data_exporter():
    """导入 data_exporter（collect_all_students，扫描每学员 xlsx 的 _meta）。"""
    try:
        import data_exporter  # noqa: F401
        return data_exporter
    except ImportError:
        pass
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import data_exporter
    return data_exporter


def build_phone_sync_excel(dir_path: str, output_path: str) -> int:
    """生成 PC→手机 学员同步 Excel。

    数据源双来源合并：
    - 花名册（学员档案.xlsx，含 年龄/年级/身高/体重/备注）
    - 每学员 xlsx 的 _meta.info（Android 恢复/导入刚落地、花名册可能尚未同步）
    任一来源存在的学员都会进入同步包，字段取「先花名册、后档案 info」。

    返回:
        写入的学员行数；档案目录无效时返回 0
    """
    pm = _import_profile_manager()
    de = _import_data_exporter()
    if not dir_path or not os.path.isdir(dir_path):
        return 0
    roster = {s['name']: s for s in pm.list_students(dir_path)}
    scanned = {}
    try:
        scanned = {s['name']: s for s in de.collect_all_students(dir_path)}
    except Exception:
        scanned = {}
    names = sorted(set(roster) | set(scanned))
    if not names:
        return 0

    wb = Workbook()
    ws = wb.active
    ws.title = '学员同步'
    for i, h in enumerate(SYNC_HEADERS, 1):
        c = ws.cell(row=1, column=i, value=h)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER

    def _pick(r, s, key, default=''):
        v = r.get(key) or s.get(key)
        return v if v not in (None, '') else default

    def _to_ms(v):
        """updated_at → 毫秒整数（兼容旧字符串格式）；无效返回 ''。"""
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return ''

    def _norm_text(v):
        """文本列规范化：数字单元格（电话被 Excel 存为数值等）统一转字符串，
        避免 Android 端按文本列解析时类型不一致。"""
        if v is None:
            return ''
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    for row_idx, name in enumerate(names, start=2):
        r = roster.get(name, {})
        s = scanned.get(name, {})
        values = [
            name,
            _norm_text(_pick(r, s, 'gender', '男')),
            _norm_text(_pick(r, s, 'age', '')),
            _norm_text(r.get('grade') or ''),
            _norm_text(_pick(r, s, 'school', '')),
            _norm_text(_pick(r, s, 'phone', '')),
            _pick(r, s, 'height', ''),
            _pick(r, s, 'weight', ''),
            _to_ms(r.get('updated_at') or s.get('updated_at')),
            _norm_text(r.get('note') or ''),
        ]
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=c, value=v)
            cell.border = BORDER
            cell.alignment = CENTER if c != 10 else Alignment(horizontal='left', vertical='center')

    widths = [12, 8, 8, 14, 18, 14, 10, 10, 16, 26]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = 'A2'
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with file_lock(output_path):
        atomic_save_workbook(wb, output_path)
    return len(names)
