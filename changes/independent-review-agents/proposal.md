# Proposal: Independent Review Agents

## Why

The Agent that writes Planning artifacts or implementation can miss its own
assumptions. Design and Tasks also impose a high review burden on users. A
fixed read-only Reviewer with one fresh independent context per stage gives
semantic challenge without moving development into a new orchestration
framework.

## What Changes

- Register one hidden fixed Reviewer beside the existing visible Primary in VS
  Code and OpenCode.
- Add three semantic review checkpoints for exact full workflow:
  `proposal-specs`, `design-tasks`, and `final`.
- Add a compact Review CLI with fixed inbox/current files, exact schema and
  candidate-identity checks, safe atomic replacement, and staleness detection.
- Bind DP-1 and DP-2 to the current approved Planning candidate and DP-3 to the
  current execution-contract hash through existing state fields.
- Make the final transition guard require current final approval while keeping
  mechanical validation, tests, evidence, and user confirmations separate.
- Update shared Skills and host prompts so Primary authors, implements, fixes,
  and communicates; Reviewer only reviews.

## Scope

### In Scope

- VS Code and OpenCode Agent registration and prompts.
- Review candidate, result record, and current-result check commands.
- Review guards and the minimum candidate-identity state bindings.
- Full-workflow Planning and final review ordering.
- Source and packed runtime regressions, documentation, and current Change
  evidence.

### Out of Scope

- A new Dev role, manager service, host continuity contract, second state
  machine, or review-history service.
- Reviewer file writes, terminal/test execution, state mutation, or direct user
  interaction.
- Review checkpoints for `hotfix` or `tweak`.
- Replacing `/workflow-init`, project initialization, package delivery, or
  existing product workflows.
- Claiming company-internal validation or unexecuted real host business flows.

## Impact

- **CLI**: adds only `ssf review candidate|record|check` and three review stages.
- **State**: keeps existing states and contract hash, and adds only DP-1/DP-2
  candidate identities.
- **Guards**: Planning-to-contract and executing-to-closing require current
  approved review evidence.
- **Plugin hosts**: one Primary may invoke only the hidden fixed Reviewer;
  bootstrap remains isolated.
- **Package**: includes the new Reviewer prompts, Review CLI runtime, and tests;
  no new runtime dependency.

## Capabilities

- `independent-agent-orchestration`
- `planning-review-gate`
- `implementation-review-gate`
- `verification-framework`
- `task-planning`
- `vscode-agent-plugin`
