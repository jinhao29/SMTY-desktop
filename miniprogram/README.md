# 上门体育 · 微信小程序（上门体育 / 俱乐部管理）

Uni-app (Vue 3) + Python FastAPI。与桌面端（PySide6）/ Android 端共用业务口径，数据模型与 Android Room 实体对齐。

## 目录结构

```
miniprogram/            # uni-app 小程序前端（本目录）
├── pages/              # 17 个页面（launch/login/home/student/coach/schedule/checkin/package/settings）
├── components/         # week-grid / stat-card / student-card / coach-card / lesson-card
├── api/                # 接口封装（统一出口 api/index.js）
├── stores/             # Pinia：mode（上门/俱乐部切换）、user
├── utils/              # request / date / validator / constants
└── server/             # Python FastAPI 后端
    ├── main.py         # 入口（uvicorn main:app --port 8800）
    ├── database.py     # SQLite 数据层（server_data/miniprogram.db）
    ├── passlib_lite.py # pbkdf2 密码哈希 + HMAC token（零依赖）
    ├── deps.py         # Authorization token 校验
    └── routers/        # auth / students / coaches / lessons / checkins / packages / backup
```

## 启动后端

```bash
cd server
uvicorn main:app --host 0.0.0.0 --port 8800
# 或：python main.py
```

- 默认账号：`13800000000 / 123456`
- 环境变量：`MP_MODE=shangmen|club`（默认 shangmen）、`MP_SECRET`（token 密钥）
- 依赖：`pip install fastapi "uvicorn[standard]" httpx`

## 编译前端

```bash
npm install
npm run dev:mp-weixin     # 开发 → dist/dev/mp-weixin，用微信开发者工具导入
npm run build:mp-weixin   # 生产
```

微信开发者工具导入 `dist/dev/mp-weixin`，关闭「URL 校验」（开发期后端为 http://127.0.0.1:8800）。
**真机调试需将 `utils/request.js` 的 BASE_URL 改为局域网 IP（手机与服务器同网段）或上线 HTTPS 域名。**

## API 一览（/api/v1）

| 模块 | 端点 |
|---|---|
| 认证 | POST /auth/login · POST /auth/logout · GET /auth/me |
| 学员 | GET/POST /students · GET/PUT/DELETE /students/:id · GET /students/:id/lessons · GET /students/:id/checkins |
| 教练 | GET/POST /coaches · GET/PUT/DELETE /coaches/:id · GET /coaches/:id/schedule · GET /coaches/:id/payout |
| 排课 | GET /lessons · GET /lessons/today · GET /lessons/week · GET/POST /lessons · PUT/DELETE /lessons/:id |
| 签到 | POST /checkin/:lessonId（批量） · POST /checkout/:lessonId（批量） · GET /checkins · GET /checkins/pending · GET /checkins/today |
| 课时包 | GET/POST /packages · GET/PUT/DELETE /packages/:id · GET /packages/stats |
| 备份 | GET /backup/export · POST /backup/import（LWW 合并 + 模式校验，不匹配返回 409） |

## 业务口径（与桌面端一致）

- 学员剩余课时 = 有效课时包 remaining 之和；签到自动扣课时（最早到期的包优先，扣完标记 exhausted）
- 费用：单价 = 价格 ÷ 总课时；应收 = Σ 总课时×单价；实收 = paid_amount（-1 视同付清）；待收 = 应收 − 实收
- 备份 JSON 顶层含 `mode`（shangmen/club）+ `export_version` + 五张业务表；导入时模式不匹配拒绝
- 已签到未签退清单：`/checkins/pending`（小程序「签到」页顶部提醒，可一键补签退）
