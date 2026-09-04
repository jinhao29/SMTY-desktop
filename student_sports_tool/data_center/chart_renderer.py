# -*- coding: utf-8 -*-
"""处理器层：QtCharts 图表渲染（趋势图与雷达图）。

职责：
- 根据测评记录生成总分趋势折线图
- 根据两次测评生成项目对比雷达图
- 纯渲染逻辑，返回 QChart 对象供 UI 显示
"""
from PySide6.QtCharts import QChart, QLineSeries, QValueAxis, QCategoryAxis, QPolarChart
from PySide6.QtGui import QColor, QPen, QFont
from PySide6.QtCore import Qt


# 浅色珊瑚橙主题配色
COLOR_PRIMARY = QColor('#FF6B47')     # 主线（最近测评）
COLOR_SECONDARY = QColor('#F59E0B')   # 对比线（首次测评）
COLOR_GRID = QColor('#E5E5E5')
COLOR_TEXT = QColor('#6B6B6B')
COLOR_BG = QColor('#F5F7FA')


def create_trend_chart(records):
    """创建总分趋势折线图。

    参数:
        records: 测评记录列表（来自 _meta.records，含 date 和 total）

    返回: QChart 对象
    """
    chart = QChart()
    chart.setTitle('总分趋势')
    chart.setTitleBrush(COLOR_TEXT)
    chart.legend().hide()
    chart.setBackgroundBrush(COLOR_BG)
    chart.setBackgroundPen(QPen(COLOR_GRID))

    # 过滤有总分的记录
    scored = [r for r in records if r.get('total') is not None]
    if not scored:
        chart.setTitle('暂无测评数据')
        return chart

    series = QLineSeries()
    series.setColor(COLOR_PRIMARY)
    pen = QPen(COLOR_PRIMARY, 3)
    series.setPen(pen)

    for i, rec in enumerate(scored):
        x = i
        y = rec['total']
        series.append(x, y)

    chart.addSeries(series)

    # X轴：日期分类
    axis_x = QCategoryAxis()
    axis_x.setTitleText('测评日期')
    axis_x.setTitleBrush(COLOR_TEXT)
    axis_x.setLabelsBrush(COLOR_TEXT)
    axis_x.setGridLineVisible(False)
    for i, rec in enumerate(scored):
        label = rec.get('date', f'第{i+1}次')
        # 日期缩短为 MM-DD
        if len(label) >= 10:
            label = label[5:10]
        axis_x.append(label, i)
    chart.addAxis(axis_x, Qt.AlignBottom)
    series.attachAxis(axis_x)

    # Y轴：分数
    axis_y = QValueAxis()
    axis_y.setTitleText('总分')
    axis_y.setTitleBrush(COLOR_TEXT)
    axis_y.setLabelsBrush(COLOR_TEXT)
    axis_y.setRange(0, 100)
    axis_y.setTickCount(6)
    axis_y.setGridLineColor(COLOR_GRID)
    chart.addAxis(axis_y, Qt.AlignLeft)
    series.attachAxis(axis_y)

    return chart


def create_radar_chart(first_records, last_records):
    """创建项目得分对比雷达图。

    参数:
        first_records: 首次测评的项目得分 dict {项目名: score}
        last_records: 最近测评的项目得分 dict {项目名: score}

    返回: QChart 对象
    """
    # 取两次共有的项目
    common = sorted(set(first_records.keys()) & set(last_records.keys()))
    if not common:
        chart = QChart()
        chart.setTitle('无共同项目可对比')
        chart.setTitleBrush(COLOR_TEXT)
        chart.setBackgroundBrush(COLOR_BG)
        return chart

    chart = QPolarChart()
    chart.setTitle('项目得分对比')
    chart.setTitleBrush(COLOR_TEXT)
    chart.legend().setAlignment(Qt.AlignRight)
    chart.legend().setLabelBrush(COLOR_TEXT)
    chart.setBackgroundBrush(COLOR_BG)

    # 首次测评系列
    series_first = QLineSeries()
    series_first.setName('首次测评')
    pen1 = QPen(COLOR_SECONDARY, 2)
    series_first.setPen(pen1)

    # 最近测评系列
    series_last = QLineSeries()
    series_last.setName('最近测评')
    pen2 = QPen(COLOR_PRIMARY, 2)
    series_last.setPen(pen2)

    for proj in common:
        series_first.append(common.index(proj), first_records[proj] or 0)
        series_last.append(common.index(proj), last_records[proj] or 0)
    # 闭合雷达图
    if common:
        series_first.append(0, first_records[common[0]] or 0)
        series_last.append(0, last_records[common[0]] or 0)

    chart.addSeries(series_first)
    chart.addSeries(series_last)

    # 角度轴（项目名）
    angular = QCategoryAxis()
    angular.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)
    angular.setLabelsBrush(COLOR_TEXT)
    for i, proj in enumerate(common):
        angular.append(proj, i)
    if common:
        angular.append(common[0], len(common))
    chart.addAxis(angular, QPolarChart.PolarOrientationAngular)
    series_first.attachAxis(angular)
    series_last.attachAxis(angular)

    # 径向轴（分数）
    radial = QValueAxis()
    radial.setRange(0, 100)
    radial.setTickCount(6)
    radial.setGridLineColor(COLOR_GRID)
    radial.setLabelsBrush(COLOR_TEXT)
    chart.addAxis(radial, QPolarChart.PolarOrientationRadial)
    series_first.attachAxis(radial)
    series_last.attachAxis(radial)

    return chart
