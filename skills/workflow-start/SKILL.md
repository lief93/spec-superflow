---
name: workflow-start
description: spec-superflow 状态机工作流的统一入口。当工作区存在 .spec-superflow.yaml、changes/change-name/、proposal.md、specs/、design.md、tasks.md 或 execution-contract.md，且用户要求开始、继续、恢复、实现、规划或判断下一阶段时使用；用户明确要求启动 spec-superflow 变更时也使用。普通编码任务不得误触发。
---

# 工作流入口

负责检查变更上下文、检查更新、确认 DP-0、识别状态、路由到正确 skill，并阻止非法状态迁移。

## 适用条件

仅在存在 spec-superflow 上下文，或用户明确指定 spec-superflow 时调用。拿不准时先检查 `.spec-superflow.yaml`。普通编码、闲聊和无关工作不得调用。

## 状态

`exploring` → `specifying` → `bridging` → `approved-for-build` → `executing` → `closing`。`executing` 可进入 `debugging` 支路，`abandoned` 为终态。迁移含义不清时读取 `docs/state-machine.md`。

## 初始化

1. **检查更新**：运行 `node "${CLAUDE_PLUGIN_ROOT}/scripts/check-update.mjs"`。退出码 0 继续；1 仅提示升级，不阻塞；2 跳过。
2. **检查变更目录**：检查 `proposal.md`、`specs/`、`design.md`、`tasks.md`、`execution-contract.md`。判断需求是否明确、工件是否缺失或不稳定、契约是否存在且获批、实现是否进行中或受阻、是否进入验证收口。

## DP-0：用户确认门

变更目录不存在、规划工件缺失或为空、或者 `dp_0_confirmed` 不为 `true` 时执行 DP-0；已经确认则跳过。

DP-0 前运行 `bash "${CLAUDE_PLUGIN_ROOT}/scripts/get-config" execution.defaultLanguage`。`zh` 表示中文，`en` 表示英文，`auto` 跟随用户请求的主要语言。把解析后的文档语言写入 `dp_0_decisions`，不得让模板语言或 Schema 关键词覆盖该结果。

向用户确认：变更名称和一句话意图、已知约束、相关优化是否纳入、沟通方式是逐项确认还是先起草再评审。

确认后运行：

```bash
ssf state set <change-dir> dp_0_decisions "<确认摘要>"
ssf state set <change-dir> dp_0_confirmed true
ssf state set <change-dir> dp_0_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

再根据项目配置检查 `artifacts.order` 和 `artifacts.skip`。

## 工作流模式识别

`workflow` 为 `auto`、`null` 或未设置时，运行 `node "${CLAUDE_PLUGIN_ROOT}/scripts/infer-workflow.mjs" <change-dir>`：

- **hotfix**：不超过 2 个任务、2 个文件，且不涉及 Schema、API 或新模块。
- **tweak**：不超过 4 个任务，且仅修改配置或文档。
- **full**：其他情况。

使用 `ssf state set <dir> workflow <mode>` 持久化。若工件内容不符合 hotfix/tweak 条件，升级为 `full` 并说明原因；除非用户要求，不覆盖显式模式。

## 路由规则

### need-explorer

需求模糊、范围不清、正在比较方案或没有稳定的变更名称。

### spec-writer

执行守卫：`node "${CLAUDE_PLUGIN_ROOT}/scripts/guard/guard.mjs" check <dir> exploring specifying --json`。用户目标明确，但规划工件缺失或不完整。

### contract-builder

执行守卫：`... check <dir> specifying bridging --json`。规划工件已存在，用户要求实现，但执行契约缺失或过期。包含 `DP-3：契约批准`。

### build-executor

执行守卫：`... check <dir> approved-for-build executing --json`。契约存在、已批准且与规划工件一致。包含 `DP-4：执行模式选择`。

### bug-investigator

实现阶段遇到测试失败、异常行为、构建错误或任务阻塞。诊断完成后回到 `build-executor`。

### code-reviewer

一个执行批次完成，准备进行规格符合性和代码质量审查。

### release-archivist

执行守卫：`... check <dir> executing closing --json`。实现和验证已完成或接近完成。包含 `DP-7：归档确认`。

### spec-merger

收口时存在需要合并到长期规格的 delta specs。

### abandoned

仅在用户明确要求，或同一问题连续失败至少 3 次且用户选择放弃，或范围变化导致变更失去价值并经用户确认时进入。不得从 `closing` 或 `abandoned` 进入。

### 快速路径

- **Hotfix**：直接进入 `contract-builder`，守卫为 `exploring bridging --workflow hotfix`；DP-3 后内联执行，再轻量收口。
- **Tweak**：直接进入 `build-executor`，守卫为 `exploring approved-for-build --workflow tweak`；完成后轻量收口。

状态迁移后运行 `ssf inject <change-dir>` 更新阶段守卫文件。

## 过期检测

- **契约过期**：proposal 范围超出契约边界，或契约引用 proposal 中不存在的能力，返回 `contract-builder`。
- **规划工件过期**：proposal 中的能力没有对应 spec，或 spec 中存在 proposal 未声明的能力。
- **任务过期**：spec 中的需求没有对应任务。

## 约束

- 规划工件或契约完成前不得实现。
- 未检查状态不得直接“继续”。
- 契约过期或实现遇到故障时不得绕过对应处理阶段。
- 未完成代码审查不得收口。
- delta specs 未同步不得结束。
- `abandoned` 不得迁出，也不得自动进入。
- 不得合并已放弃变更的 delta specs。

## 输出要求

始终说明：当前识别状态、判断依据、下一步应调用的 skill。若阻塞，说明缺少的工件或批准。

决策点映射：`contract-builder` → DP-3，`build-executor` → DP-4，`bug-investigator` 升级 → DP-5，`release-archivist` 验证失败 → DP-6，归档 → DP-7。

## 异常处理

- **解析失败**：改用工件内容判断状态。
- **文件缺失**：路由到负责生成该文件的 skill。
- **用户中断**：恢复时重新读取变更目录，不使用缓存判断。
