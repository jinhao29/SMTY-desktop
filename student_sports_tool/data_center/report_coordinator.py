# -*- coding: utf-8 -*-
"""协调层：编排成长报告数据读取、图表生成、PDF 导出流程。

职责：
- 读取学员档案元数据
- 计算首次与最近测评的对比数据
- 委托 chart_renderer 生成图表
- 委托 report_exporter 生成 PDF
"""
import os
import tempfile
from datetime import datetime

from excel_builder import read_student_meta
from chart_renderer import create_trend_chart, create_radar_chart
from report_exporter import generate_report_pdf
from report_templates import determine_progress_type, get_comment_template
from PySide6.QtGui import QPainter
from PySide6.QtCore import QSize, QRect


def load_student_records(dir_path, student_name):
    """加载学员测评记录。

    返回: (基本信息 dict, 测评记录列表) 或 (None, None)
    """
    file_path = os.path.join(dir_path, f'{student_name}.xlsx')
    meta = read_student_meta(file_path)
    if not meta:
        return None, None
    return meta.get('info', {}), meta.get('records', [])


def get_scored_records(records):
    """筛选有总分的测评记录。"""
    return [r for r in records if r.get('total') is not None]


def extract_project_scores(record):
    """从单次测评记录提取项目得分 dict {项目名: score}。"""
    scores = record.get('scores', {})
    return {proj: data.get('score') for proj, data in scores.items()
            if data.get('score') is not None}


def generate_default_comment(records, first_idx, last_idx):
    """根据进步类型自动生成评语。"""
    scored = get_scored_records(records)
    if not scored:
        return get_comment_template('no_data')

    first_total = scored[first_idx].get('total') if first_idx < len(scored) else None
    last_total = scored[last_idx].get('total') if last_idx < len(scored) else None
    progress_type = determine_progress_type(first_total, last_total)
    template = get_comment_template(progress_type)

    # 提取进步/退步项目
    first_scores = extract_project_scores(scored[first_idx]) if first_idx < len(scored) else {}
    last_scores = extract_project_scores(scored[last_idx]) if last_idx < len(scored) else {}

    improved = []
    declined = []
    weak = []
    for proj in set(first_scores.keys()) | set(last_scores.keys()):
        f = first_scores.get(proj)
        l = last_scores.get(proj)
        if f is not None and l is not None:
            if l > f:
                improved.append(proj)
            elif l < f:
                declined.append(proj)
        if l is not None and l < 60:
            weak.append(proj)

    diff = abs(round(last_total - first_total, 1)) if first_total and last_total else 0
    name = scored[0].get('name', '学员') if scored else '学员'

    return template.format(
        name=name,
        diff=diff,
        improved_items='、'.join(improved[:3]) or '各项',
        declined_items='、'.join(declined[:3]) or '各项',
        weak_items='、'.join(weak[:3]) or '薄弱项',
    )


def export_chart_image(chart, width=800, height=400):
    """将 QChart 导出为临时 PNG 图片。返回图片路径。"""
    tmp_dir = tempfile.gettempdir()
    path = os.path.join(tmp_dir, f'chart_{datetime.now().strftime("%H%M%S")}.png')
    pixmap = chart.createDefaultAxes()
    # 用 grab 方法截图
    from PySide6.QtWidgets import QGraphicsView
    view = QGraphicsView(chart.scene())
    view.resize(width, height)
    pixmap = view.grab(QRect(0, 0, width, height))
    pixmap.save(path, 'PNG')
    return path


def generate_report(dir_path, student_name, first_idx, last_idx, comment, output_path):
    """生成完整成长报告 PDF（同步版，保留兼容）。

    参数:
        dir_path: 档案目录
        student_name: 学员名
        first_idx: 首次测评索引（在 scored_records 中）
        last_idx: 最近测评索引
        comment: 教练评语（为空则自动生成）
        output_path: PDF 输出路径

    返回: output_path
    """
    assets = prepare_report_assets(dir_path, student_name, first_idx, last_idx, comment)
    try:
        finalize_report_pdf(assets, output_path)
    finally:
        cleanup_report_assets(assets)
    return output_path


def prepare_report_assets(dir_path, student_name, first_idx, last_idx, comment):
    """阶段一（主线程）：加载记录、生成评语、导出趋势图 PNG。

    QChart 的 grab() 必须在 GUI 主线程执行，因此本函数不可后台化。

    返回: dict 含 info/scored/first_idx/last_idx/comment/chart_path
    """
    info, records = load_student_records(dir_path, student_name)
    if not records:
        raise ValueError(f'学员 {student_name} 无测评记录')

    scored = get_scored_records(records)
    if not scored:
        raise ValueError(f'学员 {student_name} 无有效测评成绩')

    first_idx = min(first_idx, len(scored) - 1)
    last_idx = min(last_idx, len(scored) - 1)

    if not comment:
        comment = generate_default_comment(scored, first_idx, last_idx)

    chart_path = None
    try:
        chart = create_trend_chart(scored)
        chart_path = export_chart_image(chart)
    except Exception:
        chart_path = None

    return {
        'info': info,
        'scored': scored,
        'first_idx': first_idx,
        'last_idx': last_idx,
        'comment': comment,
        'chart_path': chart_path,
        'student_name': student_name,
    }


def finalize_report_pdf(assets, output_path, progress_cb=None):
    """阶段二（可后台线程）：用阶段一产物生成 PDF。

    本函数仅做文件 I/O 与 reportlab 渲染，不涉及 Qt GUI，可安全放入 Worker。
    """
    if progress_cb:
        progress_cb('正在生成 PDF 报告...')
    generate_report_pdf(
        assets['info'], assets['scored'],
        assets['first_idx'], assets['last_idx'],
        assets['chart_path'], assets['comment'], output_path
    )
    if progress_cb:
        progress_cb(f'✓ PDF 已生成：{output_path}')
    return output_path


def cleanup_report_assets(assets):
    """清理阶段一生成的临时图片。"""
    chart_path = assets.get('chart_path') if assets else None
    if chart_path and os.path.exists(chart_path):
        try:
            os.remove(chart_path)
        except OSError:
            pass
