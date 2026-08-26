# 02 — Freeze one complete Banking evidence tracer

**What to build:** Starting from the fixed Banking public revision, deliver one end-to-end checked capture that verifies source identity, runs the workflow entry, freezes every required evidence family, binds the central portable Skill identity, and verifies the resulting evidence manifest.

**Blocked by:** 01 — Expose planning through one workflow entry.

**Status:** completed

- [x] The capture interface accepts structured inputs only and constructs fixed subprocess argument lists internally.
- [x] Banking produces contract, graph, fact packs, queue, gates, immutable plan, frozen task state, command outputs/logs, exits, test log, and a central Skill-identity reference.
- [x] The portable manifest rejects missing, extra, or tampered Banking artifacts.
- [x] The current bundled Skill manifest and binding are path-independent; historical benchmark evidence remains untouched.

## Evidence

- Production and test seams:
  - `skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py`
  - `skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py`
  - `skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
  - `tests/lib/hash-skill-tree.test.mjs`
- Current-change evidence:
  - `changes/android-to-harmony-execution-plan-dag/evidence/skill-identities/`
  - `changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/banking/`
  - `changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/evidence-tree-manifest.json`
- Focused RED:
  - The two checked-capture tests failed because `capture_execution_plan_regressions.py` did not exist.
  - The two evidence-membership/tamper tests failed because `hash_evidence_tree.py` did not exist.
  - The two current-change Skill identity tests failed because the portable manifest and binding did not exist under this change.
  - Real Banking planning exposed four additional focused RED cases: preview/UI-helper roots, an unresolved `AppLoadingScreen` root, missing shared-foundation edges for non-page production, and unassigned production behind shared foundation.
  - The affected full tools suite then exposed the exact regression `MigrationToolTests.test_execution_plan_builder_is_deterministic_and_covers_vertical_slices`: `network:profileapi` was absent from the Profile task. The same focused command passed after multi-consumer foundation detection was restricted to actual page origins.
- Focused GREEN on final bytes:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_capture_execution_plan_regressions_freezes_complete_banking_evidence MigrationAgentTests.test_capture_execution_plan_regressions_rejects_wrong_banking_remote` — PASS, `2/2`.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_banking_evidence_tree_manifest_lists_complete_portable_membership MigrationToolTests.test_banking_evidence_tree_manifest_rejects_missing_extra_and_tampered_artifacts MigrationToolTests.test_capability_graph_builder_emits_typed_resolved_edges_for_route_root_closure MigrationToolTests.test_capability_graph_does_not_promote_screen_previews_or_ui_helpers_to_roots MigrationToolTests.test_execution_plan_builder_is_deterministic_and_covers_vertical_slices` — PASS, `5/5`.
  - `node --test tests/lib/hash-skill-tree.test.mjs --test-name-pattern="canonical skill tree manifest is path-independent|digest binding artifact ties vendored skill to the canonical tree hash|optional canonical cache comparison is skipped unless explicitly configured"` — PASS, `3/3`.
- Affected regressions:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v` — PASS, `362/362`.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v` — PASS, `29/29`.
  - `node --test --experimental-strip-types tests/lib/hash-skill-tree.test.mjs tests/lib/cmd-state.test.mjs tests/lib/infer-workflow.test.mjs tests/integration/android-harmony-benchmark.test.mjs` — PASS, `55/55`.
  - `python3 -m py_compile skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py skills/migrate-android-compose-to-harmony/scripts/migration_agent.py` — PASS.
- Authoritative Banking capture:
  - Remote: `https://github.com/alexandr7035/Banking-App-Mock-Compose.git`.
  - Revision: `8f06a3fdc2dfb74b675b1c300560df19a9c2e142`.
  - Reused verified read-only candidate: `/Users/lief123/harmonyos-learning/projects/android-to-harmony-business-ui-loop-20260821/sources/Banking-App-Mock-Compose`.
  - Plan identity: `7fd9695350abb3f1cf0166ea3a3b3ef8b41419663e6e55b780d77b40dc8175da`.
  - Frozen task-state identity: `b705ebf85b53e943bef2a90fbb0633c74aa307d2c7edb9f1d910340adef7e217`.
  - Portable Skill-tree identity: `3d407b10ff2ec544e2d385a6bb14df8b387319d0d482456b95d97271af0e373f`, `70` files.
  - Evidence manifest verification: PASS, `63` files, tree digest `62392c228c2ced11692aa90f5632aa90d40aa8c5558f191dc284224a8beaaa8e`.
- Ticket-local two-axis review:
  - Standards/code quality: PASS. Fixed argv construction, path validation, atomic manifests, and graph changes remain within the existing CLI/test seams; diagnostic instrumentation was removed.
  - Spec/acceptance/evidence: PASS. Every required Banking family is frozen and content-bound, source remote/revision and workflow identities are recorded, and missing/extra/tampered evidence fails closed.
- Scope guard:
  - `changes/android-to-harmony-54-benchmark/evidence/` was not modified.
  - Tickets 03, 04, and 05 were not modified.
