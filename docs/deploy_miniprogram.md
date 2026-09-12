# 小程序后端部署指南

适用：miniprogram/server（FastAPI），为小程序「连接服务器模式」提供 API。

> 纯本地模式（数据存学员手机）**不需要**部署后端；只有需要多端共享数据的机构才要部署。

## 1. 环境要求

- Python 3.10+（Linux 服务器 / 内网 Windows 主机均可）
- 微信小程序已注册并取得正式 AppId（个人主体即可，无需认证）
- 对外服务域名必须 HTTPS 且 ICP 备案（微信要求；内网体验可跳过，见 §5）

## 2. 安装

```bash
cd miniprogram/server
pip install -r requirements.txt   # 或按 README 的依赖清单
```

## 3. 配置（MP_SECRET 注入）

`MP_SECRET` 是服务端会话签名密钥，**必须注入，严禁写进代码或提交入库**：

```bash
# Linux
export MP_SECRET="$(python -c 'import secrets;print(secrets.token_hex(32))')"

# Windows PowerShell
$env:MP_SECRET = [convert]::ToBase64String((1..32 | % { Get-Random -Maximum 256 }))
```

启动（默认 127.0.0.1:8800，公网部署绑定 0.0.0.0 并置于反向代理后）：

```bash
uvicorn main:app --host 127.0.0.1 --port 8800
```

注意：`run_server.cmd` 等本地启动脚本可能含明文 MP_SECRET，仅本机使用，**严禁提交/分发**
（已在 .gitignore 排除 `_mp_verify/`）。

## 4. 数据目录

服务端数据写在 `miniprogram/server/server_data/`（已在 .gitignore 排除）。
备份：停服后整目录打包即可。

## 5. 体验版快速发布（免备案）

纯本地模式体验：AppId 替换 + 构建 + 上传，**无需服务器**。
完整步骤见 [小程序发布清单](miniprogram_release_checklist.md)。

## 6. 与双端的数据关系

- 小程序「导出备份 JSON」可在桌面端备份面板导入（阶段五互通）；
- 桌面端「导出小程序数据(JSON)」可发回小程序「导入备份」；
- 服务器模式与本地模式数据独立，切换前请先导出备份。
