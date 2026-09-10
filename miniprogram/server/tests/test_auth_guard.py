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


def _dep_requires_auth(obj) -> bool:
    """单个依赖对象是否就是 get_current_user。"""
    fn = getattr(obj, 'dependency', None) or getattr(obj, 'call', None)
    return fn is not None and getattr(fn, '__name__', '') == 'get_current_user'


def _route_requires_auth(route) -> bool:
    """判断路由是否挂了 get_current_user 依赖。

    覆盖两种写法：
    - 路由级：APIRouter(..., dependencies=[Depends(get_current_user)])
    - 函数级：def me(user=Depends(get_current_user))

    ⚠️ 必须同时兼容 FastAPI 的两种注册形态：
    - 旧版（≤0.13x）：include_router 立即把端点展开进 app.routes
    - 新版（≥0.14x）：include_router 只放一个 _IncludedRouter 占位，端点惰性展开，
      此时 route.path 为 None，需从 route.include_context.dependencies 取 router 级依赖
    """
    import inspect

    # 路由级
    for dep in getattr(route, 'dependencies', []) or []:
        if _dep_requires_auth(dep):
            return True

    # include_router 上下文里的 router 级依赖（新版 FastAPI 的 _IncludedRouter）
    ctx = getattr(route, 'include_context', None)
    if ctx is not None:
        for dep in getattr(ctx, 'dependencies', []) or []:
            if _dep_requires_auth(dep):
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
                if _dep_requires_auth(param.default):
                    return True

    # 兜底：递归 route.dependant（某些版本把 router 级依赖放在这里）
    dependant = getattr(route, 'dependant', None)
    if dependant is not None:
        stack = [dependant]
        seen = 0
        while stack and seen < 200:
            cur = stack.pop()
            seen += 1
            if _dep_requires_auth(cur):
                return True
            for sub in getattr(cur, 'dependencies', []) or []:
                stack.append(sub)
    return False


def _iter_api_endpoints(app):
    """版本无关地枚举 (method, path, route) 三元组。

    FastAPI 0.14x 起 include_router 惰性注册（app.routes 里只有 _IncludedRouter
    占位，path=None）。为确保任何版本下都能真实枚举到端点，这里按优先级尝试：

    1. `routers.all_routers` —— 我们自己的聚合模块，每个 APIRouter 的 .routes
       始终是完整的 APIRoute 列表，完全不受 FastAPI 版本影响。**首选**。
    2. app.routes 递归展开 —— 兼容惰性注册形态（读 include_context，
       以及 _EffectiveRouteContext 的 path/endpoint）。
    3. app.openapi()['paths'] —— 最后的公开接口兜底。
    """
    seen = set()

    # --- 1. 直接遍历我们自己的 router 聚合（最稳）---
    try:
        from routers import all_routers
    except Exception:  # noqa: BLE001
        all_routers = []
    for router in all_routers:
        prefix = getattr(router, 'prefix', '') or ''
        for route in getattr(router, 'routes', []) or []:
            sub = getattr(route, 'path', '') or ''
            # 子路由的 path 在不同 FastAPI 版本下可能已含 / 不含 router prefix，
            # 这里做幂等拼接：已含前缀就原样用。
            path = sub if (prefix and sub.startswith(prefix)) else (
                (prefix + sub).replace('//', '/') or sub)
            for m in (getattr(route, 'methods', None) or set()):
                if m in ('HEAD', 'OPTIONS'):
                    continue
                key = (m, path)
                if key not in seen:
                    seen.add(key)
                    yield (m, path, route)
    if seen:
        return

    # --- 2. app.routes 递归展开（兼容惰性注册）---
    def _walk(routes, prefix=''):
        for r in routes:
            ctx = getattr(r, 'include_context', None)
            sub_prefix = getattr(ctx, 'prefix', '') if ctx is not None else ''
            full_prefix = (prefix + sub_prefix).replace('//', '/')
            inner = getattr(r, 'original_router', None)
            if inner is not None:
                yield from _walk(getattr(inner, 'routes', []) or [], full_prefix)
                continue
            # _EffectiveRouteContext：带 path / endpoint / methods
            sub = getattr(r, 'path', None)
            if sub is None:
                continue
            path = (full_prefix + sub).replace('//', '/')
            for m in (getattr(r, 'methods', None) or set()):
                if m in ('HEAD', 'OPTIONS'):
                    continue
                key = (m, path)
                if key not in seen:
                    seen.add(key)
                    yield (m, path, r)

    yield from _walk(getattr(getattr(app, 'router', app), 'routes', []) or [])

    # --- 3. openapi 兜底 ---
    if not seen:
        try:
            spec = app.openapi()
        except Exception:  # noqa: BLE001
            return
        for path, ops in (spec.get('paths') or {}).items():
            for m in (ops or {}):
                mm = m.upper()
                if mm in ('HEAD', 'OPTIONS', 'PARAMETERS'):
                    continue
                key = (mm, path)
                if key not in seen:
                    seen.add(key)
                    yield (mm, path, None)


def _collect_protected(app):
    """收集 app 上所有需要鉴权的 (method, path)。"""
    out = []
    for m, path, route in _iter_api_endpoints(app):
        if not path.startswith('/api/'):
            continue
        if route is not None and _route_requires_auth(route):
            out.append((m, path))
            continue
        # 新版惰性注册下端点对象与归属 router 分离，用路径前缀回退匹配
        if route is None and _prefix_is_guarded(path):
            out.append((m, path))
    return out


_GUARDED_PREFIXES = None


def _prefix_is_guarded(path: str) -> bool:
    """路径前缀回退：该端点在业务 router 下即视为受保护。

    仅用于 openapi 兜底（拿不到 route 对象）时的保守判断。
    """
    global _GUARDED_PREFIXES
    if _GUARDED_PREFIXES is None:
        try:
            from routers import all_routers
            _GUARDED_PREFIXES = [
                (getattr(r, 'prefix', '') or '', bool(getattr(r, 'dependencies', None)))
                for r in all_routers
            ]
        except Exception:  # noqa: BLE001
            _GUARDED_PREFIXES = []
    for prefix, guarded in _GUARDED_PREFIXES:
        if prefix and guarded and path.startswith(prefix):
            return True
    return False


def test_all_api_routes_guarded(app_module):
    """结构性断言：/api/ 下的每个端点要么挂了鉴权，要么在 PUBLIC_ROUTES 白名单里。

    这条用例是「防新增」的关键 —— 新加一个路由模块忘记挂 dependencies 会直接失败，
    不必等有人真的去未授权访问。

    ⚠️ 必须用 _iter_api_endpoints 而非直接遍历 app.routes：FastAPI 0.14x 起
    include_router 惰性注册，app.routes 里只有占位对象，直连遍历会「一个端点都
    没看到」从而假绿（2026-09-10 CI 上实测）。
    """
    app = app_module.app
    unguarded = []
    total = 0
    for m, path, route in _iter_api_endpoints(app):
        if not path.startswith('/api/'):
            continue
        total += 1
        if route is not None and _route_requires_auth(route):
            continue
        if (m, path) in PUBLIC_ROUTES:
            continue
        unguarded.append(f'{m} {path}')

    assert total >= 30, (
        f'仅枚举到 {total} 个 /api/ 端点，路由枚举逻辑可能已失效（期望 ≥30）。'
        '请检查 _iter_api_endpoints 是否兼容当前 FastAPI 版本。')
    assert not unguarded, (
        '以下 API 端点既未挂鉴权，也不在 PUBLIC_ROUTES 白名单中：\n  ' +
        '\n  '.join(sorted(set(unguarded))) +
        '\n如是刻意公开，请登记到 PUBLIC_ROUTES 并说明理由。')


def test_protected_endpoint_count(app_module):
    """守卫：受保护端点数量不应因重构意外减少（当前 34 个 + 函数级鉴权的 3 个）。"""
    protected = _collect_protected(app_module.app)
    assert len(protected) >= 30, (
        f'受保护端点仅 {len(protected)} 个，疑似鉴权大面积脱落（期望 ≥30）')
