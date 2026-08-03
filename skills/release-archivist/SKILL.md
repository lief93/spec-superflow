---
name: release-archivist
description: Close out a spec-superflow change with verification, summary, and archive readiness. Invoke when implementation is complete, verification is underway, or the user asks for a final wrap-up.
---

# Release Archivist

Finish a spec-superflow change cleanly with verification evidence.

Before creating or updating `pr-summary.md`, read `references/pr-summary.md`
and use it as the exact structure. If the reference is missing or unreadable,
stop instead of reconstructing the summary from memory.

## Full Workflow Two-Step Route

For exact persisted `workflow: full`, use two separate steps.

### Pre-review preparation

Before final semantic review, complete all applicable verification below, AC
evidence, frontend evidence, known risks, and PR summary (`pr-summary.md`).
Record every requested real-runtime acceptance result
honestly as `Pass`, `Fail`, or `PENDING`; a static or protocol test never
substitutes for an unexecuted real runtime. Run final `ssf validate
<change-dir>` and `ssf state check <change-dir>` now. Then run:

```bash
ssf guard check <change-dir> executing closing --json
```

Without a current final review, this pre-review command must exit 1 with only
the final review dimension failing. Any other failing dimension means the evidence is not
ready: repair it, rerun final validation and state check, and repeat the
preflight. Do not compute a candidate or invoke Reviewer until this condition
holds. Return the exact results to Primary without transitioning state. Primary
then freezes
`pr-summary.md`, `known-risks.md`, and `runtime-evidence.md`, computes the
worktree-aware final candidate without writing another Review artifact, and
invokes the fixed Reviewer.

Before final review, `pr-summary.md > Verification Evidence` must contain these
three exact rows with concrete evidence:

- `Artifact validate`: exact command, exit status, and evidence path.
- `State check`: exact command, exit status, and hashes.
- `Runtime acceptance`: exact real-runtime evidence and `Pass`, or the exact
  unexecuted boundary and `PENDING`.

A delivery package is not a default full-workflow obligation. Run and record
package, SHA-256, entry-count, and hygiene evidence only when the current Specs
explicitly require a delivery package or `tasks.md > TDD Test Plan`
explicitly requires a delivery package. Record it through the matching AC Test
Evidence row; do not add another fixed Verification Evidence row for an ordinary
Story.

An applicable runtime failure remains blocking. An unexecuted runtime stays
`PENDING` and is disclosed to the fixed Reviewer and in residual risks; it does
not become `Pass` and does not by itself block a source-only change. Never claim
real VS Code Chat or company-internal validation without the raw evidence.

### Post-approval state progression

After current final `Approved`, perform the state transition only, followed by
read-only persisted-state verification:

```bash
ssf state transition <change-dir> closing
ssf state get <change-dir> state
```

Require the persisted state returned by `state get` to be exactly `closing`.
That read-only command does not generate or update a candidate input. The
transition guard may read the frozen tasks, tests, evidence, runtime/delivery
status, and current final review. It must not rerun tests,
validation, state checks, Git/package/runtime commands, create or update
evidence or PR summary, or modify code, tests, risks, and review context. If the
guard reports a missing, failing, stale, or inconsistent frozen dimension, keep
state `executing`, return to pre-review preparation, and require a fresh final review
after the new complete freeze.

The remaining sections define pre-review verification for exact `full` and the
complete non-full closure flow. Do not repeat them after final approval.

## The Iron Law: Verification Before Completion

Claiming work is complete without verification is dishonesty, not efficiency. Before claiming any status:
1. IDENTIFY the command that proves the claim
2. RUN the full command fresh
3. READ output, check exit code
4. VERIFY output confirms the claim
5. Only THEN make the claim

**Forbidden before evidence**: "should", "probably", "seems to", expressions of satisfaction without output.

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check |
| Build succeeds | Build exit 0 | Linter passing |
| Bug fixed | Original symptom passes | Code changed |
| Requirements met | Line-by-line checklist | Tests passing |

## Verification Steps

### Step 1: Test Suite
Run full test suite. Record total/passed/failed/skipped. Zero failures = PASS.

For every row in `tasks.md > TDD Test Plan`, create one matching row in
`pr-summary.md > AC Test Evidence` using the exact table from
`references/pr-summary.md`.

Copy Requirement and AC from the owning task section, then copy Layer, Platform,
Test File, and Test Case exactly from each `tasks.md > TDD Test Plan` row.
Do not paraphrase, combine rows, or replace the table with prose. `Result` is
`Pass` for a successfully executed obligation and `Unavailable` only for a
planned `Unavailable` obligation. `Command` and `Evidence` must both be concrete
and non-empty.

### Step 1A: Frontend Verification

Read `## Frontend Verification` from `execution-contract.md`.

When `Frontend Impact: Yes`:

1. Run every exact UI Test File and Test Case in `tasks.md > TDD Test Plan` fresh. A broader smoke/regression suite may be additional evidence, never a replacement.
2. Run Device Test after all Batches are complete: exercise at least one
   reachable branch of each affected feature on one project baseline
   simulator/device per affected native platform. For Web, use the default real
   browser and desktop viewport; add a mobile viewport only when responsive
   behavior is affected. Externally controlled branches driven by service data,
   network state, account state, or another unavailable condition may rely on
   their exact automated UI or unit test evidence instead of device replay.
   Name the branch actually run and disclose which remaining branches were
   covered only by automated evidence; never claim those branches were run on a
   device.
3. Record one row per task test obligation in `pr-summary.md > AC Test Evidence`, plus the aggregate UI and Device results in `Frontend Verification Evidence`.
4. Each task row with `Add`, `Update`, or `Run existing` must be `Pass`. Any missing or failing required UI case is FAIL.
5. `Unavailable` is CONDITIONAL, not PASS. Record searched locations/configuration and the missing capability; proceed only after developer acceptance. Do not introduce a framework during release verification.
6. Device Test must be `Pass` for the required reachable feature branch. A
   failure in that executed branch, or missing evidence that any affected
   feature was reached, is FAIL. Lack of device evidence for an externally
   controlled remaining branch is not a failure when its exact task-owned
   automated evidence passed and the boundary is disclosed.

Screenshot testing is outside this version and is not required by this gate.

For an accepted `Unavailable` UI Test, record the decision before closure:
```bash
ssf state set <change-dir> dp_6_result "confirmed conditional: <developer acceptance and capability-gap summary>; Device Test passed"
ssf state set <change-dir> dp_6_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

### Step 2: Completeness
Compare task Batches against the actual diff. Every SHALL/MUST must have implementation evidence. Missing = Critical severity.

### Step 3: Coherence
Compare design decisions against code. Read the configured project development baseline and selected classic implementation, then read relevant project memories for non-duplicated facts. Evaluate architecture, ownership, source-of-truth, reuse, boundary, and convention consistency. Check naming consistency. Unapproved baseline deviations or inconsistencies = IMPORTANT.

### Step 4: Unintended Scope
Check for files modified outside scope fence, new dependencies not in design. Unplanned = WARN.

### Step 5: Report

| Dimension | Status | Findings |
|-----------|--------|----------|
| Completeness | PASS/FAIL/WARN | [list] |
| Correctness | PASS/FAIL/WARN | [list] |
| Coherence | PASS/FAIL/WARN | [list] |

**Verdict**: PASS (all PASS) / CONDITIONAL (WARN only) / FAIL (any FAIL).
- FAIL → fix issues or route back to build-executor
- CONDITIONAL → present WARNs, proceed only with user acceptance
- PASS → proceed to final checks

## Final Checks

- Tests passing? (cite command and output)
- All batches complete? (cite batch status)
- Update every completed `tasks.md` checkbox to `[x]` before attempting `closing`.
- Set `batches_completed` to the number of completed `## Batch N:` sections,
  never the number of task checkboxes.
- Scope added without artifact updates?
- Unresolved blockers or known risks?
- Delta specs exist that need merging?
- Frontend contract obligations have matching `pr-summary.md` evidence?
- Run `ssf audit <change-dir>` — include `decision-point-audit.md` in archive

### Auto Memory Pass

After verification establishes the final result, invoke `memory-manager` once as a catch-up pass over team-wide feedback, code-invisible project context, external references, and verified runtime or debugging conclusions that remain expensive to rediscover. Exclude personal feedback and ordinary fix recipes. Write only items that pass every admission condition. `NONE` is the normal result and must not block closure.

### DP-6 (Verification Outcome)
```bash
ssf state set <change-dir> dp_6_result "<pass|confirmed conditional|fail>: <summary>"
ssf state set <change-dir> dp_6_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```
If FAIL, do NOT proceed to DP-7. Route back or ask about abandonment.

After all mandatory checks pass, set `ssf state set <change-dir> test_result pass`. Do not set it from a successful build, code-level tests alone, or planned-but-unrun frontend checks.

### DP-7 (Archive Confirmation)
```bash
ssf state set <change-dir> dp_7_result "confirmed: <archive summary>"
ssf state set <change-dir> dp_7_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```
Verify DP-0 through DP-6 are recorded before DP-7.

## Archive Rule

If implementation diverged from the contract, return to `bridging` before closure.

## Post-Verification

This section applies only to `hotfix` and `tweak` closure. Exact `full` uses the
two-step route above and must not repeat these commands after final approval.

Run `ssf guard check <change-dir> executing closing --json` before `ssf state transition <change-dir> closing`.
If the guard fails, fix the exact reported evidence or task-completion gap
before retrying. Do not repeatedly attempt the transition while the guard
reports failures. If delta specs exist, route to `spec-merger`.

After every final artifact edit, run `ssf validate <change-dir>`. If artifacts
changed after the latest state transition, rebuild or transition state through
the supported CLI flow, then run `ssf state check <change-dir>`. Both commands
must exit zero after all evidence and summary edits. Do not claim completion
when validation fails or state is inconsistent; report the exact blocking
output and route back to the owning Skill.

## Lightweight Closure (hotfix/tweak)

Verify files exist and are non-empty, run `node --check` on code files, skip the general 5-step verification. Frontend hotfix/tweak changes still require the contract's UI Test and Device Test obligations. Still record DP-6 and DP-7.

## Exception Handling

- **Parse failures**: Report exact file and section
- **Missing files**: If audit can't generate, run `ssf audit` manually
- **User interruption**: Re-run verification from the beginning on resume
- **DP gaps**: Flag missing DPs during DP-6; ask user whether to proceed or return
