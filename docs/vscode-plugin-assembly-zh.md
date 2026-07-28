# VS Code Agent Plugin 结构与迁移指南

本文面向 Plugin 维护者，说明如何把原来分散安装的 Agent、Skill、Slash
Command、脚本和 MCP Server 组合成一个可复用的 VS Code Agent Plugin。
安装和日常使用方式见
[VS Code Spec Superflow Plugin 配置指南](vscode-agent-plugin-zh.md)。

## 1. Plugin 解决什么问题

Agent Plugin 是一组 AI 开发资源的分发单元。安装一次后，可以在多个业务项目中
复用：

- Agent：定义可选择的工作模式和总体规则。
- Skill：定义某类任务的执行要求和结果。
- Command：提供用户主动触发的 `/command`。
- MCP：向 Agent 提供可调用工具。
- Scripts、Templates、Servers：为上述组件提供运行资源。

Plugin 和业务项目是两个独立层级：

```text
用户环境
  spec-superflow-plugin/       # 安装一次，集中维护
    plugin.json
    agents/
    skills/
    commands/
    servers/

业务项目 A/                    # 不复制公共 Plugin 文件
  .github/
  src/
  tests/
  changes/

业务项目 B/
  .github/
  src/
  tests/
  changes/
```

仅安装 Plugin 不会修改当前业务项目。只有用户明确执行会写入项目的功能，例如
`project-init` 或需求工作流，项目目录才会产生对应文件。

Plugin 本身不要求 `.github/copilot-instructions.md`。该文件如果存在于 Plugin
源码仓库，只约束维护 Plugin 仓库时的 Copilot 行为，不会自动复制到业务项目。

## 2. 仓库根目录要求

通过 **Chat: Install Plugin From Source** 安装时，VS Code 克隆的是一个完整
Git 仓库。`plugin.json` 必须位于克隆后仓库的根目录。

正确：

```text
my-agent-plugin/
  plugin.json
  skills/
  agents/
  .mcp.json
```

错误：

```text
my-agent-plugin/
  copied-folder/
    plugin.json
    skills/
    agents/
```

如果将现有 Spec 仓库复制到一个新的分发仓库，应复制仓库内容，而不是在外面再
包一层目录。安装地址必须是可被 Git clone 的仓库地址，不能使用
`https://.../tree/<branch>` 形式的网页地址。

## 3. 推荐目录结构

最小 Plugin 只需要 `plugin.json` 和至少一种组件。包含 Agent、Skill、Command
和内置 MCP 时，建议使用以下结构：

```text
my-agent-plugin/
  plugin.json                  # Plugin 主清单，必须在仓库根目录
  .mcp.json                    # Plugin 内置 MCP 清单

  agents/
    my-workflow.agent.md

  skills/
    workflow-start/
      SKILL.md
    project-init/
      SKILL.md
      references/              # 可选，Skill 的补充资料

  commands/
    workflow-init.md

  servers/
    mcp-launcher               # 可选，跨平台启动器
    bootstrap-mcp.mjs          # MCP Server 可执行入口

  scripts/                     # CLI 或 Skill 使用的脚本
  templates/                   # Skill 使用的工件模板
  docs/                        # 维护与使用说明
  package.json                 # 有 Node CLI、构建或测试时使用

  .github/plugin/
    marketplace.json           # 可选，仅用于 Marketplace 分发
```

`.plugin/plugin.json`、`.claude-plugin/plugin.json` 等清单可以作为其他宿主的
兼容入口，但不能代替直接安装时的根 `plugin.json`。多个清单存在时，名称、版本
和组件路径必须同步。

## 4. `plugin.json` 格式

完整工作流的最小清单：

```json
{
  "name": "my-agent-plugin",
  "description": "Shared development workflow.",
  "version": "1.0.0",
  "author": {
    "name": "Your Team"
  },
  "skills": "skills/",
  "agents": "agents/",
  "commands": "commands/",
  "mcpServers": ".mcp.json"
}
```

主要字段：

| 字段 | 要求 |
|---|---|
| `name` | 使用小写字母、数字和连字符，并在分发范围内唯一 |
| `description` | 简短说明 Plugin 提供的能力 |
| `version` | 使用语义化版本，例如 `1.2.0` |
| `author` | 对象格式，至少包含 `name` |
| `skills` | 相对 Plugin 根目录的 Skill 目录 |
| `agents` | 相对 Plugin 根目录的 Agent 目录 |
| `commands` | 相对 Plugin 根目录的 Command 目录 |
| `mcpServers` | 相对 Plugin 根目录的 MCP 配置文件 |

清单里声明的路径必须实际存在。路径统一以 Plugin 根目录为基准，不要写业务项目
路径、维护者电脑的绝对路径或另一个仓库的相对路径。

## 5. Skill 格式

每个 Skill 使用独立目录，入口固定为 `SKILL.md`：

```text
skills/
  api-implementation/
    SKILL.md
    references/
      internal-network.md
```

`SKILL.md` 至少包含 `name` 和 `description`：

```markdown
---
name: api-implementation
description: Implement an API change using the project's existing repository, mapper, and error-handling patterns.
---

# API Implementation

## Requirements

1. Read the relevant project guidance and existing implementation.
2. Reuse the existing Repository and Mapper boundaries.
3. Produce implementation and requirement-linked tests.

## Expected Result

- Changed files and behavior
- Verification commands and results
- Remaining risks
```

要求：

- 目录名、frontmatter `name` 和文档中的引用保持一致。
- `description` 写清触发场景，避免多个 Skill 同时匹配所有请求。
- Skill 只引用 Plugin 包内真实存在的资料。
- 多个 Skill 共享的运行能力应放进公共 CLI 或脚本，不要在每个 Skill 复制实现。
- 如果 Skill 要调用全局 CLI，直接写稳定命令，例如 `ssf validate`；不要假定当前
  业务项目中存在 `scripts/`。

## 6. Agent 格式

Agent 放在 `agents/*.agent.md`：

```markdown
---
name: My Workflow
description: Develop changes through the shared engineering workflow.
argument-hint: Describe the change to plan, implement, review, or resume.
user-invocable: true
---

# My Workflow

Use the linked workflow Skill to inspect the current state and route the work.

## Skills

- [workflow-start](../skills/workflow-start/SKILL.md)
- [project-init](../skills/project-init/SKILL.md)
```

Agent 负责：

- 定义总体边界和入口。
- 说明应加载哪些 Skill。
- 约束工具调用和工作流顺序。
- 让用户在 Agent 选择器中主动选择。

Agent 不应重复每个 Skill 的全部细节。阶段要求放在对应 Skill，Agent 只保留总控
规则和路由。

## 7. Slash Command 格式

Command 放在 `commands/*.md`。文件名通常对应 `/command-name`：

```markdown
---
name: workflow-init
description: Prepare the workflow runtime.
agent: My Workflow
tools:
  - 'my-bootstrap/*'
  - 'vscode/askQuestions'
---

# Initialize Workflow

1. Call the status tool.
2. Ask for confirmation before installation.
3. Verify the installed version.
4. Stop after reporting READY or BLOCKED.
```

Command 适合明确、短小、由用户主动触发的入口，例如安装、初始化和状态检查。
`tools` 只授予该命令实际需要的工具。不要为了省事配置任意工具通配符。

## 8. Plugin 内置 MCP

### 8.1 所需文件

将一个本地 stdio MCP 完整带入 Plugin，通常需要：

```text
plugin.json
.mcp.json
servers/
  my-mcp-server.mjs
  launcher
```

如果 Server 使用第三方依赖，还需要把它构建成可直接运行的单文件产物，或确保
依赖被包含在最终 Plugin 包中。不能假定安装 Plugin 时会自动执行 `npm install`。

### 8.2 Plugin `.mcp.json`

Plugin MCP 配置使用顶层 `mcpServers`：

```json
{
  "mcpServers": {
    "my-bootstrap": {
      "command": "${PLUGIN_ROOT}/servers/launcher",
      "args": [
        "${PLUGIN_ROOT}/servers/my-mcp-server.mjs"
      ],
      "cwd": "${PLUGIN_ROOT}"
    }
  }
}
```

`${PLUGIN_ROOT}` 由 Plugin Host 解析，适合引用已安装 Plugin 中的 Server、
脚本和资源。不要把开发电脑上的绝对路径提交到 `.mcp.json`。

本地 stdio MCP Server 至少需要正确处理：

- `initialize`
- `ping`
- `tools/list`
- `tools/call`

工具需要提供唯一 `name`、明确 `description` 和 JSON Schema
`inputSchema`。Server 的标准输出只能发送 MCP JSON-RPC 消息；诊断日志写到标准
错误，否则会破坏 stdio 协议。

### 8.3 带 URL 或 Token 的 MCP

不要把真实 URL、Token、密码或内部地址写进 Plugin。VS Code 用户级或项目级
`mcp.json` 使用顶层 `servers`，并可通过 `inputs` 收集配置：

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "service-url",
      "description": "Service URL",
      "password": false
    },
    {
      "type": "promptString",
      "id": "service-token",
      "description": "Service Token",
      "password": true
    }
  ],
  "servers": {
    "business-service": {
      "type": "stdio",
      "command": "/absolute/path/to/installed/plugin/servers/launcher",
      "args": [
        "/absolute/path/to/installed/plugin/servers/business-mcp.mjs"
      ],
      "env": {
        "SERVICE_URL": "${input:service-url}",
        "SERVICE_TOKEN": "${input:service-token}"
      }
    }
  }
}
```

注意两个配置层级不同：

| 位置 | 顶层字段 | 用途 |
|---|---|---|
| Plugin `.mcp.json` | `mcpServers` | 随 Plugin 自动发现无凭据的内置 Server |
| 用户或项目 `mcp.json` | `servers`、`inputs` | 保存用户选择，并由 VS Code 收集凭据 |

如果希望安装后由 `/workflow-init` 引导配置，推荐流程是：

1. Plugin 内置一个不需要凭据的 bootstrap MCP。
2. bootstrap 只检查和注册业务 MCP，不接收 URL 或 Token 参数。
3. 注册到 VS Code 用户级 MCP 配置。
4. VS Code 启动业务 MCP 时通过原生输入框收集 URL 和 Token。
5. 用户跳过业务 MCP 时，Plugin 的 Agent、Skill 和 Command 仍可正常使用。

### 8.4 哪些 MCP 可以组合进 Plugin

| MCP 类型 | 是否适合内置 | 处理方式 |
|---|---|---|
| 有源码、可本地运行的 stdio MCP | 适合 | 将编译产物和启动器放入 `servers/` |
| 依赖 Node/Python/Java 的 stdio MCP | 视环境而定 | 内置 Server，明确运行时前置条件 |
| 依赖外部已安装命令的 MCP | 可以配置但不完全自包含 | 安装时检查依赖，缺失时明确阻塞 |
| 远程 HTTP MCP | 不需要打包 Server 源码 | 保存 Server 定义，凭据由用户提供 |
| 无权分发的二进制或源码 | 不适合内置 | 仅提供配置模板和安装说明 |

## 9. 从分散资源迁移为 Plugin

按以下顺序迁移：

1. **盘点资源**：列出所有 Agent、Skill、Command、MCP、脚本、模板和运行时依赖。
2. **确定总入口**：选择一个 Agent 负责总体工作流，避免多个 Agent 重复定义规则。
3. **整理 Skills**：每个 Skill 移入 `skills/<name>/SKILL.md`，修正相互引用和脚本
   调用。
4. **整理 Commands**：只把用户需要主动触发的动作放进 `commands/`。
5. **整理 MCP**：将可分发的 stdio Server 放进 `servers/`，用 `.mcp.json` 注册；
   带凭据的定义放到用户级配置流程。
6. **创建 manifest**：在仓库根目录创建 `plugin.json`，声明真实存在的组件路径。
7. **移除项目假设**：不得要求业务项目预先复制 Plugin 的 `skills/`、`scripts/`
   或 `templates/`。
8. **验证完整包**：在一个没有旧 Skill、旧 MCP 和旧 CLI 的环境中安装并测试。

原有分散文件的对应关系：

| 原有资源 | Plugin 中的位置 |
|---|---|
| 单独复制的 `SKILL.md` | `skills/<name>/SKILL.md` |
| 多份 Agent 提示词 | `agents/*.agent.md` |
| 手工输入的初始化提示词 | `commands/<name>.md` |
| 用户手工配置的无凭据 MCP | `.mcp.json` + `servers/` |
| 带凭据 MCP | `servers/` + 用户级注册模板或初始化流程 |
| 每个项目复制的公共脚本 | Plugin `scripts/` 或安装后的全局 CLI |
| 每个项目复制的公共模板 | Plugin `templates/` |
| 项目自己的架构规范 | 继续保留在业务项目，不合并进公共 Plugin |

## 10. 安装与分支

直接从默认分支安装：

1. 运行 **Chat: Install Plugin From Source**。
2. 输入可 clone 的 Git 地址，例如
   `https://github.com/example/my-agent-plugin.git`。
3. 在 Agent Plugins 视图确认 Plugin 已启用。

不要输入 `/tree/branch-name` 网页地址。需要测试非默认分支时，先在本地切换到
目标分支，再在 VS Code 用户设置中注册：

```jsonc
"chat.pluginLocations": {
  "/absolute/path/to/my-agent-plugin": true
}
```

Marketplace 是另一种分发方式。只有需要维护多个 Plugin 的发现和版本入口时，才
需要 Marketplace 清单；单个 Plugin 通过 Source 或本地目录安装不需要
Marketplace，也不需要业务项目增加 `.github/`。

## 11. 验证清单

结构验证：

- 仓库根目录存在可解析的 `plugin.json`。
- manifest 声明的目录和 `.mcp.json` 全部存在。
- 每个 Skill 都有合法 frontmatter 和 `SKILL.md`。
- 每个 Agent、Command 的名称和引用能解析。
- `.mcp.json` 使用 `mcpServers`，路径通过 `${PLUGIN_ROOT}` 定位。
- 最终分发包包含 Server、脚本、模板和运行依赖，不包含 Token、缓存和临时文件。

VS Code 真实验证：

- Plugin 可通过 Source 或 `chat.pluginLocations` 被发现。
- Agent 出现在 Agent 选择器中。
- Skill 可被正确路由。
- Slash Command 可发现并执行。
- **MCP: List Servers** 能看到内置 Server。
- MCP 能完成 `tools/list` 和一次真实 `tools/call`。
- 带凭据 MCP 首次启动时由 VS Code 收集配置。
- 安装 Plugin 后，未执行项目命令的业务目录保持不变。

Spec Superflow 当前实现可作为完整参考：

```text
plugin.json
agents/spec-superflow.agent.md
skills/*/SKILL.md
commands/workflow-init.md
.mcp.json
servers/spec-superflow-mcp-launcher.cmd
servers/spec-superflow-mcp.mjs
examples/mcp/token-auth/
```

格式参考：

- [VS Code Agent plugins](https://code.visualstudio.com/docs/copilot/customization/agent-plugins)
- [VS Code MCP configuration reference](https://code.visualstudio.com/docs/copilot/reference/mcp-configuration)
