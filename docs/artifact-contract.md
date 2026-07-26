# Artifact Contract

`spec-superflow` uses five primary artifacts in each change:

1. `proposal.md`
2. `specs/`
3. `design.md`
4. `tasks.md`
5. `execution-contract.md`

The first four are planning artifacts. The fifth is the execution handshake.

At the project root, each long-term capability lives under `specs/<capability>/spec.md`, which defines current behavior. Normative implementation rules and canonical paths live in `docs/project/project-guidelines.md`. Verified team feedback, code-invisible project context, and external references are recalled separately through `.spec-superflow/memories/MEMORY.md` and typed on-demand topic files; neither the project baseline nor shared Auto Memory replaces capability Specs.

## Artifact Roles

### `proposal.md`

Defines:

- why the change exists
- what is in scope
- what is explicitly out of scope
- which capabilities are affected

### `specs/`

Defines:

- required behavior
- scenarios and acceptance conditions
- behavioral edges the implementation must respect

### `design.md`

Defines:

- architecture and component boundaries
- which Requirement and Scenario each decision serves
- which area owns the change and why it belongs there
- interface and dependency decisions
- trade-offs and risk areas

### `tasks.md`

Defines:

- implementation ordering
- one owning Batch AC section for every Requirement/Scenario
- concrete file changes under each AC, including methods or types when known
- one TDD test plan per AC, with one exact platform test source file, test case, and asserted AC outcome per row
- dependency-aware work breakdown
- completion units that can become execution batches

### `execution-contract.md`

Defines:

- the approved intent lock
- the approved behavior summary
- requirement traceability from each spec requirement to behavior, test obligation, and execution batch
- an exact AC Test Matrix copied from task test plans
- implementation constraints
- task batches
- test obligations
- frontend UI and device verification requirements when the project has a user interface
- review gates
- escalation rules

`pr-summary.md` records one evidence row for every AC Test Matrix obligation, including the exact platform test file and case. For frontend changes, aggregate UI Test and Device Test evidence stays there rather than in a separate report artifact.

## Mapping

`spec-superflow` converts planning artifacts into execution inputs:

- `proposal.md` -> intent lock and scope fence
- `specs/` -> test obligations and acceptance checks
- `design.md` -> Requirement/Scenario-to-decision mapping and implementation constraints
- `tasks.md` -> Scenario-owned concrete file changes and execution batches

## Guardrail

Implementation starts only after:

- planning artifacts exist
- `execution-contract.md` exists
- the user approves the execution contract
