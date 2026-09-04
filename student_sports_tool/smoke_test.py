# -*- coding: utf-8 -*-
"""冒烟测试：构建完整主窗口 + 现代化弹窗，自动关闭后退出。"""
import sys
import app as app_mod
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

a = QApplication(sys.argv)
a.setStyleSheet(app_mod.GLOBAL_QSS)
w = app_mod.App()
w.show()

failures = []


def check_dialog():
    import modern_dialog as md
    try:
        dlg = md.ModernDialog(w, '测试', '现代化弹窗构造 OK', 'info')
        dlg.close()
        print('SMOKE OK: dialog constructed')
    except Exception as e:
        failures.append(repr(e))
        print('SMOKE FAIL:', e)
    QTimer.singleShot(400, check_indicator)


def check_indicator():
    try:
        w._on_sync_state('ok')
        assert w.lbl_sync.text() == '●  同步完成', w.lbl_sync.text()
        w._on_sync_state('syncing')
        assert w.lbl_sync.text() == '●  正在同步...'
        print('SMOKE OK: sync indicator states')
    except Exception as e:
        failures.append(repr(e))
        print('SMOKE FAIL:', e)
    QTimer.singleShot(400, check_row_actions)


def check_row_actions():
    """行操作列：填充 -> 排序 -> 按钮仍映射到正确行。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QPushButton
    from base_components import install_row_actions, refresh_row_actions, _visual_row
    try:
        t = QTableWidget()
        t.setColumnCount(1)
        t.setRowCount(3)
        for i, name in enumerate(['甲', '乙', '丙']):
            t.setItem(i, 0, QTableWidgetItem(name))
        hits = []
        install_row_actions(t, [('按钮', lambda tb, r: hits.append(r))])
        assert t.columnCount() == 2 and t.horizontalHeaderItem(1).text() == '操作'
        t.resize(500, 240)
        t.show()
        QApplication.processEvents()
        t.setSortingEnabled(True)
        t.sortByColumn(0, Qt.DescendingOrder)
        QApplication.processEvents()
        # 排序后视觉行变化：丙(2)->行0 乙(1)->行1 甲(0)->行2
        buttons = []
        for r in range(3):
            box = t.cellWidget(r, 1)
            buttons.append(box.findChild(QPushButton))
        rows = [_visual_row(t, btn) for btn in buttons]
        assert rows == [0, 1, 2], rows
        buttons[0].click()
        assert hits == [0], hits
        refresh_row_actions(t)
        assert t.cellWidget(0, 1) is not None
        print('SMOKE OK: row actions + sorting mapping')
    except Exception as e:
        failures.append(repr(e))
        print('SMOKE FAIL:', e)
    a.quit()


QTimer.singleShot(1200, check_dialog)
rc = a.exec()
print('RESULT:', 'FAIL ' + str(failures) if failures else 'ALL PASS')
sys.exit(1 if failures else rc)
