# Execution Contract

## Approved Artifacts

- **Planning Lock**: `.spec-superflow.yaml > artifacts_hash`

| Artifact | Source Of Truth |
|---|---|
| Proposal | `proposal.md` |
| Specs | `specs/` |
| Design | `design.md` or configured skip |
| Tasks | `tasks.md` |

These approved files remain the source of truth. Do not copy their behavior, decisions, file changes, or AC test rows into this contract.

## Execution Mode

- **Mode**: `Inline` | `Batch Inline` | `SDD`
- **Selection rationale**:

## Batch Gates

Use one row for every `## Batch N` in `tasks.md`; reference it instead of copying its ACs or file changes.

| Batch | Entry Gate | Exit Gate | Review Gate |
|---|---|---|---|
| Batch 1 | Approved planning lock; dependencies complete | Batch Verification and planned AC tests pass | Required review complete |

## Verification

AC-specific obligations remain in `tasks.md > TDD Test Plan`. Record only shared commands or procedures here.

| Check | Command Or Procedure | Evidence Required |
|---|---|---|
| AC tests | Run every exact test file and case planned in `tasks.md` | Per-case result in `pr-summary.md` |
| Regression | Project-specific affected regression command | Command, exit code, and summary |
| Build / Static | Project-specific build, lint, or type-check command | Command, exit code, and summary |

## Frontend Verification

- **Frontend Impact**: `Yes` | `No`
- **Reason**: Decision basis; when `No`, explain why no user-facing client is affected

Keep the table below when `Frontend Impact: Yes`; delete it when `No`.

| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
| UI Test | `Required by tasks.md` | Every UI row in `tasks.md` | UI test runtime | Run the exact planned files and cases; when unavailable, record the search scope and capability gap | Per-AC result and report path |
| Device Test | `Required` | One reachable branch per affected feature; externally controlled remaining branches stay in AC-owned automated tests | Project-standard emulator, device, or browser environment | Run and name the reachable feature branch; disclose external-condition branches covered only by automated evidence | Result, environment details, executed branch, and necessary logs |

## Stop Conditions

- Planning hash changes after approval.
- Required behavior, scope, or a design assumption changes.
- A planned test cannot run or fails after the allowed repair loop.
- Implementation requires an unapproved dependency, interface, or architecture deviation.
