# 实现任务

## 文件结构

- `Create: path/to/new-file.ts` — 一句话说明职责
- `Modify: path/to/existing.ts` — 改什么、为什么

## 接口

### Batch N → Batch M
- **Produces**: `type/function name` — 被 Batch M 用于什么目的

## 1. Batch 1: [批次目标]

- [ ] **1.1 编写失败的测试**

```language
// 带精确断言的测试代码
```

**文件（Files）**：`Create/Modify: 精确路径`

- [ ] **1.2 运行测试并确认失败**

运行：`精确命令`
预期：以“具体错误信息”失败

- [ ] **1.3 实现最小化代码**

```language
// 实现代码
```

**文件（Files）**：`Create/Modify: 精确路径`
**接口（Interfaces）**：Produces `name(type): returnType` — 被 Batch N 使用

- [ ] **1.4 运行测试并确认通过**

运行：`精确命令`
预期：通过

- [ ] **1.5 提交**

```bash
git add files
git commit -m "feat: description"
```
