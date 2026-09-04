# -*- coding: utf-8 -*-
"""数据层：成长报告评语模板与弱项建议映射表。

职责：
- 提供教练评语模板（按进步/退步/持平分类）
- 提供弱项训练建议映射表（项目名 → 建议文本）
- 提供报告标题、页脚等固定文本
"""

# 报告标题模板
REPORT_TITLE = '{name} 阶段性成长报告'
REPORT_SUBTITLE = '报告周期：{start} 至 {end}    生成日期：{today}'

# 评语模板（按进步类型分类）
COMMENT_TEMPLATES = {
    'progress_high': (
        '本阶段{name}进步显著，总分提升{diff}分！'
        '特别是在{improved_items}方面表现突出，'
        '建议继续保持当前训练强度，下阶段可适当增加难度挑战。'
    ),
    'progress_low': (
        '本阶段{name}稳步提升，总分进步{diff}分。'
        '{improved_items}有所改善，'
        '{weak_items}仍需加强，建议针对性训练。'
    ),
    'stable': (
        '本阶段{name}成绩保持稳定，总分与上次持平。'
        '建议在保持现有水平的基础上，重点突破{weak_items}，'
        '争取下阶段有明显提升。'
    ),
    'decline': (
        '本阶段{name}总分下降{diff}分，{declined_items}有所退步。'
        '建议分析原因（训练频率/强度/状态），'
        '调整训练计划，加强{weak_items}专项训练。'
    ),
    'no_data': (
        '暂无历史测评数据可供对比，本次为首次测评。'
        '建议根据本次成绩制定训练计划，定期复测跟踪进步。'
    ),
}

# 弱项训练建议映射表
WEAKNESS_ADVICE = {
    '肺活量': '建议加强有氧训练：慢跑、游泳、跳绳，每周3-4次，每次20分钟以上',
    '50米跑': '建议加强爆发力训练：高抬腿、起跑反应练习、30米冲刺，每周2-3次',
    '坐位体前屈': '建议每日拉伸训练：体前屈保持、坐姿分腿拉伸、腘绳肌拉伸',
    '1分钟跳绳': '建议每日跳绳练习：先练节奏再练速度，目标每周提升10次',
    '1分钟仰卧起坐': '建议加强核心训练：卷腹、平板支撑、俄罗斯转体，每日3组',
    '50米×8往返跑': '建议加强耐力与灵敏度：间歇跑、折返跑练习，每周2次',
    '1000米跑': '建议加强耐力训练：长距离慢跑+间歇跑结合，每周3次',
    '4分钟跳绳': '建议加强跳绳耐力：分段练习（2分钟+2分钟），逐步延长连续跳绳时间',
    '投掷实心球(2kg)': '建议加强上肢力量：俯卧撑、引体向上、爆发力投掷练习',
    '100米跑': '建议加强速度训练：起跑技术、加速跑、途中跑技术优化',
    '10米×4折返跑': '建议加强灵敏度训练：折返跑、T型跑、变向移动练习',
    '二级蛙跳': '建议加强下肢爆发力：深蹲跳、蛙跳、连续跳跃练习',
    '足球': '建议加强球感练习：运球绕桩、传球准度、射门技术',
    '篮球': '建议加强运球与投篮：行进间运球、定点投篮、上篮练习',
    '排球': '建议加强垫球技术：对墙垫球、自垫球、移动垫球',
    '乒乓球': '建议加强基本功：正反手攻球、搓球、步伐移动',
    '羽毛球': '建议加强挥拍与步伐：高远球、前后移动、杀球练习',
    '网球': '建议加强底线技术与发球：正反手抽球、发球稳定性',
}

# 页脚文本
REPORT_FOOTER = '本报告由上门体育教学管理工具自动生成，仅供训练参考。'


def get_weakness_advice(project_name):
    """获取指定项目的弱项训练建议。

    参数:
        project_name: 体测项目名

    返回: 建议文本，无匹配返回通用建议
    """
    return WEAKNESS_ADVICE.get(project_name, '建议针对性加强该项目训练，结合教练指导制定计划。')


def get_comment_template(progress_type):
    """获取评语模板。

    参数:
        progress_type: 'progress_high'/'progress_low'/'stable'/'decline'/'no_data'

    返回: 模板字符串
    """
    return COMMENT_TEMPLATES.get(progress_type, COMMENT_TEMPLATES['no_data'])


def determine_progress_type(first_total, last_total):
    """根据首次与最近总分判断进步类型。

    返回: 'progress_high'/'progress_low'/'stable'/'decline'/'no_data'
    """
    if first_total is None or last_total is None:
        return 'no_data'
    diff = last_total - first_total
    if diff >= 5:
        return 'progress_high'
    if diff > 0:
        return 'progress_low'
    if diff == 0:
        return 'stable'
    return 'decline'
