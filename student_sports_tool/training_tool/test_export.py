# -*- coding: utf-8 -*-
"""测试训练任务工具：单次+周计划，Excel+Word"""
import sys, io, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# exporter 依赖上级目录的 file_lock 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from task_model import SinglePlan, WeeklyPlan, Block, Task, DayPlan
from exporter import (
    export_single_excel, export_single_word,
    export_weekly_excel, export_weekly_word,
)

out_dir = r'c:\Users\LeeNiuBi\Desktop\shangmentiyu\training_test'
os.makedirs(out_dir, exist_ok=True)

# 单次训练单
plan = SinglePlan(
    student_name='张三', gender='男', age='12岁', coach='李教练',
    train_date='2026-06-29', location='深圳体育中心',
    goal='增强上肢力量与核心稳定性',
    blocks=[
        Block('热身', [
            Task('慢跑', 1, '5分钟', '保持匀速'),
            Task('动态拉伸', 1, '5分钟', '全身激活'),
        ]),
        Block('主项训练', [
            Task('俯卧撑', 3, '15次', '身体成直线'),
            Task('深蹲', 4, '20次', '膝盖不过脚尖'),
            Task('平板支撑', 3, '60秒', '核心收紧'),
        ]),
        Block('放松拉伸', [
            Task('股四头肌拉伸', 2, '30秒/侧', '脚跟贴臀'),
            Task('肩部拉伸', 2, '20秒/侧', '对侧压肘'),
        ]),
    ],
    coach_note='今天训练状态不错，继续保持！',
    remarks='训练前充分热身，训练后及时补充水分。',
    next_preview='下周二 18:00 速度训练',
)
p1 = os.path.join(out_dir, '张三_单次训练单.xlsx')
p2 = os.path.join(out_dir, '张三_单次训练单.docx')
export_single_excel(plan, p1)
export_single_word(plan, p2)
print(f'单次Excel: {p1}  ({os.path.getsize(p1)} 字节)')
print(f'单次Word:  {p2}  ({os.path.getsize(p2)} 字节)')

# 周计划
week = WeeklyPlan(
    student_name='张三', coach='李教练', week_start='2026-06-29',
    goal='提升耐力与速度，备战体测',
    days=[
        DayPlan('周一', '06-29', '力量训练', '深蹲4×20、俯卧撑3×15、平板支撑3×60秒', '中', '注意动作规范'),
        DayPlan('周二', '06-30', '速度训练', '30米冲刺6×30米、10米×4折返跑4趟', '重', '充分热身'),
        DayPlan('周三', '07-01', '休息', '主动恢复：散步、轻度拉伸', '休息', '保证睡眠'),
        DayPlan('周四', '07-02', '耐力训练', '慢跑30分钟、跳绳3×1分钟', '中', '保持匀速'),
        DayPlan('周五', '07-03', '球类训练', '足球运球3×20米、射门4×15次', '中', '左右脚交替'),
        DayPlan('周六', '07-04', '综合训练', '仰卧起坐4×20、卷腹3×20、柔韧拉伸', '重', '注意拉伸'),
        DayPlan('周日', '07-05', '休息', '完全休息', '休息', '准备下周训练'),
    ],
)
p3 = os.path.join(out_dir, '张三_周计划.xlsx')
p4 = os.path.join(out_dir, '张三_周计划.docx')
export_weekly_excel(week, p3)
export_weekly_word(week, p4)
print(f'周计划Excel: {p3}  ({os.path.getsize(p3)} 字节)')
print(f'周计划Word:  {p4}  ({os.path.getsize(p4)} 字节)')

print('\n所有测试通过!')
print(f'输出目录: {out_dir}')
