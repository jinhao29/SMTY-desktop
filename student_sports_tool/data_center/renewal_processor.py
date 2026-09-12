# -*- coding: utf-8 -*-
"""处理器层：续费预警与未上课天数计算（纯逻辑，无状态）。

职责：
- 根据剩余课时与阈值计算学员紧急等级
- 计算学员距最近上课的天数
- 过滤已联系学员（7天免打扰）
"""
from datetime import datetime, date


# 紧急等级常量
CRITICAL = 'critical'   # 紧急：剩余<=2 或已超支
WARNING = 'warning'     # 提醒：剩余<=阈值
NORMAL = 'normal'       # 正常
UNKNOWN = 'unknown'     # 未设置总课时


# ---------------------------------------------------------------------------
# 续费预警阈值（⚠️ 单一真源）
#
# 与 Android 端 data/model/RenewalThresholds.kt 的常量一一对应，由
# test_renewal_thresholds_parity.py 跨端锚定。改任一端必须同步另一端。
# ---------------------------------------------------------------------------

# 剩余课时 <= 此值视为「即将用完 / 需要续费提醒」
# ⚠️ 建议值 3：与 Android 现网行为一致（PC 原默认 5，提示偏早）。
#    教练仍可在「续费预警 → 高级配置」中按机构习惯覆盖此默认值。
DEFAULT_RENEWAL_THRESHOLD = 3

# 剩余课时 <= 此值视为「紧急」
CRITICAL_REMAINING = 2

# 连续未上课天数 >= 此值视为「长期未上课」（PC 独有维度，Android 暂未实现同类预警）
DEFAULT_INACTIVE_DAYS = 14


def calc_urgency(remaining, total, threshold=DEFAULT_RENEWAL_THRESHOLD):
    """计算学员续费紧急等级。

    参数:
        remaining: 剩余课时
        total: 总课时
        threshold: 提醒阈值（默认取 DEFAULT_RENEWAL_THRESHOLD）

    返回: 'critical' | 'warning' | 'normal' | 'unknown'
    """
    if total <= 0:
        return UNKNOWN
    if remaining <= CRITICAL_REMAINING or remaining < 0:
        return CRITICAL
    if remaining <= threshold:
        return WARNING
    return NORMAL


def calc_inactive_days(last_date_str):
    """计算距最近上课的天数。

    参数:
        last_date_str: 最近上课日期字符串 'YYYY-MM-DD'

    返回: 天数 int，无记录返回 -1
    """
    if not last_date_str:
        return -1
    try:
        last = datetime.strptime(last_date_str, '%Y-%m-%d').date()
        return (date.today() - last).days
    except (ValueError, TypeError):
        return -1


def is_inactive(inactive_days, threshold=DEFAULT_INACTIVE_DAYS):
    """判断是否长期未上课。"""
    if inactive_days < 0:
        return False
    return inactive_days >= threshold


def filter_active_alerts(students, followup_status,
                         threshold=DEFAULT_RENEWAL_THRESHOLD,
                         inactive_threshold=DEFAULT_INACTIVE_DAYS):
    """过滤出需要展示的预警学员。

    参数:
        students: 学员列表（来自 lesson_manager.get_summary）
        followup_status: 跟进状态 dict（来自 followup_manager）
        threshold: 续费阈值
        inactive_threshold: 未上课天数阈值

    返回: (续费预警列表, 长期未上课列表)
    """
    today = date.today()
    renewal_alerts = []
    inactive_alerts = []

    for stu in students:
        name = stu['name']
        urgency = calc_urgency(stu['remaining'], stu['total'], threshold)

        # 检查跟进免打扰（7天内已联系的不显示在续费预警中）
        followup = followup_status.get(name, {})
        expire_str = followup.get('expire', '')
        is_muted = False
        if expire_str:
            try:
                expire_date = datetime.strptime(expire_str, '%Y-%m-%d').date()
                is_muted = today <= expire_date
            except (ValueError, TypeError):
                pass

        if urgency in (CRITICAL, WARNING) and not is_muted:
            renewal_alerts.append({
                **stu,
                'urgency': urgency,
                'followup_note': followup.get('note', ''),
            })

        # 长期未上课检测
        days = calc_inactive_days(stu.get('last_date', ''))
        if is_inactive(days, inactive_threshold) and not is_muted:
            inactive_alerts.append({
                **stu,
                'inactive_days': days,
                'urgency': urgency,
                'followup_note': followup.get('note', ''),
            })

    # 排序：紧急 → 提醒
    urgency_order = {CRITICAL: 0, WARNING: 1, NORMAL: 2, UNKNOWN: 3}
    renewal_alerts.sort(key=lambda s: urgency_order.get(s['urgency'], 4))
    inactive_alerts.sort(key=lambda s: -s['inactive_days'])

    return renewal_alerts, inactive_alerts
