# 01 — Expose planning through one workflow entry

**What to build:** Make the existing migration workflow the sole normal-user path for generating and observing the current execution plan and task state, while retaining standalone helpers only as maintainer/debug seams.

**Blocked by:** None — can start immediately.

**Status:** completed

- [x] `start`, `resume`, and `status` expose the same current plan identity, task-state identity, ready tasks, and blockers through the workflow seam.
- [x] Repository integration proves Android-to-Harmony execution planning is routed through that seam without a second user planner flow.
- [x] Skill and capability guidance clearly separates normal workflow use from maintainer/debug helpers.
- [x] The focused RED/GREEN cases and affected Python/Node regressions pass without changing Batch 1 or Batch 2 semantics.

## Evidence

- Changed files:
  - `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
  - `skills/migrate-android-compose-to-harmony/SKILL.md`
  - `skills/migrate-android-compose-to-harmony/references/capability-graph-and-gates.md`
  - `tests/lib/vscode-agent-plugin.test.mjs`
- Behavioral RED:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - FAIL: `execution_plan` was absent from `start` output.
  - `node --test tests/lib/vscode-agent-plugin.test.mjs --test-name-pattern "keeps executable planning behind the workflow seam and relegates helper CLIs to maintainer debug use"`
    - FAIL: migration skill text did not explicitly bind the plan/task-state surface to `start`/`resume`/`status`.
- GREEN rerun of the exact focused seams:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - PASS
  - `node --test tests/lib/vscode-agent-plugin.test.mjs --test-name-pattern "keeps executable planning behind the workflow seam and relegates helper CLIs to maintainer debug use"`
    - PASS
- Affected regressions:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v`
    - PASS, `27/27`
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v`
    - PASS, `359/359`
  - `node --test tests/lib/vscode-agent-plugin.test.mjs`
    - PASS, `24/24`
- Workflow-only proof:
  - `migration_agent.py` now returns the current immutable `execution_plan` and mutable `execution_task_state` alongside `plan_identity`, `task_state_identity`, ready tasks, and blockers for `start`, `resume`, and `status`.
  - `SKILL.md` and `references/capability-graph-and-gates.md` now state that only the workflow seam and `migration_agent.py` are normal-user entry points; `build_capability_graph.py`, `aggregate_gate_evidence.py`, and `build_execution_plan.py` remain maintainer/debug helpers only.
- Batch 1/2 non-regression:
  - The full `test_tools.py` planner/gate suite stayed green after the workflow-entry change, including prerequisite, shared-foundation, stale/tamper, and fail-closed coverage.
- Residual risks:
  - Ticket 01 does not yet implement portable checked public-project capture or evidence-tree freezing; those remain in later tickets.

## Review round 1

**Verdict:** Request Changes

- Remove lifecycle projections from the public immutable `execution_plan`: `seed_task_states`, `task_views`, `next_executable_tasks`, `blocked_tasks`, and task lifecycle status must live only in current mutable task state or the joined top-level response.
- Extend the public-seam test with a valid task-state transition. Prove the immutable plan remains byte-identical and lifecycle-free while current state, ready tasks, and blockers change consistently across `start`, `resume`, and `status`.

### Repair evidence

- Changed files for round 1:
  - `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- Behavioral RED:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - FAIL: `execution_plan` still contained `seed_task_states` and other lifecycle projections.
- GREEN rerun of the exact focused seams:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - PASS
  - `node --test tests/lib/vscode-agent-plugin.test.mjs --test-name-pattern "keeps executable planning behind the workflow seam and relegates helper CLIs to maintainer debug use"`
    - PASS
- Full affected regressions:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v`
    - PASS, `27/27`
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v`
    - PASS, `359/359`
  - `node --test tests/lib/vscode-agent-plugin.test.mjs`
    - PASS, `24/24`
- Repair summary:
  - `migration_agent.py` now projects builder output onto an immutable public `execution_plan` before persistence and response, stripping `seed_task_states`, `task_views`, `next_executable_tasks`, `blocked_tasks`, and any task `status` fields.
  - Initial seed lifecycle is used only to create `execution-task-state.json`.
  - The focused public seam test now performs a valid task-state transition and proves the immutable plan stays byte-identical while current task state and top-level ready/blocker views update through `resume` and `status`.

## Review round 2

**Verdict:** Request Changes

- Compute and verify `plan_identity` from the final projected immutable plan payload, after removing the identity envelope and every seed/view/status/lifecycle field.
- Add a blocked-task fixture whose raw planner output contains status. Recompute the canonical identity from the persisted public immutable plan, then transition task state and prove the identity remains unchanged.

### Repair evidence
- Changed files for round 2:
  - `skills/migrate-android-compose-to-harmony/scripts/migration_agent.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- Canonical identity payload formula:
  - Start from the workflow-owned public `execution_plan`.
  - Remove `plan_identity`, `seed_task_states`, `task_views`, `next_executable_tasks`, and `blocked_tasks`.
  - Remove every task-level `status`.
  - Serialize with `json.dumps(payload, indent=2, ensure_ascii=False) + "\n"`.
  - Hash with SHA-256. The resulting digest is the only valid `plan_identity`.
- Behavioral RED:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - FAIL: persisted/public `plan_identity` did not equal the independently recomputed canonical digest from the returned immutable plan payload.
- GREEN rerun of the exact focused seams:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - PASS
  - `node --test tests/lib/vscode-agent-plugin.test.mjs --test-name-pattern "keeps executable planning behind the workflow seam and relegates helper CLIs to maintainer debug use"`
    - PASS
- Blocked/raw-status fixture proof:
  - The focused seam test now synthesizes a raw blocked fixture by adding `seed_task_states`, `task_views`, `next_executable_tasks`, `blocked_tasks`, and a task-level `status: blocked` onto the immutable plan view.
  - Independent canonical recomputation produces the same digest as the persisted immutable plan, proving those lifecycle/view fields are excluded from identity.
  - The same test then performs a valid task-state transition and proves plan bytes and `plan_identity` remain unchanged while current `execution_task_state`, `next_executable_tasks`, and `blocked_tasks` update through `resume` and `status`.
- Full affected regressions on final bytes:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - PASS
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v`
    - PASS, `27/27`
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v`
    - PASS, `359/359`
  - `node --test tests/lib/vscode-agent-plugin.test.mjs`
    - PASS, `24/24`
- Repair summary:
  - `migration_agent.py` now owns one canonical immutable-plan identity algorithm at the workflow seam and recomputes `plan_identity` from the final projected immutable payload before task-state creation, persistence, stale checks, and responses.
  - Persisted `execution-plan.json` is also validated against the same canonical projection/hash rule during current/stale assessment, so stale/tampered plan identity fails closed with the canonical-identity error instead of reusing a competing digest rule.

## Review round 3

**Verdict:** Request Changes

- Route the blocked/raw-status fixture through the production immutable-plan projection before independently hashing and asserting the persisted/public payload. A test-local canonical helper alone does not protect the production projection from regression.

## Review round 4

**Verdict:** Approved

- The blocked/raw-status payload now exercises the production projection.
- The projected immutable payload is independently serialized and hashed in the test.
- Workflow entry, immutable/mutable separation, current ready/blocker views, stale checks, and tamper rejection remain intact.

### Repair evidence

- Changed files for round 3:
  - `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
- Production seam exercised:
  - `migration_agent.project_immutable_execution_plan`
- Behavioral RED:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - FAIL on prior bytes because the blocked/raw-status fixture only proved a test-local canonical helper and did not route through the production immutable-plan projection.
- GREEN rerun of the exact focused seams:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_start_resume_and_status_expose_current_execution_plan_and_task_state`
    - PASS
  - `node --test tests/lib/vscode-agent-plugin.test.mjs --test-name-pattern "keeps executable planning behind the workflow seam and relegates helper CLIs to maintainer debug use"`
    - PASS
- Full affected regressions on final bytes:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v`
    - PASS, `27/27`
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v`
    - PASS, `359/359`
  - `node --test tests/lib/vscode-agent-plugin.test.mjs`
    - PASS, `24/24`
- Repair summary:
  - The blocked/raw-status fixture now passes through `migration_agent.project_immutable_execution_plan(...)` before identity recomputation.
  - The focused seam independently hashes the production-projected immutable payload and asserts the reported `plan_identity` matches that digest.
  - The same assertion proves the production projection removes `seed_task_states`, `task_views`, `next_executable_tasks`, `blocked_tasks`, and task-level `status`, while the existing `start`/`resume`/`status` transition, ready/blocker, stale, and tamper assertions remain intact.
  - No production defect was found in round 3; the repair was test-coverage only.
