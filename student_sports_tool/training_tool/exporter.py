# -*- coding: utf-8 -*-
"""管理层：训练任务导出。

支持两种格式：
- Excel（.xlsx）：openpyxl，深色表头+分区色块+签字栏
- Word（.docx）：python-docx，A4纵向，正式排版，适合打印或转PDF发家长
"""
import os
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, Font, PatternFill
from openpyxl.utils import get_column_letter
from task_model import SinglePlan, WeeklyPlan, Block, DayPlan
from file_lock import file_lock, atomic_save_workbook

# 统一样式
THIN = Side(style='thin', color='666666')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT = Alignment(horizontal='left', vertical='center', wrap_text=True)
TITLE_FILL = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
HEADER_FILL = PatternFill(start_color='DCE6F1', end_color='DCE6F1', fill_type='solid')
BLOCK_FILLS = {
    '热身': PatternFill(start_color='E2EFDA', end_color='E2EFDA', fill_type='solid'),
    '主项训练': PatternFill(start_color='FCE4D6', end_color='FCE4D6', fill_type='solid'),
    '放松拉伸': PatternFill(start_color='D9E1F2', end_color='D9E1F2', fill_type='solid'),
}
SIGN_FILL = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
TITLE_FONT = Font(bold=True, size=14, color='FFFFFF', name='微软雅黑')
HEADER_FONT = Font(bold=True, name='微软雅黑')
NAME_FONT = Font(bold=True, size=11, name='微软雅黑')


# =========================================================================
# Excel 导出
# =========================================================================
def export_single_excel(plan: SinglePlan, path: str):
    """导出单次训练任务单到 Excel。"""
    wb = Workbook()
    ws = wb.active
    ws.title = f"{plan.student_name}_训练单"
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 22
    ws.column_dimensions['C'].width = 8
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 30
    r = 1

    # 标题
    ws.cell(row=r, column=1, value=f"{plan.student_name}  训练任务单")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    ws.row_dimensions[r].height = 28
    r += 2

    # 基本信息
    info_pairs = [
        ('姓名', plan.student_name, '性别', plan.gender, '年龄', plan.age),
        ('教练', plan.coach, '训练日期', plan.train_date, '训练地点', plan.location),
    ]
    for label1, v1, label2, v2, label3, v3 in info_pairs:
        ws.cell(row=r, column=1, value=label1).font = HEADER_FONT
        ws.cell(row=r, column=2, value=v1)
        ws.cell(row=r, column=3, value=label2).font = HEADER_FONT
        ws.cell(row=r, column=4, value=v2)
        # 第3组放在 E 列（合并E:F不存在，简化处理）
        _style_range(ws, r, 1, r, 4)
        r += 1
    # 第二行基本信息含第3组：放在新一行
    ws.cell(row=r, column=1, value='训练目标').font = HEADER_FONT
    ws.cell(row=r, column=2, value=plan.goal)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, align=LEFT)
    ws.row_dimensions[r].height = 22
    r += 2

    # 训练内容
    ws.cell(row=r, column=1, value='训练内容')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    r += 1

    # 表头
    headers = ['序号', '动作名称', '组数', '次数/时长', '要点提示']
    for i, h in enumerate(headers, 1):
        ws.cell(row=r, column=i, value=h)
    _style_range(ws, r, 1, r, 5, fill=HEADER_FILL, font=HEADER_FONT)
    r += 1

    # 各区块
    seq = 0
    for block in plan.blocks:
        if not block.tasks:
            continue
        # 区块标题行
        ws.cell(row=r, column=1, value=block.title)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        fill = BLOCK_FILLS.get(block.title, HEADER_FILL)
        _style_range(ws, r, 1, r, 5, fill=fill, font=NAME_FONT, align=LEFT)
        r += 1
        # 任务行
        for task in block.tasks:
            seq += 1
            ws.cell(row=r, column=1, value=seq)
            ws.cell(row=r, column=2, value=task.name)
            ws.cell(row=r, column=3, value=task.sets)
            ws.cell(row=r, column=4, value=task.reps)
            ws.cell(row=r, column=5, value=task.note)
            _style_range(ws, r, 1, r, 5, align=LEFT)
            ws.row_dimensions[r].height = 22
            r += 1

    # 教练寄语
    r += 1
    ws.cell(row=r, column=1, value='教练寄语').font = HEADER_FONT
    ws.cell(row=r, column=2, value=plan.coach_note)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, align=LEFT)
    ws.row_dimensions[r].height = 30
    r += 1

    # 注意事项
    ws.cell(row=r, column=1, value='注意事项').font = HEADER_FONT
    ws.cell(row=r, column=2, value=plan.remarks)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, align=LEFT)
    ws.row_dimensions[r].height = 30
    r += 1

    # 下次课预告
    ws.cell(row=r, column=1, value='下次课预告').font = HEADER_FONT
    ws.cell(row=r, column=2, value=plan.next_preview)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, align=LEFT)
    r += 2

    # 家长签字反馈区
    ws.cell(row=r, column=1, value='家长签字与反馈')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    r += 1
    ws.cell(row=r, column=1, value='家长签字').font = HEADER_FONT
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.cell(row=r, column=4, value='完成情况').font = HEADER_FONT
    ws.cell(row=r, column=5, value='□全部完成  □部分完成  □未完成')
    _style_range(ws, r, 1, r, 5, fill=SIGN_FILL, align=LEFT)
    ws.row_dimensions[r].height = 28
    r += 1
    ws.cell(row=r, column=1, value='学员状态').font = HEADER_FONT
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    ws.cell(row=r, column=2, value='□精力充沛  □正常  □疲劳  □其他：')
    _style_range(ws, r, 1, r, 5, fill=SIGN_FILL, align=LEFT)
    ws.row_dimensions[r].height = 28
    r += 1
    ws.cell(row=r, column=1, value='家长反馈').font = HEADER_FONT
    ws.merge_cells(start_row=r, start_column=2, end_row=r+2, end_column=5)
    _style_range(ws, r, 1, r+2, 5, fill=SIGN_FILL, align=LEFT)
    for rr in range(r, r+3):
        ws.row_dimensions[rr].height = 28

    ws.freeze_panes = 'A2'
    with file_lock(path):
        atomic_save_workbook(wb, path)
    return path


def export_weekly_excel(plan: WeeklyPlan, path: str):
    """导出周计划表到 Excel（3-Sheet 教案式布局）。

    参照项目内教案模板（教案模板4-6岁.xlsx 等）的结构：
    - Sheet1 周计划总览：标题 + 基本信息（含年龄段）+ 7日概览表 + 教练寄语
    - Sheet2 每日训练明细：按教案格式展开每日（准备/教学/结束三部分）
    - Sheet3 家长须知：训练说明 + 安全提示 + 签字反馈区
    """
    wb = Workbook()
    # 默认 Sheet 改为总览
    ws_overview = wb.active
    ws_overview.title = "周计划总览"
    ws_detail = wb.create_sheet("每日训练明细")
    ws_parent = wb.create_sheet("家长须知")

    age_group = plan.age_group or '未指定'
    coach_note = plan.coach_note or '请家长督促学员按时完成训练，注意训练安全。如有疑问请及时联系教练。'

    # === Sheet1: 周计划总览 ===
    _build_overview_sheet(ws_overview, plan, age_group, coach_note)
    # === Sheet2: 每日训练明细 ===
    _build_detail_sheet(ws_detail, plan, age_group)
    # === Sheet3: 家长须知 ===
    _build_parent_sheet(ws_parent, plan, coach_note)

    with file_lock(path):
        atomic_save_workbook(wb, path)
    return path


def _build_overview_sheet(ws, plan: WeeklyPlan, age_group: str, coach_note: str):
    """Sheet1：周计划总览。"""
    # 列宽
    widths = [10, 14, 22, 40, 10, 12, 22]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 1

    # 标题
    ws.cell(row=r, column=1, value=f"{plan.student_name}  周训练计划表")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
    _style_range(ws, r, 1, r, 7, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    ws.row_dimensions[r].height = 30
    r += 2

    # 基本信息（含年龄段）
    ws.cell(row=r, column=1, value='教练').font = HEADER_FONT
    ws.cell(row=r, column=2, value=plan.coach)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.cell(row=r, column=4, value='年龄段').font = HEADER_FONT
    ws.cell(row=r, column=5, value=age_group)
    ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=7)
    _style_range(ws, r, 1, r, 7)
    r += 1
    ws.cell(row=r, column=1, value='本周起始').font = HEADER_FONT
    ws.cell(row=r, column=2, value=plan.week_start)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.cell(row=r, column=4, value='本周目标').font = HEADER_FONT
    ws.cell(row=r, column=5, value=plan.goal)
    ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=7)
    _style_range(ws, r, 1, r, 7, align=LEFT)
    ws.row_dimensions[r].height = 24
    r += 2

    # 7日概览表表头（扩展为7列：含核心内容、时长、器材）
    headers = ['星期', '日期', '训练主题', '核心内容', '强度', '时长', '器材']
    for i, h in enumerate(headers, 1):
        ws.cell(row=r, column=i, value=h)
    _style_range(ws, r, 1, r, 7, fill=HEADER_FILL, font=HEADER_FONT)
    r += 1

    # 7日概览
    for day in plan.days:
        ws.cell(row=r, column=1, value=day.weekday)
        ws.cell(row=r, column=2, value=day.date)
        ws.cell(row=r, column=3, value=day.theme)
        ws.cell(row=r, column=4, value=day.daily_goal or day.key_tasks)
        ws.cell(row=r, column=5, value=day.intensity)
        ws.cell(row=r, column=6, value=f"{day.duration_min}min" if day.duration_min else '')
        ws.cell(row=r, column=7, value=day.equipment)
        # 休息日特殊样式
        if day.intensity == '休息':
            for c in range(1, 8):
                ws.cell(row=r, column=c).fill = SIGN_FILL
        _style_range(ws, r, 1, r, 7, align=LEFT)
        ws.row_dimensions[r].height = 30
        r += 1

    r += 1
    # 教练寄语
    ws.cell(row=r, column=1, value='教练寄语')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
    _style_range(ws, r, 1, r, 7, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    r += 1
    ws.cell(row=r, column=1, value=coach_note)
    ws.merge_cells(start_row=r, start_column=1, end_row=r + 1, end_column=7)
    _style_range(ws, r, 1, r + 1, 7, align=LEFT)
    for rr in range(r, r + 2):
        ws.row_dimensions[rr].height = 28

    ws.freeze_panes = 'A2'


def _build_detail_sheet(ws, plan: WeeklyPlan, age_group: str):
    """Sheet2：每日训练明细（参照教案格式）。

    每日一个区块，含：
    - 课程标题行
    - 基本信息行（学员/年龄/教练/日期/核心内容）
    - 表头行（课序/教学内容/时间/教学方法/注意事项/组次/器材）
    - 准备部分 / 教学部分（按类别）/ 结束部分
    """
    widths = [10, 28, 8, 36, 28, 10, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 1

    for idx, day in enumerate(plan.days):
        # 课程标题
        title = f"{day.weekday}  {day.theme or '训练课'}"
        ws.cell(row=r, column=1, value=title)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        _style_range(ws, r, 1, r, 7, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
        ws.row_dimensions[r].height = 26
        r += 1

        # 基本信息行
        ws.cell(row=r, column=1, value='学员姓名').font = HEADER_FONT
        ws.cell(row=r, column=2, value=plan.student_name)
        ws.cell(row=r, column=3, value='年龄').font = HEADER_FONT
        ws.cell(row=r, column=4, value=age_group)
        ws.cell(row=r, column=5, value='教练').font = HEADER_FONT
        ws.cell(row=r, column=6, value=plan.coach)
        ws.cell(row=r, column=7, value=day.date)
        _style_range(ws, r, 1, r, 7)
        r += 1
        # 核心内容
        ws.cell(row=r, column=1, value='核心内容').font = HEADER_FONT
        ws.cell(row=r, column=2, value=day.daily_goal or day.key_tasks or '（未设置）')
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
        _style_range(ws, r, 1, r, 7, align=LEFT)
        ws.row_dimensions[r].height = 24
        r += 1

        # 表头
        headers = ['课序', '教学内容', '时间', '教学方法', '注意事项', '组次', '器材']
        for i, h in enumerate(headers, 1):
            ws.cell(row=r, column=i, value=h)
        _style_range(ws, r, 1, r, 7, fill=HEADER_FILL, font=HEADER_FONT)
        r += 1

        # 准备部分
        r = _write_day_section(ws, r, '准备部分', day.warmup,
                               '10min', BLOCK_FILLS.get('热身', HEADER_FILL))
        # 教学部分（按 --- 分隔符拆分类别，每类作为一行）
        if day.main_content:
            blocks = [b.strip() for b in day.main_content.split('---') if b.strip()]
            if not blocks:
                blocks = [day.main_content.strip()]
            for block in blocks:
                r = _write_day_section(ws, r, '教学部分', block,
                                       '15min', BLOCK_FILLS.get('主项训练', HEADER_FILL))
        # 结束部分
        r = _write_day_section(ws, r, '结束部分', day.cooldown,
                               '5min', BLOCK_FILLS.get('放松拉伸', HEADER_FILL))

        # 区块间空行
        r += 1

    ws.freeze_panes = 'A2'


def _write_day_section(ws, r, section_name, content, duration, fill):
    """写入某日的某个部分（准备/教学/结束）。

    content 可为多行文本，每行一个类别或动作列表。
    """
    ws.cell(row=r, column=1, value=section_name)
    ws.cell(row=r, column=2, value=content or '（无）')
    ws.cell(row=r, column=3, value=duration)
    # 教学方法/注意事项/组次/器材 留空（用户在 UI 中可补充完整教案）
    ws.cell(row=r, column=4, value='')
    ws.cell(row=r, column=5, value='')
    ws.cell(row=r, column=6, value='')
    ws.cell(row=r, column=7, value='')
    _style_range(ws, r, 1, r, 7, fill=fill, font=NAME_FONT, align=LEFT)
    ws.row_dimensions[r].height = 36
    return r + 1


def _build_parent_sheet(ws, plan: WeeklyPlan, coach_note: str):
    """Sheet3：家长须知。"""
    widths = [12, 22, 22, 22, 22]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 1

    # 标题
    ws.cell(row=r, column=1, value=f"{plan.student_name}  家长须知与反馈")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    ws.row_dimensions[r].height = 30
    r += 2

    # 教练寄语
    ws.cell(row=r, column=1, value='教练寄语').font = HEADER_FONT
    ws.cell(row=r, column=2, value=coach_note)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, align=LEFT)
    ws.row_dimensions[r].height = 40
    r += 1

    # 本周目标说明
    ws.cell(row=r, column=1, value='本周目标').font = HEADER_FONT
    ws.cell(row=r, column=2, value=plan.goal or '（未设置）')
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, align=LEFT)
    ws.row_dimensions[r].height = 30
    r += 2

    # 安全提示
    ws.cell(row=r, column=1, value='安全提示')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    r += 1
    safety_tips = (
        '1. 训练前充分热身，训练后拉伸放松；\n'
        '2. 如感不适请立即停止训练；\n'
        '3. 注意训练环境安全，避免滑倒或碰撞；\n'
        '4. 保持充足睡眠与合理饮食，配合训练效果更佳。'
    )
    ws.cell(row=r, column=1, value=safety_tips)
    ws.merge_cells(start_row=r, start_column=1, end_row=r + 2, end_column=5)
    _style_range(ws, r, 1, r + 2, 5, align=LEFT)
    for rr in range(r, r + 3):
        ws.row_dimensions[rr].height = 26
    r += 3
    r += 1

    # 家长签字反馈区
    ws.cell(row=r, column=1, value='家长签字与反馈')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    _style_range(ws, r, 1, r, 5, fill=TITLE_FILL, font=TITLE_FONT, align=LEFT)
    r += 1
    ws.cell(row=r, column=1, value='家长签字').font = HEADER_FONT
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.cell(row=r, column=4, value='完成情况').font = HEADER_FONT
    ws.cell(row=r, column=5, value='□全部完成  □部分完成  □未完成')
    _style_range(ws, r, 1, r, 5, fill=SIGN_FILL, align=LEFT)
    ws.row_dimensions[r].height = 28
    r += 1
    ws.cell(row=r, column=1, value='学员状态').font = HEADER_FONT
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    ws.cell(row=r, column=2, value='□精力充沛  □正常  □疲劳  □其他：')
    _style_range(ws, r, 1, r, 5, fill=SIGN_FILL, align=LEFT)
    ws.row_dimensions[r].height = 28
    r += 1
    ws.cell(row=r, column=1, value='家长反馈').font = HEADER_FONT
    ws.merge_cells(start_row=r, start_column=2, end_row=r + 2, end_column=5)
    _style_range(ws, r, 1, r + 2, 5, fill=SIGN_FILL, align=LEFT)
    for rr in range(r, r + 3):
        ws.row_dimensions[rr].height = 28

    ws.freeze_panes = 'A2'


# =========================================================================
# Word 导出
# =========================================================================
def export_single_word(plan: SinglePlan, path: str):
    """导出单次训练任务单到 Word（A4纵向）。"""
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # 页面设置：A4 纵向
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)

    # 默认字体
    style = doc.styles['Normal']
    style.font.name = '微软雅黑'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    style.font.size = Pt(10.5)

    # 标题
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"{plan.student_name}  训练任务单")
    run.font.name = '微软雅黑'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(18)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    # 基本信息
    info_table = doc.add_table(rows=3, cols=4)
    info_table.style = 'Light Grid Accent 1'
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    info_data = [
        ('姓名', plan.student_name, '性别', plan.gender),
        ('年龄', plan.age, '教练', plan.coach),
        ('训练日期', plan.train_date, '训练地点', plan.location),
    ]
    for ri, row_data in enumerate(info_data):
        for ci, val in enumerate(row_data):
            cell = info_table.cell(ri, ci)
            cell.text = val
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.name = '微软雅黑'
                    r.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
                    r.font.size = Pt(10.5)
                    if ci % 2 == 0:  # 标签列
                        r.font.bold = True

    # 训练目标
    p = doc.add_paragraph()
    p.add_run('训练目标：').bold = True
    p.add_run(plan.goal or '（未设置）')

    doc.add_paragraph()

    # 训练内容
    h = doc.add_paragraph()
    h.add_run('训练内容').bold = True
    h.runs[0].font.size = Pt(13)
    h.runs[0].font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    # 各区块表格
    for block in plan.blocks:
        if not block.tasks:
            continue
        # 区块标题
        bp = doc.add_paragraph()
        run = bp.add_run(f"【{block.title}】")
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

        # 表格
        t = doc.add_table(rows=1 + len(block.tasks), cols=5)
        t.style = 'Light Grid Accent 1'
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ['序号', '动作名称', '组数', '次数/时长', '要点提示']
        for ci, hd in enumerate(headers):
            cell = t.cell(0, ci)
            cell.text = hd
            _style_word_header(cell)
        for ri, task in enumerate(block.tasks, 1):
            t.cell(ri, 0).text = str(ri)
            t.cell(ri, 1).text = task.name
            t.cell(ri, 2).text = str(task.sets)
            t.cell(ri, 3).text = task.reps
            t.cell(ri, 4).text = task.note
        # 设置列宽
        widths = [Cm(1), Cm(4), Cm(1.5), Cm(3), Cm(7)]
        for row in t.rows:
            for ci, w in enumerate(widths):
                row.cells[ci].width = w
        doc.add_paragraph()

    # 教练寄语
    p = doc.add_paragraph()
    p.add_run('教练寄语：').bold = True
    p.add_run(plan.coach_note or '加油，坚持就是胜利！')

    # 注意事项
    p = doc.add_paragraph()
    p.add_run('注意事项：').bold = True
    p.add_run(plan.remarks or '训练前充分热身，训练后拉伸放松；如感不适请停止。')

    # 下次课预告
    p = doc.add_paragraph()
    p.add_run('下次课预告：').bold = True
    p.add_run(plan.next_preview or '（待定）')

    doc.add_paragraph()

    # 家长签字反馈区
    h = doc.add_paragraph()
    h.add_run('家长签字与反馈').bold = True
    h.runs[0].font.size = Pt(13)
    h.runs[0].font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    sign_t = doc.add_table(rows=3, cols=4)
    sign_t.style = 'Light Grid Accent 1'
    sign_data = [
        ('家长签字', '', '完成情况', '□全部完成  □部分完成  □未完成'),
        ('学员状态', '□精力充沛  □正常  □疲劳  □其他：', '', ''),
        ('家长反馈', '', '', ''),
    ]
    for ri, row_data in enumerate(sign_data):
        for ci, val in enumerate(row_data):
            sign_t.cell(ri, ci).text = val
    # 合并第3行的反馈区
    sign_t.cell(2, 0).merge(sign_t.cell(2, 0))
    sign_t.cell(2, 1).merge(sign_t.cell(2, 3))
    # 设置行高
    for row in sign_t.rows:
        tr = row._tr
        trPr = tr.get_or_add_trPr()
        trHeight = OxmlElement('w:trHeight')
        trHeight.set(qn('w:val'), '600')
        trHeight.set(qn('w:hRule'), 'atLeast')
        trPr.append(trHeight)

    doc.save(path)
    return path


def export_weekly_word(plan: WeeklyPlan, path: str):
    """导出周计划表到 Word（A4纵向，含年龄段）。"""
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn

    age_group = plan.age_group or '未指定'
    coach_note = plan.coach_note or '请家长督促学员按时完成训练，注意训练安全。如有疑问请及时联系教练。'

    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)

    style = doc.styles['Normal']
    style.font.name = '微软雅黑'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    style.font.size = Pt(10.5)

    # 标题
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"{plan.student_name}  周训练计划表")
    run.font.name = '微软雅黑'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(18)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    # 基本信息（含年龄段）
    info_t = doc.add_table(rows=2, cols=6)
    info_t.style = 'Light Grid Accent 1'
    info_t.cell(0, 0).text = '教练'
    info_t.cell(0, 1).text = plan.coach
    info_t.cell(0, 2).text = '年龄段'
    info_t.cell(0, 3).text = age_group
    info_t.cell(0, 4).text = '本周起始'
    info_t.cell(0, 5).text = plan.week_start
    info_t.cell(1, 0).text = '本周目标'
    info_t.cell(1, 1).merge(info_t.cell(1, 5)).text = plan.goal

    doc.add_paragraph()

    # 周计划表（7列：含核心内容、时长）
    t = doc.add_table(rows=1 + len(plan.days), cols=7)
    t.style = 'Light Grid Accent 1'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ['星期', '日期', '训练主题', '核心内容', '强度', '时长', '备注']
    for ci, hd in enumerate(headers):
        _style_word_header(t.cell(0, ci), hd)
    for ri, day in enumerate(plan.days, 1):
        t.cell(ri, 0).text = day.weekday
        t.cell(ri, 1).text = day.date
        t.cell(ri, 2).text = day.theme
        t.cell(ri, 3).text = day.daily_goal or day.key_tasks
        t.cell(ri, 4).text = day.intensity
        t.cell(ri, 5).text = f"{day.duration_min}min" if day.duration_min else ''
        t.cell(ri, 6).text = day.note
    # 列宽
    widths = [Cm(1.5), Cm(2), Cm(2.5), Cm(4), Cm(1.2), Cm(1.3), Cm(3)]
    for row in t.rows:
        for ci, w in enumerate(widths):
            row.cells[ci].width = w

    doc.add_paragraph()

    # 每日训练明细（参照教案格式）
    if any(d.warmup or d.main_content or d.cooldown for d in plan.days):
        h = doc.add_paragraph()
        h.add_run('每日训练明细').bold = True
        h.runs[0].font.size = Pt(13)
        h.runs[0].font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

        for day in plan.days:
            if not (day.warmup or day.main_content or day.cooldown):
                continue
            bp = doc.add_paragraph()
            run = bp.add_run(f"【{day.weekday} {day.theme or '训练课'}】")
            run.bold = True
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

            if day.daily_goal:
                p = doc.add_paragraph()
                p.add_run('核心内容：').bold = True
                p.add_run(day.daily_goal)

            if day.warmup:
                p = doc.add_paragraph()
                p.add_run('准备部分：').bold = True
                p.add_run(day.warmup)
            if day.main_content:
                p = doc.add_paragraph()
                p.add_run('教学部分：').bold = True
                p.add_run(day.main_content)
            if day.cooldown:
                p = doc.add_paragraph()
                p.add_run('结束部分：').bold = True
                p.add_run(day.cooldown)
            if day.equipment:
                p = doc.add_paragraph()
                p.add_run('器材：').bold = True
                p.add_run(day.equipment)
            doc.add_paragraph()

    # 教练寄语
    p = doc.add_paragraph()
    p.add_run('教练寄语：').bold = True
    p.add_run(coach_note)

    doc.save(path)
    return path


# =========================================================================
# 辅助函数
# =========================================================================
def _style_range(ws, r1, c1, r2, c2, fill=None, font=None, align=CENTER):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDER
            cell.alignment = align
            if fill:
                cell.fill = fill
            if font:
                cell.font = font


def _style_word_header(cell, text=None):
    if text is not None:
        cell.text = text
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    # 设置背景色
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:fill'), '1F4E78')
    tcPr.append(shd)
    for p in cell.paragraphs:
        p.alignment = 1  # WD_ALIGN_PARAGRAPH.CENTER
        for r in p.runs:
            r.font.name = '微软雅黑'
            r.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
            r.font.size = Pt(10.5)
            r.font.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
