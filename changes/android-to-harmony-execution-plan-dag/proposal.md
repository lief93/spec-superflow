# Android-to-Harmony Executable Vertical-Slice Planning

## Why

The current capability graph can account for production source files, but the
first execution-plan implementation does not yet convert that inventory into a
real migration DAG. It creates tasks at page/Composable granularity, leaves
dependency edges empty, and can assign unrelated cross-layer capabilities by
token similarity or first-slice fallback. This makes nearly every task appear
immediately executable and can report complete coverage without producing a
business-complete migration plan.

## What Changes

- Extend the capability model with deterministic, resolved semantic
  relationships needed for route/page closure and dependency planning.
- Generate route/page-rooted vertical slices whose cross-layer members include
  provenance back to resolved navigation, declaration, import, or call edges.
- Generate a validated, acyclic dependency graph with persisted task lifecycle
  state and correct next-executable calculation.
- Fail closed for ambiguous ownership, stale or tampered graph/gate/queue/plan
  inputs, and invalid task dependencies.
- Keep Spec Workflow and `migration_agent` as the only normal user entry while
  documenting standalone tools as maintainer/debug utilities.
- Produce portable, hash-bound evidence for fixed public project regressions.

## Scope

### In Scope

- Capability-graph relationship schema and deterministic relationship
  extraction required by execution planning.
- Vertical-slice construction, dependency generation, lifecycle state,
  blockers, required Skill/Gate/Test obligations, and closure provenance.
- `migration_agent start`, `resume`, and `status` integration.
- Unit, orchestrator, workflow, negative-integrity, and three-public-project
  regression evidence.
- Portable Skill identity and full evidence-tree verification.

### Out of Scope

- Migrating a new complete application or adding unrelated Compose primitives.
- Changing generated Harmony business/UI implementation behavior.
- AI image recognition or external visual services.
- Committing, pushing, releasing, or publishing artifacts.
- Reopening or modifying the already-closing
  `android-to-harmony-54-benchmark` change.

## Impact

- `skills/migrate-android-compose-to-harmony/scripts/` capability graph,
  execution planner, workflow orchestrator, and their tests.
- The bundled Android-to-Harmony Skill documentation and portable digest tests.
- Change-local evidence for Banking, Ekspensify, and Buckwheat fixed revisions.
- No impact on non-Android-to-Harmony Spec Workflow routes.

## Capabilities

- `android-harmony-execution-planning`: resolved vertical-slice closure,
  executable task dependencies, strict lifecycle/integrity handling, and
  portable evidence.
