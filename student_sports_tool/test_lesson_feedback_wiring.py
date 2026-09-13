# -*- coding: utf-8 -*-
"""批 1 接线测试：LessonWindow（5 字段上课记录）与 feedback_storage（7 字段课后反馈）。

背景：这两块此前**从未被实例化 / 从未被任何 UI 调用**（功能写完但无入口）。
本测试把「打开 → 填写 → 保存 → 回读」固定下来，并锚定 main_window 的接线入口，
避免以后重构时又把入口丢掉。
"""
import os
import sys
import tempfile

# Qt 需要平台插件；CI/无头环境走 offscreen
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.join(os.path.abspath('.'), 'training_tool'))

import modern_dialog as dialog          # noqa: E402

# 测试内不弹模态框
dialog.info = lambda *a, **k: None
dialog.warn = lambda *a, **k: None
dialog.error = lambda *a, **k: None
dialog.confirm = lambda *a, **k: True

from openpyxl import Workbook           # noqa: E402
from PySide6.QtWidgets import QApplication   # noqa: E402

_app = QApplication.instance() or QApplication([])

import feedback_storage as fb           # noqa: E402
import lesson_manager as lm             # noqa: E402
from lesson_window import LessonWindow  # noqa: E402


def _mk_dir(name='张三'):
    """造一个含单个学员档案的临时目录。"""
    d = tempfile.mkdtemp(prefix='_b1_wiring_')
    wb = Workbook()
    wb.active.title = '测评'
    wb.save(os.path.join(d, f'{name}.xlsx'))
    return d


def _open_window(d):
    """构造课时窗口并同步学员（学员来自汇总表，需先同步）。"""
    win = LessonWindow(d)
    win.on_sync()
    return win


def test_lesson_window_records_five_fields():
    """5 字段（学员/日期/课时数/训练内容/备注）写入并回读一致。"""
    d = _mk_dir()
    win = _open_window(d)
    assert win.cb_add_name.count() == 1

    win.cb_add_name.setCurrentText('张三')
    win.le_count.setText('1')
    win.le_content.setText('体能训练')
    win.le_note.setText('首次记录')
    win.on_add_lesson()

    detail = lm.get_detail(d, '张三')
    assert len(detail) == 1
    rec = detail[0]
    assert rec['name'] == '张三'
    assert rec['count'] == 1
    assert rec['content'] == '体能训练'
    assert rec['note'] == '首次记录'
    assert rec['date']  # 日期取窗口默认值（今天）

    summary = next(s for s in lm.get_summary(d) if s['name'] == '张三')
    assert summary['attended'] == 1


def test_lesson_window_total_and_delete_rollback():
    """设置总课时 + 删除明细后已上课时回退。"""
    d = _mk_dir()
    win = _open_window(d)

    win.cb_total_name.setCurrentText('张三')
    win.le_total.setText('20')
    win.on_set_total()
    stu = next(s for s in lm.get_summary(d) if s['name'] == '张三')
    assert stu['total'] == 20 and stu['remaining'] == 20

    win.cb_add_name.setCurrentText('张三')
    win.le_count.setText('1')
    win.le_content.setText('体能训练')
    win.on_add_lesson()
    stu = next(s for s in lm.get_summary(d) if s['name'] == '张三')
    assert stu['attended'] == 1 and stu['remaining'] == 19

    row = lm.get_detail(d, '张三')[0]['row']
    assert lm.delete_lesson(d, row)
    stu = next(s for s in lm.get_summary(d) if s['name'] == '张三')
    assert stu['attended'] == 0 and stu['remaining'] == 20


def test_feedback_seven_fields_roundtrip():
    """7 字段课后反馈写入并回读一致。"""
    d = _mk_dir()
    ok = fb.save_feedback(d, '张三', '体能训练', 90, '积极',
                          '动作标准', '加强核心', '2026-09-13')
    assert ok
    assert os.path.exists(os.path.join(d, fb.FEEDBACK_FILE))

    rows = fb.get_feedback_history(d, '张三')
    assert len(rows) == 1
    r = rows[0]
    assert r['date'] == '2026-09-13'
    assert r['name'] == '张三'
    assert r['content'] == '体能训练'
    assert r['completion'] == 90
    assert r['state'] == '积极'
    assert r['comment'] == '动作标准'
    assert r['next'] == '加强核心'


def test_feedback_does_not_pollute_lesson_file():
    """反馈与课时是两份文件，互不干扰（课时汇总不因反馈文件变化）。"""
    d = _mk_dir()
    _open_window(d)
    fb.save_feedback(d, '张三', '体能训练', 80, '认真', 'ok', '继续')
    files = sorted(os.listdir(d))
    assert '课时记录.xlsx' in files
    assert fb.FEEDBACK_FILE in files
    assert len(lm.get_summary(d)) == 1


def test_main_window_wiring_entries():
    """接线入口锚定：两个按钮在、旧 inline 控件已移除、反馈对话框可存可读。"""
    import main_window as mw

    d = _mk_dir()
    win = mw.MainWindow(d)
    win.le_dir.setText(d)

    assert win.btn_record_lesson.text() == '记录一次上课'
    assert win.btn_record_feedback.text() == '填写课后反馈'
    # 原 inline 两字段已移除（职责分离：测评不再顺带记课时）
    assert not hasattr(win, 'le_lesson_count')
    assert not hasattr(win, 'le_lesson_content')

    names = win._sync_and_list_students(d)
    assert '张三' in names

    dlg = mw.LessonFeedbackDialog(d, names, '张三')
    assert dlg.cb_name.currentText() == '张三'
    dlg.le_content.setText('体能训练')
    dlg.sb_completion.setValue(85)
    dlg.cb_state.setCurrentText('专注')
    dlg.te_comment.setPlainText('动作标准，节奏好')
    dlg.te_next.setPlainText('加强核心')
    dlg.on_save()

    rows = mw.feedback_storage().get_feedback_history(d, '张三')
    assert len(rows) == 1
    r = rows[0]
    assert r['completion'] == 85
    assert r['state'] == '专注'
    assert r['comment'] == '动作标准，节奏好'
    assert r['next'] == '加强核心'
