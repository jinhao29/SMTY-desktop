# -*- coding: utf-8 -*-
"""双端同步服务（data_center/sync_server.py）自检测试。

覆盖：/upload 自动合并、/sync/students.xlsx 拉取、/sync/version、token 鉴权、
安全校验拒绝（含可执行文件的备份）。

运行：pytest test_sync_receiver.py -v
"""
import io
import json
import os
import sys
import tempfile
import threading
import urllib.request
import zipfile

from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'student_profile'))

from data_center import sync_server


def _make_server(archive_dir: str, save_dir: str, token: str = 'test_token'):
    logs = []
    server = sync_server.create_server(
        host='127.0.0.1', port=0, save_dir=save_dir, token=token,
        archive_dir=archive_dir, log_cb=logs.append)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, 'http://127.0.0.1:%d' % server.server_address[1]


def _make_phone_backup(students, lessons=(), packages=()) -> bytes:
    """构造手机端 .smty_backup zip（export_meta.json 格式）。"""
    meta = {
        'exported_at': '2026-09-04 15:00:00',
        'students': list(students),
        'lessons': list(lessons),
        'packages': list(packages),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('export_meta.json', json.dumps(meta, ensure_ascii=False))
    return buf.getvalue()


STUDENT = {
    'name': '同步测试学员', 'age': 10, 'gender': '男', 'school': '测试一小',
    'phone': '13900000000', 'height': 140, 'weight': 35, 'grade': '小学四年级',
    'note': '双端同步', 'fatherHeight': 175, 'motherHeight': 160,
}
LESSON = {'student_name': '同步测试学员', 'date': '2026-09-01',
          'count': 1, 'content': '体能训练', 'note': '', 'coach': ''}
LESSON2 = {'student_name': '同步测试学员', 'date': '2026-09-02',
           'count': 2, 'content': '灵敏训练', 'note': '', 'coach': ''}
PACKAGE = {'student_name': '同步测试学员', 'total': 20, 'attended': 3,
           'remaining': 17, 'purchase_date': '2026-08-01', 'expire_date': ''}


def test_upload_auto_merge():
    archive_dir = tempfile.mkdtemp(prefix='smty_arch_')
    save_dir = tempfile.mkdtemp(prefix='smty_save_')
    server, base = _make_server(archive_dir, save_dir)
    try:
        data = _make_phone_backup([STUDENT], [LESSON], [PACKAGE])
        req = urllib.request.Request(
            base + '/upload', data=data, method='POST',
            headers={'X-Sync-Token': 'test_token',
                     'X-Backup-Name': 'smty_backup_20260904.smty_backup',
                     'Content-Type': 'application/octet-stream'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        assert resp.status == 200 and body['code'] == 0, body
        assert body['restored'] >= 1, body

        # 档案目录应产生该学员的 per-student xlsx
        assert os.path.exists(os.path.join(archive_dir, '同步测试学员.xlsx'))
        # 课时记录.xlsx 已生成
        assert os.path.exists(os.path.join(archive_dir, '课时记录.xlsx'))
        # 备份文件已保存
        assert os.path.exists(os.path.join(
            save_dir, 'smty_backup_20260904.smty_backup'))
        # v23.2 推送方向 LWW：手机学员自动进入 PC 花名册（身高体重随档案落地）
        import profile_manager as pm
        roster = {x['name']: x for x in pm.list_students(archive_dir)}
        assert '同步测试学员' in roster, roster
        assert roster['同步测试学员']['height'] == 140.0
        assert roster['同步测试学员']['updated_at']  # 毫秒时间戳已记录
    finally:
        server.shutdown()


def test_export_students_xlsx():
    archive_dir = tempfile.mkdtemp(prefix='smty_arch_')
    save_dir = tempfile.mkdtemp(prefix='smty_save_')
    server, base = _make_server(archive_dir, save_dir)
    try:
        data = _make_phone_backup([STUDENT])
        req = urllib.request.Request(base + '/upload', data=data, method='POST',
                                     headers={'X-Sync-Token': 'test_token'})
        urllib.request.urlopen(req, timeout=30).read()

        # 拉取学员同步包
        req2 = urllib.request.Request(base + '/sync/students.xlsx',
                                      headers={'X-Sync-Token': 'test_token'})
        with urllib.request.urlopen(req2, timeout=30) as resp:
            assert resp.status == 200
            payload = resp.read()
        assert len(payload) > 1000

        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(payload))
        ws = wb.active
        headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        # 列集必须与 Android ExcelSync 智能映射兼容（"数据更新时间"供 LWW 判新）
        assert headers == ['姓名', '性别', '年龄', '年级', '学校', '电话',
                           '身高(cm)', '体重(kg)', '数据更新时间', '备注'], headers
        row2 = [ws.cell(row=2, column=c).value for c in range(1, ws.max_column + 1)]
        # 无花名册场景：姓名/性别/学校/电话来自每学员档案 info
        assert row2[0] == '同步测试学员' and row2[1] == '男'
        assert row2[4] == '测试一小' and row2[5] == '13900000000'

        # 有花名册场景：身高体重应来自 学员档案.xlsx，且带毫秒级更新时间
        import profile_manager as pm
        pm.save_student(archive_dir, '同步测试学员', 10, 140.0, 35.0,
                        '小学四年级', note='双端同步')
        req2b = urllib.request.Request(base + '/sync/students.xlsx',
                                       headers={'X-Sync-Token': 'test_token'})
        with urllib.request.urlopen(req2b, timeout=30) as resp:
            payload2 = resp.read()
        wb2 = load_workbook(io.BytesIO(payload2))
        row2b = [wb2.active.cell(row=2, column=c).value for c in range(1, 11)]
        assert row2b[6] == 140 and row2b[7] == 35, row2b
        assert row2b[3] == '小学四年级'
        assert isinstance(row2b[8], int) and row2b[8] > 1_700_000_000_000, row2b  # epoch ms

        # 版本端点
        req3 = urllib.request.Request(base + '/sync/version',
                                      headers={'X-Sync-Token': 'test_token'})
        with urllib.request.urlopen(req3, timeout=10) as resp:
            v = json.loads(resp.read().decode('utf-8'))
        assert v['code'] == 0 and v['students'] >= 1 and v['version'] > 0, v
    finally:
        server.shutdown()


def test_token_and_health():
    archive_dir = tempfile.mkdtemp(prefix='smty_arch_')
    save_dir = tempfile.mkdtemp(prefix='smty_save_')
    server, base = _make_server(archive_dir, save_dir, token='secret')
    try:
        # /health 免鉴权
        with urllib.request.urlopen(base + '/health', timeout=10) as resp:
            assert resp.read().decode() == 'OK'
        # 错误 token → 401
        try:
            urllib.request.urlopen(base + '/sync/version', timeout=10)
            assert False, '应被 401 拒绝'
        except urllib.error.HTTPError as e:
            assert e.code == 401
        # 上传错误 token → 401
        try:
            req = urllib.request.Request(base + '/upload', data=b'x', method='POST',
                                         headers={'X-Sync-Token': 'wrong'})
            urllib.request.urlopen(req, timeout=10)
            assert False, '应被 401 拒绝'
        except urllib.error.HTTPError as e:
            assert e.code == 401
    finally:
        server.shutdown()


def test_dangerous_backup_rejected():
    archive_dir = tempfile.mkdtemp(prefix='smty_arch_')
    save_dir = tempfile.mkdtemp(prefix='smty_save_')
    server, base = _make_server(archive_dir, save_dir)
    try:
        # 含可执行文件的备份 → 422 拒绝且不写入档案目录
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('export_meta.json', '{}')
            zf.writestr('evil/_payload.exe', b'MZ fake')
        req = urllib.request.Request(base + '/upload', data=buf.getvalue(),
                                     method='POST',
                                     headers={'X-Sync-Token': 'test_token'})
        try:
            urllib.request.urlopen(req, timeout=30)
            assert False, '应被 422 拒绝'
        except urllib.error.HTTPError as e:
            assert e.code == 422
            body = json.loads(e.read().decode('utf-8'))
            assert '可执行' in body['message'], body
        assert os.listdir(archive_dir) == []  # 档案目录未被污染
    finally:
        server.shutdown()


def test_beacon_broadcast():
    """心跳广播协议对齐 Android UdpDesktopDiscoveryService（type/host/port）。

    Windows 不回环全网广播，故测试用单播目标验证报文格式；
    生产路径 target 仍为 255.255.255.255:9112。
    """
    import socket
    from data_center.sync_beacon import SyncBeacon, UDP_PORT

    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(('127.0.0.1', UDP_PORT))
    rx.settimeout(5)
    beacon = SyncBeacon(service_port=18765, interval=0.2, target_host='127.0.0.1',
                        token='pair_token', pc_name='李哥-PC')
    beacon.start()
    try:
        data, addr = rx.recvfrom(1024)
        payload = json.loads(data.decode('utf-8'))
        assert payload['type'] == 'desktop_online', payload
        assert payload['port'] == 18765, payload
        assert payload['host'], payload
        assert isinstance(payload['timestamp'], int)
        # v23.5 零配置配对字段
        assert payload['token'] == 'pair_token', payload
        assert payload['name'] == '李哥-PC', payload
    finally:
        beacon.stop()
        rx.close()


def test_device_hello_trust_flow():
    """手机回执设备指纹：登记 → 待信任 → PC 信任后 hello 返回 trusted=True。"""
    import tempfile
    archive_dir = tempfile.mkdtemp(prefix='smty_hello_')
    save_dir = tempfile.mkdtemp(prefix='smty_hello2_')
    server, base = _make_server(archive_dir, save_dir)
    try:
        hello_body = json.dumps({'type': 'phone_hello', 'device_id': 'dev123',
                                 'device_name': '小米 15', 'timestamp': 1}).encode('utf-8')
        req = urllib.request.Request(
            base + '/device/hello', data=hello_body, method='POST',
            headers={'X-Sync-Token': 'test_token',
                     'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        assert body['code'] == 0 and body['trusted'] is False, body

        # config 中已登记
        from data_center.config_manager import load_config, update_config
        devices = load_config(archive_dir).get('sync_devices') or {}
        assert 'dev123' in devices and devices['dev123']['name'] == '小米 15'
        assert devices['dev123']['trusted'] is False

        # PC 端信任后 hello 返回 trusted=True
        devices['dev123']['trusted'] = True
        update_config(archive_dir, sync_devices=devices)
        req2 = urllib.request.Request(
            base + '/device/hello', data=hello_body, method='POST',
            headers={'X-Sync-Token': 'test_token'})
        with urllib.request.urlopen(req2, timeout=10) as resp:
            body2 = json.loads(resp.read().decode('utf-8'))
        assert body2['trusted'] is True, body2
    finally:
        server.shutdown()


def test_usb_helper():
    """USB 自动 reverse：adb 不可用/无设备时安全返回空列表，绝不抛出。"""
    from data_center.usb_helper import list_adb_devices, auto_reverse
    devices = list_adb_devices()  # 本机可能有或没有 adb/设备，只验证不抛出
    assert isinstance(devices, list)
    assert isinstance(auto_reverse(8765, already_done=set(devices)), list)


def test_lww_push_merge():
    """推送方向（手机→PC）花名册 LWW 合并：新者胜、年级编码转换、PC 现值保留。"""
    import time as _t
    import profile_manager as pm
    d = tempfile.mkdtemp(prefix='smty_lww_')
    now = int(_t.time() * 1000)

    # 1. 花名册无此学员 → 建档，年级编码转 PC 标签
    r = pm.merge_student_from_phone(d, {'name': '新学员', 'age': 10, 'gender': '男',
                                        'height': 138, 'weight': 32, 'grade': '4',
                                        'updated_at': now})
    assert r == 'created', r
    s = next(x for x in pm.list_students(d) if x['name'] == '新学员')
    assert s['grade'] == '小学四年级' and s['height'] == 138.0

    # 2. 手机端时间戳更旧 → 跳过（保留 PC 数据）
    r = pm.merge_student_from_phone(d, {'name': '新学员', 'height': 150,
                                        'updated_at': now - 1000})
    assert r == 'skipped', r
    s = next(x for x in pm.list_students(d) if x['name'] == '新学员')
    assert s['height'] == 138.0

    # 3. 手机端较新 → 刷新身高年龄；年级/备注保留 PC 现值；updated_at 透传手机端时间戳
    pm.save_student(d, '新学员', 10, 138.0, 32.0, '小学四年级', note='PC备注')
    r = pm.merge_student_from_phone(d, {'name': '新学员', 'age': 11, 'height': 142,
                                        'weight': 35, 'grade': '5',
                                        'updated_at': now + 600000})
    assert r == 'updated', r
    s = next(x for x in pm.list_students(d) if x['name'] == '新学员')
    assert s['height'] == 142.0 and s['age'] == 11, s
    assert s['grade'] == '小学四年级' and s['note'] == 'PC备注'
    assert s['updated_at'] == now + 600000, s

    # 4. 无时间戳的旧版备份 → 不覆盖 PC 已有学员
    r = pm.merge_student_from_phone(d, {'name': '新学员', 'height': 999})
    assert r == 'skipped' and \
        next(x for x in pm.list_students(d) if x['name'] == '新学员')['height'] == 142.0


def test_repeated_push_idempotent():
    """重复推送同一备份（自动同步高频场景）：课时明细不得重复放大（v23.6 幂等合并）。"""
    archive_dir = tempfile.mkdtemp(prefix='smty_idem_')
    save_dir = tempfile.mkdtemp(prefix='smty_idem2_')
    server, base = _make_server(archive_dir, save_dir)
    try:
        data = _make_phone_backup([STUDENT], [LESSON, LESSON2], [PACKAGE])
        req = urllib.request.Request(
            base + '/upload', data=data, method='POST',
            headers={'X-Sync-Token': 'test_token',
                     'X-Backup-Name': 'smty_backup_idem.smty_backup'})
        urllib.request.urlopen(req, timeout=30).read()

        import lesson_manager as lm
        n1 = len(lm.get_detail(archive_dir))

        # 同一备份再推一次（防抖备份/30 分钟周期同步的常态）
        req2 = urllib.request.Request(
            base + '/upload', data=data, method='POST',
            headers={'X-Sync-Token': 'test_token',
                     'X-Backup-Name': 'smty_backup_idem2.smty_backup'})
        urllib.request.urlopen(req2, timeout=30).read()
        n2 = len(lm.get_detail(archive_dir))

        summary = {s['name']: s for s in lm.get_summary(archive_dir)}['同步测试学员']
        assert n1 == 2, n1
        assert n2 == 2, f'重复推送后明细应保持 2 条，实际 {n2}（重复放大）'
        assert summary['attended'] == 3, summary  # 1 + 2 节
    finally:
        server.shutdown()


if __name__ == '__main__':
    import urllib.error
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('PASS %s' % name)
            except AssertionError as e:
                fails += 1
                print('FAIL %s: %s' % (name, e))
    sys.exit(1 if fails else 0)
