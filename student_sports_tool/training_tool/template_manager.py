# -*- coding: utf-8 -*-
"""管理层：训练计划模板 CRUD 与加载保存。

职责：
- 内置 8 个预设模板覆盖 4 大类（中考备考/减脂塑形/体态矫正/基础体能）
- 支持从 plan_templates/custom/ 加载用户自定义模板
- 保存自定义模板为 JSON
- 删除自定义模板（预设模板不可删除）
"""
import os
import json

# 预设模板数据（内置，不可删除）
DEFAULT_TEMPLATES = [
    {
        'id': 'zk_endurance',
        'name': '中考耐力强化',
        'category': '中考备考',
        'goal': '提升1000米跑与4分钟跳绳成绩',
        'target_students': '初三备考学员',
        'intensity': '中高',
        'duration_min': 60,
        'applicable_weakness': ['1000米跑', '4分钟跳绳', '50米×8往返跑'],
        'exercises': [
            {'name': '慢跑热身', 'sets': 1, 'reps': '800m', 'note': '心率120-140'},
            {'name': '间歇跑', 'sets': 6, 'reps': '200m', 'note': '目标配速40秒，间歇90秒'},
            {'name': '跳绳', 'sets': 4, 'reps': '1分钟', 'note': '目标140次以上'},
            {'name': '高抬腿', 'sets': 3, 'reps': '30秒', 'note': '膝盖抬至腰部'},
            {'name': '全身拉伸', 'sets': 1, 'reps': '5分钟', 'note': '重点拉伸下肢'},
        ],
    },
    {
        'id': 'zk_strength',
        'name': '中考力量训练',
        'category': '中考备考',
        'goal': '提升投掷实心球与仰卧起坐成绩',
        'target_students': '初三备考学员',
        'intensity': '中高',
        'duration_min': 55,
        'applicable_weakness': ['投掷实心球(2kg)', '1分钟仰卧起坐', '二级蛙跳'],
        'exercises': [
            {'name': '慢跑热身', 'sets': 1, 'reps': '5分钟', 'note': '逐步提升心率'},
            {'name': '俯卧撑', 'sets': 4, 'reps': '15次', 'note': '身体成直线，肘部夹紧'},
            {'name': '深蹲', 'sets': 4, 'reps': '20次', 'note': '膝盖不过脚尖'},
            {'name': '仰卧起坐', 'sets': 4, 'reps': '25次', 'note': '起身时呼气'},
            {'name': '平板支撑', 'sets': 3, 'reps': '60秒', 'note': '核心收紧'},
            {'name': '全身拉伸', 'sets': 1, 'reps': '5分钟', 'note': '放松恢复'},
        ],
    },
    {
        'id': 'zk_ball',
        'name': '中考球类专项',
        'category': '中考备考',
        'goal': '提升足球/篮球/排球专项技能',
        'target_students': '初三球类选考学员',
        'intensity': '中',
        'duration_min': 50,
        'applicable_weakness': ['足球', '篮球', '排球', '乒乓球', '羽毛球'],
        'exercises': [
            {'name': '慢跑热身', 'sets': 1, 'reps': '5分钟', 'note': '全身激活'},
            {'name': '足球运球', 'sets': 3, 'reps': '20米', 'note': '左右脚交替'},
            {'name': '篮球运球', 'sets': 3, 'reps': '20米', 'note': '左右手交替'},
            {'name': '排球垫球', 'sets': 3, 'reps': '30次', 'note': '双臂夹紧'},
            {'name': '颠球', 'sets': 3, 'reps': '30次', 'note': '脚背正面'},
            {'name': '拉伸放松', 'sets': 1, 'reps': '5分钟', 'note': '肩颈与下肢'},
        ],
    },
    {
        'id': 'fat_hiit',
        'name': 'HIIT燃脂训练',
        'category': '减脂塑形',
        'goal': '高强度间歇训练，高效燃脂',
        'target_students': '减重需求学员',
        'intensity': '高',
        'duration_min': 40,
        'applicable_weakness': ['1分钟跳绳', '50米跑'],
        'exercises': [
            {'name': '开合跳', 'sets': 4, 'reps': '30秒', 'note': '手脚协调'},
            {'name': '高抬腿', 'sets': 4, 'reps': '30秒', 'note': '快速高抬'},
            {'name': '登山跑', 'sets': 4, 'reps': '30秒', 'note': '核心收紧'},
            {'name': '深蹲跳', 'sets': 4, 'reps': '15次', 'note': '落地缓冲'},
            {'name': '波比跳', 'sets': 4, 'reps': '10次', 'note': '全幅度动作'},
            {'name': '平板支撑', 'sets': 3, 'reps': '45秒', 'note': '间歇15秒'},
        ],
    },
    {
        'id': 'core_strength',
        'name': '核心力量强化',
        'category': '减脂塑形',
        'goal': '强化核心肌群，改善体态',
        'target_students': '核心薄弱学员',
        'intensity': '中',
        'duration_min': 45,
        'applicable_weakness': ['1分钟仰卧起坐', '坐位体前屈'],
        'exercises': [
            {'name': '慢跑热身', 'sets': 1, 'reps': '5分钟', 'note': '轻度激活'},
            {'name': '卷腹', 'sets': 3, 'reps': '20次', 'note': '下背贴地'},
            {'name': '俄罗斯转体', 'sets': 3, 'reps': '20次', 'note': '双脚抬离'},
            {'name': '死虫式', 'sets': 3, 'reps': '12次', 'note': '对侧伸展'},
            {'name': '侧平板支撑', 'sets': 2, 'reps': '30秒', 'note': '左右各一次'},
            {'name': '臀桥', 'sets': 3, 'reps': '15次', 'note': '顶峰收紧'},
        ],
    },
    {
        'id': 'posture_shoulder',
        'name': '圆肩矫正训练',
        'category': '体态矫正',
        'goal': '改善圆肩驼背，强化背部肌群',
        'target_students': '圆肩/头前伸学员',
        'intensity': '低',
        'duration_min': 35,
        'applicable_weakness': [],
        'exercises': [
            {'name': '肩部拉伸', 'sets': 2, 'reps': '20秒', 'note': '手臂横胸前'},
            {'name': '俯卧两头起', 'sets': 3, 'reps': '12次', 'note': '背部发力'},
            {'name': '弹力带划船', 'sets': 3, 'reps': '15次', 'note': '肩胛后缩'},
            {'name': '面拉', 'sets': 3, 'reps': '15次', 'note': '外旋发力'},
            {'name': '靠墙天使', 'sets': 3, 'reps': '10次', 'note': '贴墙滑动'},
            {'name': '胸肌拉伸', 'sets': 2, 'reps': '30秒', 'note': '门框拉伸'},
        ],
    },
    {
        'id': 'posture_pelvis',
        'name': '骨盆前倾矫正',
        'category': '体态矫正',
        'goal': '改善骨盆前倾，强化臀部与腹部',
        'target_students': '骨盆前倾学员',
        'intensity': '低',
        'duration_min': 35,
        'applicable_weakness': [],
        'exercises': [
            {'name': '髂腰肌拉伸', 'sets': 2, 'reps': '20秒', 'note': '弓步下沉'},
            {'name': '臀桥', 'sets': 4, 'reps': '15次', 'note': '顶峰停顿1秒'},
            {'name': '死虫式', 'sets': 3, 'reps': '12次', 'note': '下背贴地'},
            {'name': '平板支撑', 'sets': 3, 'reps': '45秒', 'note': '骨盆中立位'},
            {'name': '股四头肌拉伸', 'sets': 2, 'reps': '20秒', 'note': '脚跟贴臀'},
            {'name': '腘绳肌拉伸', 'sets': 2, 'reps': '20秒', 'note': '直腿前屈'},
        ],
    },
    {
        'id': 'basic_agility',
        'name': '灵敏协调训练',
        'category': '基础体能',
        'goal': '提升灵敏度与协调性',
        'target_students': '4-6岁/7-9岁/10-12岁/13-15岁学员（按年龄调整强度与组数）',
        'age_group': '全年龄段',
        'intensity': '中',
        'duration_min': 40,
        'applicable_weakness': ['50米跑', '10米×4折返跑'],
        'age_advice': {
            '4-6岁': '强度调低，组数减半，注重趣味性，时长30min',
            '7-9岁': '标准强度，注重动作规范，时长40min',
            '10-12岁': '强度适中提升，增加组数，时长45min',
            '13-15岁': '中高强度，增加爆发力要求，时长50min',
        },
        'exercises': [
            {'name': '慢跑热身', 'sets': 1, 'reps': '5分钟', 'note': '逐步提速'},
            {'name': '10米×4折返跑', 'sets': 4, 'reps': '4趟', 'note': '转身降重心'},
            {'name': '侧向滑步', 'sets': 3, 'reps': '20次', 'note': '低重心'},
            {'name': '高抬腿跑', 'sets': 4, 'reps': '20米', 'note': '步频快'},
            {'name': '后蹬跑', 'sets': 4, 'reps': '30米', 'note': '后蹬充分'},
            {'name': '跳绳', 'sets': 3, 'reps': '1分钟', 'note': '双脚轻跳'},
        ],
    },
]


def _get_custom_dir():
    """获取自定义模板目录。"""
    if getattr(__import__('sys'), 'frozen', False):
        base = os.path.dirname(__import__('sys').executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'plan_templates', 'custom')


def load_all_templates():
    """加载所有模板（预设 + 自定义）。返回模板列表。"""
    templates = list(DEFAULT_TEMPLATES)
    custom_dir = _get_custom_dir()
    if os.path.isdir(custom_dir):
        for f in sorted(os.listdir(custom_dir)):
            if not f.endswith('.json'):
                continue
            try:
                with open(os.path.join(custom_dir, f), 'r', encoding='utf-8') as fp:
                    tpl = json.load(fp)
                    if isinstance(tpl, dict) and 'id' in tpl and 'name' in tpl:
                        tpl['_custom'] = True
                        templates.append(tpl)
            except (json.JSONDecodeError, OSError):
                pass
    return templates


def get_categories():
    """获取所有模板分类。"""
    templates = load_all_templates()
    return sorted(set(t['category'] for t in templates))


def save_custom_template(template):
    """保存自定义模板。"""
    custom_dir = _get_custom_dir()
    os.makedirs(custom_dir, exist_ok=True)
    fname = f"{template['id']}.json"
    with open(os.path.join(custom_dir, fname), 'w', encoding='utf-8') as f:
        json.dump(template, f, ensure_ascii=False, indent=2)


def delete_custom_template(template_id):
    """删除自定义模板。"""
    custom_dir = _get_custom_dir()
    fpath = os.path.join(custom_dir, f'{template_id}.json')
    if os.path.exists(fpath):
        os.remove(fpath)
        return True
    return False


def is_custom(template):
    """判断是否为自定义模板。"""
    return template.get('_custom', False)
