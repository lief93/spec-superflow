# VS Code Spec Superflow VSIX 配置指南

推荐的离线交付是一个 VSIX，其中同时包含完整 Agent Plugin、CLI 源码、两个
bootstrap Language Model Tools，以及可替换的一次性 Example MCP bridge。项目
仓库不需要复制公共资源，也不需要安装第二份 Spec Superflow。

需要自行组合或维护 Plugin 时，参见
[VS Code Agent Plugin 结构与迁移指南](vscode-plugin-assembly-zh.md)。

## Plugin 结构

```text
spec-superflow-<version>.vsix
  extension/package.json            # Language Model Tools + chatPlugins
  extension/extension.cjs           # 一次性 bridge
  extension/agent-plugin/
    plugin.json
    agents/
    commands/
    skills/
    scripts/
    servers/
    package.json
```

Extension manifest 通过 `chatPlugins: [{ "path": "./agent-plugin" }]` 暴露
内置 Agent Plugin。VSIX 内的 Agent Plugin 刻意不包含 `.mcp.json`：即使公司
策略关闭原生 VS Code MCP Host，只要允许 Extension Language Model Tools，
bootstrap 和 Example MCP bridge 仍可工作。不要同时启用同一 Plugin 的 Git
安装副本，否则可能出现重复 Spec Agent。

## 运行结构

Extension 提供两个初始化工具：

- `spec_superflow_cli_status`：只读检查 Node、npm、`npm prefix -g` 下的全局
  CLI、PATH 解析结果，以及 Plugin 版本。
- `spec_superflow_install_cli`：得到用户确认后，只从当前 `${PLUGIN_ROOT}`
  安装或升级全局 CLI。
`/workflow-init` 只使用这两个工具和原生确认工具。它不执行 Spec 工作流命令、
不配置业务 MCP，也不接受其他包地址、registry 或安装路径。

安装完成后，Skills 直接执行 `ssf state`、`ssf validate`、`ssf guard` 等全局
CLI 命令。bootstrap 只把 `npm prefix -g` 下的 CLI 作为安装和版本事实来源，
并要求普通 `ssf` 命令解析到同一文件；升级失败时恢复原来的全局 CLI，不把
npm 返回成功直接当成 `READY`。

运行前需要 Node.js 和 npm。CLI 直接来自 VSIX 内置 Plugin，不需要第二份 Spec
仓库、registry 或单独压缩包。

## Full 工作流的独立 Review

只有 `full` 工作流使用固定隐藏只读 Reviewer。可见 Primary 直接负责规划、实现、
测试和 Finding 修复。第一个语义检查点在 CLI 结构校验之后审查权威用户意图、
Proposal 和 Specs。通过后，Primary 要求用户
明确确认或调整目标、范围、行为和非目标，之后才能开始详细规划。

三个检查点都使用同一个固定身份 `Spec Superflow Reviewer`。每个阶段的首次 Review
都会创建全新的隔离上下文。第一次 `Request Changes` 后，Primary 只修复一次并在
同一个 Reviewer 上下文中完成一次对新候选的完整复审。第二次 `Request Changes`
立即 `BLOCKED`，不得第三次 Review 或推进工作流状态。较早的 Finding 或 verdict
不能作为当前候选的证据；后续阶段仍创建自己的全新上下文。

第二个检查点把全部已通过的上游规划与 Design 和 Tasks 一起审查。通过后，
Primary 默认给出覆盖主要选择、影响区域、Batch 形状、测试、Findings 和风险的
简明摘要，同时提供完整 `design.md` 和 `tasks.md` 路径。用户自行选择阅读深度，
并明确确认或调整实现方向。

第一次阻塞 Finding 返回 Primary 做一次有边界的直接修复；校验通过后，在该阶段
同一个 Reviewer 上下文中复审。Reviewer 必须重新读取完整当前候选，不能复用旧
verdict。只有穷尽仓库证据后才能提出 Question；真正属于
用户的决策由 Primary 一次询问一个，并附推荐答案。语义漂移需要重复受影响的
Review 和用户确认；只改变真实 Tasks 执行 checkbox 不需要复审。

这些指令和协议测试不能证明实际 Agent picker、全新 Reviewer 上下文、行为只读的
工具使用或 Primary 中介行为。真实 VS Code 1.123 验收仍为 `PENDING`。

### 最终 Review 与合并真实运行验收

实现完成后，精确 `full` 必须先完成全部机械门禁、适用的运行时检查、要求的证据行和
PR summary，再执行一次最终独立 Code Review。只有当前 Specs 明确要求交付包，或
`tasks.md > TDD Test Plan` 明确要求交付包时，才执行对应包检查。
Reviewer 读取冻结代码候选和精确
测试/风险上下文，判断测试是否覆盖需求与失败路径、是否只是镜像实现，但不运行
测试。第一次 `Request Changes` 返回 Primary，只修复一次定位到的目标；修复后
重新冻结受影响结果和完整候选，再在同一个 Reviewer 上下文中完成唯一一次复审。
第二次 `Request Changes` 立即 `BLOCKED`。当前结果为 `Approved` 后，只允许推进
工作流状态。

最终调用只包含 Change 目录和 `final` 阶段。Reviewer 运行只读的
`ssf review candidate`，自行发现当前工件、证据路径、changed files 和解析后的
`HEAD` 基线；Primary 不再准备 candidate、路径索引、证据摘要、结果 Schema、
tracked diff、untracked 源码正文或完整 artifact/source/test/evidence 正文。
Reviewer 从 candidate 读取 review base，自行执行只读的
`git status`、固定基线 `git diff`、`git log` 和必要的 `git show`，并逐项读取每个
changed-file entry 和每个 untracked 文件。候选计算不会写 Review Markdown、
bundle 或额外 report JSON。用户全局指令属于环境状态，不是 Plugin 交付内容。

执行隔离的真实 VS Code 1.123 合并验收时，应同时证明：

1. Agent picker 中只有 `Spec Superflow` 可由用户选择。
2. Primary 精确调用 `Spec Superflow Reviewer`，且没有注册或调用独立 Dev Agent。
3. Primary-only、跨阶段 canary 和前一次 invocation canary 在全新 Reviewer
   上下文中都不泄漏。
4. Reviewer 使用普通项目读取/终端工具执行要求的只读 Git 命令并读取 untracked
   canary；调用前后 candidate identity、porcelain status、cached diff、文件
   bytes 和 staged state 完全不变。Reviewer 不运行测试或除只读
   `ssf review candidate` 以外的工作流命令，不修改 Git，也不调用其他 Agent。
5. Reviewer 结果先返回 Primary，再由 Primary 修复定位目标或询问用户；Reviewer
   直接到用户的路径不算通过。

该 Chat 验收的 automation 为 `Unavailable`。在一次真实隔离运行保存原始 trace、
截图、包身份、canary 观测、Git/文件读取 trace、调用前后 candidate/worktree
hash、中介 trace 和环境恢复
记录之前，状态始终为 `PENDING`。静态 prompt、frontmatter、单元或协议测试不能把
这些真实运行断言转换为 PASS。诚实的 `PENDING` 是已披露的真实运行边界，
不会单独导致源码候选校验失败。

## 可替换的 Example MCP bridge

VSIX 还提供 `spec_superflow_example_mcp_read`。内置
`example-mcp-reader` Skill 只传用户给出的 item URL 或 key。第一次调用时，
Extension 使用 VS Code 可见输入框收集示例 URL，并把 Token 存入 VS Code
SecretStorage；两者都不是工具参数或 Chat 内容。

每次调用只临时启动 `servers/example-item-mcp.mjs`，执行一个固定白名单 MCP
工具，然后结束进程。上游示例只返回确定性的本地数据，不访问网络。公司内仓
可以用 Jira stdio MCP 替换该 Server 和固定工具映射，同时保持 Skill 到 Tool
的边界不变。Example MCP 与 `/workflow-init` 相互独立，不影响 CLI READY。

## 安装和使用

1. 在 VS Code 命令面板运行 **Extensions: Install from VSIX...**。
2. 选择离线 `spec-superflow-<version>.vsix` 并重新加载 VS Code。
3. 确认 Agent 选择器只出现一个 **Spec Superflow**；不要再同时安装 Git 版本。
4. 保持 VS Code 内置 **Agent**，输入 `/workflow-init` 并选择 Plugin 提供的候选项。
   用鼠标点击或按 **Tab**，让 VS Code 将它提交为结构化 Slash Command；不要把
   候选文字当普通消息直接发送。命令会进入隐藏的 **Spec Superflow Setup**；
   它只能使用两个 Extension bootstrap tools 和原生确认工具，不能读取项目、
   使用终端或访问 Memory。
5. 缺少 CLI 或版本不一致时确认安装。
6. 初始化返回 `READY` 后选择 **Spec Superflow** 并描述需求；普通工作流只
   使用已经安装的 CLI，不负责安装或升级。

`/workflow-init` 只准备运行环境，不读取当前项目、不生成 change，也不启动需求。
应先在内置 **Agent** 执行该命令，再选择 **Spec Superflow**，避免开发 Agent
的状态机指令进入初始化请求。
命令完成后点击 **Return to Agent** 返回同一 Chat 的内置 **Agent**，之后可以
在同一 Chat 中重复执行，不需要新建 Chat。
开始需求前先执行 `/workflow-init`。Plugin 更新后也先重新执行一次，使 CLI
版本与 Plugin 保持一致。

Example MCP 由对应 Skill 在需要时调用，不属于初始化步骤。

## 多项目复用

Plugin 安装一次即可在多个项目中选择使用。各项目只维护自己的源码、测试、
项目 Skills、任务产物、Memory 和项目指导。`project-init` 生成：

```text
.github/instructions/spec-superflow.instructions.md
docs/project/project-guidelines.md
```

如果项目已有 `.github/copilot-instructions.md`，其内容保持不变。不要把中央
Plugin 的 `agents/`、`skills/`、`scripts/` 或 `skills/*/references/` 再复制到每个项目。

## 更新

用新版离线 VSIX 覆盖安装并重新加载 VS Code，然后执行 `/workflow-init`；如果
全局 CLI 较旧，会先请求确认，再从新版 VSIX 内置 Plugin 执行升级。

## 验证清单

| 检查 | 预期结果 |
|---|---|
| Plugin | 已安装、已启用且 Agent 可选择 |
| Command | `/workflow-init` 可发现 |
| bootstrap tools | `specSuperflowCliStatus` 和 `specSuperflowInstallCli` 可用 |
| CLI 缺失 | 确认后从 Plugin 安装，版本一致才返回 `READY` |
| 版本一致 | 不重复安装 |
| Example MCP | Skill 调 `spec_superflow_example_mcp_read`，单次进程启动并退出 |
| 凭据 | 原生可见输入框；Token 不进入 Chat 或工具返回值 |
| 直接提需求 | 使用 `/workflow-init` 已准备好的 CLI |
| project-init | 生成独立 instructions，根 instructions 不变 |
| 多项目 | 复用同一 Plugin，各项目没有公共工作流副本 |

协议和单元测试不能替代真实 VS Code Chat 中的 Plugin 安装、Command 发现、
确认交互和初始化后工作流验证。

格式参考：[VS Code Agent plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins)。
