# -*- coding: utf-8 -*-
"""学员档案模块：基本信息登记 + BMI 自动计算 + 课时联动展示。

分层结构：
- bmi_processor.py: 纯逻辑，BMI 计算与体型分类
- profile_storage.py: 数据层，Excel 读写
- profile_manager.py: 管理层，增删改查 + 续费预警
- profile_screen.py: UI 层
"""
