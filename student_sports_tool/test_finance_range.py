# -*- coding: utf-8 -*-
"""批 3 测试：财务页按时间段对账（fee_manager 区间口径）。

背景：此前财务页只有「全量」与「本月」两个口径，月底想按任意区间核对
收入只能自己拿计算器加。批 3 让收费记录可按日期区间过滤并汇总。

口径约定（重要）：**应收 / 待收不随时间段变化**（它们由课时包决定，与时间无关），
只有实收随区间变化——否则同一张统计卡在不同筛选下会自相矛盾。
"""
import os
import sys
import tempfile
from datetime import date

# GUI 冒烟需要平台插件；无头环境走 offscreen（必须在导入 PySide6 之前设置）
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, os.path.abspath('.'))

import fee_manager as fm                    # noqa: E402


def _mk_dir():
    return tempfile.mkdtemp(prefix='_b3_range_')


def _seed(d):
    """三条跨越两个月的收费。"""
    fm.add_payment(d, '张三', '2026-08-15', 4000, 20, '微信', '首付')
    fm.add_payment(d, '张三', '2026-09-05', 2000, 10, '支付宝', '续费')
    fm.add_payment(d, '李四', '2026-09-20', 1500, 10, '现金', '')


def test_filter_payments_none_returns_all():
    d = _mk_dir()
    _seed(d)
    recs = fm.get_payments(d)
    assert len(fm.filter_payments(recs)) == 3
    assert len(fm.filter_payments(recs, None, None)) == 3


def test_filter_payments_by_range_inclusive():
    d = _mk_dir()
    _seed(d)
    recs = fm.get_payments(d)
    only_sep = fm.filter_payments(recs, '2026-09-01', '2026-09-30')
    assert len(only_sep) == 2
    assert {r['name'] for r in only_sep} == {'张三', '李四'}
    # 端点为闭区间
    assert len(fm.filter_payments(recs, '2026-08-15', '2026-08-15')) == 1
    # 只给下界
    assert len(fm.filter_payments(recs, '2026-09-01', None)) == 2
    # 只给上界
    assert len(fm.filter_payments(recs, None, '2026-08-31')) == 1
    # 空区间
    assert fm.filter_payments(recs, '2026-10-01', '2026-10-31') == []


def test_compute_totals_month_and_range():
    d = _mk_dir()
    _seed(d)
    rows = fm.compute_finance(d)
    recs = fm.get_payments(d)

    # 不筛选：range_paid = 全量实收
    t_all = fm.compute_totals(rows, recs, today=date(2026, 9, 30))
    assert t_all['range_label'] == '全部'
    assert t_all['range_paid'] == t_all['total_paid'] == 7500.0
    assert t_all['range_count'] == 3
    # 本月实收（2026-09）
    assert t_all['month_paid'] == 3500.0

    # 筛选 9 月：实收变 3500，但应收/待收必须保持不变
    t_sep = fm.compute_totals(rows, recs, today=date(2026, 9, 30),
                              date_from='2026-09-01', date_to='2026-09-30')
    assert t_sep['range_paid'] == 3500.0
    assert t_sep['range_count'] == 2
    assert t_sep['total_receivable'] == t_all['total_receivable']
    assert t_sep['total_due'] == t_all['total_due']


def test_compute_totals_empty_range():
    d = _mk_dir()
    _seed(d)
    rows = fm.compute_finance(d)
    recs = fm.get_payments(d)
    t = fm.compute_totals(rows, recs, today=date(2026, 9, 30),
                          date_from='2026-01-01', date_to='2026-01-31')
    assert t['range_paid'] == 0.0
    assert t['range_count'] == 0
    assert t['total_paid'] == 7500.0   # 全量实收不受影响


def test_export_alert_list_is_importable_from_finance_path():
    """批 3：财务页复用的导出函数必须可导入（抽出后两处共用）。"""
    from data_center.renewal_panel import export_alert_list
    assert callable(export_alert_list)


def test_finance_page_range_controls_smoke():
    """GUI 冒烟：时间段控件接线正确，「本月 / 全部」切换能改变统计口径。"""
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from finance_page import FinancePage

    d = _mk_dir()
    _seed(d)

    page = FinancePage()
    page.set_archive_dir(d)          # 内部触发 refresh

    # 控件就位
    assert page.btn_this_month.text() == '本月'
    assert page.btn_all_time.text() == '全部'
    assert page.btn_export_due.text() == '导出欠费清单'
    assert page.btn_apply_range.text() == '应用时间段'

    # 默认全量口径：第 4 张卡是「本月实收」
    assert page._range_from == '' and page._range_to == ''
    assert page.stat_month.lbl_label.text() == '本月实收'

    # 点「本月」→ 切到区间口径，且实收按 9 月算（3500）
    page.on_this_month()
    assert page._range_from.endswith('-01')
    assert page.stat_month.lbl_label.text() == '区间实收'

    # 点「全部」→ 回到本月口径
    page.on_all_time()
    assert page._range_from == '' and page._range_to == ''
    assert page.stat_month.lbl_label.text() == '本月实收'


def test_finance_page_range_filters_payment_table():
    """GUI 冒烟：时间段筛选会同时收窄「收费记录」表。"""
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from finance_page import FinancePage

    d = _mk_dir()
    _seed(d)
    page = FinancePage()
    page.set_archive_dir(d)
    assert page.table_payments.rowCount() == 3      # 全量 3 笔

    page._range_from, page._range_to = '2026-09-01', '2026-09-30'
    page.refresh()
    assert page.table_payments.rowCount() == 2      # 9 月只有 2 笔
