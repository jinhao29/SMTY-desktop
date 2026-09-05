# -*- coding: utf-8 -*-
"""UI 组件外观层（Facade）：统一入口重新导出所有 UI 组件。

M3-S3 拆分后，原 ui_components.py 按单一职责切分为：
- base_components.py：视觉令牌（ColorPalette/Shapes/FontHelper/Shadows）
                     + 基础组件（BaseCard/IconBox/_draw_icon/_fade_color）
- stat_components.py：业务卡片（StatCard/GradientHeroCard）
- chart_components.py：图表（BarChartWidget/LineChartWidget/HistoryListWidget）
- nav_components.py：导航（IconButton/NavBar）

本文件保留为 Facade，确保现有 `from ui_components import ...` 不破坏。
新代码应直接从子模块导入，遵循单一职责。
"""
from base_components import (
    ColorPalette,
    Shapes,
    FontHelper,
    Shadows,
    BaseCard,
    FormSheet,
    IconBox,
    _draw_icon,
    _fade_color,
)
from stat_components import (
    StatCard,
    GradientHeroCard,
)
from chart_components import (
    BarChartWidget,
    LineChartWidget,
    HistoryListWidget,
)
from nav_components import (
    IconButton,
    NavBar,
)

__all__ = [
    # 视觉令牌
    'ColorPalette', 'Shapes', 'FontHelper', 'Shadows',
    # 基础组件
    'BaseCard', 'FormSheet', 'IconBox', '_draw_icon', '_fade_color',
    # 业务卡片
    'StatCard', 'GradientHeroCard',
    # 图表
    'BarChartWidget', 'LineChartWidget', 'HistoryListWidget',
    # 导航
    'IconButton', 'NavBar',
]
