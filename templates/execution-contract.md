# Execution Contract

## Intent Lock

- **Change name**:
- **Problem to solve**:
- **In scope**:
- **Out of scope**:

## Approved Behavior

- **Approved requirement summary**:
- **Key scenarios**:
- **Acceptance checks**:

## Requirement Traceability

| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|
|  |  |  | Batch 1 |

## AC Test Matrix

Copy every test obligation for each AC from `tasks.md` without changing it. Use one row per test file and test case; do not combine them into "related tests" or a "regression suite."

| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

## Design Constraints

- **Project baseline source**: `docs/project/project-guidelines.md` | Not configured
- **Selected classic implementations**:
- **Approved deviations**: `None` | deviation with rationale
- **Project Memory source**: `.spec-superflow/memories/MEMORY.md` + relevant topic files | Not configured
- **Technology constraints**:
- **Architecture constraints**:
- **Data and interface constraints**:
- **Dependency constraints**:
- **Reuse targets and extension points**:
- **Runtime and platform facts**:

## Task Batches

### Batch 1

- **Goal**:
- **Inputs**:
- **Outputs**:
- **Done when**:

### Batch 2

- **Goal**:
- **Inputs**:
- **Outputs**:
- **Done when**:

## Test Obligations

- **Behavior that must start with a failing test**:
- **Required edge cases**:
- **Regression-sensitive areas**:

## Frontend Verification

- **Frontend Impact**: `Yes` | `No`
- **Reason**: Decision basis; when `No`, explain why no user-facing client is affected

Keep the table below when `Frontend Impact: Yes`; delete it when `No`.

| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
| UI Test | `Required by AC Test Matrix` | Every UI row in the `AC Test Matrix` | UI test runtime | Command that runs the exact files and cases in the matrix; when unavailable, record the search scope and capability gap | Pass/fail result and report path for each AC |
| Device Test | `Required` | Every User-visible AC in the `AC Test Matrix` | Project-standard emulator, device, or browser environment | Run the UI files and cases from the matrix in the target environment; list separate manual steps for paths that cannot be automated | Result, environment details, and necessary logs for each AC |

## Execution Mode

- **Mode**: `Inline` | `Batch Inline` | `SDD`
- **Selection rationale**:

## Verification Dimensions

| Dimension | Status | Findings |
|---|---|---|
| Completeness | Pending | - |
| Correctness | Pending | - |
| Coherence | Pending | - |

**Overall conclusion**: Pending

## Review Gates

- **Mandatory review points**:
- **Blocking categories**:

## Escalation Rules

- **When to return to `specifying`**:
- **When to return to `bridging`**:
- **When implementation must not continue**:
