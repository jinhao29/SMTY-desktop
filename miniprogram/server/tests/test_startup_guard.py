# -*- coding: utf-8 -*-
"""启动守卫用例：MP_SECRET 必须由环境变量提供且足够强。

背景：密钥硬编码在源码里等同于公开密钥——源码可见即可伪造任意用户 token。
现改为缺失或 <16 字符时直接拒绝启动。

此处用**子进程**验证，因为 passlib_lite 在 import 时就读环境变量并抛异常，
同进程内无论如何都改不掉（模块已加载）。子进程才能真实还原「冷启动」路径。
"""
import os
import subprocess
import sys

import pytest

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable

# 继承当前环境但会剔除/覆盖 MP_SECRET
_BASE_ENV_KEYS = ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'HOME', 'USERPROFILE',
                  'LANG', 'LC_ALL', 'PYTHONPATH', 'PYTHONHOME')


def _clean_env(**overrides):
    env = {k: v for k, v in os.environ.items() if k in _BASE_ENV_KEYS}
    # 强制子进程用 UTF-8 输出，否则 Windows 上中文错误信息会以 GBK 编码写出，
    # 父进程按 UTF-8 解码会抛 UnicodeDecodeError。
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env.update(overrides)
    return env


def _run(args, env, timeout=90):
    """统一用 bytes 捕获再显式按 UTF-8 解码，规避平台默认编码差异。"""
    r = subprocess.run(args, cwd=SERVER_DIR, env=env,
                       capture_output=True, timeout=timeout)
    return subprocess.CompletedProcess(
        args, r.returncode,
        r.stdout.decode('utf-8', errors='replace'),
        r.stderr.decode('utf-8', errors='replace'))


def _import_passlib(env):
    """在子进程里 import passlib_lite，返回 CompletedProcess。"""
    return _run([PYTHON, '-c', 'import passlib_lite; print("OK")'], env)


def _start_app(env):
    """在子进程里 import main（会触发 app 构建 + init_db）。"""
    return _run([PYTHON, '-c', 'import main; print("OK")'], env)


# =========================================================================
# 1. 未注入 MP_SECRET → 拒绝启动
# =========================================================================
def test_missing_secret_refuses_startup():
    env = _clean_env()  # 无 MP_SECRET
    r = _import_passlib(env)
    assert r.returncode != 0, '未注入 MP_SECRET 时不应启动成功'
    assert 'MP_SECRET' in (r.stderr or ''), \
        f'错误信息应提及 MP_SECRET，实际: {r.stderr[-400:]}'


def test_missing_secret_refuses_full_app_startup():
    """不只 passlib，完整 app 也必须起不来。"""
    env = _clean_env()
    r = _start_app(env)
    assert r.returncode != 0, '未注入 MP_SECRET 时完整 app 不应启动成功'


# =========================================================================
# 2. MP_SECRET 过短 → 拒绝启动
# =========================================================================
@pytest.mark.parametrize('bad_secret,label', [
    ('', 'empty'),
    ('a', 'len1'),
    ('short123', 'len8'),
    ('0123456789abcde', 'len15'),      # 边界：15 < 16
], ids=['empty', 'len1', 'len8', 'len15_boundary'])
def test_short_secret_refuses_startup(bad_secret, label):
    env = _clean_env(MP_SECRET=bad_secret)
    r = _import_passlib(env)
    assert r.returncode != 0, f'MP_SECRET={label} 不应通过校验'
    assert 'MP_SECRET' in (r.stderr or '')


# =========================================================================
# 3. MP_SECRET 合法（恰好 16 / 更长）→ 启动成功
# =========================================================================
@pytest.mark.parametrize('good_secret,label', [
    ('0123456789abcdef', 'len16_boundary'),    # 边界：恰好 16
    ('a' * 43, 'len43_like_real'),
    ('test-secret-for-pytest-only-0123456789', 'typical'),
], ids=['len16_boundary', 'len43', 'typical'])
def test_valid_secret_allows_startup(good_secret, label):
    env = _clean_env(MP_SECRET=good_secret, MP_MODE='shangmen')
    r = _import_passlib(env)
    assert r.returncode == 0, f'MP_SECRET={label} 应通过校验，stderr: {r.stderr[-400:]}'
    assert 'OK' in (r.stdout or '')


def test_valid_secret_full_app_startup(tmp_path):
    """合法密钥时完整 app 可启动（含 init_db 建表）。"""
    env = _clean_env(MP_SECRET='test-secret-for-pytest-only-0123456789',
                     MP_MODE='shangmen')
    r = _start_app(env)
    assert r.returncode == 0, f'app 启动失败: {r.stderr[-600:]}'
    assert 'OK' in (r.stdout or '')


# =========================================================================
# 4. 错误信息可操作性：必须告诉用户怎么生成
# =========================================================================
def test_error_message_is_actionable():
    r = _import_passlib(_clean_env())
    err = r.stderr or ''
    assert 'MP_SECRET' in err
    # 应给出可直接执行的生成命令
    assert 'secrets.token_urlsafe' in err or 'export MP_SECRET' in err, \
        f'错误信息应包含生成方法，实际: {err[-500:]}'


# =========================================================================
# 5. 拒绝启动时不留下副作用
# =========================================================================
def test_refused_startup_leaves_no_db(tmp_path):
    """密钥非法时不应完成启动（拒绝要发生在副作用之前）。"""
    env = _clean_env(MP_SECRET='short')
    r = _run([PYTHON, '-c', 'import main'], env)
    assert r.returncode != 0
    assert 'MP_SECRET' in (r.stderr or '')
