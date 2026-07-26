# Spec Superflow 演示脚本

建议时长 12 分钟。演示只讲三条主线：安装更新、普通需求、Android 到鸿蒙迁移。

## 演示前准备

- 离线包：`release-assets/v0.14.0/`
- 普通需求仓库：`validation-runs/mars-photos-empty-state-20260726`
- 普通需求证据：`validation/evidence/ordinary-requirement-sdd.md`
- 安装证据：`validation/evidence/offline-install-upgrade.md`
- 一个已启动或可启动的 Android 模拟器
- 公司电脑上的 Plugin、CLI、业务 Skills 和鸿蒙项目

现场只运行短命令。Gradle 首次构建、网络下载和鸿蒙设备启动在演示前完成。

## 0:00-1:00 先看结构

展示 `docs/hsbc-ai-workflow-briefing-zh.md` 的工作流总图。

讲解：

> 这套方案只有两个变化：AI 进入现有开发流程；开发过程自动形成任务上下文。AI 做重复推进，人确认关键产物，测试和设备证据决定是否完成。

预期结果：听众先理解 Agent、CLI、项目规则和任务产物的边界。

## 1:00-3:30 安装与更新

### 点击

1. VS Code 选择 **Spec Superflow** Agent。
2. 输入 `/workflow-init`，从建议中选择 Plugin 提供的命令。

### 预期

以下结果需要在真实 VS Code Plugin Chat 中现场执行，不能由离线脚本替代：

```text
READY
Node: PASS
CLI: 0.14.0
```

### 补充命令

```bash
ssf --version
```

讲解：

> Plugin 安装一次并在多个业务仓库复用。`/workflow-init` 只负责安装和版本验证，不会自动开始需求。CLI 已匹配时二次执行不会重复安装。

切换点：CLI 返回 READY 后打开普通需求仓库。

## 3:30-7:30 普通需求 SDD

需求：成功返回零张照片时显示空状态和 Refresh，并保持原有非空列表行为。

### 展示任务结构

```bash
find changes/empty-state-refresh -maxdepth 3 -type f | sort
ssf validate changes/empty-state-refresh
ssf state check changes/empty-state-refresh
```

预期：

- proposal、spec、design、tasks、execution contract、PR evidence 全部存在。
- `validate` 全部通过。
- 状态为 `closing`，工件哈希一致。

### 展示追溯关系

依次打开：

1. `specs/photo-results/spec.md` 的三个 Scenario。
2. `design.md` 的 Requirement And Scenario Coverage。
3. `tasks.md` 的 AC、文件改动和 TDD Test Plan。
4. `pr-summary.md` 的 AC Test Evidence。

讲解：

> 同一个 AC 从需求、设计、文件改动、测试计划一直串到最终证据。测试文件和用例名在执行契约后不能被“相关测试通过”替代。

### 现场短验证

```bash
./gradlew :app:testDebugUnitTest
ANDROID_SERIAL=<serial> ./gradlew \
  :app:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=com.example.marsphotos.ui.screens.HomeScreenTest
```

预期：Unit 全通过；Compose UI 3/3 通过。

切换点：测试开始后先展示已有 XML evidence，避免现场等待占用讲解时间。

## 7:30-10:00 Android 到鸿蒙

展示一个已迁移页面和对应的迁移 Spec/Test/Gate。

讲解：

> 同一工作流可以支撑迁移任务。差异在于项目 Skill 会先拆 Android 行为、UI、接口、状态和交互，再迁移测试并按失败测试补齐鸿蒙实现。现有流程已经覆盖 6 个页面，功能一致、UI 接近；Code Review 和鸿蒙 UI Test 必须按实际证据单独报告。

现场验证优先级：

1. 运行一个迁移后的业务测试。
2. 打开页面，执行一个真实交互。
3. 展示测试结果和未完成项，不用截图或口头判断替代 UI Test。

切换点：设备执行超过 30 秒时直接展示预录证据并继续。

## 10:00-12:00 协作和维护

展示：

- 项目规则：`.github/copilot-instructions.md`
- 项目业务 Skills：`.github/skills/`
- 任务上下文：`changes/<change-name>/`
- 选择性 Memory：`.spec-superflow/memories/`

讲解：

> 这些文件同时服务于人人、人 AI 和 AI AI。新的开发 Agent 可以读取历史任务和项目规则，Review Agent 读取同一执行契约和测试矩阵。Skill 只有经过 Eval 和空白上下文验证后才进入中央 Plugin。

结束语：

> 这套工作方式提高效率的依据，不是 AI 生成了多少代码，而是需求、产物和验证边界是否清楚，接手和 Review 是否能少依赖口头解释。

## 现场失败切换

| 风险 | 现场处理 | 直接展示的证据 |
|---|---|---|
| 无公网或 npm 不可用 | 使用本地 tgz，不修改公司 registry | `offline-install-upgrade.md`、SHA256、离线验证结果 |
| `/workflow-init` 安装慢 | 展示本地 CLI 安装原语，Chat 结果保持 Pending | `ssf --version`、CLI 安装 evidence |
| Android 模拟器未启动 | 不现场冷启动，直接读 XML 和 HTML report | `ordinary-requirement-sdd.md` |
| 鸿蒙设备或内网服务不可用 | 展示已保存的测试结果、页面证据和明确未完成项 | 公司项目 evidence 索引 |
| Chat 路由错误 | 重新选择 Spec Superflow Agent，再执行命令 | Agent 名称、Plugin 版本、命令建议 |
| 现场时间不足 | 只讲总图、普通需求追溯链和三条状态结论 | 两份 evidence 文档 |

## 演练记录

| 环节 | 预期 | 结果 | 证据 |
|---|---|---|---|
| 最终 tgz 完整性与直接 CLI 安装 | CLI `0.14.0` | 本地 PASS | `validation/evidence/offline-install-upgrade.md` |
| 直接 CLI 旧版升级 | `0.13.0` 升到 `0.14.0` | 本地 PASS | `validation/evidence/offline-install-upgrade.md` |
| `/workflow-init` 发现、执行、READY 与二次调用 | 真实 VS Code Plugin Chat | Pending VS Code runtime | 内网 `installation.md` |
| 正式 Plugin MCP | 公司批准的真实 Server 和 tool call | Not Configured | 内网 `plugin-runtime.md` |
| 普通需求工件校验 | 全部 valid、状态 consistent | 本地 PASS，0.08 秒 | `validation/evidence/local-demo-rehearsal.md` |
| 普通需求 Unit/UI/Device | 0 failures | 本地 PASS，约 20 秒 | `validation/evidence/local-demo-rehearsal.md` |
| 公司 Plugin/CLI/业务 Skills | 公司环境实际执行 | 内网下载后按门禁执行 | 公司环境 evidence |
| 鸿蒙真实流程 | 测试、页面交互和 evidence | 内网下载后按真实项目执行 | 公司项目 evidence |

内网执行步骤见 `docs/internal-validation-prompt-zh.md`。
