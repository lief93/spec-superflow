# Android-to-Harmony Execution Planning Specification

## ADDED Requirements

### Requirement: Resolved route-rooted vertical-slice closure

The migration workflow SHALL construct each executable business slice from a
real route or page root and SHALL include cross-layer capabilities only through
resolved navigation, declaration, import, call, ownership, or explicitly
modeled shared-capability relationships.

#### Scenario: Build a cross-layer slice from resolved relationships

- **WHEN** a route or page resolves through state or business logic to a
  repository, network, storage, platform, UI-system, or control capability
- **THEN** the execution plan places those capabilities in the route/page slice
  and records the exact relationship path that justified every member

#### Scenario: Reject similarity and first-slice fallback ownership

- **WHEN** a production capability has no resolved relationship to a route/page
  slice
- **THEN** the workflow leaves it unassigned with a structured local blocker
  instead of assigning it by filename tokens, path similarity, task ordering,
  or the first available slice

#### Scenario: Reject leaf artifacts as standalone migration tasks

- **WHEN** a source file, preview, leaf Composable, or control is classified but
  is not itself a navigable route/page root
- **THEN** it joins a route/page closure through resolved relationships or
  remains explicitly blocked, and never becomes an executable task solely
  because it is a distinct declaration or file

#### Scenario: Reject accounting-only completion

- **WHEN** every production node and source file is mechanically assigned but a
  slice lacks resolved provenance, required cross-layer closure, dependency
  semantics, or actionable obligations
- **THEN** the plan remains invalid and the workflow does not report migration
  planning or production coverage complete

#### Scenario: Associate tests without claiming production implementation

- **WHEN** test-support sources resolve to a route/page slice or its production
  dependencies
- **THEN** the plan records them as required test obligations and excludes them
  from production ownership and production-completion accounting

### Requirement: Executable dependency DAG and task lifecycle

The migration workflow SHALL emit a deterministic acyclic task graph whose
dependency edges originate from resolved capability relationships and whose
next-executable set reflects persisted task lifecycle state. Every task packet
SHALL contain a stable collision-checked identifier, dependency identifiers,
the selected migration Skill, actionable Gate and Test obligations, blocker
state, route/page closure provenance, and current evidence identity.

#### Scenario: Emit a complete executable task packet

- **WHEN** the workflow creates a vertical-slice task
- **THEN** the task contains all required packet fields with resolvable
  references, and planning fails instead of emitting a partial or
  identifier-colliding packet

#### Scenario: Hold dependent work until prerequisites complete

- **WHEN** a pending task depends on an incomplete foundational or upstream
  migration task
- **THEN** the dependent task is absent from the next-executable set until all
  prerequisites are completed and unblocked

#### Scenario: Unlock downstream work after completion

- **WHEN** the workflow records completion of every prerequisite task and
  current passing evidence for every required Gate and Test obligation
- **THEN** `resume` and `status` expose the newly ready downstream task from the
  same validated execution-plan identity

#### Scenario: Reject invalid dependency graphs

- **WHEN** a task references an unknown dependency or the task graph contains a
  cycle
- **THEN** planning fails with a non-zero result and exposes no executable task
  set

### Requirement: Local fail-closed blockers and gate enforcement

The migration workflow SHALL apply unresolved review items and failed capability
gates only to slices connected by verified relationships, and SHALL fail closed
when their scope cannot be established reliably.

#### Scenario: Block only a related slice

- **WHEN** an unresolved production source or failed gate is connected to one
  route/page closure
- **THEN** that slice is blocked while unrelated dependency-ready slices remain
  eligible for execution

#### Scenario: Refuse unscoped ambiguity

- **WHEN** an unresolved production source or failed gate cannot be connected
  reliably to any route/page closure
- **THEN** the workflow reports an explicit unassigned blocker and does not
  claim complete production coverage

### Requirement: Strict plan identity and tamper rejection

The migration workflow SHALL cryptographically bind the contract, capability
graph content, review queue, gate report node set and statuses, Skill tree, task
state, and execution plan, and SHALL reject stale or tampered persisted
artifacts.

#### Scenario: Reject changed planning inputs

- **WHEN** the graph, gate report, review queue, Skill digest, task state, or
  execution plan differs from its recorded identity
- **THEN** `start`, `resume`, or `status` returns a non-zero failure or a strict
  error state with an empty executable set

#### Scenario: Preserve one current identity across workflow commands

- **WHEN** unchanged current artifacts are read through `start`, `resume`, and
  `status`
- **THEN** all commands report the same execution-plan identity, dependency
  state, ready tasks, and blockers

### Requirement: Single workflow entry and portable evidence

The normal user workflow SHALL invoke execution planning automatically through
Spec Workflow and `migration_agent`, and SHALL produce portable evidence bound
to the final implementation bytes and public-source revisions.

#### Scenario: Run planning through the workflow entry

- **WHEN** an Android-to-Harmony change reaches execution planning through the
  normal Spec Workflow entry
- **THEN** the workflow generates, validates, and reports the current plan
  without requiring the user to invoke a standalone planner command

#### Scenario: Verify the complete evidence tree

- **WHEN** fixed-revision public project regression evidence is frozen
- **THEN** a relative-path SHA-256 manifest covers contracts, graphs, fact
  packs, queues, gate reports, plans, command logs, exit results, test logs, and
  Skill identities, and its verifier fails after any covered artifact changes

#### Scenario: Run portable default tests

- **WHEN** the repository test suite runs on another machine or CI environment
- **THEN** it does not depend on a developer-specific plugin cache path, while
  optional canonical-cache comparison can be enabled explicitly for local
  evidence
