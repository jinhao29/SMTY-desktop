# -*- coding: utf-8 -*-
"""入口：学员体测档案录入工具。

M3-S4 拆分后：
- 业务逻辑迁移至 archive_controller.py
- MainWindow UI 外壳迁移至 main_window.py
- 本文件仅作为应用入口（保留以兼容旧启动脚本与 .spec）

操作流程：选择类型→填基本信息→录入实测成绩(自动评分)→填评价→保存到Excel。
"""
import sys
from PySide6.QtWidgets import QApplication

# 统一使用全局金融风主题（兼容旧引用名 DARK_QSS）
from theme import FINANCIAL_QSS
DARK_QSS = FINANCIAL_QSS

from main_window import MainWindow


def main():
    """应用入口。"""
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
