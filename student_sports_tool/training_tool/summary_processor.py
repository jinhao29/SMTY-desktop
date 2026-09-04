# -*- coding: utf-8 -*-
"""处理器层：阶段总结数据聚合。

职责：
- 在指定时间段内，聚合学员的课时数、训练量、成绩进步、教练评语
- 纯逻辑单元，无 UI 依赖，便于单元测试
- 数据来源：lesson_manager（课时）+ feedback_storage（反馈）+ 学员档案（成绩）

聚合维度：
- 课时统计：总课时 / 已上 / 剩余 / 阶段内消课数
- 训练量：阶段内反馈条数、平均完成度、训练内容摘要
- 成绩进步：阶段前后各项目成绩对比、总分变化
- 教练评语：阶段内所有评语聚合
"""
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

# 复用已有数据层（这些模块由 app.py 加入 sys.path）
import lesson_manager
from feedback_storage import get_feedback_history
from excel_builder import read_student_meta


def _parse_date(date_str: str) -> Optional[datetime]:
    """解析日期字符串，支持 YYYY-MM-DD 与 YYYY/MM/DD。失败返回 None。"""
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip().replace('/', '-')
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _in_range(date_str: str, start: Optional[datetime], end: Optional[datetime]) -> bool:
    """判断日期是否在 [start, end] 区间内。start/end 为 None 表示不限。"""
    dt = _parse_date(date_str)
    if dt is None:
        return False
    if start and dt < start:
        return False
    if end and dt > end:
        return False
    return True


def list_students_with_files(dir_path: str) -> List[Dict]:
    """列出档案目录中所有学员（用于阶段总结的学员选择下拉）。

    返回: [{name, file_path, has_profile}]，按姓名排序。
    """
    result = []
    if not os.path.isdir(dir_path):
        return result
    for f in sorted(os.listdir(dir_path)):
        if not f.lower().endswith('.xlsx'):
            continue
        if f.startswith('~$') or f.startswith('课时记录') or f.startswith('课堂反馈') or f.startswith('学员档案'):
            continue
        name = f[:-5]
        result.append({
            'name': name,
            'file_path': os.path.join(dir_path, f),
            'has_profile': True,
        })
    return result


def aggregate_lessons(dir_path: str, student_name: str,
                      start: Optional[datetime] = None,
                      end: Optional[datetime] = None) -> Dict:
    """聚合阶段内课时数据。

    返回:
        {
            'total': 总课时,
            'attended_total': 累计已上,
            'remaining': 剩余,
            'stage_count': 阶段内消课数,
            'stage_dates': [阶段内上课日期字符串],
            'last_date': 最近上课日期,
        }
    """
    summary = lesson_manager.get_summary(dir_path)
    target = next((s for s in summary if s['name'] == student_name), None)
    total = target['total'] if target else 0
    attended_total = target['attended'] if target else 0
    remaining = target['remaining'] if target else 0
    last_date = target['last_date'] if target else ''

    # 阶段内明细
    details = lesson_manager.get_detail(dir_path, student_name)
    stage_dates = []
    stage_count = 0
    for d in details:
        if _in_range(d.get('date', ''), start, end):
            stage_count += int(d.get('count', 0) or 0)
            stage_dates.append(str(d.get('date', '')))

    return {
        'total': total,
        'attended_total': attended_total,
        'remaining': remaining,
        'stage_count': stage_count,
        'stage_dates': stage_dates,
        'last_date': last_date,
    }


def aggregate_feedback(dir_path: str, student_name: str,
                       start: Optional[datetime] = None,
                       end: Optional[datetime] = None,
                       limit: int = 200) -> Dict:
    """聚合阶段内课后反馈数据。

    返回:
        {
            'count': 阶段内反馈条数,
            'avg_completion': 平均完成度(%, 整数),
            'contents': [训练内容...],
            'states': [学员状态...],
            'comments': [教练评语...],
            'next_suggestions': [下次课建议...],
            'recent': [最近反馈 raw 列表],
        }
    """
    # 取较多条数以覆盖阶段范围
    history = get_feedback_history(dir_path, student_name, limit=limit)
    filtered = [h for h in history if _in_range(h.get('date', ''), start, end)]

    completions = [int(h.get('completion', 0) or 0) for h in filtered]
    avg_completion = int(sum(completions) / len(completions)) if completions else 0

    return {
        'count': len(filtered),
        'avg_completion': avg_completion,
        'contents': [h.get('content', '') for h in filtered if h.get('content')],
        'states': [h.get('state', '') for h in filtered if h.get('state')],
        'comments': [h.get('comment', '') for h in filtered if h.get('comment')],
        'next_suggestions': [h.get('next', '') for h in filtered if h.get('next')],
        'recent': filtered[:10],
    }


def aggregate_score_progress(file_path: str,
                             start: Optional[datetime] = None,
                             end: Optional[datetime] = None) -> Dict:
    """聚合阶段内成绩进步数据（基于学员档案文件的 _meta 元数据）。

    返回:
        {
            'has_score': 是否含成绩型档案,
            'items': [项目名...],
            'first': {项目: {value, score, grade, date}}  阶段内首次,
            'last': {项目: {value, score, grade, date}}   阶段内末次,
            'progress': {项目: {value_diff, score_diff}}  进步对比,
            'total_first': 首次总分,
            'total_last': 末次总分,
            'total_diff': 总分变化,
        }
    """
    meta = read_student_meta(file_path)
    if not meta or not meta.get('records'):
        return {'has_score': False, 'items': [], 'first': {}, 'last': {},
                'progress': {}, 'total_first': None, 'total_last': None, 'total_diff': None}

    records = meta['records']
    # 筛选阶段内记录（带成绩的）
    stage_recs = []
    for r in records:
        if not r.get('scores'):
            continue
        if _in_range(r.get('date', ''), start, end):
            stage_recs.append(r)

    if not stage_recs:
        return {'has_score': True, 'items': [], 'first': {}, 'last': {},
                'progress': {}, 'total_first': None, 'total_last': None, 'total_diff': None}

    first = stage_recs[0]
    last = stage_recs[-1]
    items = sorted(set(list(first.get('scores', {}).keys()) + list(last.get('scores', {}).keys())))

    progress = {}
    for item in items:
        f = first['scores'].get(item, {})
        l = last['scores'].get(item, {})
        f_val = _to_float(f.get('value'))
        l_val = _to_float(l.get('value'))
        f_score = _to_float(f.get('score'))
        l_score = _to_float(l.get('score'))
        progress[item] = {
            'value_diff': (l_val - f_val) if (f_val is not None and l_val is not None) else None,
            'score_diff': (l_score - f_score) if (f_score is not None and l_score is not None) else None,
            'first_value': f.get('value', ''),
            'last_value': l.get('value', ''),
            'first_score': f.get('score'),
            'last_score': l.get('score'),
        }

    total_first = first.get('total')
    total_last = last.get('total')
    total_diff = None
    if total_first is not None and total_last is not None:
        total_diff = _to_float(total_last) - _to_float(total_first)

    return {
        'has_score': True,
        'items': items,
        'first': first,
        'last': last,
        'progress': progress,
        'total_first': total_first,
        'total_last': total_last,
        'total_diff': total_diff,
    }


def _to_float(val) -> Optional[float]:
    """安全转换为 float，失败返回 None。"""
    if val is None or val == '':
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def build_stage_summary(dir_path: str, student_name: str,
                        start_date: str = '', end_date: str = '') -> Dict:
    """构建完整的阶段总结数据。

    参数:
        dir_path: 档案目录
        student_name: 学员姓名
        start_date: 起始日期 YYYY-MM-DD（空字符串表示不限）
        end_date: 结束日期 YYYY-MM-DD（空字符串表示不限）

    返回: 聚合后的 dict，含 lessons/feedback/score_progress/profile 元数据
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    # end 含当日（结束日 23:59:59）
    if end:
        end = end.replace(hour=23, minute=59, second=59)

    # 找学员档案文件
    # M5-S1: 调用统一清洗器
    try:
        from filename_sanitizer import sanitize_filename
        safe_name = sanitize_filename(student_name)
    except ImportError:
        safe_name = student_name.replace('/', '_').replace('\\', '_').strip()
    file_path = os.path.join(dir_path, f"{safe_name}.xlsx")
    if not os.path.exists(file_path):
        file_path = ''

    lessons = aggregate_lessons(dir_path, student_name, start, end)
    feedback = aggregate_feedback(dir_path, student_name, start, end)
    score = aggregate_score_progress(file_path, start, end) if file_path else {
        'has_score': False, 'items': [], 'first': {}, 'last': {},
        'progress': {}, 'total_first': None, 'total_last': None, 'total_diff': None,
    }

    return {
        'student_name': student_name,
        'start_date': start_date,
        'end_date': end_date,
        'file_path': file_path,
        'lessons': lessons,
        'feedback': feedback,
        'score': score,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


def suggest_summary(summary: Dict) -> str:
    """根据阶段总结数据生成简短文字总结（用于导出 Word 的概述段）。"""
    if not summary:
        return ''
    name = summary.get('student_name', '学员')
    lessons = summary.get('lessons', {})
    feedback = summary.get('feedback', {})
    score = summary.get('score', {})
    parts = []

    stage_count = lessons.get('stage_count', 0)
    if stage_count > 0:
        parts.append(f"本阶段共完成 {stage_count} 课时训练")

    fb_count = feedback.get('count', 0)
    if fb_count > 0:
        avg = feedback.get('avg_completion', 0)
        parts.append(f"累计 {fb_count} 次课后反馈，平均完成度 {avg}%")

    if score.get('has_score') and score.get('total_diff') is not None:
        diff = score['total_diff']
        arrow = '提升' if diff > 0 else ('下降' if diff < 0 else '持平')
        parts.append(f"测评总分{arrow} {abs(diff):.1f} 分")

    if not parts:
        return f"{name} 在本阶段暂无足够数据，建议持续记录课时与反馈以便生成完整总结。"

    return f"{name}：" + "；".join(parts) + "。"


def default_stage_range(months: int = 3) -> Tuple[str, str]:
    """生成默认的阶段范围：最近 N 个月（含当日）。返回 (start_str, end_str)。"""
    end = datetime.now()
    start = end - timedelta(days=30 * months)
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')
