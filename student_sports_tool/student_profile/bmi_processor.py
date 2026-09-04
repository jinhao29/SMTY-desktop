# -*- coding: utf-8 -*-
"""处理器层：BMI 计算与体型分类（纯逻辑，无副作用，便于单元测试）。

判定标准采用中国成人 BMI 标准：
- 偏瘦：BMI < 18.5
- 正常：18.5 ≤ BMI < 24
- 超重：24 ≤ BMI < 28
- 肥胖：BMI ≥ 28

儿童青少年 BMI 标准因年龄/性别而异，本模块提供简化版「儿童青少年 BMI 百分位」参考，
但默认仍使用成人标准并标注提示。
"""


def calc_bmi(height_cm: float, weight_kg: float) -> float:
    """计算 BMI 值。

    参数:
        height_cm: 身高（厘米），需 > 0
        weight_kg: 体重（千克），需 > 0

    返回:
        BMI 值，保留一位小数。输入非法时返回 0.0。
    """
    if height_cm <= 0 or weight_kg <= 0:
        return 0.0
    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m * height_m)
    return round(bmi, 1)


def classify_body_type(bmi: float, age: int = 0) -> str:
    """根据 BMI 判定体型分类。

    参数:
        bmi: BMI 值
        age: 年龄（0 或缺失时使用成人标准；<18 时加注「请参考儿童青少年标准」）

    返回:
        体型分类字符串：偏瘦 / 正常 / 超重 / 肥胖 / 未知
    """
    if bmi <= 0:
        return '未知'
    if bmi < 18.5:
        base = '偏瘦'
    elif bmi < 24:
        base = '正常'
    elif bmi < 28:
        base = '超重'
    else:
        base = '肥胖'
    # 儿童青少年加注提示
    if age and age < 18 and base != '正常':
        base += '（请参考儿童青少年标准）'
    return base


def body_type_color(body_type: str) -> str:
    """体型分类对应的颜色（用于 UI 高亮，返回十六进制颜色字符串）。"""
    if '偏瘦' in body_type:
        return '#60A5FA'  # 蓝
    if '正常' in body_type:
        return '#34D399'  # 绿
    if '超重' in body_type:
        return '#FBBF24'  # 黄
    if '肥胖' in body_type:
        return '#F87171'  # 红
    return '#9CA3AF'  # 灰（未知）


def get_bmi_advice(bmi: float, age: int = 0) -> str:
    """根据 BMI 给出简短的运动训练建议。"""
    if bmi <= 0:
        return '请完善身高体重信息'
    if bmi < 18.5:
        return '偏瘦：建议加强力量训练，增加优质蛋白摄入，避免过量有氧。'
    if bmi < 24:
        return '正常：保持均衡训练，有氧与力量结合，维持当前体成分。'
    if bmi < 28:
        return '超重：建议增加有氧训练比例（如慢跑、跳绳），控制饮食总热量。'
    return '肥胖：优先低冲击有氧（游泳、椭圆机），配合饮食管理，循序渐进。'
