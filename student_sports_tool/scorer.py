# -*- coding: utf-8 -*-
"""处理器层：体测评分计算。

职责：
- 解析用户输入的成绩（支持多种时间格式）
- 根据满分/及格标准线性插值计算得分（0-100）
- 给出等级（优秀/良好/及格/不及格）
- 纯逻辑，无状态，可独立测试
"""
from standards import Std, MORE, LESS


def parse_value(raw: str, unit: str) -> float:
    """将用户输入解析为数值。

    支持格式：
    - 秒/次/米/cm/ml: 直接数字，如 '13.8'、'592'
    - 分秒: '4'05"'/'4:05'/'245' → 秒数

    ⚠️ 负数成绩显式拒绝（与 Android Scorer.kt v50 语义对齐）：
    负值在 direction=LESS 的项目里会走 `val <= full` 分支直接拿 100 分，
    是评分系统的静默错误，必须在解析层拦截。
    """
    if raw is None:
        raise ValueError('成绩为空')
    s = str(raw).strip()
    if not s:
        raise ValueError('成绩为空')
    # 分秒格式：含 ' : 或 " 的，解析为秒
    if unit == '分秒':
        val = _parse_time(s)
    else:
        try:
            val = float(s)
        except (TypeError, ValueError):
            raise ValueError('格式错误')
    if val < 0:
        raise ValueError('成绩不能为负数')
    return val


def _parse_time(s: str) -> float:
    """解析分秒为秒数。支持 4'05" / 4:05 / 4分05秒 / 纯秒数。"""
    s = s.replace('分', ':').replace('秒', '')
    s = s.replace('′', "'").replace('″', '"').replace('’', "'").replace('”', '"')
    # 4'05" 格式
    if "'" in s and '"' in s:
        parts = s.replace('"', '').split("'")
        return int(parts[0]) * 60 + float(parts[1])
    # 4'05 格式（无闭合引号）
    if "'" in s:
        parts = s.split("'")
        return int(parts[0]) * 60 + float(parts[1])
    # 4:05 格式
    if ':' in s:
        parts = s.split(':')
        return int(parts[0]) * 60 + float(parts[1])
    # 纯秒数
    return float(s)


def format_value(val: float, unit: str) -> str:
    """将数值格式化为显示文本。分秒→4'05"，其他→原值。"""
    if val is None:
        return ''
    if unit == '分秒':
        m = int(val // 60)
        sec = val - m * 60
        if sec == int(sec):
            return f"{m}'{int(sec):02d}\""
        return f"{m}'{sec:04.1f}\""
    if val == int(val):
        return str(int(val))
    return f"{val:g}"


def calc_score(std: Std, gender: str, raw_value: str):
    """计算单项得分。

    参数:
        std: 项目标准
        gender: '男' 或 '女'
        raw_value: 用户输入的成绩文本

    返回:
        dict: {score: float, grade: str, value: float, ok: bool, msg: str}
    """
    try:
        val = parse_value(raw_value, std.unit)
    except ValueError as e:
        return {'score': None, 'grade': '', 'value': None, 'ok': False, 'msg': str(e)}

    full = std.boys_full if gender == '男' else std.girls_full
    pass_ = std.boys_pass if gender == '男' else std.girls_pass

    if std.direction == MORE:
        score = _score_more(val, full, pass_)
    else:
        score = _score_less(val, full, pass_)

    score = max(0.0, min(100.0, score))
    return {
        'score': score,
        'grade': _grade_label(score),
        'value': val,
        'ok': True,
        'msg': '',
    }


def _score_more(val, full, pass_):
    """值越大越好：达到满分给100，达到及格给60，中间线性插值。"""
    if val >= full:
        return 100.0
    if val <= pass_:
        # 低于及格，按比例给分（最低0）
        if pass_ == 0:
            return 0.0 if val <= 0 else max(0.0, val / full * 60)
        ratio = max(0.0, val / pass_)
        return ratio * 60.0
    # 介于及格与满分之间：60 + (val-pass)/(full-pass) * 40
    return 60.0 + (val - pass_) / (full - pass_) * 40.0


def _score_less(val, full, pass_):
    """值越小越好：达到满分给100，达到及格给60，中间线性插值。"""
    if val <= full:
        return 100.0
    if val >= pass_:
        # 低于及格（比及格还慢/差）
        # 按 (val-pass) 越大越差，线性递减到0
        # 以 pass 为60分基准，每超过 递减
        # 简化：用 pass→60, 额外差值按 (full-pass) 区间比例扣
        extra = val - pass_
        span = pass_ - full
        if span <= 0:
            return 30.0
        return max(0.0, 60.0 - extra / span * 60.0)
    # 介于满分与及格之间：60 + (pass-val)/(pass-full) * 40
    return 60.0 + (pass_ - val) / (pass_ - full) * 40.0


def _grade_label(score: float) -> str:
    """得分转等级（国家体测标准）。"""
    if score >= 90:
        return '优秀'
    if score >= 75:
        return '良好'
    if score >= 60:
        return '及格'
    return '不及格'


def calc_total(scores):
    """计算总分（所有有效得分的平均分）。"""
    valid = [s['score'] for s in scores if s.get('ok') and s['score'] is not None]
    if not valid:
        return 0.0
    return sum(valid) / len(valid)
