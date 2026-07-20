---
name: contract-builder
description: Convert approved planning artifacts into an execution contract. Invoke when the user wants to start building, asks to move from planning to implementation, or when execution-contract.md is missing or stale.
---

# Contract Builder

Converts planning artifacts into a single execution handshake: `execution-contract.md`. Use `templates/execution-contract.md` as the baseline structure.

Read before generating: `proposal.md`, change-local `specs/`, `design.md`, `tasks.md`, and `docs/artifact-contract.md`. For each delta capability, read the project-root `specs/<capability>/spec.md` as the existing behavior baseline. List project memory names, read `memory_maintenance` and `core`, then follow only references relevant to the design and affected modules.

## Artifact Mapping

| Source | Extract |
|--------|---------|
| `proposal.md` → `## Why` + `## What Changes` | Intent Lock (problem + scope) |
| `proposal.md` → `## Scope > ### Out of Scope` | Scope Fence |
| `specs/` → each `### Requirement:` | Approved Requirements, Scenarios, Test Obligations |
| `design.md` → `## Decisions` | Architecture, Interface, Dependency Constraints |
| Relevant project memories + `design.md` | Implementation-relevant architecture, boundary, reuse, and runtime constraints |
| `tasks.md` → numbered task groups | Execution Batches, Completion Definitions, Review Timing |

## Cross-Check: Requirement Coverage

Before finalizing:
1. List every SHALL/MUST from `specs/`
2. Verify each is reflected in Approved Behavior, has a test obligation, and appears in at least one batch
3. Flag unmapped requirements in Escalation Rules
4. Note cross-batch dependencies

## Requirement Traceability Table

`execution-contract.md` must include a `## Requirement Traceability` table with these exact columns:

| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|

Rules:
- Include one row for every `### Requirement:` from `specs/**/spec.md`.
- `Requirement` must use the exact requirement name from the spec.
- `Approved Behavior`, `Test Obligation`, and `Batch` must be non-empty.
- `Batch` must reference an existing `### Batch N` heading from `## Task Batches`.
- Do not satisfy traceability by listing requirement names without behavior/test/batch mappings.

## Contract Structure

Must make obvious: approved behavior, out-of-scope, implementation constraints, batches, test obligations, review gates, and conditions that force a rewind to planning. In Design Constraints, reference only the memories actually read and copy only the applicable invariants into the matching fields. Prefer compression over repeating memory content.

## Approval Model (DP-3)

After drafting: summarize handoff rules, identify ambiguity, flag unmapped requirements, ask user to approve explicitly. After approval:
```bash
ssf state set <change-dir> dp_3_result "approved: <summary>"
ssf state set <change-dir> dp_3_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```
DP-3 is a hard gate — no implementation without this record.

## Stale Contract Detection

Refresh if: scope changed in proposal, requirements changed in specs, constraints changed in design, batches changed materially in tasks, or the contract no longer matches intent.

## Hotfix Mode

Generate minimal contract: Intent Lock (one sentence), Task List (numbered), Approval Gate (DP-3). Skip Scope Fence, Build Rules, Review Gates, Test Evidence. Still requires DP-3 approval.

## Guardrails

- Do not continue to implementation if ambiguity remains
- Do not approve the contract on the user's behalf
- Do not skip the contract because planning docs look complete
- Flag unmapped requirements; do not silently drop them

## Post-Generation

Run `node scripts/spec-superflow.mjs state init <change-dir>` to create `.spec-superflow.yaml` with hashes.
Run `node scripts/spec-superflow.mjs validate <change-dir>` after writing the contract.

If validation fails on `execution-contract.md` traceability, regenerate the whole `execution-contract.md` from `proposal.md`, `specs/`, `design.md`, and `tasks.md`; do not append a bare list of requirement names. Re-run validate once. If it still fails, report the exact unmapped requirements or missing batches before asking for approval.

## Exception Handling

- **Parse failures**: Report specific file and section. Suggest re-running `spec-writer`.
- **Missing files**: List every missing artifact. Route back to `spec-writer`.
- **User interruption**: Re-read all artifacts on resume; check contract staleness via content comparison.
- **Validation failure**: Flag unmapped requirements in Escalation Rules and approval summary.
