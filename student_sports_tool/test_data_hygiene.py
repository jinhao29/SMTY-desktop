# -*- coding: utf-8 -*-
"""档案目录数据卫生自检：主数据文件不得被当成学员（2026-09-06 污染事故回归测试）。

事故：收费记录.xlsx 落在档案目录后，学员扫描把它当成学员「收费记录」，
经双向同步污染 PC 花名册与手机学员表。

运行：pytest test_data_hygiene.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lesson_manager as lm


def _make_archive(tmp_path):
    """构造含主数据文件的档案目录（各文件由 _ensure_file 生成合法结构）。"""
    lm._ensure_file(str(tmp_path))
    fm_path = os.path.join(str(tmp_path), '收费记录.xlsx')
    import fee_manager as fm
    fm._ensure_file(str(tmp_path))
    assert os.path.exists(fm_path)
    # 模拟历史事故：汇总表被写入假学员行
    from openpyxl import load_workbook
    wb = lm._load_wb(lm._lesson_file_path(str(tmp_path)))
    ws = wb['汇总']
    for i, name in enumerate(('收费记录', '课堂反馈'), start=2):
        ws.cell(row=i, column=1, value=name)
    lm._save_wb(lm._lesson_file_path(str(tmp_path)), wb)
    return str(tmp_path)


def test_master_files_not_treated_as_students(tmp_path):
    """收费记录/学员档案/教练档案/课时记录 不得出现在学员扫描名单里。"""
    d = _make_archive(tmp_path)
    students = lm._get_students_from_dir(d)
    assert '收费记录' not in students
    assert '学员档案' not in students and '教练档案' not in students
    assert '课时记录' not in students


def test_sync_students_cleans_ghost_master_rows(tmp_path):
    """sync_students 清理汇总表中以主数据文件名为名的幽灵学员行。"""
    d = _make_archive(tmp_path)
    assert any(s['name'] == '收费记录' for s in lm.get_summary(d))
    lm.sync_students(d)
    names = {s['name'] for s in lm.get_summary(d)}
    assert '收费记录' not in names


if __name__ == '__main__':
    import tempfile
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn(tempfile.mkdtemp(prefix='smty_hygiene_'))
                print('PASS %s' % name)
            except AssertionError as e:
                fails += 1
                print('FAIL %s: %s' % (name, e))
    sys.exit(1 if fails else 0)
