# 变更提案：Token 效率优化

## 背景（Why）

spec-superflow 是一个 prompt 注入型 workflow 插件，每次会话都会加载 hooks、phase-guard、skill 指令等内容。v0.8.7 版本中，9 个 skill 的 SKILL.md 累计约 2,461 行 / 95,167 字符（估算约 24,000 tokens），加上 hooks 注入和 phase guard，每次会话启动的基础 token 开销可观。

当前问题：

1. **Hooks 注入声明不准确**：`hooks/session-start` 声称 "~80 tokens"，但实际内容约 1,595 字符（估算约 400 tokens），且包含多平台兼容逻辑（Claude Code / Cursor / Copilot CLI 三套 printf 分支）和冗长的注释
2. **Skill prompt 膨胀**：9 个 skill 合计 2,461 行，存在重复的模板说明（如"Use This Skill When"在每个 skill 中格式不同但语义重复）、过长的示例代码块、多层嵌套的强调标记（EXTREMELY_IMPORTANT / CRITICAL / ⚠️）
3. **workflow-start 初始化开销**：每次启动需 inspect change directory、run update check、run guard checks、run infer-workflow——这些操作本身开销小，但它们的输出（JSON）和错误提示会被注入上下文
4. **Phase guard 注入冗余**：`.claude/always/phase-guard.md`（14 行）和 `GEMINI.md`（10 行 phase guard）存在重复的版本号和阶段描述，且二者的"允许/禁止操作"列表与状态机定义有结构性重叠
5. **缺乏度量基线**：没有系统化的 token 度量机制——不知道每次会话各组件消耗多少 token、各 skill 在压缩前后的 token 变化、CI 中无法 enforce token 预算

本变更对上述五个维度进行全面优化，建立 token 度量基线，并在 CI 中增加可选的 token 预算检查。

## 变更内容（What Changes）

- **D1 Hooks 注入精简**：审查并压缩 `hooks/session-start` 的注入内容，修正 token 估算，简化多平台兼容逻辑
- **D2 Skill 指令精简**：逐个审查 9 个 skill 的 SKILL.md，去除冗余措辞、统一格式、压缩示例、减少重复的边界说明
- **D3 workflow-start 初始化优化**：审查 `workflow-start/SKILL.md` 的初始化步骤，将非必要步骤延迟加载或跳过
- **D4 Phase guard 注入最小化**：统一 `.claude/always/phase-guard.md` 和 `GEMINI.md` 的注入格式，消除与状态机的结构性重叠，最小化注入体积
- **D5 Token 度量基线**：建立各组件 token 估算基准，在 lint 框架中新增 token 相关规则，CI 中可选 enforce

## 能力（Capabilities）

### 新增能力

- `token-baseline` — 各 skill/hook/guard 的 token 估算基线和度量工具
- `token-lint-rules` — lint 规则集中的 token 相关检查（最大行数、最大字符数、禁止冗余模式）

### 修改能力

- `hooks-injection` — `hooks/session-start` 注入内容压缩
- `skill-instructions` — 9 个 skill 的 SKILL.md 精简
- `phase-guard-injection` — Claude Code 和 Gemini CLI 的 phase guard 最小化
- `lint-framework` — `scripts/lint/lint-skills.mjs` 新增 token 规则

## 范围（Scope）

### 范围内（In Scope）

- `hooks/session-start` 内容审查与压缩（含平台兼容逻辑简化）
- 9 个 skill 的 SKILL.md 精简（保留逻辑完整性，去除冗余措辞、重复示例、不必要强调标记）
- `workflow-start/SKILL.md` 的初始化步骤审查（延迟非必要检查、简化输出）
- `.claude/always/phase-guard.md` 和 `GEMINI.md` 的注入内容最小化
- `scripts/lint/lint-skills.mjs` 新增 token 相关 lint 规则（最大行数、最大字符数、禁止模式）
- 建立 token 度量基线文档和度量脚本
- CI 中可选 token 预算检查（不阻塞 CI，warning only）

### 范围外（Out of Scope）

- 跨平台一致性（Claude Code / Cursor / Codex / Copilot / Gemini CLI 的 manifest 和注入机制）— 留给 v1.0.0
- 新功能开发、skill 增删合并
- 已有门禁的削弱（不能为了省 token 而砍掉 guard 检查维度）
- TypeScript 引擎（`src/`）的重构
- Batch Inline 等架构级 token 优化（不同性质的优化，留给独立 change）

## 影响（Impact）

- 影响的代码区域：`hooks/session-start`、`skills/*/SKILL.md`（9 个文件）、`.claude/always/phase-guard.md`、`GEMINI.md`、`scripts/lint/lint-skills.mjs`
- 影响的 API 或接口：无——所有修改仅影响 prompt 文本内容，不改变插件行为逻辑
- 依赖或涉及的外部系统：无
- 风险：skill 压缩可能导致指令不够清晰，需要通过 lint 规则和人工审查确保逻辑完整性不退化

## 关键参考文件

- `hooks/session-start` — 当前注入内容（23 行 / 1,595 字符）
- `.claude/always/phase-guard.md` — Claude Code 的 phase guard（14 行）
- `GEMINI.md` — Gemini CLI 的 phase guard（10 行 guard 内容）
- `skills/*/SKILL.md` — 9 个 skill 的完整指令（2,461 行 / 95,167 字符）
- `scripts/guard/guard.mjs` + `scripts/guard/checks/` — guard 系统
- `scripts/check-version-consistency.mjs` — pre-commit 检查
- `scripts/lint/lint-skills.mjs` — lint 框架（本次变更会新增 token 相关规则）
