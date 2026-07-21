# 实现任务

## 接口

### Batch N → Batch M
- **Produces**: `type/function name` — 被 Batch M 用于什么目的

## Batch 1: [批次目标]

Depends on: None

### AC: [Spec 中完全一致的 Scenario 标题]

- **Requirement**: [Spec 中完全一致的 Requirement 标题]

#### File Changes

不要使用行号。每个文件只说明它为当前 AC 承担的具体变化；已确定时写出现有或新增的方法名，但不要把每个方法拆成独立 Task。同一文件服务多个 AC 时，在各 AC 下分别说明对应变化。

##### Modify `path/to/existing-file.ts`

- **Current responsibility**: 当前职责
- **Change**: 修改什么行为以及修改后的结果
- **Add**: 新增什么方法、字段或类型及其职责；没有则删除本项
- **Reuse**: 复用的现有组件、方法或模式；没有则填写 `None`

##### Create `path/to/new-file.ts`

- **Responsibility**: 新文件的单一职责
- **Add**: 新增的主要方法、字段或类型及其职责
- **Used by**: 哪些现有文件或 Batch 使用它

#### TDD Test Plan

只保留能证明当前 AC 的测试层，不要求每层都写；同一行为放在最低成本且稳定的层验证，避免重复覆盖。

| Layer | Action | Target | Proves |
|---|---|---|---|
| `Unit` / `Component` / `Integration` / `UI` | `Add` / `Update` / `Run existing` / `Unavailable` / `Not applicable` | 精确测试文件、用例或相关回归集合 | 对应的行为、边界或回归风险 |

#### TDD Steps

- [ ] **1.1 RED：编写或更新计划中的测试并确认失败**

```language
// 带精确断言的测试代码
```

**Files**: `Create/Modify: exact/path`

Run: `exact command`
Expected: FAIL with the behavior-specific assertion because production behavior is absent

- [ ] **1.2 GREEN：实现使当前测试通过的最小代码**

```language
// 实现代码
```

**Files**: `Create/Modify: exact/path`
**Interfaces**: Produces `name(type): returnType` — 被 Batch N 消费

- [ ] **1.3 对其余 `Add` / `Update` 测试重复 RED → GREEN**

Run: `exact command per planned test`
Expected: each new or changed test fails before its behavior exists, then passes

- [ ] **1.4 REFACTOR：运行当前 AC 的全部计划测试和相关回归**

Run: `exact command`
Expected: PASS

- [ ] **1.5 提交**

```bash
git add files
git commit -m "feat: description"
```
