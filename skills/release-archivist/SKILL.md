---
name: release-archivist
description: Close out a spec-superflow change with verification, summary, and archive readiness. Invoke when implementation is complete, verification is underway, or the user asks for a final wrap-up.
---

# Release Archivist

Finish a spec-superflow change cleanly with verification evidence.

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

### Step 1A: Frontend Verification

Read `## Frontend Verification` from `execution-contract.md`.

When `Frontend Impact: Yes`:

1. Run the planned affected UI regression set fresh. This includes added/updated UI tests or the related historical UI tests named by each AC. If there is no direct historical match, run the planned module smoke/regression set. Do not default to the entire project suite unless shared navigation, shared UI, global state, or acceptable test cost justifies it.
2. Run Device Test after all Batches are complete: build, install/launch, and exercise each affected user path on at least one project baseline simulator/device per affected native platform. For Web, use the default real browser and desktop viewport; add a mobile viewport only when responsive behavior is affected.
3. Record actual results in `pr-summary.md > Frontend Verification Evidence`: planned obligation, result, environment, command/procedure, and evidence.
4. UI Test result must be `Pass` when the contract says `Add`, `Update`, or `Run existing`. A missing or failing required UI Test is FAIL.
5. `Unavailable` is CONDITIONAL, not PASS. Record searched locations/configuration and the missing capability; proceed only after developer acceptance. Do not introduce a framework during release verification.
6. Device Test must be `Pass`. Missing evidence, build/install/launch failure, or an unverified affected path is FAIL.

Screenshot testing is outside this version and is not required by this gate.

For an accepted `Unavailable` UI Test, record the decision before closure:
```bash
ssf state set <change-dir> dp_6_result "confirmed conditional: <developer acceptance and capability-gap summary>; Device Test passed"
ssf state set <change-dir> dp_6_timestamp $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

### Step 2: Completeness
Compare contract batches against actual diff. Every SHALL/MUST must have implementation evidence. Missing = Critical severity.

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
- Scope added without artifact updates?
- Unresolved blockers or known risks?
- Delta specs exist that need merging?
- Frontend contract obligations have matching `pr-summary.md` evidence?
- Run `ssf audit <change-dir>` — include `decision-point-audit.md` in archive

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

Run `node scripts/spec-superflow.mjs state transition <change-dir> closing`. If delta specs exist, route to `spec-merger`.

## Lightweight Closure (hotfix/tweak)

Verify files exist and are non-empty, run `node --check` on code files, skip the general 5-step verification. Frontend hotfix/tweak changes still require the contract's UI Test and Device Test obligations. Still record DP-6 and DP-7.

## Exception Handling

- **Parse failures**: Report exact file and section
- **Missing files**: If audit can't generate, run `ssf audit` manually
- **User interruption**: Re-run verification from the beginning on resume
- **DP gaps**: Flag missing DPs during DP-6; ask user whether to proceed or return
