# Tasks: Android-to-Harmony Executable Vertical-Slice Planning

## Production scope

- `skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py`
- `skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py`
- `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
- `skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py`
- `skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py`
- `skills/migrate-android-compose-to-harmony/SKILL.md`
- `skills/migrate-android-compose-to-harmony/references/capability-graph-and-gates.md`

## Unchanged upstream behavior

- `prepare_safe_snapshot.py`, `validate_ai_safe_tree.py`,
  `analyze_compose_project.py`, `generate_migration_backlog.py`, and Harmony
  code-generation scripts remain unchanged in this change. They provide inputs
  or downstream execution seams, but they do not own execution-plan DAG
  behavior.
- Project-root Spec Workflow state-machine behavior remains scoped. This change
  may add Android-to-Harmony-specific assertions in tests, but it does not
  change non-Android workflow semantics.

## Existing unverified worktree inputs

- `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
  currently contains unverified red-test edits that belong to
  `Hold dependent work until prerequisites complete` and
  `Reject changed planning inputs`. They must be reconciled and rerun during
  execution; they are not accepted evidence now.
- `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
  currently contains unverified red-test edits that belong to
  `Reject changed planning inputs` and
  `Preserve one current identity across workflow commands`.
- `tests/lib/hash-skill-tree.test.mjs` currently contains an unverified red-test
  edit that belongs to `Run portable default tests`.

## Batch 1: Graph relationships, slice qualification, and local blocker scope
- **Depends on**: none

### AC: Build a cross-layer slice from resolved relationships
- **Requirement**: Resolved route-rooted vertical-slice closure
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py`
- **Why this file**: This file owns the authoritative candidate graph facts that
  the planner must consume instead of guessing from names.
- **Change**: Add `root_qualification[]` and `resolved_edges[]`, with exact
  root-qualification records and deterministic closure edge kinds
  (`route_entry`, `route_binding`, `page_declares_control`,
  `page_uses_business`, `business_uses_repository`,
  `repository_uses_network`, `repository_uses_storage`,
  `page_uses_platform`, `page_uses_ui_system`, `shared_foundation_member`,
  `test_obligation`, `runtime_navigation`, `runtime_import`, `runtime_call`).

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file already owns graph/planner fixture coverage for
  the Android-to-Harmony Skill CLI seams.
- **Change**: Add a synthetic graph/planner fixture that proves a route/page
  slice can include business, network, storage, platform, UI-system, and
  control members with explicit closure provenance from those exact edge kinds.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_capability_graph_builder_emits_typed_resolved_edges_for_route_root_closure` | The graph emits deterministic `root_qualification[]` and `resolved_edges[]` records with stable edge kinds and source evidence. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_builds_cross_layer_slice_from_resolved_relationships` | A route/page slice gains cross-layer members only through recorded resolved-edge provenance. |

### AC: Reject similarity and first-slice fallback ownership
- **Requirement**: Resolved route-rooted vertical-slice closure
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file currently applies token scoring and first-slice
  fallback when graph facts are insufficient.
- **Change**: Remove similarity-based and first-slice ownership fallback for
  production nodes; require resolved-edge-backed ownership or an explicit local
  blocker.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file already owns negative plan-construction tests.
- **Change**: Add a negative fixture where a production node has no resolved
  relationship and ensure planning rejects arbitrary assignment.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_rejects_similarity_and_first_slice_fallback_ownership` | Unrelated production nodes are not assigned by filename tokens, path overlap, ordering, or default slice selection. |

### AC: Reject leaf artifacts as standalone migration tasks
- **Requirement**: Resolved route-rooted vertical-slice closure
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py`
- **Why this file**: Root qualification begins with graph semantics, not with
  task construction alone.
- **Change**: Add deterministic root qualification rules so only
  `route_inventory_root`, `android_navigation_root`, or `entry_screen_root`
  records in `root_qualification[]` may spawn executable tasks.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file decides which graph nodes become executable
  tasks.
- **Change**: Construct executable tasks only from qualified route/page roots
  and route shared/foundation work through dependency packets instead of
  standalone leaf tasks.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file owns planner task-shape assertions.
- **Change**: Add a fixture proving a preview/control/leaf file does not create
  its own task packet.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_rejects_leaf_artifacts_as_standalone_migration_tasks` | Leaf Composables, previews, controls, and isolated files never become executable slice roots without route/page qualification. |

### AC: Reject accounting-only completion
- **Requirement**: Resolved route-rooted vertical-slice closure
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file currently reports full production coverage once
  nodes and files are assigned, even if the assignment is semantically weak.
- **Change**: Validate that every slice packet has resolved provenance,
  cross-layer closure or explicit absence, dependency semantics, and actionable
  obligations before the plan is accepted as current.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file already asserts deterministic plan coverage.
- **Change**: Add a negative fixture where coverage reaches zero uncovered files
  but packet provenance or obligations are incomplete, and require planning to
  fail.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_rejects_accounting_only_completion_without_semantic_closure` | Production coverage alone does not make the plan valid when closure provenance or obligations are missing. |

### AC: Associate tests without claiming production implementation
- **Requirement**: Resolved route-rooted vertical-slice closure
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file owns the task packet fields that separate
  production ownership from related test obligations.
- **Change**: Keep `test_support` nodes out of production owner lists and
  production-coverage accounting while attaching them to the correct route/page
  or foundation packet as required tests.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file already exercises `test_support` attachment in
  plan fixtures.
- **Change**: Extend fixture assertions so test-support nodes appear only in
  `related_test_support_node_ids` and required-test obligations.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Update | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_is_deterministic_and_covers_vertical_slices` | Test-support files remain obligation-only and do not satisfy production ownership or completion. |

### AC: Block only a related slice
- **Requirement**: Local fail-closed blockers and gate enforcement
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py`
- **Why this file**: This file owns gate report semantics and node-level status.
- **Change**: Emit `graph_sha256`, `graph_node_ids[]`, `review_queue_sha256`,
  `node_statuses_sha256`, and `report_by_node`, so the planner can bind gate
  scope to resolved closure and foundation ownership.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file turns graph and gate artifacts into blocked or
  ready task packets.
- **Change**: Apply unresolved review-queue items and failed gate statuses only
  to the slices or foundation tasks connected by resolved provenance.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file owns end-to-end graph/gate/plan fixtures.
- **Change**: Add a fixture where one route/page closure is blocked while an
  unrelated ready slice remains executable.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_blocks_only_relationship_scoped_slice` | A blocker or gate failure stops only the connected slice or foundation task, not every slice globally. |

### AC: Refuse unscoped ambiguity
- **Requirement**: Local fail-closed blockers and gate enforcement
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py`
- **Why this file**: This file is the producer of scope-bearing graph facts.
- **Change**: Preserve explicit ambiguity when a production node or failed gate
  cannot be linked to any qualified root or foundation through resolved graph
  relationships.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py`
- **Why this file**: This file owns failed-gate reporting before planning.
- **Change**: Preserve unscoped failed-gate records in `report_by_node` instead
  of coercing them into a root-local gate status.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file currently converts weakly owned production nodes
  into arbitrary task assignments.
- **Change**: Emit an explicit unassigned blocker, mark production incomplete,
  and return no executable fallback when an unresolved production node or a
  failed gate cannot be scoped to any qualified root or foundation.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file already owns review-queue and plan failure
  assertions.
- **Change**: Add negative fixtures for both an unresolved production node and
  an unscoped failed gate.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_refuses_unscoped_ambiguity` | An unresolved production node produces an explicit unassigned blocker, keeps production incomplete, exposes no executable fallback, and is never silently attached to a slice. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_rejects_unscoped_failed_gate_without_executable_fallback` | An unscoped failed gate produces an explicit unassigned blocker, keeps production incomplete, and exposes no executable fallback. |

### Batch Verification
- [x] RED: `python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_capability_graph_builder_emits_typed_resolved_edges_for_route_root_closure MigrationToolTests.test_execution_plan_builder_builds_cross_layer_slice_from_resolved_relationships MigrationToolTests.test_execution_plan_builder_rejects_similarity_and_first_slice_fallback_ownership MigrationToolTests.test_execution_plan_builder_rejects_leaf_artifacts_as_standalone_migration_tasks MigrationToolTests.test_execution_plan_builder_rejects_accounting_only_completion_without_semantic_closure MigrationToolTests.test_execution_plan_builder_is_deterministic_and_covers_vertical_slices MigrationToolTests.test_execution_plan_builder_blocks_only_relationship_scoped_slice MigrationToolTests.test_execution_plan_builder_refuses_unscoped_ambiguity MigrationToolTests.test_execution_plan_builder_rejects_unscoped_failed_gate_without_executable_fallback` and record the expected focused failures before implementation.
- [x] GREEN: Rerun the same focused command and pass every planned Batch 1 case.
- [x] Regression: `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v` with zero failures.

## Batch 2: Task packets, prerequisite DAG, lifecycle, and strict identity
- **Depends on**: Batch 1 typed edges, route/page qualification, and scoped-blocker outputs

### AC: Emit a complete executable task packet
- **Requirement**: Executable dependency DAG and task lifecycle
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file defines the execution-plan schema and currently
  emits partial packets with empty dependency semantics.
- **Change**: Expand task packets to include stable collision-checked IDs,
  route/page root identity, foundation ownership, dependency IDs, required
  Skill/Gate/Test obligations, closure provenance, blocker definitions, frozen
  evidence references, and an explicitly delimited immutable payload used to
  compute `plan_identity`. Task packets must not embed their own content hash or
  the mutable task-state identity.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file already owns direct assertions on task packet
  shape.
- **Change**: Add a packet-completeness fixture plus negative coverage for
  collision/partial packets, self-referential plan envelopes, and packets that
  illegally persist mutable task-state identity.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_emits_complete_executable_task_packet` | Every vertical-slice packet contains the required immutable definition, dependency, obligation, blocker, provenance, and frozen evidence fields, while the plan envelope excludes self-hash and mutable task-state identity. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_rejects_self_referential_or_mutable_plan_identity_payload` | Planning fails when the immutable plan payload embeds its own identity or any mutable task-state identity. |

### AC: Hold dependent work until prerequisites complete
- **Requirement**: Executable dependency DAG and task lifecycle
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file currently leaves `dependent_task_ids` empty and
  treats most tasks as immediately ready.
- **Change**: Build `prerequisite_edges[]` and `dependent_task_ids` only from
  explicit implementation-prerequisite kinds:
  `shared_foundation_prerequisite` and `produced_contract_prerequisite`.
  Runtime-only closure edges must stay in `closure_provenance[]` and must not
  create task dependencies.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file already contains an unverified red test for real
  dependency edges and lifecycle.
- **Change**: Reconcile the existing unverified
  `test_execution_plan_builder_uses_real_dependency_edges_and_task_lifecycle`
  coverage under the approved scenario and extend it with explicit
  dependency-readiness assertions, runtime-edge non-dependency assertions,
  single-owner shared-foundation fan-out assertions, and a positive
  `produced_contract_prerequisite` fixture in which one task produces a typed
  capability or adapter contract that a consumer task must wait on.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Update | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_uses_real_dependency_edges_and_task_lifecycle` | Dependent tasks remain non-ready until their prerequisite slices or foundation tasks are completed and unblocked. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_does_not_create_task_dependency_from_runtime_edges_only` | Runtime navigation/import/call edges remain closure provenance and do not become task dependencies by themselves. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_fans_out_single_owner_shared_foundation_without_duplicating_ownership` | A shared foundation is implemented once, then consumed by two slices through explicit prerequisite edges without duplicating ownership. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_emits_produced_contract_prerequisite_for_typed_consumer` | A typed producer-to-consumer fixture emits the exact `produced_contract_prerequisite`, preserves source-edge provenance, topologically orders producer before consumer, and keeps the consumer `pending` until the producer completes. |

### AC: Unlock downstream work after completion
- **Requirement**: Executable dependency DAG and task lifecycle
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
- **Why this file**: This file is the only normal workflow entry that can
  persist and report mutable task lifecycle state.
- **Change**: Persist `execution-task-state.json`, bind it to immutable plan
  identity, as the sole mutable lifecycle record, with a one-way reference to
  immutable `plan_identity`, a current `task_state_identity`, and per-task
  lifecycle state. `resume` and `status` must join immutable packets with this
  current state and recompute ready tasks from completed prerequisites plus
  current passing gate/test obligations.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- **Why this file**: This file owns end-to-end `migration_agent` state
  transitions.
- **Change**: Add an orchestrator case that advances prerequisite task state
  and verifies the newly unlocked downstream task from the same validated
  immutable plan identity, plus a parity case proving task-state updates do not
  mutate the plan identity.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_resume_unlocks_downstream_tasks_after_prerequisite_completion` | `resume` and `status` expose the same newly ready downstream task only after prerequisite completion and current passing obligations. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_task_state_updates_do_not_change_execution_plan_identity` | Advancing mutable task state changes only `task_state_identity`; immutable `plan_identity` and packet payload remain unchanged. |

### AC: Reject invalid dependency graphs
- **Requirement**: Executable dependency DAG and task lifecycle
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file already owns dependency validation and
  topological ordering.
- **Change**: Reject unknown dependency IDs and cycles before writing a plan or
  exposing executable tasks.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file owns planner negative cases.
- **Change**: Add exact unknown-dependency and cyclic-dependency fixtures that
  fail closed.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_rejects_unknown_and_cyclic_dependencies` | Planning exits non-zero and exposes no executable set when dependencies are unknown or cyclic. |

### AC: Reject changed planning inputs
- **Requirement**: Strict plan identity and tamper rejection
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py`
- **Why this file**: This file currently validates only top-level identity
  fields and does not bind the node set or graph content strongly enough for
  planner use.
- **Change**: Bind graph SHA-256, review-queue digest, graph node set, and
  node statuses into the gate report in a form the planner can verify.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py`
- **Why this file**: This file validates graph and gate artifacts before task
  construction.
- **Change**: Reject stale or tampered contract bytes, graph bytes, review
  queue, gate-report node set/statuses, immutable plan identity, Skill digest,
  and mutable task-state identity with no executable fallback.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
- **Why this file**: This file currently reports stale execution-plan drift as
  a soft stale status instead of a hard execution block.
- **Change**: Convert stale/tampered contract, graph, review queue, gate
  report, Skill tree, immutable plan, or mutable task-state identity into a
  non-zero `status`/`resume` failure or a strict blocked/error response with an
  empty executable set.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file already contains unverified red tamper tests.
- **Change**: Reconcile the existing unverified gate-report tamper test and add
  a table-driven negative planner matrix covering contract bytes, graph bytes,
  review queue, gate node set, gate node statuses, Skill digest/tree, immutable
  plan identity, and mutable task-state identity.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- **Why this file**: This file already contains unverified stale-plan status
  edits that belong to this scenario.
- **Change**: Reconcile the existing unverified stale-plan and tampered-gate
  cases and add orchestrator coverage for the same stale-input families.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Update | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_rejects_gate_report_node_set_and_graph_hash_drift` | The planner rejects tampered graph/gate-report identity and exposes no valid execution plan. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_builder_rejects_stale_input_matrix` | A table-driven planner matrix rejects stale contract bytes, graph, review queue, gate node set/statuses, Skill digest/tree, immutable plan, and mutable task-state identity with non-zero failure and empty executable fallback. |
| Integration | Python CLI | Update | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_status_marks_execution_plan_artifact_stale_when_persisted_plan_drifts` | `status` fails closed instead of returning executable work from a drifted plan. |
| Integration | Python CLI | Update | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_resume_rejects_tampered_gate_report_identity_and_executable_tasks` | `resume` fails closed when the gate report identity or node set is tampered. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_migration_agent_rejects_stale_input_matrix` | The same stale-input families are rejected by the workflow entry with strict error and empty executable set. |

### AC: Preserve one current identity across workflow commands
- **Requirement**: Strict plan identity and tamper rejection
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
- **Why this file**: This file owns the public `start`, `resume`, and `status`
  responses for Android-to-Harmony workflow runs.
- **Change**: Persist and return one immutable plan identity plus one mutable
  task-state identity consistently across `start`, `resume`, and `status`.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- **Why this file**: This file already checks cross-command parity for the
  orchestrator.
- **Change**: Add an exact case that verifies stable identity, ready-task set,
  and blocker set across unchanged current artifacts.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_start_resume_and_status_preserve_execution_plan_identity` | Unchanged current artifacts yield the same plan identity, task-state identity, ready tasks, and blockers across all workflow commands. |

### Batch Verification
- [x] RED: `python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_execution_plan_builder_emits_complete_executable_task_packet MigrationToolTests.test_execution_plan_builder_rejects_self_referential_or_mutable_plan_identity_payload MigrationToolTests.test_execution_plan_builder_uses_real_dependency_edges_and_task_lifecycle MigrationToolTests.test_execution_plan_builder_does_not_create_task_dependency_from_runtime_edges_only MigrationToolTests.test_execution_plan_builder_fans_out_single_owner_shared_foundation_without_duplicating_ownership MigrationToolTests.test_execution_plan_builder_emits_produced_contract_prerequisite_for_typed_consumer MigrationToolTests.test_execution_plan_builder_rejects_unknown_and_cyclic_dependencies MigrationToolTests.test_execution_plan_builder_rejects_gate_report_node_set_and_graph_hash_drift MigrationToolTests.test_execution_plan_builder_rejects_stale_input_matrix` and `python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_status_marks_execution_plan_artifact_stale_when_persisted_plan_drifts MigrationAgentTests.test_resume_rejects_tampered_gate_report_identity_and_executable_tasks MigrationAgentTests.test_resume_unlocks_downstream_tasks_after_prerequisite_completion MigrationAgentTests.test_task_state_updates_do_not_change_execution_plan_identity MigrationAgentTests.test_start_resume_and_status_preserve_execution_plan_identity MigrationAgentTests.test_migration_agent_rejects_stale_input_matrix` and record the expected focused failures before implementation.
- [x] GREEN: Rerun the same focused commands and pass every planned Batch 2 case.
- [x] Regression: `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v` and `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v` with zero failures.

## Batch 3: Workflow-only entry, portable evidence, and repository test portability
- **Depends on**: Batch 2 immutable plan, mutable task-state, and integrity outputs; integrates Batch 1 graph/closure provenance plus Batch 2 plan-state evidence without re-deriving them

### AC: Run planning through the workflow entry
- **Requirement**: Single workflow entry and portable evidence
- **User-visible**: No

#### File Changes
##### Modify `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
- **Why this file**: This file is the approved user-facing Android-to-Harmony
  workflow entry.
- **Change**: Keep capability-graph, gate-report, task-state, and plan
  generation/validation on the `migration_agent` path and expose current plan
  status through `start`, `resume`, and `status` without requiring standalone
  planner commands.

##### Modify `skills/migrate-android-compose-to-harmony/SKILL.md`
- **Why this file**: This file currently describes both workflow and standalone
  planner usage to end users.
- **Change**: Restrict normal-user instructions to Spec Workflow and
  `migration_agent`, and move standalone graph/planner/backlog commands into
  maintainer/debug wording only.

##### Modify `skills/migrate-android-compose-to-harmony/references/capability-graph-and-gates.md`
- **Why this file**: This file owns the machine-contract and operator guidance
  for internal capability artifacts.
- **Change**: Document workflow ownership, immutable plan identity, mutable
  task-state identity, and maintainer/debug-only helper usage without creating
  a second user workflow.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- **Why this file**: This file verifies workflow-entry behavior at the actual
  CLI seam.
- **Change**: Add or extend `migration_agent` cases so planning artifacts are
  generated and reported through `start`/`resume`/`status`.

##### Modify `tests/integration/android-harmony-benchmark.test.mjs`
- **Why this file**: This repository integration test is the correct place to
  protect workflow-only Android-to-Harmony routing from regression.
- **Change**: Add a workflow/integration assertion that Android-to-Harmony
  planning is surfaced through the existing workflow entry, not a separate user
  planner flow.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_status_reports_current_execution_plan_through_workflow_entry` | `migration_agent` exposes current plan state without requiring a standalone planner command. |
| Integration | Node 22 | Add | tests/integration/android-harmony-benchmark.test.mjs | `it('routes Android-to-Harmony execution planning through the workflow entry only')` | The repository workflow path keeps Android-to-Harmony planning on the workflow/migration-agent seam. |

### AC: Verify the complete evidence tree
- **Requirement**: Single workflow entry and portable evidence
- **User-visible**: No

#### File Changes
##### Create `skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py`
- **Why this file**: The current repository has no freeze helper that both
  verifies fixed public revisions and captures named stdout, stderr, exit, and
  subtree artifacts for execution-plan regressions.
- **Change**: Add one maintainer-only checked-capture helper that performs
  source acquisition or reuse verification from structured parameters only:
  `source-url`, `expected-revision`, `source-dir`, optional `reuse-candidate`,
  plus project/run/evidence locations. The helper itself must construct fixed
  subprocess argv lists for clone, fetch, checkout, `remote get-url`, and
  `rev-parse HEAD`; it must not accept arbitrary shell-command flags. It records
  each command's stdout, stderr, command log, and exit artifact, runs
  `migration_agent.py start` and `status`, freezes the required subtree
  contents, writes a per-project `skill-identity-reference.json` pointing at the
  central manifest and binding, and fails closed when any required family is
  missing.

##### Create `skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py`
- **Why this file**: This change needs a dedicated, reusable internal helper to
  hash and verify a relative-path requirement evidence tree without overloading
  the Skill-tree digest contract.
- **Change**: Add relative-path SHA-256 manifest/envelope generation and
  verification for these exact evidence families:
  contracts, capability graph, fact packs, review queue, gate reports,
  immutable plan, frozen task state, command stdout, command stderr, command
  logs, exit artifacts, test logs, Skill identities, and fixed-regression
  outputs for Banking, Ekspensify, and Buckwheat. The verifier must reject
  missing membership, unexpected extra artifacts, or tampering in any listed
  family.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
- **Why this file**: This file owns workflow-side artifact generation and
  identity reporting.
- **Change**: Invoke the evidence-tree manifest/envelope helper for frozen
  execution-planning evidence, bind exact Banking/Ekspensify/Buckwheat
  regression artifact paths and revisions into the manifest, and expose
  verifier failures as stale/tampered execution state. The current change owns
  its frozen outputs under
  `changes/android-to-harmony-execution-plan-dag/evidence/`:
  `skill-identities/bundled-skill-tree-manifest.json`,
  `skill-identities/repo-skill-binding.json`,
  `execution-plan-dag-v1/{banking,ekspensify,buckwheat}/`, and
  `execution-plan-dag-v1/evidence-tree-manifest.json`. Historical
  `changes/android-to-harmony-54-benchmark/evidence/` inputs remain read-only.
  Each project subtree stores contract originals, capability graph, fact packs,
  review queue, gate report, immutable plan, frozen task state, command
  stdout/stderr/command logs, exit artifacts, test logs, and one
  `skill-identity-reference.json` that names the central current-change
  `evidence/skill-identities/` manifest plus binding digests. Skill identity
  ownership is never duplicated inside project subtrees.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- **Why this file**: This file is the existing Python seam for synthetic
  planner/evidence helper coverage.
- **Change**: Add manifest-membership and tamper-negative tests for every
  evidence family and for each of the three fixed-regression project subtrees,
  using the exact current-change subtree names rather than synthetic
  placeholders. The subtree assertions must require all non-identity evidence
  families plus a content-bound reference to the central
  `evidence/skill-identities/` artifacts.

##### Modify `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- **Why this file**: This file owns end-to-end workflow and checked-capture
  behavior at the actual orchestration seam.
- **Change**: Add the structured-acquisition and freeze cases that prove the
  helper clones or reuses sources through fixed argv sequencing, repairs wrong
  HEAD checkouts, fails closed on wrong remote or final HEAD mismatch, records
  acquisition command stdout/stderr/exit evidence, and rejects incomplete
  frozen public-project subtrees.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_evidence_tree_manifest_lists_required_evidence_families` | The manifest enumerates contracts, graph, fact packs, review queue, gate report, immutable plan, frozen task state, stdout/stderr/logs, exit artifacts, test logs, Skill identities, and Banking/Ekspensify/Buckwheat regression evidence. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_evidence_tree_manifest_rejects_tampering` | Any covered artifact change causes manifest verification to fail. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_tools.py | `test_execution_plan_evidence_tree_manifest_rejects_project_regression_artifact_tampering` | Banking, Ekspensify, and Buckwheat regression subtrees are individually manifest-bound and tamper-rejected. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_capture_execution_plan_regressions_freezes_complete_public_project_evidence` | The checked-capture helper freezes Banking, Ekspensify, and Buckwheat only when each subtree contains contract originals, graph, fact packs, review queue, gate report, immutable plan, frozen task state, stdout/stderr/command logs, exit artifacts, test logs, and a central Skill identity reference. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_capture_execution_plan_regressions_acquires_and_verifies_fixed_public_revisions` | A missing source directory is cloned then checked out and verified; a wrong-HEAD checkout is fetched, rechecked out, and verified; a wrong remote or final HEAD mismatch fails closed before freeze. |
| Integration | Python CLI | Add | skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py | `test_capture_execution_plan_regressions_records_acquisition_command_evidence_for_all_project_forms` | Banking, Ekspensify, and Buckwheat parameterized forms each record command log, stdout, stderr, and exit artifacts for acquisition, verification, start, and status steps. |

#### Fixed Public Regression Inputs
- **Banking-App-Mock-Compose**:
  Source URL `https://github.com/alexandr7035/Banking-App-Mock-Compose.git`,
  fixed revision `8f06a3fdc2dfb74b675b1c300560df19a9c2e142`, with a read-only
  verified local reuse candidate at
  `/Users/lief123/harmonyos-learning/projects/android-to-harmony-business-ui-loop-20260821/sources/Banking-App-Mock-Compose`.
  Exact repository command:
  `python3 skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py --change-dir changes/android-to-harmony-execution-plan-dag --project banking --source-url https://github.com/alexandr7035/Banking-App-Mock-Compose.git --expected-revision 8f06a3fdc2dfb74b675b1c300560df19a9c2e142 --source-dir changes/android-to-harmony-execution-plan-dag/evidence/sources/banking/source --reuse-candidate changes/android-to-harmony-execution-plan-dag/evidence/sources-cache/banking --project-name BankingExecutionPlanDag --bundle-name com.specsuperflow.banking.executionplandag --run-root changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/banking/run-root --target-dir changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/banking/target --evidence-subtree changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/banking`
  Expected subtree:
  `changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/banking/`
  with `contract/`, `capability-graph.json`, `fact-packs/`,
  `review-queue.json`, `gate-report.json`, `execution-plan.json`,
  `frozen-task-state.json`, `logs/01-start.stdout.txt`,
  `logs/01-start.stderr.txt`, `logs/01-start.command.log`,
  `logs/02-status.stdout.txt`, `logs/02-status.stderr.txt`,
  `logs/02-status.command.log`, `exit/01-start.exit.json`,
  `exit/02-status.exit.json`, `tests/start-status.test.log`, and
  `skill-identity-reference.json`.
- **ekspensify-android**:
  Source URL `https://github.com/dilipsuthar264/ekspensify-android.git`,
  fixed revision `0292c62e267a8b9cbc0d9dc580d80c549701661c`, with a read-only
  verified local reuse candidate at
  `/Users/lief123/harmonyos-learning/projects/android-to-harmony-form-candidates-20260803/sources/ekspensify-android`.
  Exact repository command:
  `python3 skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py --change-dir changes/android-to-harmony-execution-plan-dag --project ekspensify --source-url https://github.com/dilipsuthar264/ekspensify-android.git --expected-revision 0292c62e267a8b9cbc0d9dc580d80c549701661c --source-dir changes/android-to-harmony-execution-plan-dag/evidence/sources/ekspensify/source --reuse-candidate changes/android-to-harmony-execution-plan-dag/evidence/sources-cache/ekspensify --project-name EkspensifyExecutionPlanDag --bundle-name com.specsuperflow.ekspensify.executionplandag --run-root changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/ekspensify/run-root --target-dir changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/ekspensify/target --evidence-subtree changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/ekspensify`
  Expected subtree:
  `changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/ekspensify/`
  with the same required evidence families and filenames as Banking.
- **buckwheat**:
  Source URL `https://github.com/danilkinkin/buckwheat.git`, fixed revision
  `4b60102db5293059aadb7be22bf6390ae4b345a7`, with a read-only verified local
  reuse candidate at
  `/Users/lief123/harmonyos-learning/projects/android-to-harmony-form-candidates-20260803/sources/buckwheat`.
  Exact repository command:
  `python3 skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py --change-dir changes/android-to-harmony-execution-plan-dag --project buckwheat --source-url https://github.com/danilkinkin/buckwheat.git --expected-revision 4b60102db5293059aadb7be22bf6390ae4b345a7 --source-dir changes/android-to-harmony-execution-plan-dag/evidence/sources/buckwheat/source --reuse-candidate changes/android-to-harmony-execution-plan-dag/evidence/sources-cache/buckwheat --project-name BuckwheatExecutionPlanDag --bundle-name com.specsuperflow.buckwheat.executionplandag --run-root changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/buckwheat/run-root --target-dir changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/buckwheat/target --evidence-subtree changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/buckwheat`
  Expected subtree:
  `changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/buckwheat/`
  with the same required evidence families and filenames as Banking.

### AC: Run portable default tests
- **Requirement**: Single workflow entry and portable evidence
- **User-visible**: No

#### File Changes
##### Create `changes/android-to-harmony-execution-plan-dag/evidence/skill-identities/bundled-skill-tree-manifest.json`
- **Why this file**: The current change must own the bundled Skill tree
  manifest that default JS tests verify after `hash_evidence_tree.py` and other
  bundled-tree edits change the file count and digest.
- **Change**: Record the repo-local bundled Android-to-Harmony Skill tree
  manifest for the current change only.

##### Create `changes/android-to-harmony-execution-plan-dag/evidence/skill-identities/repo-skill-binding.json`
- **Why this file**: The default JS digest-binding test needs an in-scope,
  current-change binding rather than the stale binding under
  `android-to-harmony-54-benchmark`.
- **Change**: Record the current change's repo-local binding between the
  bundled Skill path and the current bundled Skill tree manifest.

##### Modify `tests/lib/hash-skill-tree.test.mjs`
- **Why this file**: This is the repository JS seam that currently hard-codes a
  developer-specific canonical-cache path in default test execution.
- **Change**: Make repo-local bundled-skill hashing the default portable test
  path, point the default manifest/binding lookup at
  `changes/android-to-harmony-execution-plan-dag/evidence/skill-identities/`,
  keep canonical-cache comparison as an explicit opt-in local-evidence branch,
  and leave `android-to-harmony-54-benchmark` evidence untouched.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node 22 | Update | tests/lib/hash-skill-tree.test.mjs | `canonical skill tree manifest is path-independent` | Pre-change failure reflects the stale old manifest path and digest assumptions; post-change pass validates the current bundled tree against the current-change manifest. |
| Integration | Node 22 | Update | tests/lib/hash-skill-tree.test.mjs | `digest binding artifact ties vendored skill to the canonical tree hash` | Pre-change failure reflects the stale old binding under `android-to-harmony-54-benchmark`; post-change pass validates the current bundled tree against the current-change binding. |
| Integration | Node 22 | Run existing | tests/lib/hash-skill-tree.test.mjs | `optional canonical cache comparison is skipped unless explicitly configured` | This exact optional-cache case is already a truthful baseline pass today and is rerun after implementation so default JS tests remain repo-local and opt-in for canonical-cache comparison. |

### Batch Verification
- [ ] RED: `python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_status_reports_current_execution_plan_through_workflow_entry MigrationAgentTests.test_capture_execution_plan_regressions_freezes_complete_public_project_evidence MigrationAgentTests.test_capture_execution_plan_regressions_acquires_and_verifies_fixed_public_revisions MigrationAgentTests.test_capture_execution_plan_regressions_records_acquisition_command_evidence_for_all_project_forms` and `python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_execution_plan_evidence_tree_manifest_lists_required_evidence_families MigrationToolTests.test_execution_plan_evidence_tree_manifest_rejects_tampering MigrationToolTests.test_execution_plan_evidence_tree_manifest_rejects_project_regression_artifact_tampering` and `node --test tests/integration/android-harmony-benchmark.test.mjs --test-name-pattern="routes Android-to-Harmony execution planning through the workflow entry only"` and `node --test tests/lib/hash-skill-tree.test.mjs --test-name-pattern="canonical skill tree manifest is path-independent|digest binding artifact ties vendored skill to the canonical tree hash"` and record the expected focused failures before implementation.
- [ ] BASELINE PASS: `node --test tests/lib/hash-skill-tree.test.mjs --test-name-pattern="optional canonical cache comparison is skipped unless explicitly configured"` and record the current observed pass for the optional-cache skip case before implementation.
- [ ] GREEN: Rerun the exact RED commands and pass every planned Batch 3 case, then rerun `node --test tests/lib/hash-skill-tree.test.mjs --test-name-pattern="optional canonical cache comparison is skipped unless explicitly configured"` as the required post-change RERUN.
- [ ] Mandatory evidence freeze after GREEN: run the three exact public-project capture commands above for Banking, Ekspensify, and Buckwheat; verify each current-change subtree contains the full required evidence family plus `skill-identity-reference.json`; then run `python3 skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py --change-dir changes/android-to-harmony-execution-plan-dag --evidence-root changes/android-to-harmony-execution-plan-dag/evidence --output changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/evidence-tree-manifest.json` and `python3 skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py --verify --change-dir changes/android-to-harmony-execution-plan-dag --evidence-root changes/android-to-harmony-execution-plan-dag/evidence --input changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/evidence-tree-manifest.json`.
- [ ] Regression: `python3 -m py_compile skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`, `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v`, `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v`, and `node --test --experimental-strip-types tests/lib/hash-skill-tree.test.mjs tests/lib/cmd-state.test.mjs tests/lib/infer-workflow.test.mjs tests/integration/android-harmony-benchmark.test.mjs` with zero failures.
