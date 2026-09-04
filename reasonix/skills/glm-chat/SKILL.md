# GLM-4.6v-Flash 聊天 Skill

基于智谱 GLM-4.6v-Flash 模型的对话和识图能力。

## 能力

- ✅ 文本对话
- ✅ 图片识别（OCR、商品识别、文档分析等）
- ✅ 视频/文件理解
- ✅ 思考模式（开启/关闭）
- ✅ 流式输出

## 使用方式

### 方法一：直接调用 Skill

```
glm-chat --messages '[{"role": "user", "content": "你好"}]'
```

### 方法二：识图

```
glm-chat --messages '[{"role": "user", "content": "这是什么图片？", "image_url": "https://example.com/image.jpg"}]'
```

或：

```
glm-chat --messages '[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "image.jpg"}}, {"type": "text", "text": "请描述这张图片"}]}]'
```

### 方法三：多模态理解

```
glm-chat --messages '[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "photo.jpg"}}, {"type": "text", "text": "识别图片中的物体"}]}]'
```

## 参数

- `messages`（必需）：对话消息数组
  - `role`：角色（`user`/`assistant`/`system`）
  - `content`：消息内容（字符串或数组）
    - 文本：`{"type": "text", "text": "内容"}`
    - 图片：`{"type": "image_url", "image_url": {"url": "图片路径或URL"}}`
    - 视频：`{"type": "video_url", "video_url": {"url": "视频URL"}}`
    - 文件：`{"type": "file_url", "file_url": {"url": "文件URL"}}`
- `stream`（可选）：是否流式输出（默认 `false`）
- `thinking`（可选）：思考模式，如 `{ type: "enabled" }`
- `model`（可选）：模型名称，默认 `glm-4.6v-flash`

## 示例

### 简单对话

```
glm-chat --messages '[{"role": "user", "content": "介绍一下你自己"}]'
```

### 开启思考模式

```
glm-chat --messages '[{"role": "user", "content": "解释一下量子纠缠"}]' --thinking '{"type": "enabled"}'
```

### 图片识别

```
glm-chat --messages '[{"role": "user", "content": "这是什么图片？", "image_url": "photo.jpg"}]'
```

### 多轮对话

```
glm-chat --messages '[{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！有什么我可以帮助你的吗？"}, {"role": "user", "content": "我想了解 GLM-4.6v-Flash"}]'
```

### 文档分析

```
glm-chat --messages '[{"role": "user", "content": "分析这张图片中的文档，提取关键信息", "image_url": "contract.jpg"}]'
```

### 商品识别

```
glm-chat --messages '[{"role": "user", "content": "识别图片中的商品，包括名称、价格、描述", "image_url": "product.jpg"}]'
```

## 配置

### 设置 API Key

```bash
# Windows PowerShell
$env:ZHIPU_API_KEY="your_api_key_here"

# Windows CMD
set ZHIPU_API_KEY=your_api_key_here

# Linux/Mac
export ZHIPU_API_KEY=your_api_key_here
```

### 永久设置（推荐）

1. 右键"此电脑" → "属性"
2. "高级系统设置" → "环境变量"
3. "用户变量" → "新建"
4. 变量名：`ZHIPU_API_KEY`
5. 变量值：你的 API Key

## MCP 工具

此 Skill 调用 MCP 服务器提供的工具：
- `chat`：文本对话
- `vision`：多模态理解（图片/视频/文件）

## 注意事项

- 免费额度有限，请合理使用
- API Key 请妥善保管，不要泄露
- 需要联网才能使用
- 支持长上下文（128K tokens）

## 更多文档

- [智谱AI文档](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.6v-flash)
- [GLM-GUIDE.md](../GLM-GUIDE.md)
- [IMAGE-RECOGNIZE.md](../IMAGE-RECOGNIZE.md)
