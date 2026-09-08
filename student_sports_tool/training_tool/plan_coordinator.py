# -*- coding: utf-8 -*-
"""协调层：训练计划编排业务逻辑。

职责：
- 区块配置持久化（blocks_config.json 读写）
- 智能推荐：根据学员年龄匹配教案，生成 Block 列表（单次训练单）或 DayPlan 列表（周计划）
- 桥接 lesson_plan_loader（教案加载）与 task_model（数据模型）

不包含 UI 代码，纯逻辑层，便于单元测试。
"""
import os
import sys
import json

# 任务模型
from task_model import Block, make_default_blocks, make_default_week


# ===== 区块配置持久化 =====

def _get_config_dir():
    """获取配置文件目录：打包后用 exe 同级目录，源码运行用源码目录。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：exe 所在目录（可写入）
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_get_config_dir(), 'blocks_config.json')


def load_blocks_config():
    """从配置文件加载自定义区块配置。

    返回:
        区块标题列表，如 ['热身', '主项训练', '放松拉伸', '专项训练']
        文件不存在或读取失败时返回 None（由调用方使用默认值）。
    """
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(t) for t in data if str(t).strip()]
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_blocks_config(titles):
    """保存区块标题列表到配置文件。"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(titles, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_initial_blocks():
    """加载初始区块列表：优先使用持久化配置，否则返回默认 3 区块。

    返回:
        (blocks, default_count) 元组
    """
    titles = load_blocks_config()
    if titles and len(titles) >= 3:
        return [Block(title=t) for t in titles], 3
    return make_default_blocks(), 3


# ===== 智能推荐：单次训练单 =====

def _resolve_student_age_group(name: str, archive_dir: str):
    """读取学员年龄并映射年龄段（推荐公共前置）。

    返回:
        {'ok': True, 'age': int, 'age_group': str}
        {'ok': False, 'reason': str, 'code': str}  code: no_name/no_dir/no_module/no_age/no_age_group/no_plans
    """
    if not name:
        return {'ok': False, 'reason': '请先选择或输入学员姓名', 'code': 'no_name'}
    if not archive_dir:
        return {'ok': False, 'reason': '档案目录未设置，无法读取学员年龄', 'code': 'no_dir'}
    try:
        import lesson_plan_loader as lpl
    except ImportError:
        return {'ok': False, 'reason': '教案加载模块缺失', 'code': 'no_module'}
    age = lpl.get_student_age(name, archive_dir)
    if age is None or age <= 0:
        return {
            'ok': False, 'code': 'no_age',
            'reason': f'未找到学员「{name}」的年龄信息，请先在「学员档案」中完善',
        }
    age_group = lpl.age_to_group(age)
    if not age_group:
        return {'ok': False, 'reason': '无法确定学员年龄段', 'code': 'no_age_group'}
    return {'ok': True, 'age': age, 'age_group': age_group}


def recommend_single_plan(name: str, archive_dir: str):
    """根据学员年龄匹配教案，生成单次训练单的 Block 列表。

    流程:
        1. 读取学员年龄 → 年龄段
        2. 加载该年龄段全部教案
        3. 若多节教案，由调用方（UI）让用户选择本次课
        4. 教案转换为 Block 列表（替换默认 3 区块）

    参数:
        name: 学员姓名
        archive_dir: 档案目录

    返回:
        dict:
            {'ok': True, 'age': int, 'age_group': str, 'lessons': list, 'lesson': Lesson}
            {'ok': False, 'reason': str, 'code': str}
            code 取值：
                'no_name' / 'no_dir' / 'no_module' / 'no_age'
                'no_age_group' / 'no_plans' / 'no_lessons' / 'convert_failed'
    """
    pre = _resolve_student_age_group(name, archive_dir)
    if not pre.get('ok'):
        return pre
    age, age_group = pre['age'], pre['age_group']
    try:
        import lesson_plan_loader as lpl
    except ImportError:
        return {'ok': False, 'reason': '教案加载模块缺失', 'code': 'no_module'}
    # 3. 加载教案
    try:
        plans = lpl.load_all_plans()
    except Exception as e:
        return {'ok': False, 'reason': f'加载教案失败：\n{e}', 'code': 'no_plans'}
    lessons = plans.get(age_group, [])
    if not lessons:
        return {'ok': False, 'reason': f'未找到「{age_group}」的教案模板', 'code': 'no_lessons'}

    return {
        'ok': True,
        'age': age,
        'age_group': age_group,
        'lessons': lessons,
        # 默认指向第一节，由 UI 决定是否让用户选择
        'lesson': lessons[0],
    }


def recommend_random_single(name: str, archive_dir: str):
    """智能推荐（随机搭配版）：按学员年龄段教案池随机合成一节训练课。

    与 recommend_single_plan 的区别：不取整节教案，而是从该年龄段
    全部教案的各时间段任务池（热身/教学类别/放松）随机抽取动作搭配，
    每次点击生成不同组合，方便连续排课不重样。

    返回:
        dict:
            {'ok': True, 'age': int, 'age_group': str, 'lesson': LessonSection}
            {'ok': False, 'reason': str, 'code': str}
    """
    pre = _resolve_student_age_group(name, archive_dir)
    if not pre.get('ok'):
        return pre
    age, age_group = pre['age'], pre['age_group']
    try:
        import lesson_plan_loader as lpl
    except ImportError:
        return {'ok': False, 'reason': '教案加载模块缺失', 'code': 'no_module'}
    try:
        lesson = lpl.build_random_lesson(age_group)
    except Exception as e:
        return {'ok': False, 'reason': f'随机搭配失败：\n{e}', 'code': 'no_plans'}
    if lesson is None:
        return {'ok': False, 'reason': f'未找到「{age_group}」的教案模板', 'code': 'no_lessons'}
    return {'ok': True, 'age': age, 'age_group': age_group, 'lesson': lesson}


def lesson_to_blocks(lesson):
    """将教案对象转换为 Block 列表（委托 lesson_plan_loader）。

    返回:
        list[Block] 或 None（转换失败时返回 None）
    """
    try:
        import lesson_plan_loader as lpl
        return lpl.lesson_to_blocks(lesson)
    except Exception:
        return None


# ===== 智能推荐：周计划 =====

def recommend_weekly_plan(name: str, archive_dir: str, days: int = 7):
    """根据学员年龄匹配教案，生成一周训练计划。

    流程:
        1. 读取学员年龄 → 年龄段
        2. 加载该年龄段全部教案，按顺序循环填充指定天数
        3. 周日默认设为休息日

    参数:
        name: 学员姓名
        archive_dir: 档案目录
        days: 天数（默认 7 天）

    返回:
        dict:
            {'ok': True, 'age': int, 'age_group': str, 'week_lessons': list[Lesson]}
            {'ok': False, 'reason': str, 'code': str}
    """
    if not name:
        return {'ok': False, 'reason': '请先选择或输入学员姓名', 'code': 'no_name'}
    if not archive_dir:
        return {'ok': False, 'reason': '档案目录未设置，无法读取学员年龄', 'code': 'no_dir'}
    try:
        import lesson_plan_loader as lpl
    except ImportError:
        return {'ok': False, 'reason': '教案加载模块缺失', 'code': 'no_module'}

    # 1. 读取学员年龄
    age = lpl.get_student_age(name, archive_dir)
    if age is None or age <= 0:
        return {
            'ok': False, 'code': 'no_age',
            'reason': f'未找到学员「{name}」的年龄信息，请先在「学员档案」中完善',
        }
    # 2. 年龄 → 年龄段
    age_group = lpl.age_to_group(age)
    if not age_group:
        return {'ok': False, 'reason': '无法确定学员年龄段', 'code': 'no_age_group'}
    # 3. 加载教案并推荐一周
    try:
        plans = lpl.load_all_plans()
    except Exception as e:
        return {'ok': False, 'reason': f'加载教案失败：\n{e}', 'code': 'no_plans'}
    try:
        week_lessons = lpl.recommend_weekly_plan(age_group, plans, days=days)
    except Exception as e:
        return {'ok': False, 'reason': f'推荐周计划失败：\n{e}', 'code': 'no_plans'}
    if not week_lessons:
        return {'ok': False, 'reason': f'未找到「{age_group}」的教案模板', 'code': 'no_lessons'}

    return {
        'ok': True,
        'age': age,
        'age_group': age_group,
        'week_lessons': week_lessons,
    }


def lesson_to_day_plan_dict(lesson):
    """将教案对象转换为 DayPlan 字段 dict（委托 lesson_plan_loader）。

    返回:
        dict 或 None（转换失败时返回 None）
    """
    try:
        import lesson_plan_loader as lpl
        return lpl.lesson_to_day_plan(lesson)
    except Exception:
        return None


def apply_weekly_lessons_to_days(days_list, week_lessons):
    """将 week_lessons 循环填充到 days_list（原地修改）。

    参数:
        days_list: list[DayPlan] 长度 7
        week_lessons: list[Lesson] 由 recommend_weekly_plan 返回

    返回:
        days_list（已填充）
    """
    try:
        import lesson_plan_loader as lpl
    except ImportError:
        return days_list
    for i, day in enumerate(days_list):
        if i >= len(week_lessons):
            break
        lesson = week_lessons[i]
        dp = lpl.lesson_to_day_plan(lesson)
        if not dp:
            continue
        day.theme = dp.get('theme', '')
        day.daily_goal = dp.get('daily_goal', '')
        day.duration_min = dp.get('duration_min', 60) or 60
        day.warmup = dp.get('warmup', '')
        day.main_content = dp.get('main_content', '')
        day.cooldown = dp.get('cooldown', '')
        day.equipment = dp.get('equipment', '')
        # 核心动作摘要：从教学部分提取类别名
        main_cats = []
        for sec in lesson.main_sections:
            if sec.category:
                main_cats.append(sec.category)
        day.key_tasks = '、'.join(main_cats) if main_cats else day.theme
        # 周日默认休息
        if i == 6:
            day.intensity = '休息'
            day.note = '主动恢复：散步、拉伸、泡沫轴放松'
        else:
            day.intensity = '中'
            day.note = ''
    return days_list


def make_default_week_days():
    """生成默认一周 DayPlan 列表（委托 task_model）。"""
    return make_default_week()
