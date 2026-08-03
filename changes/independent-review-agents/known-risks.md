# Known Risks

## Residual Product Risks

1. **Reviewer immutability is a behavioral contract.** It receives ordinary host
   project-read and terminal tools so it can independently inspect SCM, but it
   must not edit, mutate Git, run tests/workflow commands, or invoke another
   Agent. The OpenCode public-tool probe proves the required read path leaves a
   controlled fixture unchanged; it cannot guarantee arbitrary model adherence.
   Primary must still freeze exact commands/results and raw evidence. Reviewer
   checks whether that evidence proves each acceptance item; aggregate counts
   alone are insufficient.
2. **Host prompts are part of runtime behavior.** Source contract tests and
   packed OpenCode resolution reduce drift, but a complete post-simplification
   real VS Code Chat business workflow has not been run and remains `PENDING`.
3. **Fresh stage contexts add latency.** The design limits this to three
   high-value checkpoints, allows one bounded same-context re-review, and leaves
   `hotfix`/`tweak` unchanged.
4. **A fixed Reviewer can be unavailable.** The workflow fails closed and keeps
   state unchanged; there is no self-review fallback.
5. **Approval can become stale during repair.** Candidate identity and current
   check invalidate changed Planning, worktree, or evidence inputs and require
   a new candidate review in the same bounded stage context.
6. **Upstream semantic repair can invalidate downstream work.** Primary must ask
   whether to reopen the earliest affected Planning stage before changing
   approved upstream meaning.

## Evidence Boundaries

- Node/source and packed runtime tests prove CLI, guard, file safety, Plugin
  registration, and package behavior only.
- Static Agent or protocol tests do not prove a real VS Code/OpenCode semantic
  review conversation. The OpenCode public-tool probe proves only tool
  availability and unchanged controlled repository state for required reads.
- No company-internal network or remote computer was accessed. Internal
  validation remains pending and must not be reported as passed.
- No tag, release, npm publication, or package upload is part of this candidate.
