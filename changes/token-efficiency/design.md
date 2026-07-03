# 设计文档：Token 效率优化

## Context

### 当前状态

spec-superflow v0.8.7 的 prompt 注入体系包含：

| 组件 | 行数 | 字符数 | 估算 Token |
|------|------|--------|-----------|
| `hooks/session-start` | 23 | 1,595 | ~400 |
| 9 个 skill SKILL.md | 2,461 | 95,167 | ~24,000 |
| `phase-guard.md` | 14 | ~350 | ~100 |
| `GEMINI.md` guard | 10 | ~300 | ~80 |
| **合计** | **2,508** | **97,412** | **~24,580** |

> Token 估算公式：英文 1 token ≈ 4 字符，中文 1 token ≈ 1.5 字符。实际值因模型 tokenizer 而异。

### 约束

- **逻辑完整性不可退化**：压缩不能导致 skill 指令模糊或遗漏关键规则
- **行为不可变**：压缩后的指令必须产生与压缩前等效的 workflow 行为
- **版本号同步**：所有修改的文件必须通过 `ssf version` 自动同步版本号
- **零运行时依赖**：不能引入新的 npm 依赖
- **CI 不阻塞**：token 相关检查在 CI 中必须是 warning 级别（可选 upgrade 为 error）

### 利益相关者

- 所有 spec-superflow 用户（每次会话都承担 token 开销）
- 使用多平台（Claude Code + Cursor + Gemini CLI）的用户（承担多套注入）

## Goals

1. **压缩 30%+ 总注入 token**：目标从 ~24,580 token 降至 ≤ 17,000 token
2. **建立可度量基线**：`token-baseline.json` + `scripts/token-baseline.mjs` 提供可复现的度量
3. **自动化 enforce**：lint 规则在 CI 中 warning，本地 `--strict` 模式可升级为 error
4. **零功能退化**：所有现有测试通过，workflow 行为不变

## Decisions

### D1: 压缩策略 — 优先去重和精简，而非重写

**Choice**: 采用渐进的"去重-精简-统一"策略，不对 skill 进行结构性重写。

**Rationale**:
- 重写 9 个 skill 的风险太高（可能引入行为退化）
- 大部分冗余来自重复的模板说明、过长的示例、可合并的边界条件列举
- 渐进式压缩可以在每个 batch 后验证行为不变

**Alternatives considered**:
- **完全重写**：将 9 个 skill 合并为更少的 skill → 拒绝：改变 workflow 结构，风险大，scope 膨胀
- **仅做 lint 规则**：不修改 skill 内容，只加 lint → 拒绝：不解决实际问题，lint 规则只有在有人修时才有效

### D2: Phase guard 格式 — 引用状态机而非逐条列举

**Choice**: Phase guard 内容改为 `<state-name>` + 简短提示，由 workflow-start 在上下文中解释当前状态的含义。

**Rationale**:
- 当前 phase guard 逐条列出允许/禁止操作（"创建规划工件"、"执行实现代码"等），这些信息已经存在于 state-machine.md 和 workflow-start 的路由规则中
- phase guard 的角色是"信号"而非"文档"——它只需要告诉模型当前处于哪个状态，模型会从 workflow-start 中了解该状态的含义
- 消除双重维护负担（修改状态机时不需要同步更新 phase guard 的操作列表）

**Alternatives considered**:
- **完全移除 phase guard**：不注入任何 phase guard → 拒绝：DP gate 需要 phase guard 作为 session-level 的 guard 层
- **保留当前格式但缩短**：压缩措辞但不改变结构 → 部分采用：当前方案本质上是"保留格式但引用状态机"

### D3: Hooks 注入 — 共享内容变量 + 平台特定包装

**Choice**: 提取共享的注入内容为单一变量，三个平台的 printf 分支仅负责包装输出格式。

**Rationale**:
- 当前三套 printf 中，注入内容（`session_context`）完全相同，仅在包装格式上有差异
- 提取共享变量后，只需维护一处注入内容
- 注释可以集中在一处，而非在每个平台分支中重复

**Alternatives considered**:
- **移除多平台支持，仅保留 Claude Code** → 拒绝：v1.0.0 前仍需要多平台支持
- **使用 JSON 模板文件** → 拒绝：引入额外文件读取，复杂度增加

### D4: Token 度量 — 字符计数为基础，不依赖 tokenizer API

**Choice**: 基于字符数估算 token（英文 1:4，中文 1:1.5），不调用外部 tokenizer API。

**Rationale**:
- 零依赖约束（不能引入 `tiktoken` 等包）
- 估算精度足够用于趋势对比（压缩前 vs 压缩后）
- 实际 token 数因模型 tokenizer 而异，估算值作为统一基准更有可比性

**Alternatives considered**:
- **引入 tiktoken** → 拒绝：违反零依赖约束
- **仅记录字符数，不做 token 估算** → 拒绝：用户和开发者更关心 token 数，纯字符数不够直观

### D5: Lint 分类 — 复用现有框架，不新建独立系统

**Choice**: 在现有 `lint-skills.mjs` 中新增 `--include token` 分类，不创建新的 lint 系统。

**Rationale**:
- lint 框架已经有 `--include` 参数支持规则分类
- 新增分类比新建文件更简洁
- 规则发现和报告格式复用现有基础设施

**Alternatives considered**:
- **新建 `lint-tokens.mjs`** → 拒绝：增加维护负担，用户需要记住两个 lint 命令
- **使用 CI 独立 step** → 补充方案：CI 中 token lint 作为独立 step 运行，但使用同一框架

## Risks And Trade-Offs

| Risk | Probability | Impact | Mitigation |
|------|-----------|--------|------------|
| 压缩后 skill 指令不够清晰，导致 workflow 行为偏差 | Medium | High | 每个 batch 后手动验证 workflow-start → build-executor 的关键路径 |
| 中文内容压缩后 token 节省不明显 | High | Low | 中文本身紧凑，主要节省来自英文部分和代码块，目标 30% 有挑战但可实现 |
| Phase guard 简化导致模型在无 workflow-start 的会话中缺乏上下文 | Low | Medium | Phase guard 仅在 `.claude/always/` 中注入,大多数会话都有 workflow-start 上下文 |
| Token 估算与实际 tokenizer 差异大 | Medium | Low | 估算用于趋势对比，不用于精确计费；差异不影响优化效果判断 |

### Trade-off: 压缩 vs 可读性

压缩 skill 指令意味着减少示例、缩短说明、去除强调标记。好处是 token 节省，代价是 skill 指令对人类读者的可读性下降。考虑到 skill SKILL.md 的主要读者是 LLM（非人类），且更短的指令通常对 LLM 也更清晰，这个 trade-off 是可接受的。

### Trade-off: 自动化 vs 精确性

使用字符估算而非真实 tokenizer 意味着度量值不精确。但度量目标是"检测趋势"而非"精确计费"，估算足够。如果未来需要精确度量，可以引入 tokenizer 作为 optional dependency。
