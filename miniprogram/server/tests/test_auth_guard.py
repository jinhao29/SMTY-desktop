# -*- coding: utf-8 -*-
"""鉴权回归用例（核心）。

背景：2026-09-10 发现 P0 —— 6 个业务路由模块（students / coaches / lessons /
checkins / packages / backup）的 APIRouter 全部漏挂 get_current_user，
34 个端点在不带 token 时返回 200 并正常读写数据。

本文件固化该修复，防止未来新增路由模块或改动 APIRouter 时鉴权再次回归。
"""
import base64
import time

import pytest

from conftest import TEST_PHONE, TEST_PASSWORD
from passlib_lite import issue_token, SECRET as _SECRET

# --- 受保护端点清单：新增路由模块时必须同步补充 ---
# 格式: (模块名, method, path)
# path 中的 {sid} 等占位符用测试数据填充，仅用于鉴权拦截（鉴权先于业务逻辑）。
PROTECTED_ENDPOINTS = [
    # students —— 7 个
    ('students', 'GET', '/api/v1/students'),
    ('students', 'GET', '/api/v1/students/1'),
    ('students', 'POST', '/api/v1/students'),
    ('students', 'PUT', '/api/v1/students/1'),
    ('students', 'DELETE', '/api/v1/students/1'),
    ('students', 'GET', '/api/v1/students/1/lessons'),
    ('students', 'GET', '/api/v1/students/1/checkins'),
    # coaches —— 7 个
    ('coaches', 'GET', '/api/v1/coaches'),
    ('coaches', 'GET', '/api/v1/coaches/1'),
    ('coaches', 'POST', '/api/v1/coaches'),
    ('coaches', 'PUT', '/api/v1/coaches/1'),
    ('coaches', 'DELETE', '/api/v1/coaches/1'),
    ('coaches', 'GET', '/api/v1/coaches/1/schedule'),
    ('coaches', 'GET', '/api/v1/coaches/1/payout'),
    # lessons —— 7 个
    ('lessons', 'GET', '/api/v1/lessons'),
    ('lessons', 'GET', '/api/v1/lessons/today'),
    ('lessons', 'GET', '/api/v1/lessons/week?start=2026-09-14&end=2026-09-20'),
    ('lessons', 'GET', '/api/v1/lessons/1'),
    ('lessons', 'POST', '/api/v1/lessons'),
    ('lessons', 'PUT', '/api/v1/lessons/1'),
    ('lessons', 'DELETE', '/api/v1/lessons/1'),
    # checkins —— 5 个
    ('checkins', 'POST', '/api/v1/checkin/1'),
    ('checkins', 'POST', '/api/v1/checkout/1'),
    ('checkins', 'GET', '/api/v1/checkins'),
    ('checkins', 'GET', '/api/v1/checkins/pending'),
    ('checkins', 'GET', '/api/v1/checkins/today'),
    # packages —— 6 个
    ('packages', 'GET', '/api/v1/packages'),
    ('packages', 'GET', '/api/v1/packages/stats'),
    ('packages', 'GET', '/api/v1/packages/1'),
    ('packages', 'POST', '/api/v1/packages'),
    ('packages', 'PUT', '/api/v1/packages/1'),
    ('packages', 'DELETE', '/api/v1/packages/1'),
    # backup —— 2 个
    ('backup', 'GET', '/api/v1/backup/export'),
    ('backup', 'POST', '/api/v1/backup/import'),
]

# 每个受保护模块至少一个「代表端点」用于多维度鉴权攻击测试
MODULE_PROBES = [
    ('students', 'GET', '/api/v1/students'),
    ('coaches', 'GET', '/api/v1/coaches'),
    ('lessons', 'GET', '/api/v1/lessons'),
    ('checkins', 'GET', '/api/v1/checkins'),
    ('packages', 'GET', '/api/v1/packages'),
    ('backup', 'GET', '/api/v1/backup/export'),
]

_ENDPOINT_IDS = ['%s-%s-%s' % (m, meth, p.split('?')[0].replace('/api/v1/', '').replace('/', '_'))
                 for m, meth, p in PROTECTED_ENDPOINTS]
_PROBE_IDS = [m for m, _, _ in MODULE_PROBES]


def _call(client, method, path, headers=None, json_body=None):
    return client.request(method, path, headers=headers or {}, json=json_body)


# =========================================================================
# 1. 全端点覆盖：不带任何 Authorization header 必须 401
# =========================================================================
@pytest.mark.parametrize('module,method,path', PROTECTED_ENDPOINTS, ids=_ENDPOINT_IDS)
def test_no_token_rejected(client, module, method, path):
    """不带 token 访问任一受保护端点 → 401。

    这是本轮 P0 的直接回归防线：任何端点漏挂鉴权都会被这条用例抓到。
    """
    r = _call(client, method, path)
    assert r.status_code == 401, (
        f'[{module}] {method} {path} 未携带 token 时返回 {r.status_code}，'
        f'期望 401 —— 该端点可能漏挂 get_current_user')


# =========================================================================
# 2. 伪造签名 token → 401
# =========================================================================
@pytest.mark.parametrize('module,method,path', MODULE_PROBES, ids=_PROBE_IDS)
def test_forged_signature_rejected(client, module, method, path):
    """token 结构合法但签名错误 → 401。"""
    forged = base64.urlsafe_b64encode(b'1.13800000000.9999999999').decode().rstrip('=')
    headers = {'Authorization': 'Bearer %s.deadbeefdeadbeef' % forged}
    r = _call(client, method, path, headers=headers)
    assert r.status_code == 401, f'[{module}] 伪造签名被放行（{r.status_code}）'


# =========================================================================
# 3. 篡改载荷 token（保留原签名）→ 401
# =========================================================================
@pytest.mark.parametrize('module,method,path', MODULE_PROBES, ids=_PROBE_IDS)
def test_tampered_payload_rejected(client, module, method, path, valid_token):
    """改动载荷但沿用旧签名 → 401（HMAC 校验必须失败）。"""
    b64, sig = valid_token.rsplit('.', 1)
    tampered = b64[:-2] + ('AA' if not b64.endswith('AA') else 'BB') + '.' + sig
    headers = {'Authorization': 'Bearer ' + tampered}
    r = _call(client, method, path, headers=headers)
    assert r.status_code == 401, f'[{module}] 篡改载荷被放行（{r.status_code}）'


# =========================================================================
# 4. 过期 token → 401
# =========================================================================
def _make_expired_token(user_id: int, phone: str) -> str:
    """构造一个签名正确但 exp 已过期的 token（复用真实签名算法）。"""
    import hashlib
    import hmac
    payload = f'{user_id}.{phone}.{int(time.time()) - 3600}'.encode()
    b64 = base64.urlsafe_b64encode(payload).decode().rstrip('=')
    sig = hmac.new(_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return f'{b64}.{sig}'


@pytest.mark.parametrize('module,method,path', MODULE_PROBES, ids=_PROBE_IDS)
def test_expired_token_rejected(client, module, method, path):
    """签名正确但已过期 → 401。"""
    headers = {'Authorization': 'Bearer ' + _make_expired_token(1, '13800000000')}
    r = _call(client, method, path, headers=headers)
    assert r.status_code == 401, f'[{module}] 过期 token 被放行（{r.status_code}）'


# =========================================================================
# 5. 有效 token → 放行（不能修成「一律 401」）
# =========================================================================
@pytest.mark.parametrize('module,method,path', [
    ('students', 'GET', '/api/v1/students'),
    ('coaches', 'GET', '/api/v1/coaches'),
    ('lessons', 'GET', '/api/v1/lessons'),
    ('checkins', 'GET', '/api/v1/checkins'),
    ('packages', 'GET', '/api/v1/packages'),
    ('packages', 'GET', '/api/v1/packages/stats'),
    ('backup', 'GET', '/api/v1/backup/export'),
], ids=['students', 'coaches', 'lessons', 'checkins', 'packages', 'packages_stats', 'backup'])
def test_valid_token_allowed(client, module, method, path, auth_headers):
    """有效 token 必须放行 —— 确保鉴权不是「一律拒绝」。"""
    r = _call(client, method, path, headers=auth_headers)
    assert r.status_code == 200, (
        f'[{module}] {method} {path} 携带有效 token 却返回 {r.status_code}')


# =========================================================================
# 6. 畸形 Authorization header → 401（不崩 500）
# =========================================================================
@pytest.mark.parametrize('bad_header', [
    '',                      # 空
    'Bearer',                # 只有前缀
    'Bearer ',               # 前缀 + 空格
    'Token abc.def',         # 错误 scheme
    'abc.def',               # 无 scheme
    'Bearer ..',             # 结构畸形
    'Bearer ' + 'x' * 5000,  # 超长
], ids=['empty', 'prefix_only', 'prefix_space', 'wrong_scheme', 'no_scheme',
        'malformed', 'oversized'])
def test_malformed_authorization_rejected(client, bad_header):
    """畸形 header 应 401，而非 500 —— 鉴权层不能因解析异常崩溃。"""
    r = client.get('/api/v1/students', headers={'Authorization': bad_header})
    assert r.status_code == 401, f'畸形 header {bad_header!r} 返回 {r.status_code}'


# =========================================================================
# 7. 公开端点：/auth/login 无 token 也应可访问
# =========================================================================
def test_login_is_public(client):
    """登录接口必须公开 —— 否则无法获取 token，形成死锁。"""
    r = client.post('/api/v1/auth/login',
                    json={'phone': TEST_PHONE, 'password': TEST_PASSWORD})
    assert r.status_code == 200, f'/auth/login 应公开可访问，实际 {r.status_code}'
    assert 'token' in r.json()


def test_health_is_public(client):
    r = client.get('/api/v1/health')
    assert r.status_code == 200
    assert r.json().get('ok') is True


def test_login_does_not_require_token(client):
    """无反证：错误口令应 400（业务错误）而非 401（鉴权错误）。"""
    r = client.post('/api/v1/auth/login',
                    json={'phone': '13800000000', 'password': 'wrong'})
    assert r.status_code == 400, f'错误口令应 400，实际 {r.status_code}'


# =========================================================================
# 8. auth.py 内部：/me 与 /logout 仍需鉴权
# =========================================================================
@pytest.mark.parametrize('method,path', [
    ('GET', '/api/v1/auth/me'),
    ('POST', '/api/v1/auth/logout'),
], ids=['me', 'logout'])
def test_auth_me_and_logout_protected(client, method, path):
    r = _call(client, method, path)
    assert r.status_code == 401, f'{path} 未携带 token 应 401，实际 {r.status_code}'


# =========================================================================
# 9. ocr.py 保持原有鉴权行为
# =========================================================================
def test_ocr_requires_auth(client):
    """OCR 端点已单独挂 Depends(get_current_user)，无 token 应 401。"""
    r = client.post('/api/v1/ocr/image')
    assert r.status_code == 401, f'OCR 无 token 应 401，实际 {r.status_code}'


# =========================================================================
# 10. 结构性防线：所有已注册路由必须带鉴权（除白名单）
# =========================================================================
# 有意公开的端点（新增公开端点必须在此登记，强制显式决策）
PUBLIC_ROUTES = {
    ('POST', '/api/v1/auth/login'),
    ('GET', '/api/v1/health'),
    ('GET', '/openapi.json'),
    ('GET', '/docs'),
    ('GET', '/docs/oauth2-redirect'),
    ('GET', '/redoc'),
}


def _route_requires_auth(route) -> bool:
    """判断路由是否挂了 get_current_user 依赖。

    覆盖两种写法：
    - 路由级：APIRouter(..., dependencies=[Depends(get_current_user)])
    - 函数级：def me(user=Depends(get_current_user))
    """
    import inspect

    # 路由级
    for dep in getattr(route, 'dependencies', []) or []:
        fn = getattr(dep, 'dependency', None)
        if fn is not None and getattr(fn, '__name__', '') == 'get_current_user':
            return True

    # 函数级：检查端点函数的默认参数里有没有 Depends(get_current_user)
    endpoint = getattr(route, 'endpoint', None)
    if endpoint is not None:
        try:
            sig = inspect.signature(endpoint)
        except (TypeError, ValueError):
            sig = None
        if sig is not None:
            for param in sig.parameters.values():
                dep = getattr(param.default, 'dependency', None)
                if dep is not None and getattr(dep, '__name__', '') == 'get_current_user':
                    return True

    # 依赖覆盖（router 级 dependencies 会挂到 route 上，但某些版本放在
    # route.dependant 里，做一层兜底递归）
    dependant = getattr(route, 'dependant', None)
    if dependant is not None:
        stack = [dependant]
        seen = 0
        while stack and seen < 200:
            cur = stack.pop()
            seen += 1
            call = getattr(cur, 'call', None)
            if call is not None and getattr(call, '__name__', '') == 'get_current_user':
                return True
            for sub in getattr(cur, 'dependencies', []) or []:
                stack.append(sub)
    return False


def _collect_protected(app):
    """收集 app 上所有需要鉴权的 (method, path)。"""
    out = []
    for route in app.routes:
        path = getattr(route, 'path', '')
        if not path.startswith('/api/'):
            continue
        methods = getattr(route, 'methods', set()) or set()
        for m in methods:
            if m in ('HEAD', 'OPTIONS'):
                continue
            if _route_requires_auth(route):
                out.append((m, path))
    return out


def test_all_api_routes_guarded(app_module):
    """结构性断言：/api/ 下的每个端点要么挂了鉴权，要么在 PUBLIC_ROUTES 白名单里。

    这条用例是「防新增」的关键 —— 新加一个路由模块忘记挂 dependencies 会直接失败，
    不必等有人真的去未授权访问。
    """
    app = app_module.app
    unguarded = []
    for route in app.routes:
        path = getattr(route, 'path', '')
        if not path.startswith('/api/'):
            continue
        for m in (getattr(route, 'methods', set()) or set()):
            if m in ('HEAD', 'OPTIONS'):
                continue
            if _route_requires_auth(route):
                continue
            # 函数级鉴权（auth.py / ocr.py 的写法）无法从 route.dependencies 看出，
            # 此时退化为「是否在白名单」判断，未登记即视为漏挂。
            if (m, path) not in PUBLIC_ROUTES:
                unguarded.append(f'{m} {path}')
    assert not unguarded, (
        '以下 API 端点既未挂鉴权，也不在 PUBLIC_ROUTES 白名单中：\n  ' +
        '\n  '.join(sorted(set(unguarded))) +
        '\n如是刻意公开，请登记到 PUBLIC_ROUTES 并说明理由。')


def test_protected_endpoint_count(app_module):
    """守卫：受保护端点数量不应因重构意外减少（当前 34 个 + 函数级鉴权的 3 个）。"""
    protected = _collect_protected(app_module.app)
    assert len(protected) >= 30, (
        f'受保护端点仅 {len(protected)} 个，疑似鉴权大面积脱落（期望 ≥30）')
