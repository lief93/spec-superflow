# Progress Ledger: independent-review-agents

## Current authoritative candidate

- Current state: `specifying`.
- Workflow: `full`; one user-visible Primary owns all mutable work and one
  hidden fixed read-only Reviewer owns the three semantic checkpoints.
- Current planning artifacts hash:
  `sha256:e5f95847929915012d2f14249c6d4e3a363f9c6f5020bb5d42accf8e9331275d`.
- Current execution-contract hash:
  `sha256:6d165da18b9d7a872fd7e9f9c66284b6d7a5c6bbca3bf41f4a8ffdf1cfa10b7c`.
- Current Review result and CLI-owned current-candidate sidecar files: none.
- DP-1 through DP-4 and their candidate/hash bindings: unset.
- `batches_completed`: `0`.
- Host contract suite: `46/46 PASS`; typed evidence plus managed workflow:
  `26/26 PASS`; complete source suite: `419/419 PASS`.
- Exact OpenCode 1.14.48 repository/packed resolved configuration: `1/1 PASS`
  through public `opencode debug agent/config` only.
- Exact package: 175 entries, SHA-256
  `6a86e8cc3ee1e4548d76b85596e25f58aaaf8b4bb13ed7cf8249831eb0811fb7`.
  Offline isolated-prefix install, installed version/doctor/prompt checks, and
  hygiene all PASS.
- Pre-fix GPT-5.4 Mars Photos Design/Tasks E2E: `FAIL`; it exposed the oversized
  handoff, skipped raw record/check, incomplete initial review, missed upstream
  overlap, and invalid Android static-selector proof. Post-fix model-driven E2E:
  `PENDING`; resolved prompt tests do not replace it.
- Real VS Code 1.123 combined acceptance: `PENDING`; it has not been executed
  for the current candidate.
- Company-internal validation remains `PENDING` and unclaimed.
- Reviewer context contract: each stage's initial review starts fresh; only its
  one repair/re-review may resume that stage context. Host task identifiers stay
  ephemeral and are not written into project artifacts.
- Candidate implementation files exist, but the state ledger does not claim
  current Planning review, user approval, execution authorization, completed
  Batches, final Code Review, or runtime acceptance.

## Superseded ledgers

Earlier five-Batch and three-Batch execution ledgers are historical only. Their
approval records, hashes, test totals, package hashes, and `executing` state do
not describe the current candidate and are not completion evidence.
