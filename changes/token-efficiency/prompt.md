# Token 效率优化 — 新会话启动提示语

> 将此提示语复制到新会话中，配合 `/workflow-start` 启动。

---

## 背景

spec-superflow v0.8.7 刚完成 **state-machine-skill-audit**（PR #13，已 squash merge 到 main）。该 change 对状态机、Skill 质量、DP 协议做了全面加固：

- ✅ Guard 矩阵补全：7 个检查维度，43 个回归测试，DP gate（DP-3/DP-4 强制执行）
- ✅ Skill 质量审计：5 条 lint 规则，9 个 skill 从 33 个问题降至 0
- ✅ Parser 双语支持修复（extractSection 不一致）
- ✅ F1 Document Map + F2 增量确认 + F5 DP Gate Guard 全部修复
- 📝 C（跨平台一致性）留给 v1.0.0

完整上下文见 `changes/state-machine-skill-audit/`（proposal + specs + design + tasks + execution-contract）。

## 本次 Change：Token 效率优化

### 问题

spec-superflow 作为一个 prompt 注入型 workflow 插件，每次会话都会加载 hooks、phase-guard、skill 指令等。当前没有系统化度量过 token 开销，可能存在：

1. **Hooks 注入冗余**：`hooks/session-start` 声称 "~40 tokens"，但实际内容可能大于此数
2. **Skill prompt 膨胀**：9 个 skill 累计约 2300 行 SKILL.md，部分指令可能有压缩空间（重复的模板说明、过长的示例）
3. **workflow-start 初始化开销**：每次启动都要 inspect change directory、run update check、run guard checks、run infer-workflow——能否更轻量？
4. **Phase guard 注入**：`.claude/always/phase-guard.md` 和 `GEMINI.md` 中的注入内容是否最小化？
5. **lint/guard 运行时开销**：每次 `ssf state transition` 都跑 guard，每次 commit 都跑 version check——这些检查的耗时和 token 开销是否合理？

### 范围

- hooks/session-start 内容审查与压缩
- 9 个 skill SKILL.md 的精简（保留逻辑，去除冗余措辞）
- workflow-start 初始化的必要步骤审查（哪些可以延迟？哪些可以跳过？）
- phase-guard 注入内容最小化
- 建立 token 度量基线（各 skill 行数/字符数/token 估算，CI 中可选 enforce）

### 范围外

- 跨平台一致性（→ v1.0.0）
- 新功能开发
- 已有门禁的削弱（不能为了省 token 而砍掉 guard 检查）

### 沟通偏好

逐步确认每个关键决策。允许破坏性变更（skill 内容重写、结构重组均可）。

### 启动方式

```
/plugin update spec-superflow@spec-superflow
/reload-plugins

用 workflow-start 开始 token 效率优化
```

### 关键参考文件

- `hooks/session-start` — 当前注入内容
- `.claude/always/phase-guard.md` — Claude Code 的 phase guard
- `GEMINI.md` — Gemini CLI 的 phase guard
- `skills/*/SKILL.md` — 9 个 skill 的完整指令
- `scripts/guard/guard.mjs` + `scripts/guard/checks/` — guard 系统
- `scripts/check-version-consistency.mjs` — pre-commit 检查
- `scripts/lint/lint-skills.mjs` — lint 框架（本次 change 会新增 token 相关规则）
- `changes/state-machine-skill-audit/` — 上一轮的完整工件（参考其结构和格式）
