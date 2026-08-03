---
name: contract-builder
description: Convert approved planning artifacts into an execution contract. Invoke when the user wants to start building, asks to move from planning to implementation, or when execution-contract.md is missing or stale.
---

# Contract Builder

Convert approved planning artifacts into a compact execution lock: `execution-contract.md`. Use `templates/execution-contract.md` as the exact structure. The contract records what is approved, how execution is gated, and when to stop; it does not restate planning content.

Read before generating: `proposal.md`, change-local `specs/`, `design.md`, `tasks.md`, and `docs/artifact-contract.md`. Read `docs/project/project-guidelines.md` when configured. For each delta capability, read the project-root `specs/<capability>/spec.md` as the existing behavior baseline. If `.spec-superflow/memories/MEMORY.md` exists, read its entrypoint and only relevant topics.

## Source Of Truth

- `proposal.md`: intent and scope
- `specs/`: approved behavior and Scenarios
- `design.md`: decisions, baseline alignment, constraints, and deviations
- `tasks.md`: Batch/AC ownership, file changes, TDD Test Plans, and Batch Verification

Reference these artifacts from `## Approved Artifacts`. Do not copy their behavior summaries, Requirement mappings, decisions, file lists, Task Batches, or AC test matrix into the contract. `tasks.md > TDD Test Plan` remains the source of truth for exact test obligations and later `pr-summary.md` evidence.

## Planning Cross-Check

Before generating the contract, verify without copying the result:

1. Every SHALL/MUST and Scenario in `specs/` appears in the design coverage table and exactly one task Batch AC.
2. Every task file change follows the selected baseline/reuse pattern or has an approved design deviation.
3. Every required edge case has an exact fixture or precondition and observable assertion in `tasks.md`.
4. Every TDD row has a controllable precondition and observable result. Reject no-op fakes, no-op callbacks, inert refreshes, inaccessible UI state, and generic suite labels.
5. Interface changes enumerate all discovered production implementations, adapters, fakes, mocks, test doubles, and affected module compile/test obligations.
6. Every Batch has one executable Batch Verification block and valid dependency order.

If any check fails, stop and route back to the owning planning artifact. Do not repair the contract by copying missing content into it.

## Contract Structure

The contract contains only:

- `## Approved Artifacts`: source paths plus `.spec-superflow.yaml > artifacts_hash` as the planning lock
- `## Execution Mode`: selected mode and rationale
- `## Batch Gates`: one reference row for every `## Batch N` in `tasks.md`
- `## Verification`: shared project commands or procedures; AC-specific tests stay in `tasks.md`
- `## Frontend Verification`: aggregate UI/device environment obligations
- `## Stop Conditions`: conditions that force a return to planning or block execution

Do not add Approved Behavior, Requirement Traceability, AC Test Matrix, Design Constraints, Task Batches, Test Obligations, or Verification Dimensions sections. Their information already has an owning artifact.

## Frontend Verification

Classify a change as frontend when it affects a Web, Android, HarmonyOS, iOS, desktop, or other user-interface client.

- `Frontend Impact: Yes`: include UI Test and Device Test rows.
- Set UI Test to `Required by tasks.md`; exact actions, files, and cases remain in each AC's TDD Test Plan.
- For visible output derived from application state, require an injectable rendering seam and separate proof of state-to-UI derivation from lazy, scrolling, or repeated-content behavior. A child-parameter assertion alone is insufficient.
- Device Test is `Required`. Default to one project-baseline simulator/device per affected native platform, or the default real browser for Web. Add environments only when behavior depends on system version, screen size, Market, permission, or device capability.
- If no UI framework exists, preserve `Unavailable` in the task row, record the inspected locations/configuration, and do not add a framework without developer approval.
- Read commands and runtime prerequisites from code, relevant Memory, build files, package scripts, and existing tests. Do not invent commands.
- `Frontend Impact: No`: record the concrete reason and omit the table.
- Screenshot tests are outside this version.

## Approval Model (DP-3)

After drafting, summarize the execution mode, Batch gates, shared verification, frontend environment, and stop conditions. Ask the user to approve explicitly. After approval:

```bash
ssf state set <change-dir> dp_3_result "approved: <summary>"
ssf state set <change-dir> dp_3_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

DP-3 is a hard gate. Do not start implementation without it.

## Stale Contract Detection

Refresh when the planning artifact hash changes or the execution mode, shared verification procedure, frontend environment, or Batch gates change.

## Hotfix Mode

Use the same compact structure with only applicable artifact references and Batch gates. DP-3 is still required.

## Post-Generation

Run:

```bash
ssf state init <change-dir>
ssf validate <change-dir>
```

If validation fails, regenerate the contract from the approved artifact set. Do not paste planning content into it. Re-run validation once; if it still fails, report the exact missing source reference, Batch gate, verification procedure, or stop condition before asking for approval.

## Guardrails

- Do not approve the contract on the user's behalf.
- Do not continue when planning ambiguity or unmapped behavior remains.
- Do not skip the contract because planning files look complete.
- Do not use chat history as an execution authority.

## Exception Handling

- **Parse failures**: Report the exact file and section; route back to `spec-writer`.
- **Missing files**: List every missing artifact; route back to `spec-writer`.
- **User interruption**: Re-read all artifacts and check freshness on resume.
- **Validation failure**: Return to the artifact that owns the missing information; do not duplicate it into the contract.
