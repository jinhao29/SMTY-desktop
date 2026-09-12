# 版本号与发版流程规范

> 2026-09-12 摸底定稿。两端均为「**发版时人工 bump，日常功能提交不动版本**」。
> 功能提交信息里出现的 v1.0.x 是**特性标签**（如"v1.0.5 数据库加密"），不代表已发版；
> 已发版本以 git tag 与版本文件为准。

## Android（jinhao29/SMTY）

### 版本规则

- **单一真源**：`android_app/version_code.txt`，内容 `MAJOR.MINOR.PATCH`（无 v 前缀）
- `versionCode = MAJOR*10000 + MINOR*100 + PATCH`（`app/build.gradle.kts:24-32` 计算；
  App 端 `extractRemoteVersionCode` 同公式解析远端版本，两端必须同规）
- `versionName = MAJOR.MINOR.PATCH`
- 当前值：`1.0.2`（= 最后一次 release `a9dfbe5 release: v1.0.2 (新签名密钥库)`）

### 发版步骤（人工，缺一不可）

1. 修改 `version_code.txt`（如 `1.0.2` → `1.0.6`）并提交
2. 打**同名 tag**：`git tag v1.0.6 && git push origin v1.0.6`
3. CI（`.github/workflows/build-apk.yml`）在 tag 推送时：
   - 校验 tag 与 version_code.txt **完全一致**，不一致直接报错拒发（防呆）
   - 注入 VERSION_NAME / VERSION_CODE，用 `KEYSTORE_BASE64` 等 4 个 Secrets 做 release 签名
   - 发布到 GitHub Release
4. 本地验证发版包：覆盖安装到真机（同签名），启动后「设置-关于」核对版本号

### 注意

- 日常构建（无 tag）版本号同样来自 version_code.txt，但**不会**发布
- debug 签名 fallback 仅限无 Secrets 环境；正式发版必须走 CI Secrets
- 未发版的功能累积越多，下次 bump 的 PATCH/MINI 级别自行判断（当前积压：
  SQLCipher 加密、HMAC 配对、小程序互通、重放窗口等，建议直接 1.0.6 或 1.1.0）

## 桌面端（jinhao29/SMTY-desktop）

### 版本规则

- **单一真源**：`student_sports_tool/VERSION`，内容 `vMAJOR.MINOR.PATCH`（**有** v 前缀，
  与 Android 相反，勿混淆）
- 当前值：`v1.0.0`（`3146f7a 桌面端发版链路` 建立真源后的首个版本）
- 历史混乱值（如 v62）已废弃；`make_release.py` 对格式非法直接 fail，测试锁定该行为

### 发版步骤

1. 修改 `student_sports_tool/VERSION` 并提交（make_release 会校验并提示 git add）
2. `python make_release.py`：PyInstaller 打包 → `student_sports_tool/release/shangmen-tool-vX.Y.Z.zip`
   + sha256 侧车 → 按脚本输出的 `gh release create` 命令发布
3. 打包强制包含 `legal/`（test_legal_docs.py 锁定），缺文件直接失败

## 两端是否对齐？

**不强制对齐，但建议同节奏发版时保持相同版本号**（方便售后对账：用户报的版本号两端一致）。
两端独立发版完全允许——Android 走 tag+CI，桌面端走 make_release.py 脚本。

## 发版前检查清单

- [ ] Android：version_code.txt 已 bump 且与 tag 一致
- [ ] Android：真机覆盖安装验证（同签名）
- [ ] 桌面端：VERSION 已 bump（v 前缀格式）
- [ ] 桌面端：`python -m pytest` 全绿
- [ ] 两端：合规文本 legal/ 无【待填】占位（test_legal_docs 占位检查 + 人工确认）
- [ ] 桌面端：打包产物含 legal/ 与 VERSION
