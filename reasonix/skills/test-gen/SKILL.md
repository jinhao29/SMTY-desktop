# Test Gen 测试生成 Skill

基于智谱 GLM 的单元测试生成能力。为给定代码生成 pytest（Python）或 JUnit（Java/Kotlin）测试。

## 能力

- ✅ 根据函数签名与逻辑生成单元测试
- ✅ 覆盖边界条件与异常路径
- ✅ 输出 pytest / JUnit 格式，可直接运行

## 使用方式

```
test-gen --messages '[{"role": "user", "content": "为以下 Python 函数生成 pytest 测试：\n<粘贴函数>"}]'
```

## 最佳实践

- 明确目标测试框架（pytest / JUnit）与语言
- 附上函数完整签名与关键分支，测试覆盖更完整
