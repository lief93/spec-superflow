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

## AC Test Matrix

从 `tasks.md` 原样复制每个 AC 的全部测试义务。一个测试文件或用例占一行，不合并为“相关测试”或“回归集合”。

| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

## Design Constraints

- **项目开发基线来源**：`docs/project/project-guidelines.md` | Not configured
- **采用的经典实现**：
- **已批准偏离**：`None` | 偏离及理由
- **项目 Memory 来源**：`.spec-superflow/memories/MEMORY.md` + relevant topic files | Not configured
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
| UI Test | `Required by AC Test Matrix` | `AC Test Matrix` 中所有 UI 行 | UI 测试运行环境 | 能运行矩阵中精确文件/用例的命令；不可用时记录查找范围和能力缺口 | 每个 AC 的通过/失败结果和报告路径 |
| Device Test | `Required` | `AC Test Matrix` 中所有 User-visible AC | 项目基准模拟器、真机或浏览器环境 | 在目标环境运行矩阵中的 UI 文件/用例；无法自动化的路径另列人工步骤 | 每个 AC 的运行结果、环境信息和必要日志 |

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
