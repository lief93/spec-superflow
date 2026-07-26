# 内网 AI 执行清单

将本文件和 `release-assets/v0.14.0/` 一起带入内网。把下面内容交给内网 AI，
并提供实际业务仓库、鸿蒙仓库和公司业务 Skills 的路径。

## 可直接交给内网 AI 的任务

```text
目标：在当前公司电脑验证 Spec Superflow v0.14.0，并保留可审计 evidence。

输入：
- 离线目录：<OFFLINE_BUNDLE_DIR>
- 普通业务仓库：<BUSINESS_REPO>
- Android→鸿蒙仓库：<HARMONY_REPO>
- 公司业务 Skills：<BUSINESS_SKILLS_PATH>

约束：
- 不访问公网，不修改 npm registry，不使用 sudo。
- 不覆盖业务仓库已有 Copilot Instructions、Skills 或 MCP 配置。
- 不把中央 Agent、Skills、scripts、templates 复制到业务仓库。
- 每项只按实际命令和报告判定 Pass/Fail；失败时保存最小错误摘要。
- 默认 Plugin 的 .mcp.json 为空。只有配置并启动了公司批准的本地 MCP，
  才能把 MCP 验证写成 Pass。

按顺序执行：

1. 校验离线包
   - 在离线目录执行：shasum -a 256 -c SHA256SUMS
   - 读取 manifest.json，确认版本、Node 要求和 tgz 文件名一致。

2. 安装或更新 Plugin
   - 将 tgz 解压到稳定的版本目录。
   - 在 VS Code 用户级 chat.pluginLocations 注册解压后的 package 目录。
   - 重新加载 VS Code，确认可以选择 Spec Superflow Agent。
   - 不改业务仓库配置。

3. 通过 Chat 初始化 CLI
   - 选择 Spec Superflow Agent。
   - 执行：
     /workflow-init package=<OFFLINE_BUNDLE_DIR>/spec-superflow-0.14.0.tgz
   - 预期：READY；ssf --version 输出 0.14.0。
   - 再执行一次，预期跳过安装并保持 READY。
   - 如果电脑已有旧版，先记录旧版本，再执行同一命令验证升级。

4. 验证 Plugin 内容
   - Agent 选择器存在 Spec Superflow。
   - Configure Skills 能发现中央工作流 Skills。
   - 业务仓库没有新增中央 scripts、templates 或 Skills 副本。
   - 在空白仓库执行 workflow-start，确认 ssf state、guard、validate 可运行，
     且任务产物只写入当前仓库。

5. 验证公司业务 Skills
   - 在业务仓库读取项目 Instructions 和公司业务 Skills。
   - 选择 Spec Superflow Agent 后，发起一个只读 Context Check。
   - 记录实际加载的项目规则、Skill 名称和来源路径。
   - 确认中央工作流 Skill 与业务 Skill 不同名、不互相覆盖。

6. 验证公司 MCP
   - 如果公司已配置批准的本地 MCP，运行 MCP: List Servers 和 Configure Tools。
   - 记录 Server 名、启动命令来源和一个只读 tool call 结果。
   - Server 不存在、运行时未安装或工具未调用时，结果必须是 Fail/Not Configured，
     不能用仓库里的 MCP fixture 单元测试代替真实 VS Code 调用。

7. 完成一个普通真实需求
   - 先做 Requirement & Context Check。
   - 生成 proposal、spec、design、tasks。
   - 确认 Scenario 在 design、tasks 和准确测试文件/用例中可追溯。
   - 生成并确认 execution-contract。
   - 先取得真实 RED，再最小实现到 GREEN。
   - 前端需求执行 Unit Test、准确 UI Test 和至少一个设备/模拟器测试。
   - 独立 Review，生成 pr-summary、AC Test Evidence 和 decision audit。
   - 只有 guard 通过后进入 closing。

8. 完成一个 Android→鸿蒙代表性需求
   - 选择一个边界清晰的页面或业务流程。
   - 读取 Android 行为、测试、接口、状态和交互，生成迁移 Spec/Design/Tasks。
   - 迁移或新增测试，先取得 RED。
   - 按项目内部框架和公司业务 Skills 实现。
   - 执行编译、Unit Test、UI Test 和真实设备/模拟器验证。
   - 使用独立 Review Agent 检查公共组件复用、重复实现、架构分层和遗漏测试。

9. 输出最终 evidence
   - installation.md：包校验、Plugin、CLI、升级、幂等。
   - plugin-runtime.md：Agent、Skills、MCP 实际发现和调用。
   - ordinary-requirement.md：完整 SDD 产物、RED/GREEN、测试、Review、closing。
   - harmony-requirement.md：迁移范围、测试、设备、Review 和未完成项。
   - summary.md：四项最终 Pass/Fail，不隐藏失败。
```

## 判断标准

| 项目 | Pass 条件 |
|---|---|
| 安装与更新 | Plugin 和 CLI 都是 `0.14.0`，离线安装、升级和二次执行均通过 |
| Plugin 运行时 | Agent 和中央 Skills 可发现，CLI 命令在业务仓库运行，产物不写入 Plugin |
| 公司业务 Skills | 能从业务仓库被读取并真实影响 Context Check 或实现 |
| MCP | 公司批准的 Server 在 VS Code 中启动并完成一次真实 tool call；默认空配置不算 Pass |
| 普通需求 | Scenario 到代码和准确测试证据可追溯，Unit/UI/Device 和 closing 通过 |
| 鸿蒙需求 | 迁移功能、测试、设备执行和独立 Review 均有实际证据 |
