# VS Code Spec Superflow Plugin 配置指南

完整的 Spec Superflow 仓库作为一个 Agent Plugin 安装，包含 Agent、Skills、
Commands、Templates、CLI 源码和一个轻量的 bootstrap MCP。项目仓库不需要复制
这些公共资源，也不需要再下载另一份 Spec Superflow。

## Plugin 结构

```text
spec-superflow-plugin/
  .plugin/plugin.json
  plugin.json
  agents/
  skills/
  commands/
  servers/spec-superflow-mcp-launcher.cmd
  servers/spec-superflow-mcp.mjs
  scripts/
  templates/
  .mcp.json
  package.json
  .github/plugin/marketplace.json   # 可选的分发元数据
```

VS Code 按以下顺序识别 manifest：

1. `.plugin/plugin.json`
2. 根目录 `plugin.json`
3. `.github/plugin/plugin.json`
4. `.claude-plugin/plugin.json`

本仓库使用 OpenPlugin manifest，因此 `.mcp.json` 可以通过 `${PLUGIN_ROOT}`
启动 Plugin 内的 Server。

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

格式要求：

| 项目 | 要求 |
|---|---|
| `name` | 小写字母、数字和连字符 |
| `version` | 语义化版本 |
| `author` | 对象格式，至少包含 `name` |
| 组件路径 | 相对于 Plugin 根目录且真实存在 |
| Agent | `agents/*.agent.md` |
| Skill | `skills/<name>/SKILL.md`，目录名和 frontmatter 名称一致 |
| Command | `commands/*.md`，使用 VS Code Prompt 字段 `name`、`description`、`agent` 和 `tools`；不使用 `allowed-tools` |
| MCP | manifest 指向 `.mcp.json`，使用 `${PLUGIN_ROOT}` 引用内置文件 |

## 运行结构

bootstrap MCP 提供四个初始化工具：

- `spec_superflow_cli_status`：只读检查 Node、npm、已安装 `ssf` 的路径和
  版本，以及 Plugin 版本。
- `spec_superflow_install_cli`：得到用户确认后，只从当前 `${PLUGIN_ROOT}`
  安装或升级全局 CLI。
- `spec_superflow_optional_mcp_status`：检查可选 MCP 定义是否已注册，不读取
  URL 或 Token。
- `spec_superflow_install_optional_mcp`：用户选择启用后，通过 VS Code CLI
  注册 Plugin 内置的 stdio Server。

它不执行 Spec 工作流命令，不接受其他包地址、registry 或安装路径，也不把
URL、Token 作为工具参数。

安装完成后，Skills 直接执行 `ssf state`、`ssf validate`、`ssf guard` 等全局
CLI 命令。bootstrap 会用 `ssf --version` 校验版本；升级失败时恢复原来可用的
CLI，不把 npm 返回成功直接当成 `READY`。

运行前需要 Node.js 和 npm。CLI 直接来自已安装的 Plugin，不需要第二份 Spec
仓库或单独的压缩包。

## 可选的 URL 和 Token MCP

本地 stdio MCP 可以把源码和运行文件一起放进 Plugin。`stdio` 只是 VS Code
与 Server 进程之间的通信方式，不代表 Server 必须独立安装。Plugin 可以像
bootstrap MCP 一样，通过
`${PLUGIN_ROOT}/servers/spec-superflow-mcp-launcher.cmd` 启动内置的
JavaScript Server。macOS 和 Linux 上，如果从图形界面启动的 VS Code 没有
继承 Node.js 路径，启动器会从用户登录 Shell 查找 Node.js；Windows 上需要
让 Node.js 位于系统 `PATH`。

业务 MCP 是可选能力。用户选择跳过时返回：

```text
workflow=READY, optionalMcp=SKIPPED
```

CLI、Skills、规划、测试和 Review 工作流仍然可以正常使用。

凭据配置需要按作用域处理：

| 配置位置 | 顶层 Server 字段 | 交互式 `inputs` |
|---|---|---|
| Agent Plugin `.mcp.json` | `mcpServers` | 启动内置 bootstrap Server；不在这里定义凭据 |
| 用户或项目 `mcp.json` | `servers` | 支持；首次启动弹窗，输入值由 VS Code 安全保存 |

用户在 `/workflow-init` 中选择启用后，
`spec_superflow_install_optional_mcp` 使用 VS Code `--add-mcp` 注册内置
定义。该工具不接收凭据。注册完成后返回：

```text
workflow=READY, optionalMcp=REGISTERED
```

然后在命令面板运行 **MCP: List Servers**，选择
**spec-superflow-optional-example**，再选择 **Start Server**。VS Code 会用
原生输入框询问服务 URL 和 Token，两项输入都保持可见，便于使用者核对；实际值
不会写入 MCP 配置文件或经过 Chat，而是由 VS Code 安全凭据存储保存。再次执行
`/workflow-init` 可验证运行中的 Server，并返回 `optionalMcp=READY`。

注册后的定义通过内置启动器运行 `servers/token-example-mcp.mjs`。等价配置
保存在 `examples/mcp/token-auth/` 供检查。Token 和具体服务 URL 不应提交到
Plugin 仓库。

## 安装和使用

1. 在 VS Code 命令面板运行 **Chat: Install Plugin From Source**。
2. 输入完整 Plugin 仓库的 Git 地址。
3. 在 Agent Plugins 视图确认 **Spec Superflow** 已启用。
4. 保持 VS Code 内置 **Agent**，输入 `/workflow-init` 并选择 Plugin 提供的候选项。
   用鼠标点击或按 **Tab**，让 VS Code 将它提交为结构化 Slash Command；不要把
   候选文字当普通消息直接发送。
5. 缺少 CLI 或版本不一致时确认安装。
6. 选择是否配置可选 MCP；跳过时返回
   `workflow=READY, optionalMcp=SKIPPED`。
7. 选择启用后等待 `optionalMcp=REGISTERED`，再运行
   **MCP: List Servers** 并启动 **spec-superflow-optional-example**。
8. 在 VS Code 的可见原生输入框填写 URL 和 Token，再执行一次
   `/workflow-init` 验证 `optionalMcp=READY`。
9. 初始化返回 `workflow=READY` 后选择 **Spec Superflow** 并描述需求；普通工作流只
   使用已经安装的 CLI，不负责安装或升级。

`/workflow-init` 只准备运行环境，不读取当前项目、不生成 change，也不启动需求。
应先在内置 **Agent** 执行该命令，再选择 **Spec Superflow**，避免开发 Agent
的状态机指令进入初始化请求。
开始需求前先执行 `/workflow-init`。Plugin 更新后也先重新执行一次，使 CLI
版本与 Plugin 保持一致。

本地调试可以在用户设置中注册仓库：

```jsonc
"chat.pluginLocations": {
  "/absolute/path/to/spec-superflow-plugin": true
}
```

## 多项目复用

Plugin 安装一次即可在多个项目中选择使用。各项目只维护自己的源码、测试、
项目 Skills、任务产物、Memory 和项目指导。不要把中央 Plugin 的 `agents/`、
`skills/`、`scripts/` 或 `templates/` 再复制到每个项目。

## 更新

更新 Plugin 源后，保持所有 manifest、`package.json` 和 `/workflow-init` 的
版本一致。重新执行 `/workflow-init`；如果已安装 CLI 版本较旧，bootstrap 会
先请求确认，再执行升级。

## 验证清单

| 检查 | 预期结果 |
|---|---|
| Plugin | 已安装、已启用且 Agent 可选择 |
| Command | `/workflow-init` 可发现 |
| bootstrap MCP | `spec-superflow` 启动并列出 CLI 与可选 MCP 初始化工具 |
| CLI 缺失 | 确认后从 Plugin 安装，版本一致才返回 `READY` |
| 版本一致 | 不重复安装 |
| 跳过可选 MCP | `workflow=READY, optionalMcp=SKIPPED` |
| 注册可选 MCP | `workflow=READY, optionalMcp=REGISTERED` |
| 启动可选 MCP | VS Code 询问可见的 URL 和 Token，并启动内置 Server |
| 验证可选 MCP | 再次执行 `/workflow-init` 返回 `workflow=READY, optionalMcp=READY` |
| 直接提需求 | 使用 `/workflow-init` 已准备好的 CLI |
| 多项目 | 复用同一 Plugin，各项目没有公共工作流副本 |

协议和单元测试不能替代真实 VS Code Chat 中的 Plugin 安装、Command 发现、
确认交互和初始化后工作流验证。

格式参考：[VS Code Agent plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins)
和 [MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)。
