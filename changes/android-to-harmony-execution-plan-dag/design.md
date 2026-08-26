# Design: Android-to-Harmony Executable Vertical-Slice Planning

## Context

The minimum behavior-changing production seam is the existing internal
capability-artifact pipeline under
`skills/migrate-android-compose-to-harmony/scripts/`:

- `build_capability_graph.py` derives machine-readable migration facts from the
  safe contract.
- `aggregate_gate_evidence.py` validates current gate scope and node status.
- `build_execution_plan.py` converts graph facts into executable migration
  tasks.
- `migration_agent.py` is the only normal workflow entry that persists and
  reports the current plan.

The current implementation still violates the approved upstream contract in two
fundamental ways. First, the capability graph is mostly a parent/child
inventory tree, so the planner has no trustworthy cross-layer relationships to
consume. Second, the planner compensates with page-per-task construction,
filename/token scoring, and first-slice fallback, which can mechanically cover
files without proving a real route/page migration closure or an executable
dependency order.

The existing public seams and exact test harnesses already exist in:

- `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- `tests/lib/hash-skill-tree.test.mjs`
- `tests/integration/android-harmony-benchmark.test.mjs`

Those seams are the approved ownership points for this change. The previously
edited red tests in `test_tools.py`, `test_orchestrator.py`, and
`tests/lib/hash-skill-tree.test.mjs` are only unverified worktree inputs from a
stopped implementation attempt; they are not accepted evidence and must be
reconciled under the approved ACs before any later execution freeze.

No project-root long-lived capability spec owns this behavior today. The
approved change-local delta Spec is therefore the behavioral source of truth,
and the existing bundled Android-to-Harmony Skill plus current workflow tests
are the reuse anchors. The normal user entry remains Spec Workflow plus
`migration_agent`; standalone planner, graph, and evidence scripts remain
maintainer/debug-only implementation seams.

## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Why Here |
|---|---|---|---|---|---|---|
| Resolved route-rooted vertical-slice closure | Build a cross-layer slice from resolved relationships | Typed Resolved Edge Graph | `build_capability_graph.py`, `build_execution_plan.py` | Existing graph node schema and current planner output | Replace token/path inference with typed resolved edges | Cross-layer closure must start with graph facts and end in planner provenance. |
| Resolved route-rooted vertical-slice closure | Reject similarity and first-slice fallback ownership | Route/Page Slice Qualification And Shared Foundations | `build_execution_plan.py` | Existing review queue and coverage accounting | No filename/token or task-order ownership fallback | Slice ownership is decided only where tasks are formed. |
| Resolved route-rooted vertical-slice closure | Reject leaf artifacts as standalone migration tasks | Route/Page Slice Qualification And Shared Foundations | `build_capability_graph.py`, `build_execution_plan.py` | Existing page/control/business/storage/platform layer model | Leaf composable/control/file nodes never become executable roots by themselves | Root qualification depends on graph semantics and planner task construction together. |
| Resolved route-rooted vertical-slice closure | Reject accounting-only completion | Local Blockers And Gate-Scoped Readiness | `build_execution_plan.py`, `aggregate_gate_evidence.py` | Existing coverage fields and gate report | Coverage is necessary but insufficient without closure, blockers, and obligations | Semantic completeness belongs to plan validation and gate scope, not file counts alone. |
| Resolved route-rooted vertical-slice closure | Associate tests without claiming production implementation | Route/Page Slice Qualification And Shared Foundations | `build_execution_plan.py` | Existing `test_support` graph layer | Tests are obligations, never production owners | Task packet construction owns production/test separation. |
| Executable dependency DAG and task lifecycle | Emit a complete executable task packet | Implementation-Prerequisite DAG And Immutable Plan State | `build_execution_plan.py` | Existing plan schema and deterministic JSON output | Every task packet needs stable identity and complete references | Packet completeness is a planner responsibility. |
| Executable dependency DAG and task lifecycle | Hold dependent work until prerequisites complete | Implementation-Prerequisite DAG And Immutable Plan State | `build_execution_plan.py`, `migration_agent.py` | Existing topological sort and status/resume responses | Only implementation prerequisites create DAG edges; runtime behavior alone does not | Planner computes order, workflow reports readiness from persisted state. |
| Executable dependency DAG and task lifecycle | Unlock downstream work after completion | Implementation-Prerequisite DAG And Immutable Plan State | `migration_agent.py` | Existing start/resume/status pipeline | Mutable task lifecycle must be separated from immutable plan bytes | Readiness changes belong to workflow state, not plan regeneration. |
| Executable dependency DAG and task lifecycle | Reject invalid dependency graphs | Implementation-Prerequisite DAG And Immutable Plan State | `build_execution_plan.py` | Existing cycle rejection helper | Unknown dependencies and cycles both fail closed | Dependency validation is part of plan construction. |
| Local fail-closed blockers and gate enforcement | Block only a related slice | Local Blockers And Gate-Scoped Readiness | `aggregate_gate_evidence.py`, `build_execution_plan.py` | Existing gate-report and review-queue artifacts | Blockers must be scoped by verified relationship paths, not applied globally | Gate state and closure membership are joined only after both artifacts exist. |
| Local fail-closed blockers and gate enforcement | Refuse unscoped ambiguity | Local Blockers And Gate-Scoped Readiness | `build_capability_graph.py`, `aggregate_gate_evidence.py`, `build_execution_plan.py` | Existing unclassified queue | Ambiguous production ownership and unscoped failed gates remain explicit and local, never guessed | The graph identifies ambiguity, the gate report identifies failed scope, and the planner decides whether any slice can be scoped safely. |
| Strict plan identity and tamper rejection | Reject changed planning inputs | Workflow-Owned Integrity And Portable Evidence | `aggregate_gate_evidence.py`, `build_execution_plan.py`, `migration_agent.py` | Existing SHA-256 contract/graph/Skill bindings | Add graph-content, review-queue, gate-node-set, plan-state, and plan identity binding | All executable decisions must be rejected before readiness is reported. |
| Strict plan identity and tamper rejection | Preserve one current identity across workflow commands | Implementation-Prerequisite DAG And Immutable Plan State | `migration_agent.py` | Existing capability-artifact persistence | `start`, `resume`, and `status` must all read the same immutable plan identity and mutable task state | Workflow command parity is owned by the orchestrator. |
| Single workflow entry and portable evidence | Run planning through the workflow entry | Workflow-Only User Entry | `migration_agent.py`, `skills/migrate-android-compose-to-harmony/SKILL.md`, `references/capability-graph-and-gates.md` | Existing Android-to-Harmony workflow path | Standalone planner tools are maintainer/debug only | User entry semantics belong to the workflow/orchestrator contract. |
| Single workflow entry and portable evidence | Verify the complete evidence tree | Workflow-Owned Integrity And Portable Evidence | internal evidence-tree hashing/verifier helper, `migration_agent.py` | Existing skill-tree hashing and current capability artifacts | Relative-path manifest must cover the full requirement evidence tree | Evidence portability and tamper rejection are cross-artifact verification concerns. |
| Single workflow entry and portable evidence | Run portable default tests | Workflow-Only User Entry | `tests/lib/hash-skill-tree.test.mjs` | Existing bundled-skill digest test | Default test path must be repo-local; personal cache remains opt-in only | Portable test behavior is enforced at the JS test seam. |

## Decisions

### Decision: Typed Resolved Edge Graph
- **Choice**: `build_capability_graph.py` will become the single producer of two
  exact deterministic graph structures consumed later by
  `build_execution_plan.py`: `root_qualification[]` and `resolved_edges[]`.
  `root_qualification[]` records which `page:*` nodes are executable roots and
  why, with fields:
  `node_id`, `qualified_as_root`, `qualification_kind`, `source_path`,
  `source_symbol`, and `evidence`.
  `resolved_edges[]` records closure relationships, with fields:
  `edge_id`, `kind`, `from_node_id`, `to_node_id`, `source_path`,
  `source_symbol`, `evidence`, and `consumed_by_planner`.
  The allowed edge kinds are:
  `route_entry`, `route_binding`, `page_declares_control`,
  `page_uses_business`, `business_uses_repository`,
  `repository_uses_network`, `repository_uses_storage`,
  `page_uses_platform`, `page_uses_ui_system`,
  `shared_foundation_member`, `test_obligation`,
  `runtime_navigation`, `runtime_import`, and `runtime_call`.
  `runtime_navigation`, `runtime_import`, and `runtime_call` are closure-only
  provenance edges and set `consumed_by_planner` to `provenance_only`.
  Non-runtime ownership edges set `consumed_by_planner` to
  `closure_and_assignment`.
- **Rationale**: The approved Spec requires route/page-rooted vertical slices
  backed by exact relationship paths. Without typed graph fields the planner can
  only guess ownership from names and paths, which is the current failure mode.
- **Alternatives considered**: Recomputing planner ownership from filename
  tokens or migration batches was rejected because it recreates false coverage.
  Building one task per file or Composable was rejected because it loses
  business closure and does not describe an executable migration outcome.

### Decision: Route/Page Slice Qualification And Shared Foundations
- **Choice**: A node qualifies as an executable slice root only when
  `root_qualification[].qualified_as_root == true` and the qualification record
  proves one of these exact rules:
  `qualification_kind == "route_inventory_root"` from
  `contract.ui.routes`,
  `qualification_kind == "android_navigation_root"` from
  `ui.android_navigation_inventory`,
  or `qualification_kind == "entry_screen_root"` from a directly routable
  activity/fragment/layout entry recorded in the graph.
  Any preview, control, leaf Composable, helper file, or unattached page-like
  declaration without one of those exact qualification kinds remains non-root.
  Shared production capabilities reached from multiple roots through
  `shared_foundation_member` edges become a single-owner foundation task. That
  foundation is implemented once, then consumed by multiple slices through
  planner prerequisite edges; ownership is never duplicated across slices.
  `test_support` nodes remain obligation-only and may only enter a packet
  through `test_obligation` edges.
- **Rationale**: This preserves one authoritative production owner per source
  while still allowing reuse across slices. It also prevents leaf declarations
  and tests from masquerading as business-complete migration work.
- **Alternatives considered**: Allowing every classified page/control/file node
  to spawn a task was rejected because it produces composable-level busywork.
  Duplicating shared business/data/platform nodes into each slice was rejected
  because it creates conflicting implementation ownership and misleading
  readiness.

### Decision: Implementation-Prerequisite DAG And Immutable Plan State
- **Choice**: `build_execution_plan.py` will consume `root_qualification[]` and
  `resolved_edges[]` and produce an immutable `execution-plan.json` plus a
  separate mutable `execution-task-state.json` owned by `migration_agent.py`.
  The immutable plan contains only immutable task packets plus exact
  prerequisite edges. Each packet stores immutable task definition,
  dependency ids, obligations, closure provenance, blocker definitions, and
  frozen evidence references; it never stores the mutable task-state identity,
  and it never embeds its own content hash. Plan identity is computed from an
  excluded envelope or explicitly delimited payload, then recorded outside the
  hashed payload.
  The exact planner dependency field is `prerequisite_edges[]` with fields:
  `edge_id`, `kind`, `producer_task_id`, `consumer_task_id`, `producer_node_id`,
  `consumer_node_id`, `reason`, and `source_edge_ids`.
  The only allowed prerequisite kinds are:
  `shared_foundation_prerequisite` and `produced_contract_prerequisite`.
  `shared_foundation_prerequisite` is emitted when two or more slice roots
  consume the same single-owner foundation task. `produced_contract_prerequisite`
  is emitted when one task must produce a typed capability or adapter contract
  that another task consumes for implementation. Runtime navigation/import/call
  edges never become task dependencies; they remain only in
  `closure_provenance[]`.
  `migration_agent.py` owns mutable lifecycle state with exact statuses
  `pending`, `ready`, `blocked`, and `completed`, bound one-way to the
  immutable `plan_identity`. `execution-task-state.json` stores
  `plan_identity`, a current `task_state_identity`, and the mutable per-task
  lifecycle map. `start`, `resume`, and `status` join immutable packets with
  the current task-state file at runtime rather than persisting mutable state
  back into the plan.
- **Rationale**: This separates “what the plan is” from “how far execution has
  progressed”, prevents ordinary state updates from changing the plan hash, and
  avoids turning all runtime loops into artificial dependency cycles.
- **Alternatives considered**: Storing mutable lifecycle directly inside the
  plan was rejected because every completion would invalidate the plan.
  Converting every navigation/call edge into a task dependency was rejected
  because normal apps contain legal runtime cycles that are not implementation
  blockers.

### Decision: Local Blockers And Gate-Scoped Readiness
- **Choice**: `aggregate_gate_evidence.py` will produce a gate report that the
  planner can consume directly, with exact integrity and scope fields:
  `graph_sha256`, `graph_node_ids[]`, `review_queue_sha256`,
  `node_statuses_sha256`, and `report_by_node`.
  `report_by_node` is keyed by node id and records the effective gate status,
  failed gates, and evidence references for that node.
  `build_execution_plan.py` combines `report_by_node` with
  `resolved_edges[]` and `root_qualification[]` to derive local blockers.
  If a failed gate or unresolved production ambiguity can be scoped to one root
  or one foundation task, only that packet is blocked. If the graph or gate
  report cannot prove scope, the planner emits an explicit unassigned blocker,
  marks production incomplete, and returns no executable fallback for that work.
- **Rationale**: The approved Spec requires local blockers, not an all-stop
  queue, but also forbids guessing when scope cannot be proven.
- **Alternatives considered**: Blocking every slice for any unresolved node was
  rejected because it destroys useful parallelism. Ignoring gate node status or
  review-queue scope was rejected because it would mark blocked work ready.

### Decision: Workflow-Owned Integrity And Portable Evidence
- **Choice**: `aggregate_gate_evidence.py`, `build_execution_plan.py`, and
  `migration_agent.py` will bind exact identity families:
  contract bytes, graph bytes, review queue bytes, gate node set/statuses,
  immutable plan bytes, mutable task-state bytes, and Skill tree digest.
  `build_execution_plan.py` validates those identities before it writes a plan.
  `migration_agent.py` validates them before it returns executable work.
  An internal relative-path evidence-tree helper will hash and verify these
  exact evidence families at freeze time:
  contract originals, capability graph, fact packs, review queue, gate report,
  immutable plan, frozen task state, command stdout, command stderr, command
  logs, exit artifacts, test logs, and Skill identity manifests.
  It also covers fixed-regression artifacts for Banking, Ekspensify, and
  Buckwheat under
  `changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/`.
  The Skill identity model is centralized: the current change owns one
  `evidence/skill-identities/` manifest plus binding pair, and each fixed
  project subtree stores only a content-bound reference or digest that points at
  those central identity artifacts. Project subtrees do not own duplicate Skill
  manifests.
  Historical evidence under
  `changes/android-to-harmony-54-benchmark/evidence/` remains strictly
  read-only and may only serve as source provenance for fixed public revisions
  and expected artifact families.
  Default JS tests hash the repo-local bundled Skill, while optional
  canonical-cache comparison is enabled only via an explicit environment
  variable.
- **Rationale**: This satisfies the fail-closed staleness requirement and keeps
  regression tests portable across CI and other machines.
- **Alternatives considered**: Timestamp-based freshness was rejected because
  it cannot detect semantically equivalent rewrites or manual tampering.
  Hard-coding a developer cache path in default tests was rejected as
  non-portable. Creating a second user-facing planner CLI was rejected because
  the approved contract says workflow and `migration_agent` remain the only
  normal entry points.

### Decision: Workflow-Only User Entry
- **Choice**: Keep all automatic planning, validation, and status reporting on
  the existing Spec Workflow plus `migration_agent` path. `SKILL.md` and the
  capability-graph/gates reference document may describe standalone scripts only
  as maintainer/debug helpers for reproducibility, tests, and low-level
  diagnosis. Batch 3 integrates, rather than duplicates, the evidence and
  identities produced by Batches 1 and 2.
- **Rationale**: The user contract for this change is a single workflow entry,
  not a second planning interface.
- **Alternatives considered**: Teaching users to call `build_capability_graph`,
  `aggregate_gate_evidence`, or `build_execution_plan` directly was rejected as
  duplicate surface area and a source of stale artifact handling mistakes.

## Risks And Trade-Offs

- Static source analysis will still miss some dynamic dependency-injection or
  reflection-heavy relationships. The intentional behavior is to queue or block
  that work explicitly rather than invent ownership.
- Single-owner shared foundations create more visible prerequisite tasks than a
  simplistic page-only plan, but that cost is necessary to prevent duplicate
  implementation ownership.
- The existing unverified red-test edits prove only that a previous attempt
  started writing coverage. They remain planning inputs, not validation
  evidence, until a later execution contract binds them to passing commands.
- Portable evidence can prove public-project regression and tamper rejection,
  but it cannot by itself claim full migration success for every future Android
  application topology.
