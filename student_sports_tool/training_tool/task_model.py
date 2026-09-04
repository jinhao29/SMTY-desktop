# -*- coding: utf-8 -*-
"""数据层：训练任务数据模型。

支持两种模式：
- 单次训练单（SinglePlan）：含完整动作明细，分区块（热身/主项/放松）
- 周计划表（WeeklyPlan）：7天概览，每天训练主题+核心动作摘要
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Task:
    """单个训练动作。"""
    name: str          # 动作名
    sets: int          # 组数
    reps: str          # 次数/距离/时长
    note: str = ''     # 要点提示


@dataclass
class Block:
    """训练区块（如热身、主项、放松）。"""
    title: str                  # 区块标题
    tasks: List[Task] = field(default_factory=list)


@dataclass
class SinglePlan:
    """单次训练任务单。"""
    # 基本信息
    student_name: str = ''
    gender: str = ''
    age: str = ''
    coach: str = ''
    train_date: str = ''
    location: str = ''
    # 训练目标
    goal: str = ''
    # 训练区块
    blocks: List[Block] = field(default_factory=list)
    # 寄语与备注
    coach_note: str = ''         # 教练寄语
    remarks: str = ''            # 注意事项
    next_preview: str = ''       # 下次课预告


@dataclass
class DayPlan:
    """周计划中某一天的计划。

    分龄教案字段（参照项目内教案模板）：
    - duration_min: 当日训练总时长（分钟），如 60
    - daily_goal: 当日核心内容/训练目标（如"下肢力量+核心力量+协调能力"）
    - warmup: 准备部分动作明细（如"1.娃娃蹲 2.提踵走 3.双腿轻跳"）
    - main_content: 教学部分动作明细，按类别分组（多行文本，每行一类）
    - cooldown: 结束部分动作明细（如"1.体前屈 2.蛙式 3.侧压腿"）
    - equipment: 当日所需器材（如"绳梯1个、垫子1个、标志桶2个"）
    """
    weekday: str                # 周一..周日
    date: str = ''              # 日期
    theme: str = ''             # 训练主题（如"力量训练"）
    key_tasks: str = ''         # 核心动作摘要（如"深蹲4×20、俯卧撑3×15"）
    intensity: str = ''         # 强度（轻/中/重/休息）
    note: str = ''              # 备注
    # 分龄教案字段
    duration_min: int = 60              # 当日训练时长（分钟）
    daily_goal: str = ''                # 当日核心内容/训练目标
    warmup: str = ''                    # 准备部分动作
    main_content: str = ''              # 教学部分（按类别，多行文本）
    cooldown: str = ''                  # 结束部分动作
    equipment: str = ''                 # 当日器材


@dataclass
class WeeklyPlan:
    """周计划表。

    分龄字段：
    - age_group: 年龄段（4-6岁/7-9岁/10-12岁/13-15岁/中考）
    - coach_note: 教练寄语（导出时显示在家长须知区）
    """
    student_name: str = ''
    coach: str = ''
    week_start: str = ''        # 周一日期
    goal: str = ''              # 本周目标
    days: List[DayPlan] = field(default_factory=list)
    # 分龄字段
    age_group: str = ''                 # 年龄段
    coach_note: str = ''                # 教练寄语


def make_default_blocks():
    """创建默认的3个区块（热身/主项/放松）。"""
    return [
        Block(title='热身'),
        Block(title='主项训练'),
        Block(title='放松拉伸'),
    ]


def make_default_week():
    """创建默认的7天周计划。"""
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return [DayPlan(weekday=w) for w in weekdays]
