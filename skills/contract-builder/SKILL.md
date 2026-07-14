---
name: contract-builder
description: 将已批准的规划工件转换为执行契约。当用户要求从规划进入实现，或 execution-contract.md 缺失、过期时使用。
---

# 执行契约生成

把规划工件压缩成唯一的实现交接协议 `execution-contract.md`，以 `templates/execution-contract.md` 为基础结构。

生成前读取 `proposal.md`、`specs/`、`design.md`、`tasks.md` 和 `docs/artifact-contract.md`，并运行：

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/get-config" execution.defaultLanguage
```

`zh` 时所有面向人的标题、正文、表格内容、批次描述和批准摘要使用中文；`en` 使用英文；`auto` 跟随已批准规划工件的主要语言。不得让英文模板决定输出语言。仅在校验协议要求时保留固定英文标题、表头和关键词，可使用中英双语标题。

## 工件映射

| 来源 | 提取内容 |
|---|---|
| `proposal.md` 的 Why 和 What Changes | 意图锁定：问题与范围 |
| `proposal.md` 的 Scope / Out of Scope | 范围边界 |
| `specs/` 的每个 `### Requirement:` | 已批准需求、场景和测试义务 |
| `design.md` 的 Decisions | 架构、接口和依赖约束 |
| `tasks.md` 的任务组 | 执行批次、完成定义和审查时机 |

## 需求覆盖交叉检查

最终生成前：

1. 列出 `specs/` 中每个 SHALL/MUST。
2. 确认每条需求都出现在 Approved Behavior，具有测试义务，并映射到至少一个批次。
3. 在 Escalation Rules 中标记未映射需求。
4. 记录跨批次依赖。

## 需求可追溯表

`execution-contract.md` 必须包含 `## Requirement Traceability`，并使用以下精确列名：

| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|

规则：

- `specs/**/spec.md` 中每个 `### Requirement:` 必须对应一行。
- Requirement 必须使用 spec 中的精确需求名称。
- Approved Behavior、Test Obligation 和 Batch 不得为空。
- Batch 必须引用 `## Task Batches` 下存在的 `### Batch N`。
- 仅列需求名称而不映射行为、测试和批次，不算满足可追溯性。

## 契约结构

必须清晰呈现：已批准行为、范围外内容、约束、批次、测试义务、审查门，以及必须退回规划阶段的条件。优先压缩信息，避免重复规划工件全文。

## DP-3：契约批准

起草后总结交接规则，指出歧义和未映射需求，并要求用户明确批准。批准后运行：

```bash
ssf state set <change-dir> dp_3_result "approved: <摘要>"
ssf state set <change-dir> dp_3_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

DP-3 是硬门禁，未记录不得实现。

## 契约过期判断

以下情况必须重新生成：proposal 范围变化、spec 需求变化、design 约束变化、tasks 批次发生实质变化，或契约不再符合意图。

## Hotfix 模式

生成最小契约：一句话 Intent Lock、编号 Task List、DP-3 Approval Gate。可省略 Scope Fence、Build Rules、Review Gates 和 Test Evidence，但仍必须经过 DP-3。

## 约束

- 仍有歧义时不得进入实现。
- 不得替用户批准契约。
- 不得因为规划文档完整而跳过契约。
- 不得静默丢弃未映射需求。

## 生成后处理

运行：

```bash
node scripts/spec-superflow.mjs state init <change-dir>
node scripts/spec-superflow.mjs validate <change-dir>
```

若 execution-contract 的可追溯性校验失败，依据 proposal、specs、design 和 tasks 重新生成完整契约，不得追加一份孤立需求列表。再校验一次；仍失败则报告精确的未映射需求或缺失批次，批准前停止。

## 异常处理

- **解析失败**：报告具体文件和章节，建议重新执行 `spec-writer`。
- **文件缺失**：列出全部缺失工件并返回 `spec-writer`。
- **用户中断**：恢复时重新读取全部工件，并通过内容比较判断契约是否过期。
- **校验失败**：在 Escalation Rules 和批准摘要中标记未映射需求。
