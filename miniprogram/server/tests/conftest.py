# -*- coding: utf-8 -*-
"""pytest 共享 fixture。

关键设计：
1. **必须在 import 任何业务模块之前注入 MP_SECRET** —— passlib_lite 在模块导入时
   就读环境变量并校验，缺失会直接抛 RuntimeError。因此本文件用 os.environ.setdefault
   在顶层先设置好，早于 conftest 之外的 import。
2. **临时数据库**：database.DATA_DIR 是模块级常量，方向与真实库分离靠 monkeypatch
   在 session fixture 里改写 DATA_DIR，确保测试绝不碰 server_data/ 下的真实库。
3. **headless**：全程用 fastapi.testclient（不需要真实端口/uvicorn）。
"""
import os
import sys
import tempfile

# --- 最早时机注入测试密钥（先于任何业务模块导入）---
TEST_SECRET = 'test-secret-for-pytest-only-0123456789'
os.environ.setdefault('MP_SECRET', TEST_SECRET)
os.environ.setdefault('MP_MODE', 'shangmen')

# 让 `import database` / `from routers import ...` 可用
_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
from passlib_lite import issue_token, hash_password  # noqa: E402

# 测试管理员（与生产机密无关，仅测试库内播种）
TEST_PHONE = '13800000000'
TEST_PASSWORD = 'TestPassw0rd!2026'


@pytest.fixture(scope='session', autouse=True)
def _isolated_data_dir():
    """把 database.DATA_DIR 指向临时目录，彻底隔离真实库。

    session 级：整个测试会话共用一个临时目录，避免每个用例重建 schema。
    """
    tmp = tempfile.mkdtemp(prefix='mp_test_db_')
    original = database.DATA_DIR
    database.DATA_DIR = tmp
    yield tmp
    database.DATA_DIR = original


@pytest.fixture(scope='session')
def app_module(_isolated_data_dir):
    """导入 FastAPI app（此时 MP_SECRET 已就位，DATA_DIR 已隔离）。"""
    import main
    return main


@pytest.fixture(scope='session')
def client(app_module, _isolated_data_dir):
    """headless TestClient（触发 startup → init_db 建表）。"""
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture(scope='session', autouse=True)
def _seed_admin(client, _isolated_data_dir):
    """在两个模式库里各种一个测试管理员账号。"""
    for mode in database.VALID_MODES:
        conn = database.get_conn_for_mode(mode)
        row = conn.execute("SELECT id FROM users WHERE phone=?", (TEST_PHONE,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users(phone,password_hash,name,role,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (TEST_PHONE, hash_password(TEST_PASSWORD), '测试教练', 'coach',
                 database.now_str(), database.now_str()))
            conn.commit()
    yield


@pytest.fixture
def auth_headers():
    """有效 token 的请求头（依赖已播种的管理员）。"""
    # 从库中取真实 user_id
    conn = database.get_conn_for_mode('shangmen')
    row = conn.execute("SELECT id FROM users WHERE phone=?", (TEST_PHONE,)).fetchone()
    assert row, '测试管理员未播种，_seed_admin fixture 应已执行'
    return {'Authorization': 'Bearer ' + issue_token(row['id'], TEST_PHONE)}


@pytest.fixture
def valid_token():
    conn = database.get_conn_for_mode('shangmen')
    row = conn.execute("SELECT id FROM users WHERE phone=?", (TEST_PHONE,)).fetchone()
    assert row
    return issue_token(row['id'], TEST_PHONE)


@pytest.fixture(autouse=True)
def _clean_business_tables(client):
    """每个用例前清空业务表，保证用例间互不干扰（保留 users）。"""
    yield
    for mode in database.VALID_MODES:
        conn = database.get_conn_for_mode(mode)
        for t in ('checkin_records', 'lessons', 'lesson_packages', 'students', 'coaches'):
            conn.execute(f'DELETE FROM {t}')
        conn.execute('DELETE FROM sqlite_sequence')
        conn.commit()
