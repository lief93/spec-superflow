---
name: workflow-start
description: Primary entry point for the spec-superflow state-machine workflow. Invoke when the user is inside an active spec-superflow change directory (look for .spec-superflow.yaml, changes/<name>/, proposal.md, specs/, design.md, tasks.md, or execution-contract.md) and asks to start, continue, resume, implement, plan, or figure out the next workflow step. Also invoke when the user explicitly asks to start a new spec-superflow change or route through the spec-superflow workflow. Do not invoke for /workflow-init or Plugin, CLI, or MCP runtime setup. Do not invoke for unrelated coding tasks that happen to use words like start, continue, implement, or plan.
disable-model-invocation: true
---

# Workflow Start

Primary entry point for `spec-superflow`. Jobs: load the project development baseline, relevant project memories, and change artifacts; confirm DP-0; determine state; route to the correct skill; and block invalid transitions.

## Hard Exclusion

Do not invoke for `/workflow-init` or Plugin, CLI, or MCP runtime setup. Return
control to the selected command. Do not inspect the workspace, read another
Skill, or create or resume a Change.

## Use This Skill When

Only invoke when spec-superflow context is present: `.spec-superflow.yaml` exists, artifacts like `proposal.md`/`specs/`/`design.md`/`tasks.md`/`execution-contract.md` are present, or user explicitly invokes spec-superflow by name. When in doubt, check for `.spec-superflow.yaml` first.

Do NOT invoke for: general coding tasks outside spec-superflow changes, casual questions, unrelated work.

## States

`exploring` → `specifying` → `bridging` → `approved-for-build` → `executing` → `closing`, with `debugging` side-path from `executing`, and `abandoned` as terminal. Read `docs/state-machine.md` if transition is ambiguous.

## Initialization

1. **Load project baseline**: If `docs/project/project-guidelines.md` exists, read its technology and architecture tables, inspect the classic implementation index, and read only recipes relevant to the request. If the user explicitly asks to initialize or refresh the project baseline, route to `project-init`. A missing baseline does not block an ordinary change; mention `/project-init` once.
2. **Recall shared auto memory**: If `.spec-superflow/memories/MEMORY.md` exists, read only its first 200 lines or 25,000 bytes. Use the one-line hooks to select up to five `feedback`, `project`, or `reference` topics clearly relevant to the request, and verify stale claims before relying on them. If the user asks to remember, forget, inspect, or consolidate a project learning, route to `memory-manager`. Missing Memory is normal and does not need initialization at task start.
3. **Inspect change folder**: Check for `proposal.md`, `specs/`, `design.md`, `tasks.md`, `execution-contract.md`. Answer: Is the change fuzzy? Artifacts missing/unstable? Contract exist? User approved contract? Execution in progress or blocked? In verification/wrap-up?

## DP-0: User Confirmation Gate

Run DP-0 when: change folder doesn't exist, planning artifacts missing/empty, or `dp_0_confirmed` ≠ `true`. Skip if `dp_0_confirmed` is `true`.

Ask: change name + one-sentence intent, known constraints, related optimizations (include or stay focused?), communication preference (ask per decision or draft for review).

After confirmation, normalize the change name to a safe lowercase kebab-case
directory name. If the change does not exist, run
`ssf state init changes/<change-name>` to initialize the exact
`changes/<change-name>` directory before recording DP-0. Treat that directory
as `<change-dir>` for every later command and artifact:

```bash
ssf state init changes/<change-name>
ssf state set <change-dir> dp_0_decisions "<summary>"
ssf state set <change-dir> dp_0_confirmed true
ssf state set <change-dir> dp_0_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

Do not create `proposal.md`, `design.md`, `tasks.md`, or delta specs at the repository root. They belong under `<change-dir>`.

Config-aware routing: check `artifacts.order` and `artifacts.skip` from project config.

## Mode Detection

When the user explicitly requests the full workflow, persist `workflow` as
`full` and do not infer `hotfix` or `tweak`.

If workflow is `auto`/`null`/unset: run `ssf infer-workflow <change-dir>`. Inference: **hotfix** (≤2 tasks, ≤2 files, no schema/API/new modules), **tweak** (≤4 tasks, config/doc only), **full** (anything larger). Persist with `ssf state set <dir> workflow <mode>`.

Validate mode against artifact content. If hotfix/tweak criteria not met → upgrade to `full` and output reason. Don't overwrite explicit mode unless user asks.

## Routing Rules

### Route to project-init
The user explicitly asks to initialize or refresh project coding rules, architecture guidance, canonical implementations, or Copilot project context.

### Route to need-explorer
Change is fuzzy, scope unclear, comparing options, no stable change name.

### Route to spec-writer
User knows what they want and planning artifacts are missing or incomplete.
Run `ssf guard check <dir> exploring specifying --json`; fail = BLOCK.
After it passes, run `ssf state transition <dir> specifying`, verify the
persisted state is `specifying`, then route to `spec-writer`.

### Route to contract-builder
Planning artifacts exist, implementation is requested, and the contract is
missing or stale. Run `ssf guard check <dir> specifying bridging --json`; fail =
BLOCK. After it passes, run `ssf state transition <dir> bridging`, verify the
persisted state is `bridging`, then route to `contract-builder`. Include `DP-3:
Contract Approval`.

### Route to build-executor
The contract exists, is approved, and matches the planning artifacts. When the
current state is `bridging`, run
`ssf guard check <dir> bridging approved-for-build --json`; fail = BLOCK. After
it passes, run `ssf state transition <dir> approved-for-build` and verify the
persisted state. Record `DP-4: Execution Mode Selection`, then run
`ssf guard check <dir> approved-for-build executing --json`; fail = BLOCK.
After it passes, run `ssf state transition <dir> executing`, verify the
persisted state is `executing`, then route to `build-executor`.

### Route to bug-investigator
Execution hit blockage: test failure, unexpected behavior, build error, task cannot proceed. After debugging, route back to build-executor.

### Route to code-reviewer
Batch completed, batch ready for spec-compliance + code-quality verification.

### Route to release-archivist
Route to `release-archivist` while the state remains `executing` so it can
produce the final test and PR evidence and own the `executing` → `closing`
transition. After it returns, run `ssf state get <dir> state` and require
`closing`. If the persisted state is not `closing`, report BLOCKED with the
release result; do not repeat the transition from `workflow-start`. Include
`DP-7: Archive Confirmation`.

### Route to spec-merger
Delta specs exist that need merging, change closing with ADDED/MODIFIED/REMOVED/RENAMED specs.

### Route to abandoned
User explicitly requests, bug-investigator escalates after 3+ failures AND user chooses, scope change makes change no longer worthwhile AND user confirms. Block from `closing` or `abandoned`.

### Fast-Path Routing
- **Hotfix**: Skip need-explorer + spec-writer. Run `ssf guard check <dir> exploring bridging --workflow hotfix`; after it passes run `ssf state transition <dir> bridging`, then route to contract-builder (minimal). After DP-3, follow the normal approved-for-build and executing transitions, then release-archivist (lightweight).
- **Tweak**: Skip need-explorer + spec-writer + contract-builder. Run `ssf guard check <dir> exploring approved-for-build --workflow tweak`; after it passes run `ssf state transition <dir> approved-for-build`, then record DP-4 and follow the normal executing transition before direct edit. Finish through release-archivist (lightweight).

Post-transition: 💡 `ssf inject <change-dir>` to update phase-guard artifacts.

## Staleness Detection

Use persisted content hashes, not timestamps or prose that the compact contract
does not own.

**Stale contract**: run `ssf state check <change-dir> --json`. A mismatch between
the current planning artifacts and `.spec-superflow.yaml > artifacts_hash`
means the execution contract is stale; block resume and route back to
`contract-builder`. The transition guard's `contract-fresh` check enforces the
same hash rule before execution.

**Stale planning artifacts**: capability in proposal has no spec file, or spec exists for capability not in proposal → drift detected.

**Stale tasks**: requirement in specs has no corresponding task → stale tasks.

## Guardrails

- No implementation before planning artifacts or contract exist
- No "continue" without state inspection
- No implementation past stale contract
- No implementation past bug without investigation
- No closure without code review
- No closure with unsynced delta specs
- No transitions from `abandoned` (terminal)
- No transition to `abandoned` from `closing` or `abandoned`
- No auto-abandon without user confirmation
- No merging delta specs from abandoned change

## Output Standard

Always state: (1) current detected state, (2) why (cite file/content/condition), (3) which skill should run next. If blocking, explain missing artifact/approval.

Decision point references when routing:
- contract-builder → DP-3, build-executor → DP-4, bug-investigator (escalation) → DP-5, release-archivist (verification failure) → DP-6, release-archivist → DP-7

## Exception Handling

- **Parse failures**: Fall back to content-level detection if `.spec-superflow.yaml` is malformed
- **Missing files**: Route to the skill that generates the missing files
- **User interruption**: Re-inspect change directory content (not cached state) on resume
