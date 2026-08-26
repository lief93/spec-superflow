# Execution Contract

## Approved Artifacts

- **Planning Lock**: `.spec-superflow.yaml > artifacts_hash`

| Artifact | Source Of Truth |
|---|---|
| Proposal | `changes/android-to-harmony-execution-plan-dag/proposal.md` |
| Specs | `changes/android-to-harmony-execution-plan-dag/specs/android-harmony-execution-planning/spec.md` |
| Design | `changes/android-to-harmony-execution-plan-dag/design.md` |
| Tasks | `changes/android-to-harmony-execution-plan-dag/tasks.md` |

These approved files remain the source of truth. This contract only locks execution mode, batch gates, shared verification, frontend obligations, and stop conditions.

## Execution Mode

- **Mode**: `SDD`
- **Selection rationale**: Execution spans three dependent Batches and sixteen approved ACs across multiple Python and Node seams, with immutable-plan identity, mutable task-state, workflow-only entry, strict tamper rejection, and mandatory frozen evidence capture for three fixed public projects. That combination requires batchwise RED/GREEN/regression control and explicit evidence freezing rather than inline implementation.

## Batch Gates

| Batch | Entry Gate | Exit Gate | Review Gate |
|---|---|---|---|
| Batch 1 | Approved planning lock; no prior Batch dependency | Complete `tasks.md` Batch 1 RED, GREEN, and regression verification for typed graph relationships, route/page qualification, and scoped blockers | Freeze Batch 1 outputs only after the exact Batch 1 Verification block in `tasks.md` passes |
| Batch 2 | Batch 1 outputs complete: typed edges, route/page qualification, and scoped-blocker semantics | Complete `tasks.md` Batch 2 RED, GREEN, and regression verification for immutable task packets, prerequisite DAG semantics, lifecycle state, and strict identity binding | Freeze Batch 2 outputs only after the exact Batch 2 Verification block in `tasks.md` passes against the same current plan inputs |
| Batch 3 | Batch 2 outputs complete: immutable plan, mutable task-state, and integrity outputs; Batch 1 graph/closure provenance remains current | Complete `tasks.md` Batch 3 RED, GREEN, mandatory post-GREEN public-project capture, evidence-subtree verification, manifest generation/verification, and listed regressions | Freeze execution evidence only after the exact Batch 3 Verification block in `tasks.md` passes, including the three fixed public-project captures and evidence-tree verification |

## Verification

AC-specific obligations remain in `changes/android-to-harmony-execution-plan-dag/tasks.md`. Shared execution verification is limited to the command families and evidence procedures already approved there.

| Check | Command Or Procedure | Evidence Required |
|---|---|---|
| Batch RED/GREEN | Run the exact grouped RED commands and the exact matching GREEN reruns from each Batch Verification block in `tasks.md` | Command, exit code, and focused failing/passing results bound to the current artifacts hash |
| Batch regression | Run only the regression commands listed in the relevant Batch Verification block after GREEN | Command, exit code, and suite summary for each listed Python or Node regression |
| Public-project capture | After Batch 3 GREEN, run the three mandatory Banking, Ekspensify, and Buckwheat capture procedures exactly as specified in `tasks.md`, then verify each expected evidence subtree | Frozen per-project evidence subtree with command stdout/stderr, exit artifacts, logs, graph/gate/plan outputs, and referenced central skill identity |
| Evidence manifest | Generate and verify the complete evidence-tree manifest/envelope for the current change using the approved Batch 3 procedure in `tasks.md` | Manifest/envelope output plus a successful verification result over the required evidence families |

## Frontend Verification

- **Frontend Impact**: `No`
- **Reason**: The approved scope changes migration workflow, CLI, planner, and evidence infrastructure. It does not directly modify a user-facing Web, Android, HarmonyOS, iOS, or desktop client feature, and the approved tasks do not impose UI/device runtime gates for this change.

## Stop Conditions

- `.spec-superflow.yaml > artifacts_hash` changes after this contract is approved.
- Execution requires changing the approved typed relationship model, plan identity model, evidence contract, or Batch dependency semantics instead of implementing them.
- Any RED command in `tasks.md` does not fail in the expected seam, or fails for reasons that invalidate the planned TDD path.
- The required Banking, Ekspensify, or Buckwheat public-project evidence cannot be produced, verified, or bound to the current skill/artifact identities.
- Implementation would touch an unapproved production file, add an unapproved dependency, or rely on an unapproved workflow entry outside Spec Workflow / `migration_agent`.
- Plan, graph, review queue, gate report, mutable task-state, skill identity, or evidence inputs drift or fail integrity checks during execution.
