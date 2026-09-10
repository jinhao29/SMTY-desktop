# -*- coding: utf-8 -*-
"""临时诊断 2：为什么 CI 上业务路由没注册进 app。用完即删。"""
import sys


def test_diag2(app_module):
    import main
    from routers import all_routers

    print('\n=== DIAG2 ===')
    print('sys.path[:4]:', sys.path[:4])
    print('routers count:', len(all_routers))
    for r in all_routers:
        print(f'  router prefix={getattr(r, "prefix", None)!r} '
              f'routes={len(getattr(r, "routes", []) or [])} '
              f'type={type(r).__name__} '
              f'module={type(r).__module__}')

    app = main.app
    print('app.routes len:', len(app.routes))
    for r in app.routes:
        print(f'  app route path={getattr(r, "path", None)!r} '
              f'type={type(r).__name__} module={type(r).__module__}')
    print('=== END DIAG2 ===\n')
