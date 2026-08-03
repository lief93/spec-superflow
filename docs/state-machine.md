# State Machine

`spec-superflow` treats workflow progression as explicit state transitions.

## States

### `exploring`

- intent is still fuzzy
- options are still being compared
- no implementation is allowed
- `need-explorer` is active

### `specifying`

- planning artifacts are being written or revised
- proposal, specs, design, and tasks are refined
- `spec-writer` is active
- schema validation runs on every artifact generation

### `bridging`

- planning artifacts are translated into `execution-contract.md`
- ambiguity is compressed into explicit approved decisions
- `contract-builder` is active
- parsing engine auto-extracts intent/scope/test-obligations/constraints/batches

### `approved-for-build`

- the execution contract exists
- the user has approved it
- implementation can now begin

### `executing`

- implementation follows the execution contract
- TDD, SDD (subagent-driven), review gates, and escalation rules apply
- `build-executor` is active
- `code-reviewer` invoked after each execution batch

### `debugging`

- execution has hit a bug, test failure, or unexpected behavior
- `bug-investigator` is active
- 4-phase debugging (Root Cause → Pattern Analysis → Hypothesis → Implementation)
- After debugging completes, returns to `executing`

### `closing`

- verification is complete with evidence
- `release-archivist` is active
- `verification-before-completion` gate enforced
- `spec-merger` invoked if delta specs need merging into main specs
- the change can be summarized, archived, or handed off

### `abandoned`

- the change has been abandoned by the user or after bug-investigator escalation
- no delta spec merge is allowed
- no further state transitions are allowed
- delta specs are preserved for reference only

## Terminal States

- `closing` — successful completion with verification
- `abandoned` — change abandoned (no delta spec merge, no further transitions allowed)

## Transitions

```text
  exploring ──── hotfix/tweak ────> bridging          (fast-path)
  exploring ──── tweak ──────────> approved-for-build (fast-path)

  exploring -> specifying -> bridging -> approved-for-build -> executing -> closing
                ^              ^             |                 ^    |
                |              |             v                 |    |
                |              |         debugging ────────────┘    |
                |              |                                    |
                |              +------------------------------------+
                |              (contract drift → re-bridge)
                +---------------------------------------------------+
                     (scope change → re-specify)

  (any non-terminal state) ──> abandoned
                                (terminal, no further transitions)
```

## Mandatory Rewind

The workflow must move back to `specifying` or `bridging` when:

- new scope appears
- a critical interface changes
- a key design assumption is wrong
- current artifacts no longer define the intended behavior
- `ssf state check <change-dir> --json` reports that the current planning
  artifacts no longer match `.spec-superflow.yaml > artifacts_hash`

## Debugging State

During `executing`, if a bug, test failure, or unexpected behavior blocks progress:

1. Pause `executing` and enter `debugging`
2. `bug-investigator` performs 4-phase root cause analysis
3. If root cause found → fix (with TDD) → return to `executing`
4. If 3+ fix attempts fail → question architecture → escalate to user

## Anti-Pattern

Do not stay in `executing` and "just adjust things in chat" when scope or behavior changes.

If the contract changed, the artifacts changed.
