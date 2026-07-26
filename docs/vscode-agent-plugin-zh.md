# VS Code Spec Superflow Plugin 配置指南

本方案把完整的 Spec Superflow 仓库作为一个 VS Code Agent Plugin。安装 Plugin
时，VS Code 会克隆整个仓库，因此 Agent、Skills、Commands、Templates、脚本和
内置 MCP bridge 会一起安装，不需要再安装或复制另一份 Spec Superflow。

## 目标结构

```text
spec-superflow-plugin/
  .plugin/plugin.json              # OpenPlugin manifest
  plugin.json                      # 可选：跨工具兼容的 manifest 副本
  agents/
    spec-superflow.agent.md        # 可选择的 Agent
  skills/
    <skill-name>/
      SKILL.md                     # 工作流 Skill
  commands/
    workflow-init.md               # /workflow-init 自检命令
  servers/
    spec-superflow-mcp.mjs         # 内置 MCP bridge
  scripts/                         # 确定性工作流实现
  templates/                       # Spec、Design、Tasks 等模板
  .mcp.json                        # MCP Server 启动配置
  package.json                     # 版本和 Node 要求
  .github/
    plugin/marketplace.json        # 可选：发布为 marketplace 时使用
    copilot-instructions.md        # 可选：仅约束本仓库自身的维护
```

`scripts/`、`templates/` 和 Server 虽然不是 manifest 中独立注册的组件，但会随
整个仓库一起安装，并由 Skill 或 MCP Server 使用。

## Plugin 格式要求

VS Code 按以下顺序识别 manifest：

1. `.plugin/plugin.json`
2. 根目录 `plugin.json`
3. `.github/plugin/plugin.json`
4. `.claude-plugin/plugin.json`

本仓库使用 `.plugin/plugin.json`，因此属于 OpenPlugin 格式，可以在 MCP 配置中
使用 `${PLUGIN_ROOT}` 引用安装后的 Plugin 根目录。

最小 manifest：

```json
{
  "name": "spec-superflow",
  "description": "Spec-driven development workflow.",
  "version": "0.14.0",
  "author": {
    "name": "Your Team"
  },
  "skills": "skills/",
  "agents": "agents/",
  "commands": "commands/",
  "mcpServers": ".mcp.json"
}
```

需要遵守：

| 项目 | 要求 |
|---|---|
| `name` | 只能使用小写字母、数字和连字符，最长 64 字符 |
| `version` | 使用语义化版本，例如 `0.14.0` |
| `author` | 使用对象格式，至少包含 `name` |
| 组件路径 | 相对于 Plugin 根目录；目录必须真实存在 |
| Agent | 放在 `agents/`，文件名以 `.agent.md` 结尾 |
| Skill | `skills/<name>/SKILL.md`；目录名与 frontmatter 中的 `name` 一致 |
| Skill 名称 | 使用 kebab-case，不添加命名空间前缀 |
| Command | 放在 `commands/`，Markdown frontmatter 中声明 `name` 和 `description` |
| MCP | 顶层字段必须是 `mcpServers`；Plugin 内文件通过 `${PLUGIN_ROOT}` 引用 |

如果同时保留多个 manifest，`name`、`version` 和组件路径必须同步。

## 内置运行方式

`.mcp.json`：

```json
{
  "mcpServers": {
    "spec-superflow": {
      "command": "node",
      "args": [
        "${PLUGIN_ROOT}/servers/spec-superflow-mcp.mjs"
      ],
      "cwd": "${PLUGIN_ROOT}"
    }
  }
}
```

MCP bridge 提供：

- `spec_superflow_health`：验证 Plugin 版本和内置运行时。
- `spec_superflow_run`：在当前打开的项目中执行 Plugin 自带的确定性工作流命令。

Agent 将 Skill 中的逻辑命令 `ssf <args>` 转换为
`spec_superflow_run(workspace, args)`。脚本来自 Plugin 仓库，生成的 Spec、
Design、Tasks、Memory、测试和代码仍写入当前打开的项目。

`/workflow-init` 只调用 `spec_superflow_health` 检查 Plugin 是否完整，不下载、
安装或更新其他包。

运行要求只有：

- VS Code 已启用 Agent Plugin 功能。
- GitHub Copilot Chat 可以使用 Agent、Command 和 MCP 工具。
- `node` 可用并满足 `package.json` 中的版本要求。

## 从现有 Spec 仓库制作 Plugin

如果已有一个单独仓库用于维护 Spec Superflow：

1. 将 Spec Superflow 的完整仓库内容放到该仓库根目录。
2. 保留 `agents/`、`skills/`、`commands/`、`servers/`、`scripts/` 和
   `templates/`，不要只复制 `.github/`。
3. 按上面的结构添加或检查 `.plugin/plugin.json` 和 `.mcp.json`。
4. 确保 `dist/` 等运行时文件已经提交；使用者不应在安装后执行构建。
5. 将仓库提交到可被使用者 Git 客户端访问的 Git 地址。

`.github/` 不是直接安装 Plugin 的必需目录：

- `.github/plugin/marketplace.json` 只在需要 marketplace 安装和版本发现时使用。
- `.github/copilot-instructions.md` 只约束维护这个 Plugin 仓库时的开发行为。
- 它不会替代 `.plugin/plugin.json`，也不会自动把目录中的文件注册成 Plugin
  Agent 或 Skill。

## 安装和使用

1. 在 VS Code 命令面板运行 **Chat: Install Plugin From Source**。
2. 输入 Plugin 仓库的 Git 地址。
3. 在 Extensions 中搜索 `@agentPlugins @installed`，确认
   **Spec Superflow** 已启用。
4. 在 Chat Agent 选择器中选择 **Spec Superflow**。
5. 执行 `/workflow-init`，预期返回 `READY`。
6. 打开任意项目，描述需求并启动工作流。

也可以先克隆仓库，再通过用户设置注册本地目录：

```jsonc
"chat.pluginLocations": {
  "/absolute/path/to/spec-superflow-plugin": true
}
```

Plugin 安装一次即可在多个项目中复用。项目仓库只保留自己的：

```text
.github/copilot-instructions.md
.github/instructions/
.github/skills/
changes/
.spec-superflow/
应用源码和测试
```

不要把 Plugin 的 `agents/`、`skills/`、`scripts/` 或 `templates/` 再复制到每个
项目。项目级 Agent 或 Skill 与 Plugin 中同名时，项目级配置会优先，可能导致
Plugin 组件被忽略。

## 更新

1. 更新 Plugin 源仓库中的 Spec Superflow 文件。
2. 同步修改所有 manifest 和 marketplace 中的 `version`。
3. 提交并推送仓库。
4. 在 VS Code 中运行 **Extensions: Check for Extension Updates**，或重新执行
   **Chat: Install Plugin From Source**。
5. 再次执行 `/workflow-init`，确认返回的新版本与仓库一致。

不需要单独维护 CLI 版本。

## 验证清单

| 检查 | 预期结果 |
|---|---|
| Plugin 安装 | Agent Plugins 中显示并启用 Spec Superflow |
| Agent | Agent 选择器中可以选择 Spec Superflow |
| Command | `/workflow-init` 可发现并返回 `READY` |
| Skills | Agent 可以进入 `workflow-start` 并路由到对应 Skill |
| MCP | `MCP: List Servers` 显示 `spec-superflow` |
| MCP 工具 | `spec_superflow_health` 和 `spec_superflow_run` 可调用 |
| 项目隔离 | 产物只写入当前打开的项目，不写入 Plugin 安装目录 |
| 多项目复用 | 两个项目使用同一个 Plugin，且没有工作流目录副本 |
| 更新 | 更新仓库版本后，VS Code 加载的新版本与 `/workflow-init` 一致 |

单元测试只能证明 manifest、Server 协议和脚本调用成立。最终验收仍应在真实
VS Code Chat 中完成 Command 发现、MCP 启动和一次工作流调用。

格式依据：[VS Code Agent plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins)
和 [GitHub Copilot CLI plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)。
