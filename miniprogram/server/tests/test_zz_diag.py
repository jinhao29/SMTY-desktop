# -*- coding: utf-8 -*-
"""临时诊断：定位 CI 上 _collect_protected 返回 0 的原因。用完即删。"""
import sys


def test_diag(app_module):
    app = app_module.app
    from test_auth_guard import _route_requires_auth

    total = 0
    api = 0
    dur = 0
    dep_empty = 0
    samples = []
    for route in app.routes:
        total += 1
        path = getattr(route, 'path', '')
        if not path.startswith('/api/'):
            continue
        api += 1
        if _route_requires_auth(route):
            dur += 1
        deps = getattr(route, 'dependencies', None)
        if not deps:
            dep_empty += 1
        if len(samples) < 6:
            samples.append(
                f'{path} methods={getattr(route, "methods", None)} '
                f'deps={deps} type={type(route).__name__}')

    print('\n=== DIAG ===')
    print('python:', sys.version.split()[0], sys.platform)
    print('main module file:', getattr(app_module, '__file__', None))
    print('app id:', id(app))
    print('total routes:', total, 'api routes:', api)
    print('_route_requires_auth True:', dur)
    print('routes with empty dependencies:', dep_empty)
    print('main.app.routes is app.routes:', app_module.app.routes is app.routes)
    for s in samples:
        print('  ', s)
    print('app routes sample:', [getattr(r, 'path', '') for r in app.routes[:8]])
    print('=== END DIAG ===\n')
