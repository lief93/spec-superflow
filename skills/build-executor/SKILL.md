---
name: build-executor
description: Govern implementation from an approved execution contract. Invoke when execution-contract.md is approved and the user wants disciplined build work, TDD execution, or guarded batch-by-batch implementation.
---

# Build Executor

Controls the implementation phase. Uses `execution-contract.md` as the workflow authority.

## Required Inputs

Read: `execution-contract.md`, `tasks.md`, relevant change-local `specs/`, relevant `design.md`, and matching project-root `specs/<capability>/spec.md`. Read the project baseline path named in the contract and the selected classic implementation before changing code. If `.spec-superflow/memories/MEMORY.md` exists, read its entrypoint and only linked topics relevant to the execution batches. (Skip contract/spec requirements when workflow is `tweak`.)

Check workflow mode first: `ssf state get <change-dir> workflow`. If `tweak` → direct edit mode. If `hotfix` or `full` → standard contract-first discipline.

Config check: `ssf config --get execution.inlineThreshold` (default: 3).

## Core Laws

### Law 1: Contract First
The execution contract is the approved handoff artifact, not chat history.

### Law 2: TDD Iron Law — No Production Code Without a Failing Test First
RED (write test, see it fail) → GREEN (write minimal code, see it pass) → REFACTOR (clean up, suite stays green).

**Red Flags**: "Quick implementation first, test later" / "Skip the test, manually verify" / "I already know it works" / "Just this one time without tests." ALL mean STOP and write the test first.

### Law 3: Review Before Drift
Block on: logic defects, spec violations, missing required tests, unintended scope expansion.

### Law 4: Rewind on Contract Break
Return to `specifying` or `bridging` if: new behavior appears, interfaces change materially, design assumptions fail, artifacts no longer define intended implementation.

### Law 5: Auto Memory Provides Recalled Context
Use relevant Memory as prior project learning, not as a rule source. If current code, tests, Specs, ADRs, or project guidelines conflict with a memory, treat the memory as stale and repair it through `memory-manager`.

### Law 6: Project Baseline Governs Code Shape
Follow the contract's selected classic implementation and applicable architecture rules. A necessary deviation must return to design/contract approval; do not silently choose a locally convenient pattern.

### Law 7: Frontend Verification Is Contract Work
When `execution-contract.md` says `Frontend Impact: Yes`, UI and device obligations are part of completion, not optional polish. Do not replace them with unit tests or a successful build.

## Execution Mode Selection

Auto-selection based on: task count, cross-module dependencies, risk indicators (new API/schema/config, open questions, unimplemented dependencies).

| Mode | Criteria |
|------|----------|
| **Inline** | ≤3 tasks, no cross-module deps |
| **Batch Inline** | >3 tasks, same module, no risk indicators, ≤15 min effort |
| **SDD** (default) | Everything else |

Report mode + reasoning before executing. User can override: "use SDD", "use inline", or "use batch inline".

## Batch Inline Execution

For low-risk, same-module tasks. Current agent executes directly. TDD Iron Law still applies.

Procedure: announce mode → write failing test → confirm failure → implement → run suite → refactor → lightweight checkpoint (files exist, no placeholders, test passed, no unintended changes) → report.

Boundaries: if any task touches >1 module, involves schema/API/config changes, or has open questions → downgrade to Inline or SDD.

## SDD Workflow

For changes with multiple execution batches. Dispatch an implementer subagent per AC, review each AC, then run a broad review after all batches.

### Per-AC Loop
1. **Dispatch implementer**: Use `skills/build-executor/implementer-prompt.md` template. Extract the Nth AC brief with `ssf task-brief PLAN_FILE N` (legacy `Task N` plans remain supported). Include: where the AC fits, brief path, project baseline path and selected recipe, interfaces from prior work, relevant memory paths or `Not configured`, relevant capability `spec.md` paths, and report file path.
2. **Handle response**: DONE → generate review package + dispatch reviewer. DONE_WITH_CONCERNS → assess. NEEDS_CONTEXT → provide context. BLOCKED → re-dispatch with better model or escalate.
3. **Review**: Use `skills/build-executor/task-reviewer-prompt.md`. Pass the project baseline path and selected recipe, relevant memory paths or `Not configured`, and relevant capability `spec.md` paths. Reviewer returns spec compliance + baseline compliance + code quality verdicts.
4. **Fix**: If Critical or Important issues, dispatch fix subagent, re-review.
5. **Mark complete**: Append to `.superpowers/sdd/progress.md`: `AC N: complete (commits <base7>..<head7>, review clean)`
6. **Remember selectively**: If this AC produced verified team-wide feedback, code-invisible project context, an external reference, or an expensive-to-rediscover runtime or debugging conclusion, invoke `memory-manager` immediately. Personal feedback and ordinary fix recipes do not qualify. Most ACs should produce no Memory.

Use every exact file/case row in the AC's `TDD Test Plan` to drive execution. Never substitute documentation checks, builds, another test, or an aggregate suite result for the named case. `Add` and `Update` use RED → GREEN → REFACTOR when production behavior is new or changing. When the AC only adds or strengthens coverage for behavior that already works, record a baseline PASS and preserve that behavior; never inject a sentinel or deliberate failure to manufacture RED. `Run existing` establishes the baseline before work and verifies regression afterward. For frontend UI rows:

- `Add`/`Update`: implement and run the named UI Test.
- `Run existing`: run the exact historical UI test file and case named by the AC.
- `Unavailable`: do not add a framework silently; preserve the recorded capability gap for release verification.
- Execute a user-triggered WHEN through the rendered control. A direct ViewModel, callback, repository, or reducer call may arrange a precondition or simulate a system/lifecycle event, but cannot substitute for the planned user action.
- Reacquire UI nodes with a stable semantic selector after any action that may recompose, rerender, refresh, or navigate. Do not retain a node handle across a render-tree change.

Before marking the AC complete, map every observable WHEN/THEN/AND outcome to actual assertions in one or more planned rows. Internal state, calls, persistence, ordering, and concurrency need Unit/Component/Integration proof; visible state and user interaction need UI proof. Passing row counts do not establish complete AC coverage.

For `Add`/`Update` that cover new or changed behavior, confirm the named UI case is RED before the behavior exists and GREEN afterward. For test-only coverage of existing behavior, record the named case as baseline PASS and do not change production solely to create a RED phase. `Run existing` also establishes and protects the regression baseline without an artificial failure. After each relevant Batch, run its exact UI cases. After all Batches, run the affected UI regression set once in addition to, not instead of, those cases. Leave the final Device Test to `release-archivist`, after the implementation and review are stable.

### Model Selection
Use least powerful model per role: mechanical (cheap), integration/judgment (standard), architecture/design (most capable), review (match diff), final review (most capable). Always specify model explicitly.

### Progress Ledger
Track in `.superpowers/sdd/progress.md`. Check for existing ledger — completed tasks are done. After each batch: `ssf state set <change-dir> batches_completed <N>`.

## Inline Execution Mode

For ≤3 tasks, no cross-module deps. Executes in current session.

Per AC: extract brief → write failing test → confirm failure → implement → confirm green → run the AC's UI Test obligation when applicable → checkpoint review (done-when criteria, SHALL/MUST verification) → commit → append to progress ledger.

If task hits BLOCKED (3+ fix failures or changes outside declared scope), escalate to SDD.

## Tweak Mode

Skip TDD. Apply changes directly. Verify file integrity (exists, non-empty, valid syntax). No batch execution — sequential changes.

## DP Records

DP-4 (execution mode): `ssf state set <change-dir> dp_4_result "<mode>: <rationale>"` + timestamp.
DP-5 (debug escalation): `ssf state set <change-dir> dp_5_result "<resolution>"` + timestamp.

## Completion Standard

Don't report completion until: code tests pass, planned UI tests pass or an approved `Unavailable` gap is preserved, contract obligations are satisfied, review blockers are resolved, all batches are reviewed (per-task + final), and the workflow is ready for `release-archivist` to run final UI regression and Device Test.

## Exception Handling

- **Parse failures**: Stop and report exact line/format issue. Route back to `contract-builder`.
- **Missing artifacts**: Route back to appropriate upstream skill. Don't guess.
- **User interruption**: Progress ledger enables recovery. Check ledger on resume.
