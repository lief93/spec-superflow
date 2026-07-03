# 执行合同：Token 效率优化

## Intent Lock

- **变更名称**：Token 效率优化
- **要解决的问题**：spec-superflow 作为 prompt 注入型插件，每次会话加载 hooks/skills/phase-guard 累计约 24,580 token。当前无系统化度量，存在 hooks 注入声明不准确（声称 ~80 tokens 实际 ~400）、skill 指令膨胀（9 个 skill 共 2,461 行）、phase guard 与状态机结构性重叠、缺乏 token 度量基线等问题
- **范围内**：
  1. `hooks/session-start` 注入内容压缩（≤150 字符，共享变量，注释 ≤3 行）
  2. 9 个 skill SKILL.md 精简（累计 ≤1,800 行，每个 ≤250 行）
  3. `workflow-start/SKILL.md` 初始化步骤优化（≤5 步，文件 ≤300 行）
  4. `.claude/always/phase-guard.md` 和 `GEMINI.md` 注入最小化（≤8 行，引用状态机）
  5. Token 度量基线和 lint 规则（token-baseline.mjs + token-rules.mjs + CI 集成）
- **范围外**：跨平台一致性（→v1.0.0）、新功能开发、门禁削弱、TypeScript 引擎重构、Batch Inline 架构级优化

## Approved Behavior

- **已批准需求摘要**：
  - hooks-injection: 注入消息 ≤150 字符、平台分支共享变量、注释 ≤3 行、声明 token 准确
  - skill-instructions: 每个 SKILL.md ≤250 行、累计 ≤1,800 行、禁止 EXTREMELY_IMPORTANT/CRITICAL、代码块 ≤15 行、逻辑完整性不退化、模板格式统一
  - workflow-start-init: 初始化 ≤5 步、文件 ≤300 行、guard check 最小化为 transition-legality
  - phase-guard-injection: ≤8 行、双平台一致、引用状态机而非逐条列举、版本自动同步
  - token-baseline: 覆盖所有组件、支持 --compare 对比、CI warning 级别、pre-commit 可选检查

- **关键场景**：
  - 压缩后所有现有测试通过（逻辑完整性不退化）
  - 压缩后 lint 规则 0 error（warning 可接受）
  - Token baseline 工具正确输出每个组件的 {lines, chars, estimatedTokens}
  - `--compare baseline.json` 正确输出变化量和百分比

- **验收检查**：
  - AC1: `hooks/session-start` 的 `session_context` ≤ 150 字符
  - AC2: 9 个 skill 累计 ≤ 1,800 行
  - AC3: `.claude/always/phase-guard.md` ≤ 8 行
  - AC4: `node scripts/token-baseline.mjs` 输出所有组件的完整度量
  - AC5: `node scripts/lint/lint-skills.mjs --include token` 0 error
  - AC6: `npm test` 所有测试通过
  - AC7: `node scripts/check-version-consistency.mjs` 通过
  - AC8: 总计估算 token 从 ~24,580 降至 ≤ 17,000（压缩 ≥30%）

## Design Constraints

- **架构约束**：
  - D1: 渐进式"去重-精简-统一"策略 — 不对 skill 进行结构性重写，仅去除冗余
  - D2: Phase guard 改为引用状态名称，由 workflow-start 解释状态含义
  - D3: Hooks 注入提取共享内容变量，三平台分支仅包装输出格式
  - D4: Token 度量以字符计数为基础（英文 1:4，中文 1:1.5），不依赖外部 tokenizer API
  - D5: 复用现有 `lint-skills.mjs` 框架，新增 `--include token` 分类

- **接口约束**：
  - 新模块 `scripts/token-baseline.mjs` 导出 `{ lines, chars, estimatedTokens }` 结构
  - 新模块 `scripts/lint/rules/token-rules.mjs` 导出标准 lint 规则函数 `{ pass, failures }`
  - `lint-skills.mjs` 的 `--include` 参数向后兼容

- **依赖约束**：
  - 零运行时依赖（不引入 tiktoken 等 npm 包）
  - Node >= 22（与项目现有要求一致）

- **数据约束**：
  - `token-baseline.json` 格式：`{ _comment, timestamp, version, components: { [path]: { lines, chars, estimatedTokens } } }`

## Task Batches

### Batch 1: Token 度量基线与 Lint 规则
- **目标**：建立度量工具和 lint 基础设施
- **输入**：无（首批）
- **输出**：`scripts/token-baseline.mjs`、`scripts/lint/rules/token-rules.mjs`、修改后的 `scripts/lint/lint-skills.mjs`
- **完成标准**：`node scripts/token-baseline.mjs` 正确输出度量；`node scripts/lint/lint-skills.mjs --include token` 可执行；所有新增测试通过

### Batch 2: Hooks + Phase Guard 压缩
- **目标**：压缩注入内容
- **输入**：Batch 1 的 lint 规则用于验证
- **输出**：压缩后的 `hooks/session-start`、`.claude/always/phase-guard.md`、`GEMINI.md`
- **完成标准**：session_context ≤ 150 字符；phase-guard.md ≤ 8 行；双平台内容一致；版本号一致

### Batch 3: Skill 压缩 — Group A
- **目标**：压缩 5 个小/中型 skill
- **输入**：Batch 1 的 lint 规则
- **输出**：压缩后的 need-explorer、spec-merger、code-reviewer、release-archivist、contract-builder SKILL.md
- **完成标准**：每个 ≤ 各自目标行数；lint 0 error；逻辑完整性验证通过

### Batch 4: Skill 压缩 — Group B + workflow-start 优化
- **目标**：压缩 4 个大型 skill，优化初始化
- **输入**：Batch 3 的压缩经验
- **输出**：压缩后的 bug-investigator、spec-writer、build-executor、workflow-start SKILL.md
- **完成标准**：workflow-start ≤ 300 行；其余各 ≤ 各自目标；9 个 skill 累计 ≤ 1,800 行；lint 0 error

### Batch 5: CI 集成 + 基线快照 + 最终验证
- **目标**：完成集成和度量
- **输入**：Batch 2-4 的所有压缩结果
- **输出**：CI workflow 更新、`token-baseline.json`、版本一致性验证
- **完成标准**：所有 AC 满足；总计 token ≤ 17,000；npm test 通过；doctor 通过

## Test Obligations

- **必须先从失败测试开始的行为**：
  - `token-baseline.mjs` 对已知文件的度量输出（先写测试验证输出结构）
  - `token-rules.mjs` 对超限文件的检测（先写测试验证检测逻辑）
  - `lint-skills.mjs --include token` 参数解析（先写测试验证参数识别）

- **必需的边界情况**：
  - 空文件（0 行）的度量不应报错
  - 中文为主的 skill 文件（如 need-explorer）的 token 估算准确度
  - 代码块解析对嵌套 markdown 的容错
  - `--compare` 模式下基线文件缺失时的错误处理

- **回归敏感区域**：
  - `npm test` 全量测试套件（任何 skill 压缩不能改变行为）
  - `ssf validate` 对压缩后的 artifacts 验证
  - `check-version-consistency.mjs` 对新增文件的版本检查
  - Guard check 的 transition 矩阵（workflow-start 的 guard check 最小化不能破坏 transition 验证）

## Execution Mode

- **模式**：Batch Inline（逐 batch 执行，每 batch 内 TDD）
- **选择理由**：5 个 batch 有明确的依赖链（Batch 1 → 2/3/4 → 5），但 Batch 2/3/4 之间相对独立。Batch Inline 允许在完成 Batch 1 后并行推进 Batch 2 和 3，最后汇聚到 Batch 5

## Verification Dimensions

| 维度 | 状态 | 发现 |
|------|------|------|
| Completeness | Pending | — |
| Correctness | Pending | — |
| Coherence | Pending | — |

**总体结论**：Pending（在执行完成后由 code-reviewer 填充）

## Review Gates

- **强制审查点**：
  - Batch 1 完成后：审查 token baseline 工具和 lint 规则的正确性
  - Batch 4 完成后：审查所有 9 个 skill 的逻辑完整性（关键 gate）
  - Batch 5 完成后：最终 code-reviewer 审查所有变更

- **阻塞类别**：
  - Critical: npm test 失败、lint 规则 error、逻辑完整性缺失
  - Important: lint warning、token 压缩未达目标
  - Minor: 注释措辞、变量命名

## Escalation Rules

- **何时回退到 `specifying`**：如果压缩导致 skill 指令产生歧义且无法通过简单修复恢复，回退修改 specs
- **何时回退到 `bridging`**：如果压缩实现发现设计决策不可行（如目标行数过于激进导致逻辑必须退化），回退修改合同
- **何时不得继续实现**：
  - 任何 skill 压缩后无法通过现有测试
  - lint 规则检测到逻辑完整性缺失
  - `ssf doctor` 报告插件健康问题
  - 版本号不一致（`check-version-consistency.mjs` 失败）

## Requirements Coverage

所有 22 个需求均映射到至少一个执行 batch：

| 需求来源 | 需求数 | 覆盖 Batch | 状态 |
|----------|--------|-----------|------|
| hooks-injection | 4 | Batch 2 | ✅ |
| skill-instructions | 6 | Batch 3, 4 | ✅ |
| workflow-start-init | 3 | Batch 4 | ✅ |
| phase-guard-injection | 4 | Batch 2 | ✅ |
| token-baseline | 5 | Batch 1, 5 | ✅ |

无未覆盖需求。
