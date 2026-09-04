# -*- coding: utf-8 -*-
"""纯算法层：身高预测 + 身高评级 + TDEE + 膳食模板。

自 Android 端 :core / :data 逐行移植，算法规则保持两端一致（勿单端改动）：
- 身高预测：HeightPredictionProcessor.kt（CMH 遗传公式 + 后天修正 ±3.5cm）
- 身高评级：GrowthStandard.kt（卫健委 P3/P50/P97 标准，3-18 岁）
- TDEE：TdeeProcessor.kt（Mifflin-St Jeor，发育期禁热量缺口）
- 膳食模板：DietTemplatePreset.kt（3+2 饮食法 3 套模板）

无状态纯函数，便于单元测试（见 test_growth_processor.py）。
"""
import math

# ==================== 身高预测（对齐 HeightPredictionProcessor） ====================

MAX_ADJUSTMENT = 3.5  # 后天修正值上限（cm）


def predict_height(gender: str, age: int, father_height: float, mother_height: float,
                   avg_sleep_hours: float, nutrition_score: int,
                   sports_mins_per_week: int):
    """执行身高预测计算，返回结果字典；父母身高缺失时返回 None。

    算法规则：
    1. 遗传靶身高（CMH 公式）：男孩 = (父高+母高+13)/2；女孩 = (父高+母高-13)/2
    2. 后天修正：睡眠≥8.5h +1cm / <7h -1cm；营养≥4 +1cm / ≤2 -1cm；
       每周运动≥180min +1.5cm；总修正限制在 ±3.5cm
    3. 骨骼闭合提示：男孩 >16 岁 / 女孩 >14 岁
    """
    father = float(father_height or 0)
    mother = float(mother_height or 0)
    if father <= 0 or mother <= 0:
        return None

    # 1. 遗传靶身高（CMH 公式：女孩 -13，其余 +13）
    target = (father + mother - 13) / 2.0 if gender == '女' else (father + mother + 13) / 2.0

    # 2. 后天环境修正值
    hours = float(avg_sleep_hours or 0)
    if hours <= 0:
        sleep_adj = 0.0
    elif hours >= 8.5:
        sleep_adj = 1.0
    elif hours < 7.0:
        sleep_adj = -1.0
    else:
        sleep_adj = 0.0

    score = int(nutrition_score or 0)
    if score <= 0:
        nutrition_adj = 0.0
    elif score >= 4:
        nutrition_adj = 1.0
    elif score <= 2:
        nutrition_adj = -1.0
    else:
        nutrition_adj = 0.0

    mins = int(sports_mins_per_week or 0)
    sports_adj = 1.5 if (mins > 0 and mins >= 180) else 0.0

    raw_adjustment = sleep_adj + nutrition_adj + sports_adj
    # 3. 限制总修正值在 ±3.5cm 以内
    adjustment = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, raw_adjustment))

    # 4. 预测身高与浮动区间
    adjusted = target + adjustment
    band = max(abs(adjustment), 2.0)
    lower, upper = adjusted - band, adjusted + band

    # 5. 建议文案
    if -0.01 < adjustment <= 0.0:
        advice = '后天环境维持良好，保持当前生活习惯即可'
    else:
        parts = []
        if sleep_adj < 0:
            parts.append('建议保证每日 8.5 小时以上睡眠')
        if nutrition_adj < 0:
            parts.append('建议改善饮食营养均衡度')
        if sports_adj <= 0:
            parts.append('建议每周运动 3 次以上，每次 1 小时')
        advice = '；'.join(parts) if parts else '睡眠、营养、运动均达标，后天环境优秀'

    # 6. 骨骼闭合警告
    bone_warning = None
    age = int(age or 0)
    if age > 0:
        limit = 14 if gender == '女' else 16
        if age > limit:
            bone_warning = '骨骼可能已闭合，请以医院骨龄检测为准'

    r1 = lambda v: round(v, 1)  # noqa: E731 保留一位小数
    return {
        'target_height': r1(target),
        'adjusted_height': r1(adjusted),
        'lower_bound': r1(lower),
        'upper_bound': r1(upper),
        'adjustment': r1(adjustment),
        'advice_text': advice,
        'bone_age_warning': bone_warning,
        'rating': rate_height(gender, age, r1(adjusted)),
    }


# ==================== 身高评级（对齐 GrowthStandardTable） ====================

# 中国卫健委儿童身高标准：P3 / P50 / P97（cm），3-18 岁
GROWTH_STANDARD_MALE = [
    (3, 89.3, 96.8, 104.3), (4, 95.8, 103.7, 111.6), (5, 102.1, 110.5, 118.9),
    (6, 108.6, 117.7, 126.8), (7, 114.0, 124.0, 134.0), (8, 119.3, 130.0, 140.7),
    (9, 124.3, 135.4, 146.5), (10, 128.7, 140.2, 151.7), (11, 133.4, 145.3, 157.2),
    (12, 139.1, 151.5, 163.9), (13, 145.9, 159.5, 173.1), (14, 152.0, 165.6, 179.2),
    (15, 156.5, 169.7, 182.9), (16, 159.1, 171.6, 184.1), (17, 160.1, 172.3, 184.5),
    (18, 160.5, 172.7, 184.9),
]
GROWTH_STANDARD_FEMALE = [
    (3, 88.2, 95.6, 103.0), (4, 94.3, 102.3, 110.3), (5, 100.5, 109.1, 117.7),
    (6, 107.1, 115.8, 124.5), (7, 112.7, 122.0, 131.3), (8, 118.2, 128.2, 138.2),
    (9, 123.3, 134.1, 144.9), (10, 128.7, 140.3, 151.9), (11, 135.0, 147.2, 159.4),
    (12, 142.2, 154.5, 166.8), (13, 147.6, 159.3, 171.0), (14, 150.6, 161.8, 173.0),
    (15, 152.3, 162.8, 173.3), (16, 153.0, 163.0, 173.0), (17, 153.2, 163.2, 173.2),
    (18, 153.4, 163.4, 173.4),
]

RATING_LABELS = {'short': '偏矮', 'average': '正常', 'tall': '优秀'}
RATING_COLORS = {'short': '#F87171', 'average': '#34D399', 'tall': '#60A5FA'}


def lookup_growth_standard(gender: str, age: int):
    """按性别与年龄查询标准 (age, p3, p50, p97)；年龄超 3-18 范围返回 None。"""
    table = GROWTH_STANDARD_FEMALE if gender == '女' else GROWTH_STANDARD_MALE
    for row in table:
        if row[0] == age:
            return row
    return None


def rate_height(gender: str, age: int, current_height: float):
    """当前身高评级。返回 {rating, label, color, p3, p50, p97} 或 None（年龄超范围）。"""
    std = lookup_growth_standard(gender, age)
    if not std or current_height <= 0:
        return None
    _, p3, p50, p97 = std
    if current_height < p3:
        rating = 'short'
    elif current_height > p97:
        rating = 'tall'
    else:
        rating = 'average'
    return {'rating': rating, 'label': RATING_LABELS[rating], 'color': RATING_COLORS[rating],
            'p3': p3, 'p50': p50, 'p97': p97}


# ==================== TDEE（对齐 TdeeProcessor / ActivityLevel） ====================

# (key, 活动系数, 中文标签)
ACTIVITY_LEVELS = [
    ('sedentary', 1.2, '久坐无运动'),
    ('light', 1.375, '轻度运动（每周1-3次）'),
    ('moderate', 1.55, '中度运动（每周3-5次）'),
    ('active', 1.725, '高度运动（每周6-7次）'),
    ('very_active', 1.9, '极高强度（每日训练）'),
]
DEFAULT_ACTIVITY = 'moderate'


def calc_tdee(gender: str, weight_kg: float, height_cm: float, age: int,
              activity_level: str = DEFAULT_ACTIVITY):
    """计算 BMR/TDEE（Mifflin-St Jeor）。任一参数无效返回 None。

    减脂建议规则：年龄 >16 岁输出 400 大卡缺口；≤16 岁强制警告不允许缺口。
    """
    w = float(weight_kg or 0)
    h = float(height_cm or 0)
    age = int(age or 0)
    if w <= 0 or h <= 0 or age <= 0:
        return None
    factor = next((f for k, f, _ in ACTIVITY_LEVELS if k == activity_level), 1.55)

    # Mifflin-St Jeor：男 +5 / 女 -161
    if gender == '女':
        bmr = 10.0 * w + 6.25 * h - 5.0 * age - 161.0
    else:
        bmr = 10.0 * w + 6.25 * h - 5.0 * age + 5.0
    tdee = bmr * factor

    is_adult = age > 16
    # 对齐 Kotlin roundToInt（半值远离零）；Python round 为银行家舍入，勿直接用
    return {
        'bmr': int(bmr + 0.5),
        'tdee': int(tdee + 0.5),
        'deficit_advice': 400 if is_adult else None,
        'warning_text': None if is_adult else '处于生长发育期，不建议制造热量缺口，建议通过均衡饮食与运动管理体重。',
        'is_adult': is_adult,
    }


# ==================== 膳食模板（对齐 DietTemplatePreset，3+2 饮食法） ====================

def _meal(*items):
    """组装一餐：[(分类, 内容), ...] → [{'category','content'}, ...]"""
    return [{'category': c, 'content': t} for c, t in items]


DIET_TEMPLATES = [
    {
        'id': 'tpl_regular',
        'name': '常规健康发育型',
        'description': '适合大多数学员，营养均衡，满足日常发育所需',
        'meals': {
            'breakfast': _meal(('主食', '全麦面包 2 片 / 玉米 1 根'),
                               ('优质蛋白', '水煮蛋 1 个 + 牛奶 250ml'),
                               ('蔬果', '苹果半个 / 小番茄 5 颗')),
            'morning_snack': _meal(('能量补充', '香蕉 1 根 / 酸奶 1 杯 / 坚果一小把（约 15g）')),
            'lunch': _meal(('主食', '糙米饭 1 碗（约 150g）'),
                           ('高蛋白肉类', '去皮鸡胸肉 100g / 清蒸鱼 100g / 牛肉 80g'),
                           ('蔬菜', '西兰花 + 胡萝卜 + 时令蔬菜（约 200g）')),
            'afternoon_snack': _meal(('运动前 / 后补充', '全麦饼干 3 片 / 苹果 1 个 / 蛋白饮品 1 杯')),
            'dinner': _meal(('粗粮碳水', '红薯 1 个 / 杂粮粥 1 碗'),
                            ('易消化蛋白', '豆腐 100g / 清蒸鱼 80g'),
                            ('绿叶蔬菜', '菠菜 / 油菜（约 150g）')),
        },
        'pre_workout_tip': '训练前 1-2 小时：香蕉 1 根 + 全麦面包 1 片，提供持续能量',
        'post_workout_tip': '训练后 30 分钟：牛奶 250ml + 鸡蛋 1 个，黄金蛋白补充窗口',
    },
    {
        'id': 'tpl_training',
        'name': '高强度体能训练型',
        'description': '适合训练量大的学员，适当增加碳水与蛋白质摄入',
        'meals': {
            'breakfast': _meal(('主食', '全麦面包 3 片 / 燕麦粥 1 大碗'),
                               ('优质蛋白', '水煮蛋 2 个 + 牛奶 300ml'),
                               ('蔬果', '香蕉 1 根 + 蓝莓一小把')),
            'morning_snack': _meal(('能量补充', '全麦三明治半个 + 坚果 20g + 酸奶 1 杯')),
            'lunch': _meal(('主食', '糙米饭 1.5 碗（约 220g）'),
                           ('高蛋白肉类', '瘦牛肉 150g / 鸡胸肉 150g / 三文鱼 120g'),
                           ('蔬菜', '西兰花 + 甜椒 + 蘑菇（约 250g）')),
            'afternoon_snack': _meal(('运动前 / 后补充', '蛋白饮 1 杯 + 香蕉 1 根 + 全麦面包 1 片')),
            'dinner': _meal(('粗粮碳水', '红薯 1.5 个 / 杂粮饭 1 碗'),
                            ('易消化蛋白', '清蒸鱼 120g + 豆腐 100g'),
                            ('绿叶蔬菜', '菠菜 / 油菜（约 200g）')),
        },
        'pre_workout_tip': '训练前 1.5 小时：燕麦粥 + 鸡蛋 1 个，碳水充足保训练强度',
        'post_workout_tip': '训练后 30 分钟：蛋白饮 1 杯 + 香蕉 1 根，快速补糖补蛋白促恢复',
    },
    {
        'id': 'tpl_fat_loss',
        'name': '减脂 / 控制体重型',
        'description': '适合体重超标学员，控制碳水总量，提高蛋白与蔬菜比例',
        'meals': {
            'breakfast': _meal(('主食', '全麦面包 1 片 / 玉米半根'),
                               ('优质蛋白', '水煮蛋 1 个 + 无糖豆浆 250ml'),
                               ('蔬果', '黄瓜 1 根 / 小番茄 6 颗')),
            'morning_snack': _meal(('能量补充', '无糖酸奶 1 小杯 + 坚果 10g')),
            'lunch': _meal(('主食', '糙米饭半碗（约 80g）'),
                           ('高蛋白肉类', '去皮鸡胸肉 120g / 清蒸鱼 100g'),
                           ('蔬菜', '西兰花 + 黄瓜 + 时令蔬菜（约 300g，多蔬菜少主食）')),
            'afternoon_snack': _meal(('运动前 / 后补充', '蛋白饮 1 杯 + 苹果半个')),
            'dinner': _meal(('粗粮碳水', '红薯半个 / 杂粮粥半碗'),
                            ('易消化蛋白', '清蒸鱼 100g + 豆腐 80g'),
                            ('绿叶蔬菜', '菠菜 / 油菜（约 200g）')),
        },
        'pre_workout_tip': '训练前 1 小时：苹果半个 + 鸡蛋 1 个，轻负担能量补充',
        'post_workout_tip': '训练后 30 分钟：蛋白饮 1 杯 + 鸡蛋 1 个，控糖保蛋白',
    },
]

# 餐次展示顺序与中文标签
MEAL_ORDER = [('breakfast', '早餐'), ('morning_snack', '上午加餐'),
              ('lunch', '午餐'), ('afternoon_snack', '下午加餐'),
              ('dinner', '晚餐')]


def get_template(template_id: str):
    """按 id 取膳食模板；找不到返回 None。"""
    for t in DIET_TEMPLATES:
        if t['id'] == template_id:
            return t
    return None
