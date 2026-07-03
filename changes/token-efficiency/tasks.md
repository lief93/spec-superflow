# 实现任务：Token 效率优化

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `scripts/token-baseline.mjs` | Token 度量工具：统计各组件行数/字符数/估算 token，支持对比基线 |
| Create | `scripts/lint/rules/token-rules.mjs` | Token 相关 lint 规则：max-lines, max-chars, max-emphasis-markers, max-code-block-length |
| Modify | `scripts/lint/lint-skills.mjs` | 新增 `--include token` 规则分类支持 |
| Modify | `hooks/session-start` | 压缩注入消息，共享内容变量，精简注释 |
| Modify | `.claude/always/phase-guard.md` | 压缩至 ≤8 行，引用状态机而非逐条列举操作 |
| Modify | `GEMINI.md` | Phase guard 块与 Claude Code 版本内容一致 |
| Modify | `skills/need-explorer/SKILL.md` | 精简指令（目标 ≤180 行） |
| Modify | `skills/spec-merger/SKILL.md` | 精简指令（目标 ≤180 行） |
| Modify | `skills/code-reviewer/SKILL.md` | 精简指令（目标 ≤220 行） |
| Modify | `skills/release-archivist/SKILL.md` | 精简指令（目标 ≤200 行） |
| Modify | `skills/contract-builder/SKILL.md` | 精简指令（目标 ≤200 行） |
| Modify | `skills/bug-investigator/SKILL.md` | 精简指令（目标 ≤220 行） |
| Modify | `skills/spec-writer/SKILL.md` | 精简指令（目标 ≤230 行） |
| Modify | `skills/build-executor/SKILL.md` | 精简指令（目标 ≤280 行） |
| Modify | `skills/workflow-start/SKILL.md` | 精简指令 + 初始化步骤优化（目标 ≤300 行） |
| Modify | `scripts/check-version-consistency.mjs` | 新增 phase-guard 和 GEMINI.md 的版本号一致性检查 |
| Modify | `.github/workflows/ci.yml` | 新增 token lint step（warning only） |
| Create | `token-baseline.json` | 压缩后的 token 度量快照 |

## Interfaces

### Batch 1 → Batch 2
- **Produces**: `token-rules.mjs` 中的 `checkMaxLines()`, `checkMaxChars()` 函数 — consumed by Batch 2 用于验证压缩后的 hooks 和 phase guard
- **Produces**: `token-baseline.mjs` CLI — consumed by Batch 5 用于生成最终基线快照

### Batch 1 → Batch 3, 4
- **Produces**: `lint-skills.mjs --include token` 参数 — consumed by Batch 3, 4 用于验证每个 skill 压缩后不超过 lint 阈值

### Batch 2 → Batch 5
- **Produces**: 压缩后的 `hooks/session-start`, `phase-guard.md`, `GEMINI.md` — consumed by Batch 5 用于生成完整基线快照

### Batch 3, 4 → Batch 5
- **Produces**: 压缩后的 9 个 `skills/*/SKILL.md` — consumed by Batch 5 用于生成完整基线快照和最终验证

---

## Batch 1: Token 度量基线与 Lint 规则

**Depends on**: None（首批）

### Task 1.1: 创建 token-baseline.mjs 度量工具

**Files**: Create: `scripts/token-baseline.mjs`

**TDD Phases**:

1. **Write failing test**: 在 `tests/lib/` 下创建测试，调用 baseline 工具对 `skills/workflow-start/SKILL.md` 统计，验证输出包含 `{ lines, chars, estimatedTokens }`
2. **Run test, confirm failure**: 文件不存在，测试报 `ERR_MODULE_NOT_FOUND`
3. **Implement**: 创建 `scripts/token-baseline.mjs`
   - 支持两种模式：`node scripts/token-baseline.mjs`（全量统计）和 `node scripts/token-baseline.mjs --compare baseline.json`（对比模式）
   - 对每个目标文件统计：行数、字符数、估算 token 数（英文 `Math.ceil(chars / 4)`，中文先分离中文字符按 1.5 估算，其余按 4 估算）
   - 输出 JSON 格式到 stdout 或 `--output <file>` 参数指定的文件
   - 支持 `--files <glob>` 参数限制统计范围
4. **Run test, confirm pass**: 对已知文件统计，验证输出格式和数值合理性
5. **Commit**: `git add scripts/token-baseline.mjs tests/lib/token-baseline.test.ts && git commit -m "feat(token): add token-baseline.mjs measurement tool"`

### Task 1.2: 创建 token lint 规则模块

**Files**: Create: `scripts/lint/rules/token-rules.mjs`

**TDD Phases**:

1. **Write failing test**: 创建测试，调用 `checkMaxLines(skillPath, 250)`，对一个 300 行的临时文件验证返回 `{ pass: false, message: "..." }`
2. **Run test, confirm failure**: 模块不存在
3. **Implement**: 创建 `scripts/lint/rules/token-rules.mjs`，导出以下函数：
   - `checkMaxLines(filePath, max)` — 检查文件行数 ≤ max
   - `checkMaxChars(filePath, max)` — 检查文件字符数 ≤ max
   - `checkMaxEmphasisMarkers(filePath, max)` — 检查 `**...**` 标记数 ≤ max，检查无 `EXTREMELY_IMPORTANT`/`CRITICAL`
   - `checkMaxCodeBlockLength(filePath, max)` — 检查每个 ``` 代码块 ≤ max 行
   - `checkImportsCount(filePath, max)` — 检查 IMPORTANT 关键词出现次数 ≤ max
   每个函数返回 `{ pass: boolean, failures: string[] }`
4. **Run test, confirm pass**: 所有规则函数对测试文件返回预期结果
5. **Commit**: `git add scripts/lint/rules/token-rules.mjs tests/lib/token-rules.test.ts && git commit -m "feat(token): add token lint rules module"`

### Task 1.3: 在 lint-skills.mjs 中新增 --include token 分类

**Files**: Modify: `scripts/lint/lint-skills.mjs`

**TDD Phases**:

1. **Write failing test**: 运行 `node scripts/lint/lint-skills.mjs --include token`，预期仅执行 token 规则且无输出（规则未注册），实际命令行参数未被识别
2. **Run test, confirm failure**: `--include token` 不被识别
3. **Implement**: 修改 `scripts/lint/lint-skills.mjs`
   - 在已有的 `--include` 参数解析后新增 `token` 分类
   - 当 `--include token` 时，导入 `./rules/token-rules.mjs` 并执行所有 token 规则
   - 对 `skills/*/SKILL.md` 目录下的所有文件运行规则
   - 同时支持对单个文件运行：`--include token --file skills/workflow-start/SKILL.md`
   - Token 规则默认以 warning 级别报告（不改变 exit code）
4. **Run test, confirm pass**: `--include token` 正确执行 token 规则并输出结果
5. **Commit**: `git add scripts/lint/lint-skills.mjs && git commit -m "feat(lint): add --include token category for token efficiency rules"`

### Task 1.4: 为 token baseline 添加测试

**Files**: Create: `tests/lib/token-baseline.test.ts`

**Implementation**:
- 测试 1：baseline 工具对已知文件（`skills/need-explorer/SKILL.md`）输出正确的 JSON 结构
- 测试 2：`--compare` 模式对两份不同的 baseline 输出正确的变化量
- 测试 3：`--files` 参数正确过滤统计范围
- 运行 `npm test` 确认所有测试通过

**Commit**: `git add tests/lib/token-baseline.test.ts && git commit -m "test(token): add token-baseline.mjs unit tests"`

### Task 1.5: Batch 1 收尾

- 运行 `node scripts/token-baseline.mjs` 生成当前基线并保存为 `token-baseline-pre.json`（临时文件，不提交）
- 记录当前总计 token 估算值
- 运行 `npm test` 确保 Batch 1 所有测试通过

**Commit**: 无单独 commit（Batch 1 已在各 task 中 commit）

---

## Batch 2: Hooks + Phase Guard 压缩

**Depends on**: Batch 1（使用 token lint 规则验证压缩结果）

### Task 2.1: 压缩 hooks/session-start

**Files**: Modify: `hooks/session-start`

**Implementation**:
1. 提取 `session_context` 变量中的注入消息，从当前的 ~400 字符压缩至 ≤150 字符：
   - 压缩前：`"<EXTREMELY_IMPORTANT>\nYou have spec-superflow installed. Use /spec-superflow:workflow-start ONLY when you detect an active spec-superflow change in the workspace (look for \`.spec-superflow.yaml\`, \`proposal.md\`, \`execution-contract.md\`, or \`specs/\` directories), OR when the user explicitly invokes it by name. For ordinary coding tasks without spec-superflow artifacts, do NOT invoke workflow-start — just handle the request directly.\n</EXTREMELY_IMPORTANT>"`
   - 压缩目标：去除 EXTREMELY_IMPORTANT 嵌套，精简至核心信息："检测到 spec-superflow 工件时用 workflow-start，否则直接处理"
2. 合并三个平台的 printf 分支：将 `session_context` 提取为共享变量，仅包装格式部分分平台
3. 精简注释：从 10 行注释压缩至 3 行（去掉重复的平台兼容说明和历史信息）
4. 更新 token 估算注释为实际值
5. 运行 `node scripts/lint/lint-skills.mjs --include token --file hooks/session-start` 验证
6. 运行 `npm test` 确保所有测试通过

**Commit**: `git add hooks/session-start && git commit -m "perf(hooks): compress session-start injection to ~40 tokens"`

### Task 2.2: 压缩 .claude/always/phase-guard.md

**Files**: Modify: `.claude/always/phase-guard.md`

**Implementation**:
1. 将内容从 14 行压缩至 ≤8 行
2. 当前格式（14 行）：
   ```
   # Phase Guard: v0.8.7
   **当前阶段**: exploring | **工作流**: auto
   ## ✅ 允许操作
   - 澄清需求、比较方案
   - 与用户讨论 scope 和 capabilities
   ## ⛔ 禁止操作
   - 创建规划工件
   - 执行实现代码
   - 修改 execution-contract.md
   ## 🔔 决策点
   - DP-1: 需求确认
   ```
3. 压缩后格式（≤8 行）：移除逐条操作列表，改为引用状态机
   ```
   # spec-superflow v0.8.7 | 阶段: {{state}} | 工作流: {{workflow}}
   遵循 workflow-start 路由规则。当前阶段允许的操作由状态机定义。
   DP gate: 进入下一阶段前需用户确认。
   ```
   注：`{{state}}` 和 `{{workflow}}` 通过 `ssf inject` 命令在状态转换时替换
4. 运行 lint 验证：`node scripts/lint/lint-skills.mjs --include token --file .claude/always/phase-guard.md`
5. 运行 `npm test`

**Commit**: `git add .claude/always/phase-guard.md && git commit -m "perf(guard): compress phase-guard.md to 6 lines"`

### Task 2.3: 同步 GEMINI.md 的 phase guard 块

**Files**: Modify: `GEMINI.md`

**Implementation**:
1. 检查 `GEMINI.md` 中 `<!-- spec-superflow-phase-guard-start -->` 和 `<!-- spec-superflow-phase-guard-end -->` 之间的内容
2. 将其替换为与 `.claude/always/phase-guard.md` 一致的内容（保留 GEMINI.md 的头部说明不变）
3. 验证两个文件的 phase guard 内容一致：`diff <(sed -n '/phase-guard-start/,/phase-guard-end/p' GEMINI.md) <(cat .claude/always/phase-guard.md)`
4. 运行 `npm test`

**Commit**: `git add GEMINI.md && git commit -m "perf(guard): sync GEMINI.md phase guard with claude version"`

### Task 2.4: 验证版本号一致性

**Files**: Modify: `scripts/check-version-consistency.mjs`（如果需要）

**Implementation**:
1. 运行 `node scripts/check-version-consistency.mjs` 验证版本号一致
2. 如果 `check-version-consistency.mjs` 尚未检查 `.claude/always/phase-guard.md` 和 `GEMINI.md` 的版本号，添加这两个文件的版本检查
3. 运行 `npm test`

**Commit**: `git add scripts/check-version-consistency.mjs && git commit -m "fix(version): add phase-guard and GEMINI.md to version consistency check"`（仅在有修改时）

### Task 2.5: Batch 2 收尾

- 运行 `node scripts/token-baseline.mjs --files "hooks/session-start,.claude/always/phase-guard.md,GEMINI.md"` 验证压缩效果
- 验证 hooks/session-start 注入消息 ≤150 字符
- 验证 phase-guard.md ≤8 行
- 运行 `npm test`

**Commit**: 无单独 commit

---

## Batch 3: Skill 压缩 — Group A（小型 skill）

**Depends on**: Batch 1（lint 规则可用），Batch 2（phase guard 已压缩）

### Task 3.1: 压缩 need-explorer/SKILL.md

**Files**: Modify: `skills/need-explorer/SKILL.md`（当前 158 行 → 目标 ≤130 行）

**Implementation**:
1. 审查当前内容，识别可压缩的部分：
   - "Use This Skill When" 触发条件：统一句式，去除冗余引导语
   - 提问策略部分：合并重复的"每次只问一个问题"表述
   - 异常处理：保留逻辑，去除冗长的分支描述
2. 压缩后运行 lint 验证：`node scripts/lint/lint-skills.mjs --include token --file skills/need-explorer/SKILL.md`
3. 阅读压缩后的内容，确认逻辑要点完整（触发条件、提问策略、handoff 规则）
4. 运行 `npm test`

**Commit**: `git add skills/need-explorer/SKILL.md && git commit -m "perf(skill): compress need-explorer SKILL.md"`

### Task 3.2: 压缩 spec-merger/SKILL.md

**Files**: Modify: `skills/spec-merger/SKILL.md`（当前 206 行 → 目标 ≤160 行）

**Implementation**:
1. 审查并压缩：合并重复的冲突检测说明，精简 merge 步骤描述
2. Lint 验证
3. 逻辑完整性检查
4. 运行 `npm test`

**Commit**: `git add skills/spec-merger/SKILL.md && git commit -m "perf(skill): compress spec-merger SKILL.md"`

### Task 3.3: 压缩 code-reviewer/SKILL.md

**Files**: Modify: `skills/code-reviewer/SKILL.md`（当前 318 行 → 目标 ≤220 行）

**Implementation**:
1. 审查并压缩：
   - 精简审查维度描述（Critical/Important/Minor 每类 ≤3 行说明）
   - 移除重复的"不要"列表
   - 压缩报告格式模板
2. Lint 验证
3. 逻辑完整性检查（review gate 流程、severity 分类、handoff 规则）
4. 运行 `npm test`

**Commit**: `git add skills/code-reviewer/SKILL.md && git commit -m "perf(skill): compress code-reviewer SKILL.md"`

### Task 3.4: 压缩 release-archivist/SKILL.md

**Files**: Modify: `skills/release-archivist/SKILL.md`（当前 243 行 → 目标 ≤180 行）

**Implementation**:
1. 审查并压缩：合并重复的验证步骤，精简归档格式说明
2. Lint 验证
3. 逻辑完整性检查
4. 运行 `npm test`

**Commit**: `git add skills/release-archivist/SKILL.md && git commit -m "perf(skill): compress release-archivist SKILL.md"`

### Task 3.5: 压缩 contract-builder/SKILL.md

**Files**: Modify: `skills/contract-builder/SKILL.md`（当前 234 行 → 目标 ≤180 行）

**Implementation**:
1. 审查并压缩：精简 contract 格式模板，移除与 spec-writer 重复的验证步骤
2. Lint 验证
3. 逻辑完整性检查（intent lock、scope fence、DP-3 协议）
4. 运行 `npm test`

**Commit**: `git add skills/contract-builder/SKILL.md && git commit -m "perf(skill): compress contract-builder SKILL.md"`

### Task 3.6: Batch 3 收尾

- 运行 `node scripts/lint/lint-skills.mjs --include token` 对所有已压缩 skill 进行 token lint
- 运行 `node scripts/token-baseline.mjs --files "skills/need-explorer/*,skills/spec-merger/*,skills/code-reviewer/*,skills/release-archivist/*,skills/contract-builder/*"` 验证累计 token 下降
- 运行 `npm test`

**Commit**: 无单独 commit

---

## Batch 4: Skill 压缩 — Group B（大型 skill）

**Depends on**: Batch 3（Group A 压缩完成，经验验证可行）

### Task 4.1: 压缩 bug-investigator/SKILL.md

**Files**: Modify: `skills/bug-investigator/SKILL.md`（当前 290 行 → 目标 ≤220 行）

**Implementation**:
1. 审查并压缩：
   - 4-phase 调试流程每 phase ≤5 行描述
   - 合并重复的 escalate 条件说明
   - 精简代码示例
2. Lint 验证
3. 逻辑完整性检查（4 phases、escalate 条件、debugging→executing 往返）
4. 运行 `npm test`

**Commit**: `git add skills/bug-investigator/SKILL.md && git commit -m "perf(skill): compress bug-investigator SKILL.md"`

### Task 4.2: 压缩 spec-writer/SKILL.md

**Files**: Modify: `skills/spec-writer/SKILL.md`（当前 277 行 → 目标 ≤230 行）

**Implementation**:
1. 审查并压缩：
   - 精简 4 个 artifact 的验证清单（保留检查项，去除重复的说明文字）
   - 合并 "Quality Bar" 和 "Self-Review Checklist" 部分（两者有大量重叠）
   - 压缩 DP-2 协议说明
2. Lint 验证
3. 逻辑完整性检查（4 artifacts、validation rules、DP-2 gate、handoff rule）
4. 运行 `npm test`

**Commit**: `git add skills/spec-writer/SKILL.md && git commit -m "perf(skill): compress spec-writer SKILL.md"`

### Task 4.3: 压缩 build-executor/SKILL.md

**Files**: Modify: `skills/build-executor/SKILL.md`（当前 360 行 → 目标 ≤280 行）

**Implementation**:
1. 审查并压缩：
   - 精简 TDD/SDD 两种执行模式的描述（合并共同部分）
   - 压缩 Review Gate 说明（引用 code-reviewer，不重复其内容）
   - 精简 batch 执行流程模板
   - 减少代码块示例
2. Lint 验证
3. 逻辑完整性检查（TDD/SDD 模式、review gate、contract drift 检测、DP-4）
4. 运行 `npm test`

**Commit**: `git add skills/build-executor/SKILL.md && git commit -m "perf(skill): compress build-executor SKILL.md"`

### Task 4.4: 压缩 workflow-start/SKILL.md + 初始化优化

**Files**: Modify: `skills/workflow-start/SKILL.md`（当前 375 行 → 目标 ≤300 行）

**Implementation**:

**Part A — 内容压缩**:
1. 精简冗余部分：
   - "Default States" 列表压缩为一行引用（→ state-machine.md）
   - "Required Inspection" 的 6 个问题合并为 3 个
   - "Config-Aware Routing" 与主路由逻辑合并
   - 去除重复的 guard check 命令示例（每个路由规则中格式相同，可提取为一次说明）
   - "Hotfix Fast-Path Routing" 和 "Tweak Fast-Path Routing" 合并为一个表格
   - "Guardrails" 列表去重（多条规则在其他部分已有说明）

**Part B — 初始化步骤优化**:
2. 将以下步骤从 workflow-start 中标记为"延迟执行"（由目标 skill 处理）：
   - `infer-workflow.mjs` 调用 → 移至 spec-writer（仅在需要创建 artifacts 时执行）
   - 完整的 guard check 矩阵 → 仅保留 transition-legality 检查，artifacts-exist 等移至目标 skill
3. 简化 update check 输出（当前输出 "✅ up to date" 或升级提示，无需改变逻辑）

4. Lint 验证：`node scripts/lint/lint-skills.mjs --include token --file skills/workflow-start/SKILL.md`
5. 逻辑完整性检查（状态检测、路由规则、DP-0 gate、staleness 检测、handoff 规则）
6. 运行 `npm test`

**Commit**: `git add skills/workflow-start/SKILL.md && git commit -m "perf(skill): compress workflow-start SKILL.md and defer non-critical init"`

### Task 4.5: Batch 4 收尾

- 运行 `node scripts/lint/lint-skills.mjs --include token` 对所有 9 个 skill 执行完整 token lint
- 运行 `node scripts/token-baseline.mjs` 生成压缩后的全量度量
- 对比 Batch 1 中保存的 `token-baseline-pre.json`，验证总计压缩 ≥30%
- 运行 `npm test`

**Commit**: 无单独 commit

---

## Batch 5: CI 集成 + 基线快照 + 最终验证

**Depends on**: Batch 3, 4（所有 skill 压缩完成）

### Task 5.1: 在 CI 中新增 token lint step

**Files**: Modify: `.github/workflows/ci.yml`

**Implementation**:
1. 在现有 CI workflow 的 test job 之后新增 step：
   ```yaml
   - name: Token efficiency lint
     run: node scripts/lint/lint-skills.mjs --include token
     continue-on-error: true  # warning only, 不阻塞 CI
   ```
2. 验证 CI 配置语法：如果安装了 `act`，运行 `act -j test`（dry-run）；否则手动检查 YAML 语法
3. 运行 `npm test`

**Commit**: `git add .github/workflows/ci.yml && git commit -m "ci(token): add token efficiency lint step (warning only)"`

### Task 5.2: 生成并保存 token 基线快照

**Files**: Create: `token-baseline.json`

**Implementation**:
1. 运行 `node scripts/token-baseline.mjs --output token-baseline.json` 生成最终基线
2. 审查基线内容，确认所有组件的度量值合理
3. 在 `token-baseline.json` 顶部添加注释说明（用 `_comment` 字段）：度量时间、版本、估算方法
4. 运行 `npm test`

**Commit**: `git add token-baseline.json && git commit -m "docs(token): add token baseline snapshot for v0.8.8"`

### Task 5.3: 验证版本号一致性

**Files**: Modify: `scripts/check-version-consistency.mjs`（如 Task 2.4 未修改则在此修改）

**Implementation**:
1. 运行 `node scripts/check-version-consistency.mjs` 确保所有文件版本一致
2. 确认 phase-guard.md 和 GEMINI.md 的版本号已纳入检查
3. 运行 `npm test`

**Commit**: `git add scripts/check-version-consistency.mjs && git commit -m "fix(version): ensure phase-guard files in version consistency check"`（仅在有修改时）

### Task 5.4: 最终验证与回归

**Implementation**:
1. 运行完整 lint：`node scripts/lint/lint-skills.mjs --include token`，确认 0 error（warning 可接受）
2. 运行 `node scripts/token-baseline.mjs`，确认总计 ≤17,000 估算 token（压缩 ≥30%）
3. 运行 `npm test`，确认所有测试通过
4. 手动审查关键 skill 的逻辑完整性（workflow-start、spec-writer、build-executor）
5. 运行 `node scripts/spec-superflow.mjs doctor` 确认插件健康
6. 清理临时文件：`rm -f token-baseline-pre.json`

**Commit**: `git commit -m "chore(token): final verification — all tests pass, token baseline saved"`（仅在有未提交修改时）

### Task 5.5: Batch 5 收尾

- 确认所有 task 已 commit
- 生成变更摘要：压缩前后对比表
- 运行 `git log --oneline token-efficiency ^main` 查看所有 commit

**Commit**: 无单独 commit（所有修改已在前面的 task 中 commit）
