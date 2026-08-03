# Benchmark Report

## Purpose

This report records only local deterministic checks that compare the simplified
review workflow with its acceptance contract. It does not claim model quality,
real VS Code Chat success, or company-internal validation.

## Current Results

| Dimension | Check | Status |
|---|---|---|
| Host topology | Source VS Code/OpenCode and shared workflow contract tests | 46/46 PASS |
| Removed protocol surface | Search shared Skills and host prompts for retired command/graph/receipt/continuity vocabulary | PASS, zero production prompt/Skill matches |
| Planning artifacts | `ssf validate changes/independent-review-agents` | PASS, 0 errors and 0 warnings |
| Review CLI | Candidate/record/check positive, body-free final output, every-byte/status identity, tracked gitlink pointer/dirty/index-state coverage, unsafe transport including no-`O_NOFOLLOW` symlink rejection, stage dependency, and staleness tests | Related Review/candidate/host/worktree 69/69 PASS; complete source suite 422/422 PASS |
| State/guards | Existing mainline lifecycle plus DP/review binding tests | Complete source suite 422/422 PASS |
| Packed runtime | Fresh package install, source/packed CLI and OpenCode public tools | Packed CLI 2/2 PASS; exact 175-entry archive offline smoke PASS; OpenCode public Reviewer status/diff/log/show/untracked-read runtime 1/1 PASS with before/after identity/status/cached diff unchanged |
| Pre-fix model E2E | GPT-5.4 Mars Photos Design/Tasks diagnostic | FAIL: handoff pollution, missing record/check, incomplete review, missed upstream overlap, and invalid static-selector proof |
| Post-fix model E2E | Model-driven VS Code/OpenCode end-to-end review | PENDING, not inferred from resolved prompts |

## Interpretation

- The intended simplification is structural: one Primary, one fixed read-only
  Reviewer, three semantic seams, current-only Review evidence, and the existing
  state machine.
- Passing contract and CLI tests can prove registration, permissions, ordering,
  identity, and fail-closed behavior.
- OpenCode's public Agent-tool interface proves the declared Reviewer can acquire
  the required SCM/file view without changing candidate identity, porcelain
  status, or cached diff in the controlled fixture. It does not prove arbitrary
  model adherence or semantic review quality.
- The pre-fix model E2E failure motivated the bounded handoff, mandatory
  raw-write/record/check sequence, overlap-first scan, and Android static-proof
  counterexample; a post-fix model E2E is still required to assess model quality.
- They cannot prove the semantic quality of an arbitrary model review or that an
  unexecuted real host/internal environment passed.
