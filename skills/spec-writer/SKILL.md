---
name: spec-writer
description: Create or refine spec-superflow planning artifacts. Invoke when the change is understood well enough to write proposal.md, specs/, design.md, and tasks.md.
---

# Spec Writer

Create or refine planning artifacts when the change has moved beyond exploration.

## Required Inputs

Read `.spec-superflow.yaml` (especially `dp_0_decisions`, `dp_0_confirmed`) and any existing planning artifacts. If `.spec-superflow/project-development-rules.md` exists, read it and map applicable rules into the design and relevant tasks. If `dp_0_confirmed` is not `true`, stop and route back to `workflow-start` for DP-0.

## Config Check

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/get-config" artifacts.order` — generate in configured order (default: proposal → specs → design → tasks). Run with `artifacts.skip` — skip any listed artifacts.

## Artifact Roles

- `proposal.md`: why and scope
- `specs/`: required behavior (testable)
- `design.md`: architecture decisions and trade-offs (not line-by-line)
- `tasks.md`: dependency-aware implementation steps

## Working Rules

**Honor DP-0**: Read `dp_0_decisions`, respect confirmed constraints, don't silently expand scope. Pause on unconfirmed decisions.

### proposal.md
Must state: problem, what changes, capabilities affected, impact areas.

### specs/
Every requirement must be testable. Use SHALL or MUST. Every requirement must have at least one `#### Scenario:` with WHEN/THEN. Group under ADDED/MODIFIED/REMOVED Requirements headers.

### design.md
Must have: Context (current state, constraints, stakeholders), Goals, Decisions (Choice + Rationale + Alternatives considered), Project Rules Compliance Plan, Risks And Trade-Offs. The compliance plan lists only applicable rules, planned code placement, and reuse targets. If rules are not configured, record `Not configured`; do not invent rules.

### tasks.md
Must include:
- **File Structure**: all files with one-sentence responsibility (Create/Modify)
- **Interfaces**: cross-batch Consumes/Produces with exact types
- **Per-task**: exact file paths, expanded TDD phases (5 steps), Interfaces block
- **Granularity**: each step 2-5 min, atomic
- **Zero placeholders**: no TBD, TODO, "figure out", "add appropriate"
- **Dependency ordering**: depends only on prior tasks, explicit "Depends on: Batch N"

## Artifact Generation

Generate one at a time. Confirm each before next. This prevents scope drift — if proposal has errors, downstream artifacts are wrong.

1. `proposal.md` → present summary → wait for confirm
2. `specs/` → present requirement list → wait for confirm
3. `design.md` → present key decisions → wait for confirm
4. `tasks.md` → present batch breakdown → wait for confirm

## Validation Checklist

### proposal.md
- `## Why` > 50 chars, `## What Changes`, `## Scope` (In/Out), `## Impact`, `## Capabilities`, no TBD/TODO

### specs/
- SHALL/MUST for required behavior, `#### Scenario:` with WHEN/THEN per requirement, grouped under delta headers, no contradictions

### design.md
- `## Context`, `## Goals`, `## Decisions` (≥1, with Choice+Rationale+Alternatives), `## Project Rules Compliance Plan`, `## Risks And Trade-Offs`

### tasks.md
- `## File Structure`, `## Interfaces`, numbered tasks, exact file paths, TDD phases, ≤5 min steps, no placeholders, every requirement mapped, explicit dependencies

**If any artifact fails validation, fix before handing off to contract-builder.**

## Validation Repair Loop

After all non-skipped planning artifacts are written, run:

```bash
ssf validate <change-dir>
```

If validation fails, do not hand off to `contract-builder`. Regenerate the failing planning artifacts from DP-0, the approved requirement discussion, and the current artifact set; do not patch symptoms with isolated lines.

Regeneration rules:

- `proposal.md` failure: regenerate `proposal.md`; because proposal scope drives downstream artifacts, re-check and regenerate `specs/`, `design.md`, and `tasks.md` if scope, capabilities, or out-of-scope items changed.
- `specs/` failure: regenerate the affected `specs/<capability>/spec.md` files using the required `spec.md` filename and delta headers; if requirement names or behaviors change, regenerate `design.md` and `tasks.md`.
- `design.md` failure: regenerate `design.md` from the current proposal/specs; if decisions, interfaces, or constraints change, regenerate `tasks.md`.
- `tasks.md` failure: regenerate `tasks.md` from the current proposal/specs/design, ensuring every requirement maps to concrete batches and TDD steps.
- `specs/ layout` failure: move or rewrite misplaced markdown into `specs/<capability>/spec.md`; remove duplicate or orphan spec files created by your failed generation attempt.

After regenerating, run `ssf validate <change-dir>` once more.

- If it passes: present the final artifact summary and proceed to DP-2 approval.
- If it still fails: stop, report the exact remaining validation errors, and do not route to `contract-builder`.

Limit: one automatic regeneration cycle per artifact family (`proposal`, `specs`, `design`, `tasks`) before stopping for user input. This prevents silent churn and keeps the repair auditable.

## DP-2: Artifact Review Gate

Present summary of all 4 artifacts (2-3 sentences each). Ask user for adjustments. After approval:
```bash
ssf state set <change-dir> dp_2_result "approved: <summary>"
ssf state set <change-dir> dp_2_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

## Handoff Rule

Do not start implementation after writing planning artifacts. Once stable, validated, and DP-2 is recorded, hand off to `contract-builder`.

## Exception Handling

- **Parse failures**: Report specific file/error; don't generate from corrupted templates
- **Missing templates**: Fall back to artifact structure defined in this skill
- **User interruption**: Artifacts on disk are the recovery checkpoint; resume from first missing/incomplete one
- **Validation failure**: Run the Validation Repair Loop. If the second validation fails, report the exact remaining failures and stop before handoff.
