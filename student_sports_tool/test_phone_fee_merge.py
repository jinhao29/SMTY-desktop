# -*- coding: utf-8 -*-
"""批 2 测试：手机端收费流水 → PC 收费记录的合并规则。

合并规则（拍板）：自然键 =（学员, 日期, 金额, 课时数, 收款方式, 备注），
与 Android 侧 `FeeRecord.stableKey` 的输入一致。

本测试锁三条底线：
1. **不重复** —— 同一笔收费重复推送只入账一次；
2. **不覆盖** —— 键冲突时跳过，PC 已有记录金额不被改写；
3. **不静默丢弃** —— 跳过的笔数被计数（供进度日志上报）。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.join(os.path.abspath('.'), 'data_center'))

import fee_manager as fm                                        # noqa: E402
from data_center.android_backup_parser import (                  # noqa: E402
    _normalize_fee, parse_meta_json,
)
from data_center.backup.backup_restorer import (                 # noqa: E402
    _existing_fee_keys, _fee_key, _import_phone_fees,
)


def _mk_dir():
    return tempfile.mkdtemp(prefix='_b2_fee_')


def _fee(name, date='2026-09-13', amount=200.0, hours=5.0, method='微信', note=''):
    return {'student_name': name, 'date': date, 'amount': amount,
            'hours': hours, 'method': method, 'note': note}


def test_first_import_inserts_all():
    d = _mk_dir()
    added, skipped = _import_phone_fees(d, [
        _fee('张三'), _fee('李四', amount=300.0, note='首付'),
    ])
    assert (added, skipped) == (2, 0)
    assert len(fm.get_payments(d)) == 2


def test_reimport_is_idempotent():
    """同一批重复推送：一笔不多、金额不被改写。"""
    d = _mk_dir()
    batch = [_fee('张三'), _fee('李四', amount=300.0)]
    _import_phone_fees(d, batch)
    added, skipped = _import_phone_fees(d, batch)
    assert (added, skipped) == (0, 2)
    assert len(fm.get_payments(d)) == 2
    rec = next(r for r in fm.get_payments(d) if r['name'] == '李四')
    assert rec['amount'] == 300.0


def test_mixed_batch_only_new_ones_insert():
    """同一天的第二笔收款（金额不同）是不同键 → 必须新增，不能被当成重复吞掉。"""
    d = _mk_dir()
    _import_phone_fees(d, [_fee('张三')])
    added, skipped = _import_phone_fees(d, [
        _fee('张三'),                     # 重复
        _fee('张三', amount=100.0),       # 同日第二笔 → 新
        _fee('王五', date='2026-09-12'),  # 新学员
    ])
    assert (added, skipped) == (2, 1)
    assert len(fm.get_payments(d)) == 3


def test_invalid_rows_are_counted_not_silently_dropped():
    d = _mk_dir()
    added, skipped = _import_phone_fees(d, [
        _fee('张三', amount=0),   # 金额 0
        _fee('李四', hours=0),    # 课时 0
    ])
    assert added == 0 and skipped == 2
    assert fm.get_payments(d) == []


def test_skip_resolution_skips_fee():
    d = _mk_dir()
    added, skipped = _import_phone_fees(
        d, [_fee('张三')], resolution_map={'张三': {'action': 'skip'}})
    assert (added, skipped) == (0, 1)
    assert fm.get_payments(d) == []


def test_rename_resolution_renames_fee():
    d = _mk_dir()
    added, _ = _import_phone_fees(
        d, [_fee('张三')],
        resolution_map={'张三': {'action': 'rename', 'new_name': '张三新'}})
    assert added == 1
    assert fm.get_payments(d)[0]['name'] == '张三新'


def test_fee_key_normalizes_float_shape():
    """200 与 200.0 必须算出同一个键，否则同一笔收费两端各成一行。"""
    assert _fee_key('张三', '2026-09-13', 200, 5, '微信', '') == \
        _fee_key('张三', '2026-09-13', 200.0, 5.0, '微信', '')


def test_existing_fee_keys_reads_written_records():
    d = _mk_dir()
    fm.add_payment(d, '张三', '2026-09-13', 200, 5, '微信', '现场')
    assert _fee_key('张三', '2026-09-13', 200, 5, '微信', '现场') in _existing_fee_keys(d)


def test_normalize_fee_accepts_android_camel_case():
    """Android 侧导出的驼峰键（studentName）也要识别。"""
    item = _normalize_fee({
        'studentName': '张三', 'date': '2026-09-13', 'amount': 200.0,
        'hours': 5.0, 'method': '微信', 'note': '现场收款',
    })
    assert item['student_name'] == '张三'
    assert item['amount'] == 200.0
    assert item['method'] == '微信'


def test_parse_meta_json_includes_fees():
    """export_meta.json 的 fees[] 要被解析出来（Android 备份的唯一通道）。"""
    d = _mk_dir()
    p = os.path.join(d, 'export_meta.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump({
            'students': [{'name': '张三', 'age': 10}],
            'fees': [{'studentName': '张三', 'date': '2026-09-13', 'amount': 200,
                      'hours': 5, 'method': '微信', 'note': ''}],
        }, f, ensure_ascii=False)
    parsed = parse_meta_json(p)
    assert parsed is not None
    assert len(parsed['fees']) == 1
    assert parsed['fees'][0]['student_name'] == '张三'
    assert len(parsed['students']) == 1
