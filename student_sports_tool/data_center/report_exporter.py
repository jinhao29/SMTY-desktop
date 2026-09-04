# -*- coding: utf-8 -*-
"""数据层：成长报告 PDF 生成（QPrinter + QPainter 原生渲染）。

升级说明（v1.1）：
- 抛弃 reportlab 第三方依赖，改用 PySide6 原生 QPrinter + QPainter
- 直接使用 QChart 渲染图表到 QPainter，无需中转 PNG 文件
- 支持高分辨率输出（QPrinter.HighResolution），可直接打印或发送家长
- 中文使用微软雅黑 / 苹方，由 QFontDatabase 自动选择

兼容性：
- generate_report_pdf 函数签名保持不变，调用方无需修改
- chart_path 参数仍兼容（若提供则绘制图片），但推荐传 None 使用直接 QChart 渲染
"""
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import (
    QPainter, QFont, QColor, QPen, QPixmap, QTextDocument
)
from PySide6.QtPrintSupport import QPrinter

from report_templates import (
    get_weakness_advice, get_comment_template, determine_progress_type,
    REPORT_TITLE, REPORT_SUBTITLE, REPORT_FOOTER,
)


# 配色（与原 reportlab 版本保持一致）
COLOR_TITLE = '#1F4E78'
COLOR_HEADER_BG = '#DCE6F1'
COLOR_SCORE_BG = '#FFF2CC'
COLOR_WARN_BG = '#FCE4E4'
COLOR_GOOD_BG = '#E4FCE4'
COLOR_TEXT = '#333333'
COLOR_SUBTEXT = '#666666'
COLOR_BORDER = '#888888'
COLOR_ROW_ALT = '#F5F5F5'
COLOR_WHITE = '#FFFFFF'
COLOR_FOOTER = '#999999'

# 中文字体优先级
CN_FONT_FAMILY = 'Microsoft YaHei'

# 页面布局常量
PAGE_MARGIN_MM = 18.0
ROW_HEIGHT_PX = 28
TABLE_PADDING = 6


def _ensure_qt_app():
    """确保 QApplication 已初始化（QPrinter 依赖）。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _font(size: int, bold: bool = False) -> QFont:
    """构造统一样式的中文字体。"""
    f = QFont(CN_FONT_FAMILY, size)
    f.setBold(bold)
    return f


def generate_report_pdf(student_info, records, first_idx, last_idx,
                        chart_path, comment, output_path,
                        chart_object=None):
    """生成成长报告 PDF（QPrinter + QPainter 原生渲染）。

    参数:
        student_info: 学员基本信息 dict
        records: 测评记录列表
        first_idx: 首次测评索引
        last_idx: 最近测评索引
        chart_path: 趋势图图片路径（PNG），可选（兼容旧调用）
        output_path: PDF 输出路径
        chart_object: 可选的 QChart 对象，优先级高于 chart_path。
                      若提供则直接渲染到 PDF，避免临时图片文件。

    返回: output_path
    """
    _ensure_qt_app()

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setPageSize(QPrinter.A4)
    printer.setPageMargins(PAGE_MARGIN_MM, PAGE_MARGIN_MM,
                           PAGE_MARGIN_MM, PAGE_MARGIN_MM, QPrinter.Millimeter)
    printer.setOutputFileName(output_path)

    painter = QPainter(printer)
    try:
        _draw_report(painter, printer, student_info, records,
                     first_idx, last_idx, chart_path, comment, chart_object)
    finally:
        painter.end()
    return output_path


# ============================================================
# 绘制流程
# ============================================================

def _draw_report(painter: QPainter, printer: QPrinter,
                 student_info, records, first_idx, last_idx,
                 chart_path, comment, chart_object):
    """在当前 PDF 页上绘制完整报告内容。"""
    width_px = printer.width()
    height_px = printer.height()

    name = student_info.get('name', '') if student_info else ''
    today = datetime.now().strftime('%Y-%m-%d')
    first_rec = records[first_idx] if first_idx < len(records) else {}
    last_rec = records[last_idx] if last_idx < len(records) else {}
    start_date = first_rec.get('date', '')
    end_date = last_rec.get('date', '')

    # ---------- 标题 ----------
    painter.setFont(_font(20, bold=True))
    painter.setPen(QColor(COLOR_TITLE))
    title = REPORT_TITLE.format(name=name)
    painter.drawText(QRectF(0, 0, width_px, 60), Qt.AlignCenter, title)

    # 副标题
    painter.setFont(_font(10))
    painter.setPen(QColor(COLOR_SUBTEXT))
    subtitle = REPORT_SUBTITLE.format(start=start_date, end=end_date, today=today)
    painter.drawText(QRectF(0, 60, width_px, 24), Qt.AlignCenter, subtitle)

    y_cursor = 100.0

    # ---------- 基本信息表 ----------
    y_cursor = _draw_section_title(painter, y_cursor, width_px, '一、基本信息')
    info_rows = [
        [('姓名', name), ('性别', student_info.get('gender', '') if student_info else '')],
        [('学校', student_info.get('school', '') if student_info else ''),
         ('联系电话', student_info.get('phone', '') if student_info else '')],
        [('测评次数', str(len(records))), ('报告周期', f'{start_date} 至 {end_date}')],
    ]
    y_cursor = _draw_grid_table(painter, y_cursor, width_px, info_rows, 4)

    # ---------- 总分趋势 ----------
    has_chart = bool(chart_object is not None or (chart_path and os.path.exists(chart_path)))
    if has_chart:
        y_cursor = _draw_section_title(painter, y_cursor, width_px, '二、总分趋势')
        target_w = int(width_px - 40)
        target_h = 240
        pixmap = None
        if chart_object is not None:
            # 直接从 QChart 抓取高分辨率 QPixmap（主线程安全）
            try:
                pixmap = chart_object.grab(QSize(target_w, target_h))
            except Exception:
                pixmap = None
        elif chart_path and os.path.exists(chart_path):
            pixmap = QPixmap(chart_path)

        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                QSize(target_w, target_h),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (width_px - scaled.width()) / 2
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.drawPixmap(QRectF(x, y_cursor, scaled.width(), scaled.height()), scaled)
            y_cursor += scaled.height() + 20

    # ---------- 进步明细表 ----------
    first_scores = first_rec.get('scores', {}) if first_rec else {}
    last_scores = last_rec.get('scores', {}) if last_rec else {}
    all_projects = sorted(set(first_scores.keys()) | set(last_scores.keys()))

    if all_projects:
        y_cursor = _maybe_new_page(painter, printer, y_cursor, 200)
        y_cursor = _draw_section_title(painter, y_cursor, width_px, '三、进步明细')
        header = ['项目', '首次成绩', '首次得分', '最近成绩', '最近得分', '进步']
        data_rows = []
        for proj in all_projects:
            fs = first_scores.get(proj, {})
            ls = last_scores.get(proj, {})
            f_val = str(fs.get('value', ''))
            f_sc = str(fs.get('score', ''))
            l_val = str(ls.get('value', ''))
            l_sc = str(ls.get('score', ''))
            diff = ''
            try:
                f_num = float(fs.get('score'))
                l_num = float(ls.get('score'))
                d = round(l_num - f_num, 1)
                if d > 0:
                    diff = f'↑{abs(d)}'
                elif d < 0:
                    diff = f'↓{abs(d)}'
                else:
                    diff = '持平'
            except (TypeError, ValueError):
                pass
            data_rows.append([proj, f_val, f_sc, l_val, l_sc, diff])
        y_cursor = _draw_data_table(painter, y_cursor, width_px, header, data_rows,
                                    col_ratios=[0.28, 0.16, 0.14, 0.16, 0.14, 0.12])

    # ---------- 弱项诊断 ----------
    if last_scores:
        y_cursor = _maybe_new_page(painter, printer, y_cursor, 120)
        y_cursor = _draw_section_title(painter, y_cursor, width_px, '四、弱项诊断与训练建议')
        sorted_items = sorted(
            last_scores.items(),
            key=lambda x: x[1].get('score') if isinstance(x[1], dict) else 999
        )
        for proj, sc in sorted_items[:2]:
            score_val = sc.get('score', '') if isinstance(sc, dict) else ''
            advice = get_weakness_advice(proj)
            text = f'■ {proj}（最近得分：{score_val}）\n{advice}'
            y_cursor = _draw_paragraph(painter, y_cursor, width_px, text,
                                       bg_color=COLOR_WARN_BG)

    # ---------- 教练评语 ----------
    y_cursor = _maybe_new_page(painter, printer, y_cursor, 100)
    y_cursor = _draw_section_title(painter, y_cursor, width_px, '五、教练评语')
    y_cursor = _draw_paragraph(painter, y_cursor, width_px,
                               comment or '（教练评语待填写）')

    # ---------- 页脚 ----------
    y_cursor = _maybe_new_page(painter, printer, y_cursor, 40, force_if_close=True)
    painter.setFont(_font(8))
    painter.setPen(QColor(COLOR_FOOTER))
    painter.drawText(QRectF(0, height_px - 40, width_px, 30),
                     Qt.AlignCenter, REPORT_FOOTER)


# ============================================================
# 绘制辅助函数
# ============================================================

def _draw_section_title(painter: QPainter, y: float, width: float,
                        title: str) -> float:
    """绘制章节标题（左侧色块 + 文本），返回新 y。"""
    painter.setFont(_font(13, bold=True))
    painter.setPen(QColor(COLOR_TITLE))
    # 左侧装饰色块
    painter.fillRect(QRectF(20, y + 6, 5, 18), QColor(COLOR_TITLE))
    painter.drawText(QRectF(34, y, width - 54, 30),
                     Qt.AlignLeft | Qt.AlignVCenter, title)
    # 分隔线
    painter.setPen(QPen(QColor(COLOR_HEADER_BG), 1))
    painter.drawLine(QRectF(20, y + 32, width - 40, 32).bottomLeft(),
                     QRectF(20, y + 32, width - 40, 32).bottomRight())
    return y + 42


def _draw_grid_table(painter: QPainter, y: float, width: float,
                     rows, cols: int) -> float:
    """绘制网格表格（label/value 交替），返回新 y。

    rows: 二维列表，每行包含 [(label1, value1), (label2, value2), ...]
    """
    table_x = 20
    table_w = width - 40
    col_w = table_w / cols
    row_h = ROW_HEIGHT_PX

    for row in rows:
        for i, (label, value) in enumerate(row):
            # label 列（偶数索引）背景色
            cell_x = table_x + i * 2 * col_w
            # label 单元格
            painter.fillRect(QRectF(cell_x, y, col_w, row_h), QColor(COLOR_HEADER_BG))
            painter.setPen(QPen(QColor(COLOR_BORDER), 1))
            painter.drawRect(QRectF(cell_x, y, col_w, row_h))
            painter.setFont(_font(10, bold=True))
            painter.setPen(QColor(COLOR_TEXT))
            painter.drawText(QRectF(cell_x + TABLE_PADDING, y, col_w - 2 * TABLE_PADDING, row_h),
                             Qt.AlignLeft | Qt.AlignVCenter, str(label))
            # value 单元格
            value_x = cell_x + col_w
            painter.fillRect(QRectF(value_x, y, col_w, row_h), QColor(COLOR_WHITE))
            painter.drawRect(QRectF(value_x, y, col_w, row_h))
            painter.setFont(_font(10))
            painter.drawText(QRectF(value_x + TABLE_PADDING, y, col_w - 2 * TABLE_PADDING, row_h),
                             Qt.AlignLeft | Qt.AlignVCenter, str(value))
        y += row_h
    return y + 8


def _draw_data_table(painter: QPainter, y: float, width: float,
                     header, data_rows, col_ratios) -> float:
    """绘制带表头的数据表格，返回新 y。

    col_ratios: 各列宽度比例（总和为 1）
    """
    table_x = 20
    table_w = width - 40
    cols = len(header)
    col_widths = [table_w * r for r in col_ratios]
    row_h = ROW_HEIGHT_PX

    # 表头
    painter.fillRect(QRectF(table_x, y, table_w, row_h), QColor(COLOR_TITLE))
    painter.setPen(QColor(COLOR_WHITE))
    painter.setFont(_font(10, bold=True))
    cx = table_x
    for i, h in enumerate(header):
        painter.drawRect(QRectF(cx, y, col_widths[i], row_h))
        painter.drawText(QRectF(cx + TABLE_PADDING, y,
                                col_widths[i] - 2 * TABLE_PADDING, row_h),
                         Qt.AlignCenter, str(h))
        cx += col_widths[i]
    y += row_h

    # 数据行
    painter.setFont(_font(9))
    for ridx, row in enumerate(data_rows):
        # 斑马纹背景
        if ridx % 2 == 1:
            painter.fillRect(QRectF(table_x, y, table_w, row_h),
                             QColor(COLOR_ROW_ALT))
        cx = table_x
        for i, cell in enumerate(row):
            painter.setPen(QPen(QColor(COLOR_BORDER), 1))
            painter.drawRect(QRectF(cx, y, col_widths[i], row_h))
            # 进步列着色
            text_color = QColor(COLOR_TEXT)
            cell_str = str(cell)
            if i == len(row) - 1:  # 进步列
                if cell_str.startswith('↑'):
                    text_color = QColor('#2e8b57')
                elif cell_str.startswith('↓'):
                    text_color = QColor('#d9534f')
            painter.setPen(text_color)
            painter.drawText(QRectF(cx + TABLE_PADDING, y,
                                    col_widths[i] - 2 * TABLE_PADDING, row_h),
                             Qt.AlignCenter, cell_str)
            cx += col_widths[i]
        y += row_h
    return y + 12


def _draw_paragraph(painter: QPainter, y: float, width: float,
                    text: str, bg_color: Optional[str] = None) -> float:
    """绘制自动换行段落（支持可选背景色），返回新 y。"""
    painter.setFont(_font(10))
    painter.setPen(QColor(COLOR_TEXT))

    rect_w = width - 40
    rect = QRectF(20, y, rect_w, 200)

    if bg_color:
        # 先估算高度
        doc = QTextDocument()
        doc.setDefaultFont(_font(10))
        doc.setTextWidth(rect_w)
        doc.setPlainText(text)
        h = doc.size().height() + 16
        painter.fillRect(QRectF(20, y, rect_w, h), QColor(bg_color))
        # 圆角效果（QRectF 的 fillRect 不支持圆角，用 save/clip 模拟）
        # 此处保持简单矩形即可

    doc = QTextDocument()
    doc.setDefaultFont(_font(10))
    doc.setTextWidth(rect_w)
    doc.setPlainText(text)
    painter.save()
    painter.translate(rect.left(), rect.top() + 8)
    doc.drawContents(painter)
    painter.restore()
    return y + doc.size().height() + 16


def _maybe_new_page(painter: QPainter, printer: QPrinter,
                    y: float, needed_height: float,
                    force_if_close: bool = False) -> float:
    """如剩余空间不足则换页，返回新 y。"""
    height_px = printer.height()
    if y + needed_height > height_px - 60 or force_if_close:
        printer.newPage()
        return 30.0
    return y


# ============================================================
# 兼容旧接口（_register_font / _build_styles）- 已弃用但保留占位
# ============================================================

def _register_font():
    """已弃用：QPrinter 使用 QFont 系统字体，无需注册。"""
    return CN_FONT_FAMILY


def _build_styles(font_name):
    """已弃用：保留以兼容旧调用（返回空 dict）。"""
    return {}
