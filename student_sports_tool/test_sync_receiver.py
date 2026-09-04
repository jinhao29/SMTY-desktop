# -*- coding: utf-8 -*-
"""backup_receiver.py（双端同步服务）自检测试。

覆盖：/upload 自动合并、/sync/students.xlsx 拉取、/sync/version、token 鉴权、
安全校验拒绝（含可执行文件的备份）。

运行：pytest test_sync_receiver.py -v
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_HERE = os.path.dirname(os.path.abspath(__file__))
RECEIVER_PATH = os.path.normpath(os.path.join(
    _HERE, '..', 'android_app', 'desktop_sync', 'backup_receiver.py'))


def _load_receiver():
    spec = importlib.util.spec_from_file_location('backup_receiver', RECEIVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_server(mod, archive_dir: str, save_dir: str, token: str = 'test_token'):
    mod.ARCHIVE_DIR = archive_dir
    mod.TOOL_ROOT = _HERE  # 让 _ensure_tool_importable 能找到本仓库模块
    mod.BackupReceiverHandler.server_token = token
    mod.BackupReceiverHandler.save_dir = save_dir
    server = ThreadingHTTPServer(('127.0.0.1', 0), mod.BackupReceiverHandler)
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
PACKAGE = {'student_name': '同步测试学员', 'total': 20, 'attended': 3,
           'remaining': 17, 'purchase_date': '2026-08-01', 'expire_date': ''}


def test_upload_auto_merge():
    mod = _load_receiver()
    archive_dir = tempfile.mkdtemp(prefix='smty_arch_')
    save_dir = tempfile.mkdtemp(prefix='smty_save_')
    server, base = _make_server(mod, archive_dir, save_dir)
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
    finally:
        server.shutdown()


def test_export_students_xlsx():
    mod = _load_receiver()
    archive_dir = tempfile.mkdtemp(prefix='smty_arch_')
    save_dir = tempfile.mkdtemp(prefix='smty_save_')
    server, base = _make_server(mod, archive_dir, save_dir)
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
        # 列集必须与 Android ExcelSync 智能映射兼容（不得含"父身高"等干扰列）
        assert headers == ['姓名', '性别', '年龄', '年级', '学校', '电话',
                           '身高(cm)', '体重(kg)', '备注'], headers
        row2 = [ws.cell(row=2, column=c).value for c in range(1, ws.max_column + 1)]
        assert row2[0] == '同步测试学员' and row2[1] == '男'
        assert row2[6] == 140 and row2[7] == 35

        # 版本端点
        req3 = urllib.request.Request(base + '/sync/version',
                                      headers={'X-Sync-Token': 'test_token'})
        with urllib.request.urlopen(req3, timeout=10) as resp:
            v = json.loads(resp.read().decode('utf-8'))
        assert v['code'] == 0 and v['students'] >= 1 and v['version'] > 0, v
    finally:
        server.shutdown()


def test_token_and_health():
    mod = _load_receiver()
    archive_dir = tempfile.mkdtemp(prefix='smty_arch_')
    save_dir = tempfile.mkdtemp(prefix='smty_save_')
    server, base = _make_server(mod, archive_dir, save_dir, token='secret')
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
    mod = _load_receiver()
    archive_dir = tempfile.mkdtemp(prefix='smty_arch_')
    save_dir = tempfile.mkdtemp(prefix='smty_save_')
    server, base = _make_server(mod, archive_dir, save_dir)
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
