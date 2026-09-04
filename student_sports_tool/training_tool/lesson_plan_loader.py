# -*- coding: utf-8 -*-
"""数据层 + 处理器层：分龄教案加载与智能推荐。

职责：
- 读取项目根目录下的 4 个教案模板 xlsx 文件，解析为结构化数据
- 提供年龄 → 年龄段映射
- 从学员档案读取学员年龄
- 根据年龄段推荐单次课 / 周计划教案内容

数据源：
- 教案文件：教案模板4-6岁.xlsx / 7-9岁 / 10-12岁 / 13-15岁
- 学员年龄：学员档案.xlsx 工作表「学员信息」B列
"""
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from openpyxl import load_workbook


# === 数据结构 ===
@dataclass
class MainSection:
    """教案中某一部分（准备/教学/结束）的一个类别块。"""
    category: str = ''       # 类别名，如「绳梯类」
    purpose: str = ''        # 目的，如「协调能力+节奏感」
    exercises: str = ''      # 动作列表原始文本
    duration: str = ''       # 时间，如「15min」
    sets: str = ''           # 组次，如「各2-4组」
    equipment: str = ''      # 器材
    note: str = ''           # 注意事项


@dataclass
class LessonSection:
    """一节完整教案课。"""
    title: str = ''                  # 课程标题
    age_group: str = ''              # 年龄段
    core_content: str = ''           # 核心内容
    warmup: MainSection = field(default_factory=MainSection)     # 准备部分
    main_sections: List[MainSection] = field(default_factory=list)  # 教学部分（多类别）
    cooldown: MainSection = field(default_factory=MainSection)   # 结束部分
    total_duration: int = 60         # 总时长（分钟）


# === 教案文件查找 ===
def _find_plan_dir() -> str:
    """查找教案文件所在目录。

    查找顺序：
    1. training_tool/lesson_plans/（打包后用，exe 同级）
    2. 项目根目录（开发期，training_tool 上两级）
    """
    base = os.path.dirname(os.path.abspath(__file__))
    # 候选1：training_tool/lesson_plans/
    cand1 = os.path.join(base, 'lesson_plans')
    if os.path.isdir(cand1) and any(f.startswith('教案模板') for f in os.listdir(cand1)):
        return cand1
    # 候选2：项目根（training_tool -> student_sports_tool -> shangmentiyu）
    cand2 = os.path.dirname(os.path.dirname(base))
    if os.path.isdir(cand2) and any(f.startswith('教案模板') for f in os.listdir(cand2)):
        return cand2
    return ''


# === 教案解析 ===
def _split_category(cell_val: str) -> tuple:
    """拆分教学部分类别单元格，如「绳梯类 | 目的：协调能力+节奏感」。
    返回 (category, purpose)。
    """
    if not cell_val:
        return ('', '')
    s = str(cell_val).strip()
    # 按 | 或 ｜（全角）拆分
    parts = re.split(r'\s*[|｜]\s*', s, maxsplit=1)
    category = parts[0].strip()
    purpose = ''
    if len(parts) > 1:
        # 去掉「目的：」前缀
        purpose = re.sub(r'^目的[：:]\s*', '', parts[1]).strip()
    return (category, purpose)


def _parse_row(ws, row_idx: int) -> Optional[MainSection]:
    """解析一行为 MainSection。返回 None 表示空行。"""
    c = ws.cell(row=row_idx, column=3).value      # C: 教学内容（类别+目的）
    h = ws.cell(row=row_idx, column=8).value      # H: 教学方法（动作列表）
    if not c and not h:
        return None
    g = ws.cell(row=row_idx, column=7).value      # G: 时间
    n = ws.cell(row=row_idx, column=14).value     # N: 注意事项
    o = ws.cell(row=row_idx, column=15).value     # O: 组次
    p = ws.cell(row=row_idx, column=16).value     # P: 器材
    category, purpose = _split_category(c if c else '')
    return MainSection(
        category=category, purpose=purpose,
        exercises=str(h).strip() if h else '',
        duration=str(g).strip() if g else '',
        sets=str(o).strip() if o else '',
        equipment=str(p).strip() if p else '',
        note=str(n).strip() if n else '',
    )


def _parse_lesson_sheet(ws, age_group: str) -> LessonSection:
    """解析一个工作表为 LessonSection。"""
    lesson = LessonSection(
        title=str(ws.cell(row=1, column=1).value or '').strip(),
        age_group=age_group,
        core_content=str(ws.cell(row=3, column=3).value or '').strip(),
    )
    current_part = ''  # 'warmup' / 'main' / 'cooldown'
    for row_idx in range(5, ws.max_row + 1):
        a_val = ws.cell(row=row_idx, column=1).value
        a_str = str(a_val).strip() if a_val else ''
        if '准备部分' in a_str:
            current_part = 'warmup'
        elif '教学部分' in a_str:
            current_part = 'main'
        elif '结束部分' in a_str:
            current_part = 'cooldown'
        sec = _parse_row(ws, row_idx)
        if not sec:
            continue
        if current_part == 'warmup' and not lesson.warmup.exercises:
            lesson.warmup = sec
        elif current_part == 'main':
            lesson.main_sections.append(sec)
        elif current_part == 'cooldown' and not lesson.cooldown.exercises:
            lesson.cooldown = sec
    # 计算总时长
    total = 0
    for dur_str in [lesson.warmup.duration] + [s.duration for s in lesson.main_sections] + [lesson.cooldown.duration]:
        m = re.search(r'(\d+)', dur_str)
        if m:
            total += int(m.group(1))
    lesson.total_duration = total if total > 0 else 60
    return lesson


# === 对外接口 ===
def load_all_plans(plan_dir: str = '') -> Dict[str, List[LessonSection]]:
    """加载所有教案，按年龄段分组。

    返回: {'4-6岁': [LessonSection, ...], '7-9岁': [...], ...}
    """
    if not plan_dir:
        plan_dir = _find_plan_dir()
    if not plan_dir or not os.path.isdir(plan_dir):
        return {}
    result: Dict[str, List[LessonSection]] = {}
    for f in sorted(os.listdir(plan_dir)):
        if not f.startswith('教案模板') or not f.endswith('.xlsx'):
            continue
        # 从文件名提取年龄段，如「教案模板4-6岁.xlsx」->「4-6岁」
        m = re.search(r'教案模板(.+?)\.xlsx', f)
        if not m:
            continue
        age_group = m.group(1)
        fpath = os.path.join(plan_dir, f)
        try:
            wb = load_workbook(fpath, data_only=True, read_only=False)
        except Exception:
            continue
        lessons = []
        for sn in wb.sheetnames:
            ws = wb[sn]
            try:
                lessons.append(_parse_lesson_sheet(ws, age_group))
            except Exception:
                continue
        if lessons:
            result[age_group] = lessons
    return result


def age_to_group(age: Optional[int]) -> str:
    """年龄 → 年龄段映射。"""
    if age is None or age <= 0:
        return ''
    if age <= 6:
        return '4-6岁'
    if age <= 9:
        return '7-9岁'
    if age <= 12:
        return '10-12岁'
    if age <= 15:
        return '13-15岁'
    return '中考'  # 16岁以上按中考/体育考试处理


def get_student_age(name: str, archive_dir: str) -> Optional[int]:
    """从学员档案.xlsx 读取学员年龄。

    学员档案结构：工作表「学员信息」，A列姓名，B列年龄。
    """
    if not name or not archive_dir:
        return None
    fpath = os.path.join(archive_dir, '学员档案.xlsx')
    if not os.path.isfile(fpath):
        return None
    try:
        wb = load_workbook(fpath, data_only=True, read_only=True)
    except Exception:
        return None
    if '学员信息' not in wb.sheetnames:
        return None
    ws = wb['学员信息']
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        row_name = str(row[0]).strip() if row[0] else ''
        if row_name == name:
            try:
                return int(row[1]) if row[1] else None
            except (ValueError, TypeError):
                return None
    return None


def recommend_weekly_plan(age_group: str,
                          plans: Optional[Dict[str, List[LessonSection]]] = None,
                          days: int = 7) -> List[LessonSection]:
    """根据年龄段推荐一周教案（7天）。

    策略：按顺序取教案，不足则循环填充。
    """
    if plans is None:
        plans = load_all_plans()
    lessons = plans.get(age_group, [])
    if not lessons:
        return []
    result = []
    for i in range(days):
        result.append(lessons[i % len(lessons)])
    return result


def recommend_single_lesson(age_group: str,
                            plans: Optional[Dict[str, List[LessonSection]]] = None,
                            pick_index: int = 0) -> Optional[LessonSection]:
    """根据年龄段推荐单次训练教案。

    pick_index: 选择该年龄段的第几节课（0-based），默认第1节。
    """
    if plans is None:
        plans = load_all_plans()
    lessons = plans.get(age_group, [])
    if not lessons:
        return None
    return lessons[pick_index % len(lessons)]


def lesson_to_day_plan(lesson: LessonSection) -> dict:
    """将 LessonSection 转换为 DayPlan 兼容的字典格式（供 WeeklyTab 填充）。"""
    # 教学部分：每个类别一块，用 --- 分隔（与 exporter 的 main_content 拆分逻辑一致）
    main_blocks = []
    for sec in lesson.main_sections:
        header = sec.category
        if sec.purpose:
            header += f' 目的:{sec.purpose}'
        body = sec.exercises
        if sec.sets:
            body += f'\n{sec.sets}'
        main_blocks.append(f'{header}\n{body}')
    main_content = '\n---\n'.join(main_blocks)
    return {
        'theme': lesson.title,
        'daily_goal': lesson.core_content,
        'duration_min': lesson.total_duration,
        'warmup': lesson.warmup.exercises,
        'main_content': main_content,
        'cooldown': lesson.cooldown.exercises,
        'equipment': '、'.join(filter(None, [s.equipment for s in [lesson.warmup] + lesson.main_sections + [lesson.cooldown]])),
    }


# === 动作文本解析（供 SingleTab 将教案动作填充到区块表格） ===
def parse_exercises_to_list(text: str) -> List[str]:
    """将动作列表文本解析为动作名列表。

    支持以下格式：
    - 数字编号：`1.动作A 2.动作B 3.动作C`
    - 换行分隔：`动作A\\n动作B\\n动作C`
    - 顿号分隔：`动作A、动作B、动作C`
    - 空格分隔的带编号动作

    自动去除空白与编号前缀，过滤空字符串。
    """
    if not text:
        return []
    s = str(text).strip()
    if not s:
        return []
    # 先按换行拆，再按顿号、空格拆，最后去编号
    raw_items: List[str] = []
    # 优先按换行
    for line in s.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 若该行包含多个数字编号动作（如 "1.动作A 2.动作B"），按编号再拆
        # 匹配 "1." "2." "1、" "2、" 等
        sub_parts = re.split(r'\s*\d+[.、)]\s*', line)
        # re.split 在开头编号时会产出第一个空串，过滤
        sub_parts = [p.strip() for p in sub_parts if p.strip()]
        if sub_parts:
            raw_items.extend(sub_parts)
        else:
            # 整行无编号，按顿号再拆
            for part in re.split(r'[、,，]', line):
                part = part.strip()
                if part:
                    raw_items.append(part)
    # 去重并保持顺序
    seen = set()
    result = []
    for item in raw_items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _parse_sets_from_text(text: str) -> tuple:
    """从文本中提取组数与次数/时长。

    如 "各2-4组" -> (3, '2-4组')；"15min" -> (3, '15min')；空 -> (3, '15次')
    返回 (sets, reps)。
    """
    if not text:
        return (3, '15次')
    s = str(text).strip()
    # 尝试匹配"各X-Y组"或"X-Y组"
    m = re.search(r'(\d+)\s*[-~]\s*(\d+)\s*组', s)
    if m:
        avg = (int(m.group(1)) + int(m.group(2))) // 2
        return (avg or 3, f'{m.group(1)}-{m.group(2)}组')
    m = re.search(r'(\d+)\s*组', s)
    if m:
        return (int(m.group(1)), f'{m.group(1)}组')
    # 匹配 min
    m = re.search(r'(\d+)\s*min', s, re.IGNORECASE)
    if m:
        return (3, f'{m.group(1)}min')
    return (3, s)


def lesson_to_blocks(lesson: LessonSection):
    """将教案转换为 SingleTab 兼容的 Block 列表（热身/主项/放松）。

    返回 [Block(热身, [Task...]), Block(主项训练, [Task...]), Block(放松拉伸, [Task...])]
    使用前请确保 task_model 已可导入（由调用方保证 sys.path）。
    """
    from task_model import Block, Task  # 延迟导入，避免数据层强耦合 UI 模型

    # 热身区块
    warmup_tasks = []
    for name in parse_exercises_to_list(lesson.warmup.exercises):
        warmup_tasks.append(Task(name=name, sets=3, reps='15次', note=''))
    warmup_block = Block(title='热身', tasks=warmup_tasks)

    # 主项训练区块（合并所有教学类别为一个区块，与默认 3 区块结构对齐）
    main_tasks = []
    for sec in lesson.main_sections:
        sec_sets, sec_reps = _parse_sets_from_text(sec.sets) if sec.sets else (3, '15次')
        for name in parse_exercises_to_list(sec.exercises):
            note_parts = []
            if sec.purpose:
                note_parts.append(f'目的:{sec.purpose}')
            if sec.note:
                note_parts.append(sec.note)
            main_tasks.append(Task(
                name=name, sets=sec_sets, reps=sec_reps,
                note=' '.join(note_parts) if note_parts else ''
            ))
    main_block = Block(title='主项训练', tasks=main_tasks)

    # 放松拉伸区块
    cooldown_tasks = []
    for name in parse_exercises_to_list(lesson.cooldown.exercises):
        cooldown_tasks.append(Task(name=name, sets=3, reps='15次', note=''))
    cooldown_block = Block(title='放松拉伸', tasks=cooldown_tasks)

    return [warmup_block, main_block, cooldown_block]
