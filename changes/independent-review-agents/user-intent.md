# User Intent: Independent Review Agents

## Problem

Planning Design/Tasks and completed implementation need semantic review from a
context independent of the Agent that authored or implemented them. The change
must remain understandable and reliable inside VS Code and OpenCode without
inventing another orchestration system.

## Confirmed Scope

- Keep one user-visible Primary. It owns user communication, planning,
  implementation, tests, evidence, and finding repair.
- Add one hidden fixed `Spec Superflow Reviewer` with ordinary host project-read
  and terminal tools. Its contract is behaviorally read-only: it may inspect the
  repository and run read-only SCM commands, but it must not mutate the
  worktree, Git state, workflow state, or another Agent. Start each stage's
  initial review in a fresh independent context and reuse that context only for
  the one permitted same-stage re-review.
- For exact `workflow: full`, review Proposal/Specs, then Design/Tasks, then the
  final frozen implementation candidate.
- Keep user DP-1, DP-2, and DP-3 confirmations separate from Reviewer approval.
- Reuse the existing state machine and `state transition` / `state set` flow.
- Keep Review CLI small: `candidate`, `record`, and `check`, with fixed in-change
  report paths and current-candidate staleness checks.
- Keep `/workflow-init` as the only bootstrap route. Ordinary requests and
  internal Skills use the global `ssf` directly.
- Keep `hotfix` and `tweak` on their existing paths without fixed Reviewer
  checkpoints.

## Non-goals

- No separate Dev Agent, extra user-visible role, or extra workflow state.
- No host identity or continuity protocol, orchestration graph, receipt, lock,
  or alternate state machine.
- No Reviewer writes, mutating Git commands, test or workflow-command
  execution, state changes, user contact, or nested Agent calls. Read-only SCM
  inspection is required, not a new product tool or command allowlist.
- No public-network dependency, remote computer access, internal-network claim,
  tag, release, or npm publication.
- No claim that an unexecuted real VS Code/OpenCode/internal runtime passed;
  unexecuted validation remains `PENDING`.

## Success Criteria

1. Both hosts expose one Primary and one hidden fixed Reviewer with the intended
   permission boundary.
2. Exact full workflow enforces three current semantic checkpoints in the
   required order, while non-full paths remain unchanged.
3. `Request Changes`, malformed output, unsafe report transport, and stale
   candidates fail closed without changing workflow state.
4. Planning DPs remain user-authored and bind to current approved candidate
   identities; DP-3 also binds the current contract hash.
5. Final approval uses an explicit Git base and covers committed, staged,
   unstaged, untracked, and evidence inputs before the single closing
   transition.
6. The public final candidate contains only metadata and path references.
   Reviewer independently obtains the complete fixed-base diff and reads every
   changed and untracked file through ordinary host tools; record/check prove
   the candidate and worktree did not drift.
7. Source and packed runtime tests prove CLI, guard, host topology, package
   hygiene, and version consistency without overstating real runtime evidence.
