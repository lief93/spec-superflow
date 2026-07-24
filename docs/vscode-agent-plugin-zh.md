# VS Code Agent Plugin 多项目复用指南

本方案将 spec-superflow 作为 VS Code 用户级 Agent Plugin 安装一次，在多个业务
仓库中按需选择使用。业务仓库不需要复制中央 Agent、Skills、scripts 或
templates。

## 最终结构

```text
VS Code 用户环境
  Spec Superflow Agent Plugin
    agents/       可选择的 Spec Superflow Agent
    skills/       统一维护的工作流 Skills
    templates/    统一维护的文档模板
    .mcp.json     可选的中央 MCP 配置

全局命令
  ssf             状态、校验、Guard、Task Brief、Review Package 等确定性能力

业务仓库 A / B / C
  .github/copilot-instructions.md   项目架构和编码规则
  .github/instructions/             项目专属 Instructions
  .github/skills/                   项目或业务专属 Skills
  changes/                          当前需求的规划和证据
  .spec-superflow/                  项目共享 Memory
  application code                 业务代码和测试
```

Plugin 和全局 CLI 由工作流维护者统一发布。项目规则、任务产物和代码仍由各业务
仓库维护。

## 安装

### 1. 安装全局 CLI

从公司内部 npm registry、离线安装包或批准的 Git 源安装与 Plugin 相同版本的
CLI：

```bash
npm install -g spec-superflow@0.13.0
ssf --version
```

`ssf --version` 应输出 `0.13.0`。版本一致由发布和安装流程人工保证。
`ssf doctor` 用于维护者检查 spec-superflow 源仓库结构，不用于业务仓库的安装验证。

### 2. 安装 VS Code Agent Plugin

1. 打开 VS Code 命令面板。
2. 运行 **Chat: Install Plugin From Source**。
3. 输入 spec-superflow 内部 Git 仓库地址。
4. 在 Extensions 中搜索 `@agentPlugins @installed`，确认 Plugin 已启用。
5. 在 Chat 的 Agent 选择器中确认可以选择 **Spec Superflow**。

Plugin 安装在当前 VS Code 用户配置中，不属于当前业务仓库。

## 在多个项目中使用

在任意业务仓库中：

1. 打开仓库。
2. 在 Chat Agent 选择器中选择 **Spec Superflow**。
3. 用普通需求描述开始或恢复工作流。

例如：

```text
使用 SDD 工作流实现订单列表的空状态。先检查需求和项目上下文，
生成规划文档，得到我的确认后再开发。
```

Agent 从中央 Plugin 加载工作流 Skills，通过全局 `ssf` 执行确定性命令，并将
`changes/`、Memory、测试和代码写入当前打开的业务仓库。

切换到另一个仓库后，选择同一个 **Spec Superflow** Agent 即可复用，无需再次
复制或安装工作流文件。切换到其他 Agent 后，Spec Superflow 的专属工作流不再
生效，也不需要卸载其他 Agent。

## 业务仓库保留什么

业务仓库只保留项目自身内容：

| 内容 | 位置 | 作用 |
|---|---|---|
| 项目规则 | `.github/copilot-instructions.md` | 架构边界、编码规范、经典实现 |
| 目录级规则 | `.github/instructions/` | 特定模块或文件范围的规则 |
| 项目 Skills | `.github/skills/` | 业务或内部框架专属能力 |
| 任务产物 | `changes/<change-name>/` | Spec、Design、Tasks、Contract、Evidence |
| 共享 Memory | `.spec-superflow/` | 经验证且值得复用的项目事实 |
| 实现产物 | 项目源码和测试目录 | 业务代码、Unit Test、UI Test、设备测试 |

不要将中央 `agents/`、`skills/`、`scripts/` 或 `templates/` 复制进业务仓库。
仓库专属 Skill 应避免与中央工作流 Skill 使用相同名称。

## CLI 与 Plugin 的职责

Plugin 负责：

- 提供可选择的 Agent。
- 决定当前工作流阶段和应使用的 Skill。
- 维护通用工作流说明和模板。

全局 `ssf` 负责：

- `state`、`validate`、`sync` 和 `audit`。
- `check-update`、`infer-workflow` 和 `guard`。
- `task-brief` 和 `review-package`。
- 项目基线与 Memory 的结构校验。

业务仓库不需要本地 `scripts/`。Skill 中的工作流命令统一通过 `ssf` 执行。

## 项目 Instructions 与 Phase Guard

`.github/copilot-instructions.md` 归业务仓库所有。Spec Superflow Agent 不执行
`ssf inject`，避免覆盖项目已有的架构和编码规则。当前阶段由所选 Agent 和
`workflow-start` 每次根据任务文件重新判断。

## MCP

Plugin 根目录的 `.mcp.json` 是中央 MCP 配置入口。当前默认配置为空：

```json
{
  "mcpServers": {}
}
```

只有在 MCP 服务命令、权限、负责人和内网安装方式明确后再统一配置。Plugin
启用时，其 MCP 可能对同一 VS Code 用户环境中的多个仓库可见，因此不要写入
项目密钥或机器专属凭据。

## 更新

发布新版本时：

1. 工作流维护者发布同版本 Plugin 和 CLI。
2. 使用者更新全局 CLI。
3. 在 VS Code Agent Plugins 视图更新 Plugin；内部 Git 源不支持自动更新时，
   重新运行 **Chat: Install Plugin From Source**。
4. 执行 `ssf --version`，确认与 Plugin 发布版本一致。

不要只更新 Plugin 或只更新 CLI。

## 验证多项目复用

至少使用两个无关业务仓库验证：

1. 两个仓库都能选择同一个 **Spec Superflow** Agent。
2. 两个仓库都没有中央 `scripts/`、`skills/` 或 `templates/` 副本。
3. Chat 能自动进入 `workflow-start` 并执行 `ssf guard`、`ssf validate` 等命令。
4. 生成的任务文档和代码只出现在当前业务仓库。
5. 两个仓库分别读取自己的 Copilot Instructions 和项目 Skills。
6. 切换到其他 Agent 后，不再应用 Spec Superflow 工作流。

## 常见问题

### Chat 提示找不到 `ssf`

确认 CLI 安装在 VS Code Terminal 使用的同一环境：

```bash
command -v ssf
ssf --version
```

Remote SSH、WSL 和 Dev Container 的命令运行在远端环境，需要在对应环境安装
CLI。

### Agent 选择器中没有 Spec Superflow

检查 `@agentPlugins @installed`、Plugin 是否启用，以及安装的 Git 源是否包含
根目录 `plugin.json` 和 `agents/spec-superflow.agent.md`。

### Chat 使用了旧 Skill

删除业务仓库中以前复制的 spec-superflow Skills，并检查用户级 Skills 中是否
还有同名旧版本。中央工作流只保留一份。

### 产物写入错误仓库

确认 VS Code 当前打开的 workspace 和 Chat Terminal 工作目录。任务产物必须
写入当前业务仓库，不能写入 Plugin 安装目录。
