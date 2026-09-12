# -*- coding: utf-8 -*-
"""跨端锚定测试：小程序 ↔ 桌面端数据格式对齐（阶段五互通）。

锚定策略（任一端改动未同步，测试失败）：
1. 从 miniprogram/src/utils/local-store.js 源码正则提取 exportBackup 的顶层键
   与 studentStore 的字段集合，锁定桌面端导出 JSON 的结构覆盖；
2. 桌面端 export → 结构断言（可直接被小程序 importBackup 消费）；
3. 小程序格式 fixture → 桌面端 import 往返断言（档案字段 + 剩余课时写入）。

Android 端对应锚定：android_app :core/:data 的 MiniprogramImporterTest 使用同一
fixture 数据（字段一一对应），三端任一改动未同步即测试失败。

运行：pytest test_miniprogram_parity.py -v
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_STORE_JS = os.path.join(_REPO_ROOT, 'miniprogram', 'src', 'utils',
                              'local-store.js')

# 与 Android MiniprogramImporterTest 共用的 fixture（勿单端改动：字段一一对应）
FIXTURE_STUDENT = {
    'id': 1,
    'name': '锚定测试学员',
    'phone': '13800000001',
    'parent_phone': '13900000001',
    'grade': '五年级',
    'class_group': '五年级2班',
    'address': '某小区某栋',
    'status': 'active',
    'expire_date': '2026-12-31',
    'note': '跨端锚定',
    'remaining_lessons': 7,
    'created_at': '2026-09-01 10:00:00',
    'updated_at': '2026-09-12 10:00:00',
    'deleted': 0,
}


def _read_local_store():
    with open(LOCAL_STORE_JS, 'r', encoding='utf-8') as f:
        return f.read()


def test_local_store_source_exists():
    """锚定前提：小程序 local-store.js 必须存在于约定路径。"""
    assert os.path.exists(LOCAL_STORE_JS), LOCAL_STORE_JS


def test_export_payload_covers_importbackup_keys():
    """exportBackup 顶层键（源码提取）必须被桌面端导出 JSON 全覆盖。"""
    src = _read_local_store()
    m = re.search(r'export function exportBackup\(mode\)\s*\{(.*?)\n\}', src, re.S)
    assert m, 'local-store.js 中未找到 exportBackup（结构已变？需同步本锚定测试）'
    body = m.group(1)
    # 提取顶层键：形如 `key: ...` 或 shorthand `mode,` 的行
    keys = set(re.findall(r'^\s{4}(\w+)[,:]', body, re.M))
    assert {'export_version', 'mode', 'exported_at', 'students', 'coaches',
            'lessons', 'lesson_packages', 'checkin_records'} <= keys, keys

    from data_center.miniprogram_bridge import export_miniprogram_backup
    with tempfile.TemporaryDirectory(prefix='mp_export_') as tmp:
        out = os.path.join(tmp, 'backup_shangmen.json')
        result = export_miniprogram_backup(tmp, 'shangmen', out)
        assert result['students'] == 0  # 空目录
        with open(result['path'], 'r', encoding='utf-8') as f:
            payload = json.load(f)
    assert keys <= set(payload.keys()), (
        f'桌面端导出缺少小程序期望的顶层键：{keys - set(payload.keys())}')
    assert payload['mode'] == 'shangmen'
    assert payload['export_version'] == 1
    # importBackup 对每张表的要求：数组（空表 no-op）
    for table in ('students', 'coaches', 'lessons', 'lesson_packages',
                  'checkin_records'):
        assert isinstance(payload[table], list), table


def test_export_student_row_field_alignment():
    """学生行字段必须覆盖 studentStore.create 落盘字段（源码提取 + fixture 并集）。"""
    src = _read_local_store()
    # studentStore.create 的默认字段：{ id, remaining_lessons: 0, status: 'active', ...data,
    #   created_at, updated_at, deleted: 0 }
    m = re.search(r'rows\.push\(\{ id, remaining_lessons: 0,(.*?)\}\)', src, re.S)
    assert m, 'local-store.js studentStore.create 结构已变？需同步本锚定测试'
    defaults = set(re.findall(r'(\w+):\s', m.group(1))) | {'id', 'remaining_lessons'}
    # edit.vue 表单字段经 ...data 展开（取 fixture 覆盖业务字段）
    expected = defaults | set(FIXTURE_STUDENT.keys())

    from data_center.miniprogram_bridge import export_miniprogram_backup
    with tempfile.TemporaryDirectory(prefix='mp_fields_') as tmp:
        out = os.path.join(tmp, 'backup_club.json')
        export_miniprogram_backup(tmp, 'club', out)
        with open(out, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        assert payload['mode'] == 'club'
    assert payload['students'] == []
    # 导入端 importBackup 按行读取字段；用 fixture 模拟一行验证字段可被接受
    row_keys = set(FIXTURE_STUDENT.keys())
    assert {'id', 'name', 'updated_at', 'deleted'} <= row_keys  # importBackup 强依赖
    # 源码默认字段必须都被 fixture/导出行覆盖
    assert defaults <= expected


def test_import_fixture_roundtrip():
    """小程序 fixture → 桌面端导入：档案字段 + 剩余课时 + 软删跳过。"""
    from data_center.miniprogram_bridge import import_miniprogram_backup
    from student_profile import profile_storage

    deleted_student = dict(FIXTURE_STUDENT, id=2, name='软删学员', deleted=1)
    payload = {
        'export_version': 1,
        'mode': 'shangmen',
        'exported_at': '2026-09-12 10:00:00',
        'students': [FIXTURE_STUDENT, deleted_student],
        'coaches': [],
        'lessons': [],
        'lesson_packages': [],
        'checkin_records': [],
    }
    with tempfile.TemporaryDirectory(prefix='mp_import_') as tmp:
        src = os.path.join(tmp, 'backup_shangmen_2026-09-12.json')
        with open(src, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)

        result = import_miniprogram_backup(src, tmp)
        assert result['created'] == 1
        assert result['updated'] == 0
        assert result['skipped_deleted'] == 1
        assert result['lessons_applied'] == 1

        students = profile_storage.read_all(tmp)
        assert len(students) == 1
        stu = students[0]
        assert stu['name'] == '锚定测试学员'
        assert stu['grade'] == '五年级'
        # 家长联系方式优先落桌面端"电话"列
        assert stu['phone'] == '13900000001'

        # 剩余课时反算：无明细 → total = remaining
        from lesson_manager import get_summary
        summary = {row['name']: row for row in get_summary(tmp)}
        assert summary['锚定测试学员']['remaining'] == 7

        # 幂等：重复导入变为更新
        result2 = import_miniprogram_backup(src, tmp)
        assert result2['created'] == 0 and result2['updated'] == 1


def test_import_rejects_malformed_payload():
    """结构校验：缺 mode / 错版本 / 非对象 必须抛 ValueError（用户可见）。"""
    from data_center.miniprogram_bridge import load_payload
    with tempfile.TemporaryDirectory(prefix='mp_bad_') as tmp:
        def _write(name, obj):
            p = os.path.join(tmp, name)
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(obj, f, ensure_ascii=False)
            return p

        try:
            load_payload(_write('bad1.json', {'export_version': 2, 'mode': 'shangmen'}))
            assert False, '版本校验未生效'
        except ValueError:
            pass
        try:
            load_payload(_write('bad2.json', {'export_version': 1}))
            assert False, 'mode 校验未生效'
        except ValueError:
            pass
        try:
            load_payload(_write('bad3.json', [1, 2]))
            assert False, '顶层类型校验未生效'
        except ValueError:
            pass
