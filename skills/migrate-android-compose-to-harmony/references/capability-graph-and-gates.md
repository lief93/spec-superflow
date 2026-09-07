# Capability Graph And Gates

Use the bundled capability graph and gate aggregation logic only for
`android-to-harmony` Changes. The normal entry remains the existing workflow or
`migration_agent.py`; they must call these modules internally and keep the
resulting artifacts under `RUN_ROOT`. The standalone scripts are maintenance
helpers for tests, reproducible evidence capture, and workflow debugging only.
They summarize candidate scope and verify existing evidence; they do not run
builds, tests, devices, or visual review on their own.

## Builder

The workflow-owned builder generates a layered candidate graph and fact packs
from the current migration contract and skill tree digest. Persisted outputs are
expected at:

- `RUN_ROOT/capability-graph.json`
- `RUN_ROOT/fact-packs/*.json`
- `RUN_ROOT/skill-tree-manifest.json`

Outputs remain candidate-only unless later evidence proves them:

- `project`: module/build graph, route/resource/platform overview
- `business`: models, state holders, use cases, repositories, tests
- `network`: API/adapter candidates and contract-test gates
- `storage`: schema/default/migration/repository-test gates
- `platform`: permission/lifecycle/device-adapter candidates
- `ui_system`: theme/token/resource candidates
- `page`: exact closures, state/action candidates
- `control`: primitive or project wrapper candidates, props/state/events/modifiers

`coverage.unassigned_source_files` is authoritative for fail-closed aggregation:
project verification must not pass while any source remains unassigned.

## Gate Profiles

Profiles are machine-readable in
`assets/gate-profile-registry.json`. Keep gate rules in the catalog or code, not
duplicated across markdown files.

Required built-in profiles:

- `stateless-control`
- `stateful-control-family`
- `page`
- `business`
- `network`
- `storage`
- `platform`
- `project`

For a `business` node, `behavior_contract` requires an artifact with
`artifact_type: behavior_contract_validation` produced by a passing target-phase
`behavior-contract.v2` validation. Generic unit or repository tests cannot satisfy that gate.
They may satisfy `state_transition_tests` when scoped and bound to the current source, contract,
skill, and target revisions. Read [behavior-contract-v2.md](behavior-contract-v2.md) for the
source inventory, target mapping, and runtime scenario requirements.

Build or `ohosTest` compile never substitutes for device UITest, visual review,
or manual review. Family-level device evidence may only cover controls when the
evidence explicitly binds the same mapping/profile/family and current
source/contract/skill bytes.

## Aggregator

The workflow-owned aggregator validates only existing evidence against the
current graph. Persisted outputs are expected at:

- `RUN_ROOT/gate-evidence-bundle.json`
- `RUN_ROOT/gate-report.json`
- `RUN_ROOT/execution-plan.json`

## Execution Plan

The workflow and `migration_agent.py` must also derive a deterministic
execution-plan DAG from the current contract, capability graph, review queue,
and gate report. Through `start`, `resume`, and `status`, they must validate
and return the current immutable plan together with the current mutable
execution task state. This is an internal planning artifact, not a second
user-facing workflow.

Rules:

- Task packets must be route/page-centered vertical slices rather than one file
  per task.
- Every production owner node from the current graph must be covered by at
  least one task packet.
- `test_support` may attach testing obligations to a task, but it never counts
  as production implementation coverage.
- Review-queue and `unclassified` blockers must only block the affected task
  packets, not every slice in the project.
- stale `contract_sha256`, `source_revision`, `skill_tree_digest`, graph, or
  gate-report bindings invalidate the plan.

If a maintainer needs to reproduce an artifact manually, they may invoke the
standalone scripts directly, but that maintainer/debug seam is not a normal
user-facing workflow step.

Allowed statuses:

- `candidate`
- `implemented`
- `verified`
- `unsupported`
- `intentionally_excluded`

Rules:

- `candidate` and `implemented` never aggregate upward into completion.
- `verified` fails if unresolved items remain or required gates are missing.
- Parent `page`/`project` verification fails while any applicable child is still
  `candidate` or `implemented`.
- `unsupported` requires both `rationale` and `decision_owner`.
- `intentionally_excluded` requires `rationale`.
- stale `source_revision`, `contract_sha256`, or `skill_tree_digest` bindings are
  rejected.
