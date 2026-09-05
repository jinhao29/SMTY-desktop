# -*- coding: utf-8 -*-
"""fee_manager 财务数据层测试：收费记录读写 + 自动计算口径。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath('.'))

import fee_manager as fm


def _mk_dir():
    return tempfile.mkdtemp(prefix='_fee_test_')


def test_add_and_get_payments():
    d = _mk_dir()
    assert fm.add_payment(d, '张三', '2026-09-01', 4000, 20, method='微信')
    assert fm.add_payment(d, '张三', '2026-08-15', 2000, 10)
    assert fm.add_payment(d, '李四', '2026-09-03', 1900, 10, note='优惠价')
    recs = fm.get_payments(d)
    assert len(recs) == 3
    # 按日期倒序
    assert recs[0]['date'] == '2026-09-03'
    only = fm.get_payments(d, name='张三')
    assert len(only) == 2 and all(r['name'] == '张三' for r in only)


def test_add_payment_rejects_invalid():
    d = _mk_dir()
    assert not fm.add_payment(d, '', '2026-09-01', 100, 10)
    assert not fm.add_payment(d, '张三', '2026-09-01', 0, 10)
    assert not fm.add_payment(d, '张三', '2026-09-01', 100, 0)


def test_delete_payment_and_renumber():
    d = _mk_dir()
    for i in range(3):
        fm.add_payment(d, f'学员{i}', '2026-09-01', 100, 1)
    recs = fm.get_payments(d)
    assert fm.delete_payment(d, recs[1]['row'])
    recs2 = fm.get_payments(d)
    assert len(recs2) == 2
    assert [r['seq'] for r in sorted(recs2, key=lambda x: x['row'])] == [1, 2]


def test_compute_student_finance_core():
    # 20 节课收 4000 → 单价 200；总课时 30、已上 12
    r = fm.compute_student_finance(total=30, attended=12,
                                   paid_amount=4000, paid_hours=20)
    assert r['unit_price'] == 200.0
    assert r['receivable'] == 6000.0   # 30 × 200
    assert r['consumed'] == 2400.0     # 12 × 200
    assert r['paid'] == 4000.0
    assert r['due'] == 2000.0
    assert r['status'] == '待收款'

    # 结清
    r2 = fm.compute_student_finance(total=20, attended=8,
                                    paid_amount=4000, paid_hours=20)
    assert r2['status'] == '已结清' and r2['due'] == 0

    # 未收费
    r3 = fm.compute_student_finance(total=10, attended=2, paid_amount=0, paid_hours=0)
    assert r3['status'] == '未收费' and r3['unit_price'] == 0.0
    assert r3['receivable'] == 0.0 and r3['consumed'] == 0.0


def test_unit_price_rounding():
    assert fm.unit_price(1000, 3) == 333.33
    assert fm.unit_price(0, 0) == 0.0


def test_compute_finance_integration():
    d = _mk_dir()
    # 造课时数据：张三 30 课时已上 12；李四 10 课时已上 1
    from lesson_manager import add_lesson, set_total_lessons
    set_total_lessons(d, '张三', 30)
    set_total_lessons(d, '李四', 10)
    for i in range(12):
        add_lesson(d, '张三', f'2026-08-{i+1:02d}', 1)
    add_lesson(d, '李四', '2026-09-01', 1)
    # 收费：张三 4000/20 课时
    fm.add_payment(d, '张三', '2026-09-01', 4000, 20)

    rows = fm.compute_finance(d)
    by_name = {r['name']: r for r in rows}
    z = by_name['张三']
    assert z['total'] == 30 and z['attended'] == 12
    assert z['unit_price'] == 200.0
    assert z['receivable'] == 6000.0 and z['consumed'] == 2400.0
    assert z['due'] == 2000.0 and z['status'] == '待收款'
    l = by_name['李四']
    assert l['status'] == '未收费' and l['paid'] == 0

    totals = fm.compute_totals(rows, fm.get_payments(d), today=__import__('datetime').date(2026, 9, 10))
    assert totals['total_paid'] == 4000.0
    assert totals['total_receivable'] == 6000.0
    assert totals['total_due'] == 2000.0
    assert totals['month_paid'] == 4000.0  # 收费日期在 9 月


if __name__ == '__main__':
    test_add_and_get_payments()
    test_add_payment_rejects_invalid()
    test_delete_payment_and_renumber()
    test_compute_student_finance_core()
    test_unit_price_rounding()
    test_compute_finance_integration()
    print('ALL PASS')
