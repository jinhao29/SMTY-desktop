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

from file_lock import file_lock


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
SYNC_HEADERS = ['姓名', '性别', '年龄', '年级', '学校', '电话', '身高(cm)', '体重(kg)', '备注']

THIN = Side(style='thin', color='888888')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center')
HEADER_FILL = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
HEADER_FONT = Font(bold=True, color='FFFFFF', name='微软雅黑')


def build_phone_sync_excel(dir_path: str, output_path: str) -> int:
    """生成 PC→手机 学员同步 Excel。

    参数:
        dir_path: 档案目录（学员档案.xlsx 所在目录）
        output_path: 输出 xlsx 路径

    返回:
        写入的学员行数；档案目录无效时返回 0
    """
    pm = _import_profile_manager()
    if not dir_path or not os.path.isdir(dir_path):
        return 0
    students = pm.list_students(dir_path)
    if not students:
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

    for r, s in enumerate(students, start=2):
        values = [
            s.get('name', ''),
            s.get('gender', '男'),
            s.get('age') or '',
            s.get('grade', ''),
            s.get('school', ''),
            s.get('phone', ''),
            s.get('height') or '',
            s.get('weight') or '',
            s.get('note', ''),
        ]
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border = BORDER
            cell.alignment = CENTER if c != 9 else None
            if c == 9:
                cell.alignment = Alignment(horizontal='left', vertical='center')

    widths = [12, 8, 8, 14, 18, 14, 10, 10, 26]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = 'A2'
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with file_lock(output_path):
        wb.save(output_path)
    return len(students)
