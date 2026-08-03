---
name: spec-writer
description: Create or refine spec-superflow planning artifacts. Invoke when the change is understood well enough to write proposal.md, specs/, design.md, and tasks.md.
---

# Spec Writer

Create or refine planning artifacts when the change has moved beyond exploration.

## Required Inputs

Read `.spec-superflow.yaml` (especially `dp_0_decisions`, `dp_0_confirmed`) and existing planning artifacts. If `docs/project/project-guidelines.md` exists, read the applicable technology/architecture rules and classic implementation recipes. For every affected capability, read the project-root `specs/<capability>/spec.md` as the current behavior baseline. If `.spec-superflow/memories/MEMORY.md` exists, read its concise entrypoint and only linked topics relevant to affected modules, runtime conditions, or design decisions. Use the project baseline for normative code placement and implementation patterns; use Memory only for non-duplicated recalled learnings. If `dp_0_confirmed` is not `true`, stop and route back to `workflow-start` for DP-0.

## Config Check

Run `ssf config --get artifacts.order` and `ssf config --get artifacts.skip`. Generate in configured order (default: proposal → specs → design → tasks) and skip any listed artifacts.

## Artifact Roles

- `<change-dir>/proposal.md`: why and scope
- `<change-dir>/specs/<capability>/spec.md`: required behavior (testable)
- `<change-dir>/design.md`: architecture decisions and trade-offs (not line-by-line)
- `<change-dir>/tasks.md`: dependency-aware implementation steps

All generated planning artifacts must stay under the active `<change-dir>`
initialized by `workflow-start`. Never create planning artifacts at the
repository root. Project-root `specs/` is only the long-lived current-behavior
baseline read by this Skill; change-specific delta specs always use
`<change-dir>/specs/<capability>/spec.md`.

## Working Rules

**Honor DP-0**: Read `dp_0_decisions`, respect confirmed constraints, don't silently expand scope. Pause on unconfirmed decisions.

**Keep Spec behavioral**: Project baseline rules do not belong in `specs/`. Apply them in `design.md` and `tasks.md`.

### proposal.md
Must state: problem, what changes, capabilities affected, impact areas.

### specs/
Every requirement must be testable. Use SHALL or MUST. Every requirement must have at least one `#### Scenario:` with WHEN/THEN. Group under ADDED/MODIFIED/REMOVED Requirements headers.

### design.md
Must have: Context, Requirement And Scenario Coverage, Decisions (Choice + Rationale + Alternatives considered), and Risks And Trade-Offs. Use one coverage table to map every Scenario to its design decision, affected area, applicable project baseline or reuse anchor, constraint or approved deviation, and ownership reason. Do not repeat the same Scenario mapping in a separate baseline table. Requirement and Scenario cells contain only the exact titles from the spec, without `Requirement:` or `Scenario:` prefixes. Use `No design change` when a Scenario needs no technical decision. Every non-`No design change` value in the coverage table must exactly match a `### Decision: <title>` heading in `## Decisions`; a descriptive sentence or numbered list item is not a decision heading. Use relevant project memories to justify non-duplicated runtime or domain facts without copying whole memories into the design. Add migration or open-question sections only when the change actually has them.

Use this exact coverage structure:

```markdown
## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Why Here |
|---|---|---|---|---|---|---|
| <exact Requirement title> | <exact Scenario title> | <exact Decision title> | path or symbol | guideline, classic implementation, or existing symbol | applicable constraint or approved deviation | ownership reason |

## Decisions
### Decision: <exact Decision title>
- **Choice**: Selected implementation approach.
- **Rationale**: Why this approach satisfies the Scenario.
- **Alternatives considered**: Rejected alternatives and why.
```

### tasks.md
Must include:
- **ACs inside each Batch**: one `### AC: <exact Scenario title>` section for each covered Scenario, with the exact Requirement title; no synthetic IDs are required
- **Single ownership**: every spec Scenario belongs to exactly one Batch AC section
- **File Changes per AC**: each Create/Modify/Delete file sits under the AC it serves, with a concrete explanation of what changes, what is added, and what is reused; when one file serves multiple ACs, repeat the file under each AC with only that AC's change
- **Baseline-derived files**: derive ownership, implementation order, and reuse candidates from the selected classic implementation; explain deviations in `design.md` rather than silently choosing another pattern
- **Interface impact closure**: when changing an interface, protocol, abstract type, public constructor, or shared contract, search for every production implementation, adapter, fake, mock, test double, and affected module. Include each file that must change, or record why a discovered implementation remains compatible. Add a compile or test obligation for every affected module; do not stop at the first implementation found
- **AC as the join key**: derive file changes from `design.md`, but do not repeat Design Decision metadata in `tasks.md`; the exact Requirement/Scenario titles connect Spec, Design, and Tasks
- **Reviewable file rationale**: every file entry states why that file is the correct ownership point for the AC, the resulting change, and any new symbol or reuse target. A reviewer must be able to follow AC -> Design Decision -> file rationale without searching for an implicit link
- **User-visible**: mark every AC `Yes` or `No`; `Yes` requires an AC-specific UI row
- **TDD Test Plan**: every AC has at least one exact test row using `Layer | Platform | Action | Test File | Test Case | Proves`; actions are `Add`, `Update`, `Run existing`, or `Unavailable`
- **Complete scenario proof**: cover every observable WHEN/THEN/AND outcome in the Scenario across the planned rows. Use Unit/Component/Integration rows for internal state, calls, persistence, ordering, and concurrency; use UI rows for rendered state and user interaction. `Proves` must name the exact outcome, not merely say the test covers the AC
- **Observable tests only**: every planned row needs a controllable precondition and an observable signal in the current or explicitly planned harness. Do not invent tests around a no-op fake, no-op callback, inert refresh, or inaccessible UI state. Add the smallest justified test seam to File Changes when the Scenario requires it; otherwise use a real existing case or omit unrelated preservation coverage
- **Edge-case precision**: every required edge case named by the spec or design must appear in an exact test row. The row must identify the fixture or precondition and the observable assertion in `Test Case` or `Proves`. An indirect assertion such as one item disappearing does not prove an empty-result state
- **Honest baseline**: `Action` describes the test-source change, not whether production behavior already exists. For test-only characterization or regression coverage, use `Add`/`Update`, record a baseline PASS, and never add a sentinel or deliberate failure to manufacture RED
- **Real targets**: name one project-relative platform test source and exact case; docs, production code, commands, globs, directories, and suite labels are invalid
- **Stable anchors**: use file paths and method/type names when known; do not use line numbers and do not split each method into a separate task
- **Interfaces**: cross-batch Consumes/Produces with exact types
- **Batch execution**: keep AC-specific files and test rows under each AC, then add one Batch Verification block per Batch with the exact RED/baseline, GREEN, and regression commands. Do not repeat the same command sequence under every AC
- **Zero placeholders**: no TBD, TODO, "figure out", "add appropriate"
- **Dependency ordering**: depends only on prior tasks, explicit "Depends on: Batch N"

Use these exact Markdown headings inside every `### AC:` section:

```markdown
## Batch 1: <goal>

### AC: <exact Scenario title>
- **Requirement**: <exact Requirement title>
- **User-visible**: No

#### File Changes
##### Modify `path/to/file`
- **Why this file**: This file owns the behavior or integration seam required by the AC.
- **Change**: Concrete resulting behavior.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Actual platform | Add | path/to/test | exact test name | exact outcome |

### Batch Verification
- [ ] RED / Baseline: Run the exact focused command and record a behavior-specific failure or baseline PASS.
- [ ] GREEN: Run the same focused command and pass every planned AC case.
- [ ] Regression: Run the affected regression command with zero failures.
```

For file entries, use exactly `##### Create \`path/to/file\``,
`##### Modify \`path/to/file\``, or `##### Delete \`path/to/file\``. Do not
replace these headings with bold list labels such as `- **File Changes**:`.

For Web, Android, HarmonyOS, iOS, desktop, or another user-interface client:

- Unit, Component, Integration, and UI tests are all part of the AC's TDD strategy; do not treat UI Test as post-TDD evidence.
- Put each behavior at the lowest stable test layer that proves it. Do not duplicate the same assertion across layers without a distinct regression risk.
- User-visible rendering, interaction, navigation, input, state, or error behavior → include an `Add` or `Update` UI row and use it as the outer RED/GREEN loop.
- A UI row must perform the Scenario's user action through a rendered control and assert the visible result. Direct ViewModel, callback, repository, or reducer calls may arrange preconditions or simulate a genuine system, lifecycle, or external event, but cannot replace a user WHEN. When no user affordance exists, add a UI row only if the Scenario has a distinct visible outcome to prove; otherwise keep the internal behavior at Unit, Component, or Integration level.
- When visible output is derived from ViewModel, reducer, store, or repository state, identify an existing injectable rendering seam or plan the smallest content-level seam that accepts that state. Test state-to-UI derivation separately from lazy, scrolling, or repeated content behavior. Do not claim state mapping is covered by asserting only a child component parameter or only the subset of items currently composed on screen.
- When that user-visible behavior already works and the requested change only adds or strengthens coverage, the outer loop is baseline PASS → preserve behavior; do not fabricate RED.
- No new UI Test needed → use `Run existing` only when a changed seam creates a credible regression risk and the named historical case observes that risk. A generic preserve statement does not require a new row.
- No direct match → use an exact file and case from the nearest module UI suite; a suite label is invalid.
- No UI framework exists → mark `Unavailable`, set Test File to `Not configured`, record searched test roots/configuration and the capability gap in Test Case, and do not add dependencies, runners, or CI setup without developer approval.
- Do not plan the final Device Test inside each AC; contract-builder aggregates it after all Batches.
- Screenshot tests are outside this rule until separately enabled.

## Artifact Generation

Generate one at a time. Stop after each artifact and wait for explicit user confirmation before generating the next. This prevents scope drift — if proposal has errors, downstream artifacts are wrong.

1. `proposal.md` → present summary → wait for confirm
2. `specs/` → present requirement list → wait for confirm
3. `design.md` → present key decisions → wait for confirm
4. `tasks.md` → present batch breakdown → wait for confirm

Never generate `execution-contract.md`; only `contract-builder` owns that
artifact, and it may run only after validated planning artifacts receive DP-2
approval. Do not merge DP-2 and DP-3 into one response.

## Validation Checklist

### proposal.md
- `## Why` > 50 chars, `## What Changes`, `## Scope` (In/Out), `## Impact`, `## Capabilities`, no TBD/TODO

### specs/
- SHALL/MUST for required behavior, `#### Scenario:` with WHEN/THEN per requirement, grouped under delta headers, no contradictions

### design.md
- `## Context`, one `## Requirement And Scenario Coverage` table containing baseline/reuse context, `## Decisions` (≥1 when design changes exist, with Choice+Rationale+Alternatives), and `## Risks And Trade-Offs`; every spec Scenario appears exactly once in the coverage map

### tasks.md
- Optional `## Interfaces`, numbered Batches, one `### AC` section per Scenario, `User-visible`, `#### File Changes`, `#### TDD Test Plan`, exact platform test files/cases and AC outcomes, concrete per-file change descriptions, one executable `### Batch Verification` per Batch, no placeholders, every Scenario mapped exactly once, explicit dependencies

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
- `tasks.md` failure: regenerate `tasks.md` from the current proposal/specs/design, ensuring every Scenario has one owning Batch AC section with its files and TDD steps.
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
