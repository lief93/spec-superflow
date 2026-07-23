# 实现任务

## 接口

### Batch N → Batch M
- **Produces**: `type/function name` — 被 Batch M 用于什么目的

## Batch 1: [批次目标]

Depends on: None

### AC: [Spec 中完全一致的 Scenario 标题]

- **Requirement**: [Spec 中完全一致的 Requirement 标题]
- **User-visible**: `Yes` | `No`

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

只保留能证明当前 AC 的测试层，不要求每层都写；同一行为放在最低成本且稳定的层验证，避免重复覆盖。多行合起来必须覆盖 Scenario 中每个可观察的 WHEN/THEN/AND：内部状态、调用、持久化、顺序和并发由 Unit/Component/Integration 证明，可见状态和用户交互由 UI 证明。`Proves` 写明精确结果，不能只写“覆盖当前 AC”。UI 行必须通过已渲染控件执行用户动作；直接调用 ViewModel、callback、repository 或 reducer 只能用于准备条件或模拟系统/生命周期事件，不能替代用户 WHEN。每一行只对应一个平台测试源码文件和一个具体测试方法/标题。不得使用 Markdown、普通业务源码、命令、目录、通配符或“相关回归集合”作为 Test File。

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| `Unit` / `Component` / `Integration` / `UI` | `Android` / `HarmonyOS` / `iOS` / `Web` / 实际平台 | `Add` / `Update` / `Run existing` / `Unavailable` | 项目相对路径下的平台测试源码；`Unavailable` 时为 `Not configured` | 精确测试方法/标题；`Unavailable` 时记录查找位置和能力缺口 | 测试断言能够证明的当前 AC 可观察结果 |

#### TDD Steps

- [ ] **1.1 RED / Baseline：编写或更新计划中的测试并确认真实起点**

```language
// 带精确断言的测试代码
```

**Files**: `Create/Modify: exact/path`

Run: `exact command`
Expected: 新增或变更行为时，因该行为尚未实现而得到真实的 behavior-specific FAIL；仅为已有行为补充或加强测试时，记录 baseline PASS，不得使用 sentinel 或故意失败制造 RED

- [ ] **1.2 GREEN / Preserve：实现使当前测试通过的最小代码；仅补测试时保持生产行为不变**

```language
// 实现代码
```

**Files**: `Create/Modify: exact/path`
**Interfaces**: Produces `name(type): returnType` — 被 Batch N 消费

- [ ] **1.3 对其余 `Add` / `Update` 测试重复真实 RED → GREEN，或记录已有行为的 baseline PASS**

Run: `exact command per planned test`
Expected: new or changed behavior fails before implementation and then passes; existing behavior coverage passes without an artificial failure

- [ ] **1.4 REFACTOR：运行当前 AC 的全部计划测试和相关回归**

Run: `exact command`
Expected: PASS

- [ ] **1.5 提交**

```bash
git add files
git commit -m "feat: description"
```
