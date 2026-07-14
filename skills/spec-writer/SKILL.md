---
name: spec-writer
description: 创建或完善 spec-superflow 规划工件。当变更已经明确，可以编写 proposal.md、specs/、design.md 和 tasks.md 时使用。
---

# 规格工件编写

需求探索稳定后，按顺序创建可验证、可执行的规划工件。

## 必需输入

读取 `.spec-superflow.yaml`，重点检查 `dp_0_decisions` 和 `dp_0_confirmed`，并读取已有规划工件。若 `dp_0_confirmed` 不为 `true`，停止并返回 `workflow-start` 执行 DP-0。

## 配置检查

运行以下命令：

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/get-config" artifacts.order
bash "${CLAUDE_PLUGIN_ROOT}/scripts/get-config" artifacts.skip
bash "${CLAUDE_PLUGIN_ROOT}/scripts/get-config" execution.defaultLanguage
```

按 `artifacts.order` 顺序生成，跳过 `artifacts.skip` 中的工件。语言规则适用于所有首次生成和重新生成的规划工件：

- `zh`：所有面向人的标题、正文、需求名称、场景、表格和摘要使用中文。
- `en`：所有面向人的内容使用英文。
- `auto`：跟随用户请求和 `dp_0_decisions` 的主要语言，不得根据英文模板或 Schema 示例推断语言。

机器可读关键词保持不变。中文工件在校验要求英文关键词的位置使用双语标题，例如 `## 变更原因（Why）`、`## 变更内容（What Changes）`、`### Requirement: 中文需求名称`、`#### Scenario: 中文场景名称`。需求正文和场景步骤使用中文，但保留 `SHALL`/`MUST` 和 `WHEN`/`THEN`。

## 工件职责

- `proposal.md`：说明为什么变更、范围和影响。
- `specs/`：定义可测试的必要行为。
- `design.md`：记录架构决策和权衡，不写逐行实现。
- `tasks.md`：给出有依赖关系、可执行的实现步骤。

## 编写规则

必须遵守 DP-0 中确认的范围和约束，不得静默扩大范围；遇到未确认决策时暂停。

### proposal.md

必须包含问题、变更内容、涉及能力、范围和影响区域。

### specs/

每条需求必须可测试，使用 SHALL 或 MUST；每条需求至少有一个包含 WHEN/THEN 的 `#### Scenario:`；按 `ADDED/MODIFIED/REMOVED Requirements` 分类。

### design.md

必须包含 `Context`、`Goals`、`Decisions`、`Risks And Trade-Offs`。每项决策写清选择、理由和考虑过的替代方案。

### tasks.md

必须包含：

- **File Structure**：列出所有 Create/Modify 文件及单句职责。
- **Interfaces**：写明跨批次 Consumes/Produces 和精确类型。
- **每项任务**：精确文件路径、完整的 5 步 TDD 阶段、Interfaces 区块。
- **粒度**：每步约 2–5 分钟且保持原子性。
- **无占位符**：不得出现 TBD、TODO、`figure out`、`add appropriate`。
- **依赖顺序**：只能依赖之前批次，并明确写 `Depends on: Batch N`。

## 生成顺序与确认

一次只生成一个工件，确认后再继续，避免上游错误扩散：

1. `proposal.md`：展示摘要并等待确认。
2. `specs/`：展示需求清单并等待确认。
3. `design.md`：展示关键决策并等待确认。
4. `tasks.md`：展示批次拆分并等待确认。

## 校验清单

### proposal.md

- `## Why` 内容超过 50 字符。
- 存在 `## What Changes`、`## Scope`（In/Out）、`## Impact`、`## Capabilities`。
- 不含 TBD/TODO。

### specs/

- 必要行为使用 SHALL/MUST。
- 每条需求至少有一个带 WHEN/THEN 的 `#### Scenario:`。
- 使用 delta 分类标题且不存在矛盾。

### design.md

- 包含 `## Context`、`## Goals`、`## Decisions` 和 `## Risks And Trade-Offs`。
- 至少一项决策包含 Choice、Rationale 和 Alternatives considered。

### tasks.md

- 包含 `## File Structure` 和 `## Interfaces`。
- 任务编号、精确路径、TDD 阶段、依赖和需求映射完整。
- 每一步不超过约 5 分钟，不含占位符。

任一工件校验失败时，不得交给 `contract-builder`。

## 自动修复循环

所有未跳过工件写完后运行：

```bash
ssf validate <change-dir>
```

校验失败时，根据 DP-0、已确认需求和当前工件集重新生成失败的整个工件，不得只追加孤立文本掩盖错误：

- `proposal.md` 失败：重新生成 proposal；若范围或能力变化，重新检查并生成下游工件。
- `specs/` 失败：重新生成对应 `specs/<capability>/spec.md`；需求名称或行为变化时，重新生成 design 和 tasks。
- `design.md` 失败：依据当前 proposal/specs 重新生成；决策、接口或约束变化时，重新生成 tasks。
- `tasks.md` 失败：依据当前 proposal/specs/design 重新生成，确保每条需求映射到具体批次和 TDD 步骤。
- specs 布局失败：移动或重写到 `specs/<capability>/spec.md`，移除本次失败生成造成的重复或孤立文件。

重新生成后再执行一次 `ssf validate`。通过则进入 DP-2；仍失败则报告精确错误并停止。每个工件类别最多自动重新生成一次。

## DP-2：工件评审门

分别用 2–3 句话总结四类工件并询问调整意见。用户批准后运行：

```bash
ssf state set <change-dir> dp_2_result "approved: <摘要>"
ssf state set <change-dir> dp_2_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

## 交接规则

写完规划工件后不得直接实现。工件稳定、校验通过并记录 DP-2 后，交给 `contract-builder`。

## 异常处理

- **解析失败**：报告具体文件和错误，不从损坏模板继续生成。
- **模板缺失**：使用本 skill 规定的工件结构。
- **用户中断**：磁盘上的工件是恢复点，从首个缺失或不完整工件继续。
- **校验失败**：执行自动修复循环；第二次仍失败则停止交接。
