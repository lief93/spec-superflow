---
name: spec-writer
description: Create or refine the exact planning artifact set selected by the current workflow route.
---

# Spec Writer

Create or refine planning artifacts when the change has moved beyond exploration.

## Full Workflow Stage Boundary

For exact `workflow: full`, planning is split into two bounded stages. The
first stage creates or repairs only `user-intent.md`, `proposal.md`, and current
delta Specs. Never create, draft, or patch Design or Tasks during that stage.
After current Proposal and Specs receive independent `Approved` review and the
user's DP-1 confirmation is bound to that candidate, the second stage changes
only `design.md` and `tasks.md`; treat Approved Proposal and Specs as read-only.

## Required Inputs

Read `.spec-superflow.yaml` (especially `dp_0_decisions`, `dp_0_confirmed`) and existing planning artifacts. If `docs/project/project-guidelines.md` exists, read the applicable technology/architecture rules and classic implementation recipes. For every affected capability, read the project-root `specs/<capability>/spec.md` as the current behavior baseline. If `.spec-superflow/memories/MEMORY.md` exists, read its concise entrypoint and only linked topics relevant to affected modules, runtime conditions, or design decisions. Use the project baseline for normative code placement and implementation patterns; use Memory only for non-duplicated recalled learnings. If `dp_0_confirmed` is not `true`, stop and route back to `workflow-start` for DP-0.

Before writing Design or Tasks, inspect the real production path that currently
owns the requested behavior and the existing tests around it. Determine the
minimum behavior-changing production seam: the smallest set of existing
production files and responsibilities that must change to satisfy the approved
behavior. Use that seam as the starting scope instead of projecting one layer,
Decision, test double, or Batch from each Scenario.

## Config Check

Run `ssf config --get artifacts.order` and `ssf config --get artifacts.skip`.
The configured order applies to `hotfix` and `tweak`. Exact `full` generates
only the current bounded planning stage and skips any listed artifact; it never
iterates proposal → specs → design → tasks in one pass.

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
Must have: Context (current state, constraints, stakeholders), Goals, Project Baseline Alignment, Requirement And Scenario Coverage, Decisions (Choice + Rationale + Alternatives considered), Risks And Trade-Offs. State the minimum behavior-changing production seam in Context. Create a Decision only when there is a real architecture choice or trade-off; never create one mechanically for each Scenario. When multiple Scenarios use the same technical choice, reuse one Decision. Before freeze, compare every Decision's Choice, Rationale, and Alternatives; when they are semantically the same, merge them and let multiple Scenarios reuse one Decision instead of splitting it by acceptance surface or resource name. Use `No design change` when a Scenario needs no technical decision, including when it is another acceptance example covered by an already selected seam. When no real architecture choice exists, keep `## Decisions`, state `No design change`, and omit every `### Decision:` entry from the template. Project Baseline Alignment maps each Scenario to an applicable classic implementation and architecture rules, and records any deliberate deviation. The coverage table uses the exact Requirement and Scenario titles from the spec and maps each Scenario to a Design Decision, affected area, and reason that area owns the change. Requirement and Scenario cells contain only the exact titles from the spec, without `Requirement:` or `Scenario:` prefixes. Every non-`No design change` value in the coverage table must exactly match a `### Decision: <title>` heading in `## Decisions`; a descriptive sentence or numbered list item is not a decision heading. Use relevant project memories to justify non-duplicated runtime or domain facts without copying whole memories into the design.

Use this exact coverage structure:

```markdown
## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Why Here |
|---|---|---|---|---|
| <exact Requirement title> | <exact Scenario title> | <exact Decision title> | path or symbol | ownership reason |

## Decisions
### Decision: <exact Decision title>
- **Choice**: Selected implementation approach.
- **Rationale**: Why this approach satisfies the Scenario.
- **Alternatives considered**: Rejected alternatives and why.
```

### tasks.md
Must include:
- **Production scope**: include only production files whose behavior must change at the minimum production seam. Add a test file only when it is necessary to prove a distinct acceptance risk; otherwise use an exact `Run existing` row
- **Unchanged upstream behavior**: for an unchanged Repository, ViewModel, store, reducer, or equivalent upstream layer, prefer existing tests and arrange required state through an existing injectable UI or rendering seam. Do not create a fake, repository, helper, or other test-only layer merely to retest unchanged behavior
- **Natural Batch shape**: group ACs by cohesive dependency and deliverable outcome, not by Scenario count; use the fewest Batches that preserve dependency order and independent verification. When all work belongs to one cohesive seam and there is no cross-batch produced artifact, interface, or contract dependency, use one Batch
- **ACs inside each Batch**: one `### AC: <exact Scenario title>` section for each covered Scenario, with the exact Requirement title; no synthetic IDs are required
- **Single ownership**: every spec Scenario belongs to exactly one Batch AC section
- **File Changes per AC**: each Create/Modify/Delete file sits under the AC it serves, with a concrete explanation of what changes, what is added, and what is reused. A shared production change has one owner AC and is described once. Other ACs contain only their distinct production delta or tests; when they have no distinct production delta, do not repeat the shared file or implementation step
- **Baseline-derived files**: derive ownership, implementation order, and reuse candidates from the selected classic implementation; explain deviations in `design.md` rather than silently choosing another pattern
- **Interface impact closure**: when changing an interface, protocol, abstract type, public constructor, or shared contract, search for every production implementation, adapter, fake, mock, test double, and affected module. Include each file that must change, or record why a discovered implementation remains compatible. Add a compile or test obligation for every affected module; do not stop at the first implementation found
- **AC as the join key**: derive file changes from `design.md`, but do not repeat Design Decision metadata in `tasks.md`; the exact Requirement/Scenario titles connect Spec, Design, and Tasks
- **User-visible**: mark every AC `Yes` or `No`; `Yes` requires an AC-specific UI row
- **TDD Test Plan**: use `Layer | Platform | Action | Test File | Test Case | Proves`. Read the real test file and exact Test Case before choosing an action. Use `Update` only when that exact case exists and its method will be extended, `Add` only for a new exact method, and `Run existing` only when the behavior and existing test remain completely unchanged; otherwise use `Unavailable` when applicable
- **Non-mechanical coverage and ownership**: every test row must prove a distinct observable risk; do not mechanically add one row per layer, file, or Scenario clause when a lower-level row already proves the same behavior. The same Test Case, including a `Run existing` row, belongs to one AC only. When an existing case can extend its assertions, use `Update`; do not create a parallel `Add` case with the same meaning. Use `Add` only for a distinct acceptance risk
- **Complete and honest scenario proof**: cover every observable WHEN/THEN/AND outcome in the Scenario across the planned rows. Use Unit/Component/Integration rows for internal state, calls, persistence, ordering, and concurrency. Every UI row must assert the visible result. Only when the Scenario WHEN is user-triggered must it exercise rendered-control interaction. For initial load, lifecycle, or external/system event, use a real existing injectable seam to arrange the condition and still assert the visible result; do not invent a user action. `Proves` may claim only an observable result that the planned command and test mechanism actually assert. A source selector, category, annotation, or similar static property belongs in a File Changes obligation when required; it is not a runtime result and must not be claimed by a behavioral test row. For example, Android `getQuantityString(0/1/2)` does not prove static `quantity="zero"`, `quantity="one"`, or `quantity="other"` selectors exist; put each required selector in File Changes
- **Edge-case precision**: every required edge case named by the spec or design must appear in an exact test row. The row must identify the fixture or precondition and the observable assertion in `Test Case` or `Proves`. An indirect assertion such as one item disappearing does not prove an empty-result state
- **Honest baseline**: `Action` describes the test-source change, not whether production behavior already exists. For test-only characterization or regression coverage, use `Add`/`Update`, record a baseline PASS, and never add a sentinel or deliberate failure to manufacture RED
- **Real targets**: name one project-relative platform test source and exact case; docs, production code, commands, globs, directories, and suite labels are invalid
- **Stable anchors**: use file paths and method/type names when known; do not use line numbers and do not split each method into a separate task
- **Interfaces**: cross-batch Consumes/Produces with exact types
- **Per-AC execution**: use exact file paths and only the execution branch that matches the work. For behavior-changing work, require RED and GREEN, each with a complete repository-executable command verified against the real project tooling. For coverage-only, characterization, or unchanged regression, require BASELINE PASS and RERUN instead; both use a complete repository-executable command selecting the exact Test Case, and never manufacture RED. An Android instrumentation command includes the real Gradle task and exact `class#method`; a JVM command includes the real Gradle task and exact `--tests` selector. A method name alone, `Run AC tests`, or a suite label is invalid
- **Granularity**: each step 2-5 min, atomic
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
- **Change**: Concrete resulting behavior.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Actual platform | Add | path/to/test | exact test name | exact outcome |

#### TDD Steps
Choose exactly one applicable branch and omit the other:
- **Behavior-changing**:
  - [ ] RED: Run `<complete repository-executable command selecting the exact Test Case>` and observe the behavior-specific failure.
  - [ ] GREEN: Implement the minimum change and rerun `<the same complete command>`.
- **Coverage-only, characterization, or unchanged regression**:
  - [ ] BASELINE PASS: Before changing test source, run `<complete repository-executable command selecting the exact Test Case>` and record the pass.
  - [ ] RERUN: After the test-source change, rerun `<the same complete command>` and record the pass.
- [ ] REFACTOR: Run `<complete repository-executable command selecting the AC tests and relevant regression tests>`.
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
- No new UI Test needed → mark the related historical UI file and case `Run existing`.
- No direct match → use an exact file and case from the nearest module UI suite; a suite label is invalid.
- No UI framework exists → mark `Unavailable`, set Test File to `Not configured`, record searched test roots/configuration and the capability gap in Test Case, and do not add dependencies, runners, or CI setup without developer approval.
- Do not plan the final Device Test inside each AC; contract-builder aggregates it after all Batches.
- Screenshot tests are outside this rule until separately enabled.

## Artifact Generation

For `hotfix` or `tweak`, generate one at a time. Stop after each artifact and
wait for explicit user confirmation before generating the next. This prevents
scope drift — if proposal has errors, downstream artifacts are wrong. Exact
`full` uses the grouped semantic handoffs below instead.

1. `proposal.md` → present summary → wait for confirm
2. `specs/` → present requirement list → wait for confirm
3. `design.md` → present key decisions → wait for confirm
4. `tasks.md` → present batch breakdown → wait for confirm

Never generate `execution-contract.md`; only `contract-builder` owns that
artifact, and it may run only after validated planning artifacts receive DP-2
approval. Do not merge DP-2 and DP-3 into one response.

## Full Workflow Planning Handoffs

When persisted workflow is exact `full`, this section replaces the
per-artifact user pauses and non-full DP-2 handoff below. Primary owns user
communication, artifact generation, and finding repair. The fixed Reviewer
owns independent semantic review. Primary must not self-review either semantic
checkpoint.

For the Proposal and Specs stage:

1. Read authoritative `user-intent.md` and current project evidence.
2. Classify the entry and trigger source for each requested behavior. When
   reusing an existing entry or trigger, inspect the real repository and retain
   the supporting path or symbol as evidence. When `user-intent.md` explicitly
   authorizes or requires a new entry, control, or trigger, allow that addition,
   but require Proposal and Scenario text to identify its location or entry,
   trigger action, and verifiable result. Without `user-intent.md` authority,
   do not invent or assume a new entry, control, or trigger.
3. Generate or repair `proposal.md` and current delta Specs only.
4. Check `user-intent.md` item by item: every explicit behavior and constraint
   must have a verifiable landing in `proposal.md` and one or more current Specs
   Scenario outcomes.
5. Cross-check relevant state and value variants, parallel observable surfaces
   such as visible behavior and accessibility semantics, and whether each
   behavior is bound either to the evidenced existing reuse or to an explicitly
   authorized new entry or trigger path.
6. Compare Scenarios pairwise by trigger, outcome, observable surface, and
   acceptance risk, including whether one is a subset or superset of another.
   When Scenarios substantially overlap, especially when the same test would
   prove multiple ACs, merge or narrow them before freezing the candidate or
   invoking Reviewer.
7. Repair every missing or contradictory landing before freezing the candidate
   or invoking Reviewer. Keep this working checklist only in Primary context;
   it is not a new artifact or matrix file.
8. Run the applicable CLI structural checks.
9. Keep all current Proposal and Specs inputs plus the exact check result in
   the Primary context. Do not create Design or Tasks and do not self-approve
   semantics.

After `ssf review check <change-dir> proposal-specs --json` passes, Primary
presents the current goals, scope, behaviors, and non-goals. Only a new
user-authored confirmation may be recorded with:

```bash
ssf state set <change-dir> dp_1_result "confirmed: <summary>"
ssf state set <change-dir> dp_1_candidate_identity "<candidate identity>"
ssf state set <change-dir> dp_1_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

For the Design and Tasks stage, require Primary to retain confirmed goals,
scope, behaviors, and non-goals plus current Approved upstream inputs and DP-1
bound to the current Proposal and Specs candidate. Treat the original request,
organized scope, and approved Proposal and Specs as the immutable upstream
contract:

1. Generate or repair `design.md` and `tasks.md`.
2. Run one in-context review-readiness pass against the real test files,
   methods, project commands, Decision semantics, test ownership, and `Proves`
   claims above; repair every gap before freeze or Reviewer invocation. Keep the
   checklist only in Primary context and create no new artifact.
3. Run the applicable CLI structural checks for Design and Tasks.
4. Keep all five current Planning input families and the exact result in
   Primary. Do not create a contract or implement.

After `ssf review check <change-dir> design-tasks --json` passes, Primary
presents a concise design, batch, and test summary plus the artifact paths.
Only a new user-authored confirmation may be recorded with:

```bash
ssf state set <change-dir> dp_2_result "confirmed: <summary>"
ssf state set <change-dir> dp_2_candidate_identity "<candidate identity>"
ssf state set <change-dir> dp_2_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

For a Proposal or Specs `Request Changes`, Primary repairs only Proposal and
Specs for fresh review; it must not generate dependent Design or Tasks before
current DP-1.
For a Design or Tasks repair, edit only `design.md`
and `tasks.md`. If a finding requires an upstream semantic change, return the
typed `upstream_conflict` without editing any upstream or downstream artifact;
stop and ask the explicit Proposal and Specs reopen question. Do not repair
Tasks or continue downstream. Primary owns the fresh first-stage approval
sequence and never edits while Reviewer runs.

## Validation Checklist

### proposal.md
- `## Why` > 50 chars, `## What Changes`, `## Scope` (In/Out), `## Impact`, `## Capabilities`, no TBD/TODO

### specs/
- SHALL/MUST for required behavior, `#### Scenario:` with WHEN/THEN per requirement, grouped under delta headers, no contradictions

### design.md
- `## Context`, `## Goals`, `## Project Baseline Alignment`, `## Requirement And Scenario Coverage`, `## Decisions` (with Choice+Rationale+Alternatives only when a real architecture choice exists), `## Risks And Trade-Offs`; every spec Scenario appears in both mapping tables

### tasks.md
- `## Interfaces`, numbered Batches, one `### AC` section per Scenario, `User-visible`, `#### File Changes`, `#### TDD Test Plan`, exact platform test files/cases and AC outcomes, concrete per-file change descriptions, ≤5 min steps, no placeholders, every Scenario mapped exactly once, explicit dependencies
- Behavior-changing work uses RED and GREEN; coverage-only, characterization, or unchanged regression uses BASELINE PASS and RERUN. Both branches include REFACTOR with a complete repository-executable command

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

## Non-full DP-2: Artifact Review Gate

For `hotfix` or `tweak` only, present summary of all 4 artifacts (2-3
sentences each). Ask user for adjustments. After approval:
```bash
ssf state set <change-dir> dp_2_result "confirmed: <summary>"
ssf state set <change-dir> dp_2_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

## Handoff Rule

Do not start implementation after writing planning artifacts. Once stable, validated, and DP-2 is recorded, hand off to `contract-builder`.

## Exception Handling

- **Parse failures**: Report specific file/error; don't generate from corrupted templates
- **Missing templates**: Fall back to artifact structure defined in this skill
- **User interruption**: Artifacts on disk are the recovery checkpoint; resume from first missing/incomplete one
- **Validation failure**: Run the Validation Repair Loop. If the second validation fails, report the exact remaining failures and stop before handoff.
