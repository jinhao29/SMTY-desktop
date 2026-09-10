# -*- coding: utf-8 -*-
"""上门体育/俱乐部管理小程序后端。

启动：
    export MP_SECRET="<32位随机串>"   # 必填，缺失拒绝启动
    export MP_ADMIN_PHONE="<管理员手机号>"  # 选填，首次启动播种管理员
    export MP_ADMIN_PASSWORD="<管理员初始密码>"  # 选填，须自行设定
    uvicorn main:app --host 127.0.0.1 --port 8800

环境变量：
    MP_MODE   shangmen(上门) | club(俱乐部)，默认 shangmen
    MP_SECRET token 签名密钥（必填，≥16 字符）
    MP_ADMIN_PHONE / MP_ADMIN_PASSWORD  首次播种的管理员账号（不设则不建任何账号）
    MP_CORS_ORIGINS  逗号分隔的 CORS 白名单，默认仅本地 5173
    MP_HOST   监听地址，默认 127.0.0.1
    MP_PORT   监听端口，默认 8800
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import init_db, _mode_ctx, DEFAULT_MODE, VALID_MODES
from routers import all_routers


def _cors_origins():
    """CORS 白名单：默认仅放行本地调试地址，生产按 MP_CORS_ORIGINS 逗号分隔配置。

    小程序请求本身无 CORS 概念，此处只服务于本地 H5 调试；
    绝不放行 '*'，否则任意站点可携带用户凭据调用 API。
    """
    raw = os.environ.get('MP_CORS_ORIGINS', '')
    origins = [o.strip() for o in raw.split(',') if o.strip()]
    return origins or ['http://localhost:5173', 'http://127.0.0.1:5173']


def _bind_host():
    """默认只监听回环；需要局域网访问时显式设 MP_HOST=0.0.0.0。"""
    return os.environ.get('MP_HOST', '127.0.0.1')

app = FastAPI(title='上门体育/俱乐部管理 API', version='1.0.0')


class ModeContextMiddleware:
    """从 X-MP-Mode header 注入请求级数据空间（纯 ASGI，避免 BaseHTTPMiddleware 的 contextvar 隔离坑）。

    每请求无条件 set（无 header 落 DEFAULT_MODE）——否则 init_db 等启动代码
    在线程 context 里 set 过的值会泄漏进后续请求。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            mode = None
            for k, v in scope['headers']:
                if k.decode().lower() == 'x-mp-mode':
                    mode = v.decode()
                    break
            _mode_ctx.set(mode if mode in VALID_MODES else DEFAULT_MODE)
        await self.app(scope, receive, send)


app.add_middleware(ModeContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=['*'],
    allow_headers=['*'],
)

for r in all_routers:
    app.include_router(r)


@app.on_event('startup')
def _startup():
    init_db()


@app.get('/api/v1/health')
def health():
    from database import current_mode
    return {'ok': True, 'service': 'miniprogram-api', 'mode': current_mode()}


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={'detail': f'服务器内部错误: {exc}'})


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=_bind_host(), port=int(os.environ.get('MP_PORT', '8800')))
