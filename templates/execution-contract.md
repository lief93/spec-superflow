# 执行合同

## Intent Lock

- **变更名称**：
- **要解决的问题**：
- **范围内**：
- **范围外**：

## Approved Behavior

- **已批准需求摘要**：
- **关键场景**：
- **验收检查**：

## Requirement Traceability

| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|
|  |  |  | Batch 1 |

## Design Constraints

- **项目 Memory 来源**：`.spec-superflow/memories/core.md` + relevant `mem:` references | Not configured
- **技术约束**：
- **架构约束**：
- **数据与接口约束**：
- **依赖约束**：
- **复用对象与扩展点**：
- **运行时与平台事实**：

## Task Batches

### Batch 1

- **目标**：
- **输入**：
- **输出**：
- **完成标准**：

### Batch 2

- **目标**：
- **输入**：
- **输出**：
- **完成标准**：

## Test Obligations

- **必须先从失败测试开始的行为**：
- **必需的边界情况**：
- **回归敏感区域**：

## Frontend Verification

- **Frontend Impact**: `Yes` | `No`
- **Reason**: 判断依据；`No` 时说明为什么不涉及用户界面客户端

`Frontend Impact: Yes` 时保留下表；`No` 时删除表格。

| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
| UI Test | `Add` / `Update` / `Run existing` / `Unavailable` | 受影响页面、流程或相关历史回归集合 | UI 测试运行环境 | 精确命令；不可用时记录查找范围和能力缺口 | 通过数量、失败数量、报告路径或不可用原因 |
| Device Test | `Required` | 本次改动影响的用户关键路径 | 项目基准模拟器、真机或浏览器环境 | 构建、安装/启动和操作步骤 | 运行结果、环境信息和必要日志 |

## Execution Mode

- **模式**：`Inline` | `Batch Inline` | `SDD`
- **选择理由**：

## Verification Dimensions

| 维度 | 状态 | 发现 |
|------|------|------|
| Completeness | Pending | — |
| Correctness | Pending | — |
| Coherence | Pending | — |

**总体结论**：Pending

## Review Gates

- **强制审查点**：
- **阻塞类别**：

## Escalation Rules

- **何时回退到 `specifying`**：
- **何时回退到 `bridging`**：
- **何时不得继续实现**：
