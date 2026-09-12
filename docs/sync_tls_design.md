# 双端同步通道 TLS 设计方案（遗留项 #4 收口）

> 状态：**设计定稿，未实现**。真机验证窗口开放后按本方案实施。
> 背景：HMAC 心跳（v1.0.6）已防上传目标劫持，token 已防未授权上传；
> TLS 的剩余收益是**防内网被动窃听**（学员姓名/电话/体测数据明文过网）。

## 1. 威胁模型与收益判定

| 威胁 | 现有防线 | TLS 增量 |
|---|---|---|
| 伪造心跳劫持上传目标 | HMAC-SHA256（配对后） | 无增量 |
| 未授权设备上传/拉取 | X-Sync-Token 鉴权 | 无增量 |
| 同网段被动抓包（隐私泄露） | 无 | **全部载荷加密** |
| 主动 MITM | 无 | TOFU 下首次连接仍可被劫持（部分增量） |

结论：内网可信度高的家庭/办公场景收益有限；公共 Wi-Fi 教学场景收益明确。

## 2. 总体设计

```
[Android HttpURLConnection] --TLS(自签证书, TOFU指纹)--> [PC ThreadingHTTPServer(ssl wrap)]
```

- **传输**：TLS 1.2+，仅 PC 端持证书（手机不校验客户端证书）
- **证书**：PC 首次开启 HTTPS 时用 `cryptography` 库生成自签证书
  （RSA 2048 / ECDSA P-256，SAN 含本机 IP 与主机名，有效期 10 年），
  存 `<档案目录>/.sync/tls_cert.pem + tls_key.pem`（.gitignore 已覆盖 .sync_backups，需补 .sync/）
- **端口**：复用 8765，同一端口按配置切换 HTTP/HTTPS（不允许同时监听两端口——避免防火墙二次放行）
- **配置**：`_data_center_config.json` 新增 `sync_https: bool`（默认 false）；
  同步面板加开关，切换后自动重启服务（复用配对码变更的重启路径）

## 3. PC 端改动（student_sports_tool）

- `data_center/tls_cert.py`（新增，数据层）：
  - `ensure_cert(archive_dir) -> (cert_path, key_path)`：不存在则生成，存在则复用
  - 证书指纹计算（SHA-256，Base64，供手机端 TOFU）
- `data_center/sync_server.py`：`create_server(..., tls_context=None)`；
  非 None 时 `socket = context.wrap_socket(socket, server_side=True)`
- `data_center/sync_service.py`：start() 读 `sync_https` 配置，构造 ssl.SSLContext
- `data_center/sync_panel.py`：HTTPS 开关 + 指纹展示（供人工核对）
- 心跳报文**不新增字段**：手机端探测到 8765 是 TLS（握手失败回退）而非改协议，见 §4

## 4. Android 端改动

- `data/internal/SyncTlsTrust.kt`（新增）：
  - TOFU：首次 TLS 连接成功后存证书 SHA-256 指纹到 DataStore（`sync_tls_fingerprint`）
  - 后续连接：指纹一致放行；不一致（证书更换/中间人）拒绝并在 UI 提示重新信任
  - hostname 校验关闭（自签证书无可信 CA），**以指纹校验替代**——这是自签方案的安全边界
- `LanSyncManager` / `MomentUploader` / `PcSyncRepository`：
  HttpURLConnection 注入自定义 SSLSocketFactory（TrustManager 只比对固定指纹）
- HTTP→HTTPS 探测：连接失败（SSLException）时按配置回退明文重试一次并记警告，
  避免单边开开关后完全断联；两端都开后自动走 HTTPS
- 设置页「桌面同步」加 HTTPS 状态展示（信任指纹前 8 位）

## 5. 兼容与回退

| 组合 | 行为 |
|---|---|
| PC HTTP + 手机旧版 | 现状不变 |
| PC HTTPS + 手机旧版 | 旧版连不上（提示升级），心跳发现不受影响 |
| PC HTTPS + 手机新版（未信任） | TOFU 首连建立信任 |
| 任一端关 HTTPS | 探测回退明文 + 警告日志 |

## 6. 测试与验收

- PC：pytest——证书生成/复用、HTTPS server 启停、`urllib` 带 ssl 上下文访问 /health
- Android：Robolectric 测 TOFU 指纹存取与不匹配拒绝（SSLSocketFactory 本体真机验证）
- 真机（必测）：HTTPS 开关切换、TOFU 首连、指纹不匹配拒绝、明文回退

## 7. 工作量与风险

- 预估：PC ~180 行 + Android ~150 行 + 测试
- 风险：TOFU 首连窗口；证书文件权限（建议仅当前用户可读）；
  HttpURLConnection 对自签证书的 SNI/握手差异需真机确认（小米/Vivo ROM 差异史）
