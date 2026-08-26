# 04 — Prove clean acquisition with Buckwheat

**What to build:** Run the checked evidence path for the fixed Buckwheat revision from an absent source directory, proving clone, checkout, remote verification, revision verification, workflow execution, and complete evidence freeze.

**Blocked by:** 02 — Freeze one complete Banking evidence tracer.

**Status:** completed

- [x] A missing source directory is acquired and verified using fixed subprocess arguments.
- [x] Remote or final revision mismatch stops before evidence can be declared complete.
- [x] Acquisition, verification, start, and status each record stdout, stderr, command, and exit evidence.
- [x] Buckwheat freezes the same complete evidence family and central Skill-identity reference as Banking.

## Evidence

- Production and test seams:
  - `skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py`
  - `skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py`
  - `skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- Focused RED:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_capture_execution_plan_regressions_acquires_missing_buckwheat_source` — FAIL, `1/1`: the checked capture rejected `buckwheat` because the exact public project was not registered.
  - The same direct-script seam with `test_capture_execution_plan_regressions_rejects_nonfixed_buckwheat_revision`, `test_capture_execution_plan_regressions_rejects_wrong_buckwheat_remote_with_evidence`, and `test_capture_execution_plan_regressions_rejects_buckwheat_final_revision_mismatch_with_evidence` — FAIL: the project was rejected before its fixed-revision and frozen failure-evidence behavior existed.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_execution_plan_evidence_tree_manifest_lists_complete_portable_membership MigrationToolTests.test_execution_plan_evidence_tree_manifest_rejects_missing_extra_and_tampered_artifacts` — FAIL, `2/2`: manifest membership allowed only Banking and Ekspensify.
  - The first real fixed-revision capture reached the planner and failed closed with `execution plan requires at least one qualified route/page root`.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_capability_graph_prefers_entry_screen_over_helper_for_shared_source_ownership` — FAIL, `1/1`: `BoxScope` took primary ownership of `MainScreen.kt`, so `page:mainscreen` lacked qualified closure.
- Focused GREEN on the identical seams:
  - The four Buckwheat acquisition/fail-closed orchestrator tests — PASS, `4/4`; the source begins absent, fixed argv perform acquisition and detached checkout, and non-authoritative revision, wrong remote, or final-HEAD mismatch stop before `01-start` while preserving command/stdout/stderr/exit evidence for the attempted path.
  - The two three-project manifest membership/tamper tests — PASS, `2/2`.
  - The shared-source ownership regression — PASS, `1/1`; a non-preview entry-style composable outranks an earlier helper in the same file.
- Authoritative Buckwheat capture:
  - Remote: `https://github.com/danilkinkin/buckwheat.git`.
  - Revision: `4b60102db5293059aadb7be22bf6390ae4b345a7`.
  - The prepared cache at `/Users/lief123/harmonyos-learning/projects/android-to-harmony-form-candidates-20260803/sources/buckwheat` was verified clean at that exact public origin and revision before use. The separate change-local source directory began absent, recorded clone, origin replacement, revision presence, detached checkout, final remote/HEAD/detached verification, and was removed after the successful freeze.
  - Plan identity: `71ddf68e3d10d0a13a7890666795ac8959578d2dc501fe7d5c51297937a29c28`.
  - Frozen task-state identity: `0a07bc3eab1b465402b384184940c9d4b6aaa2dd0570d8932bb53ca93c124c25`; start and status expose the same plan and task-state identities.
  - Final portable Skill-tree identity after review repair: `019c8c55efeb9a0e5bf343a46549ed86fea050a17398d8777f3d8e01646b0d23`, `70` files. Manifest content SHA-256: `2881f387a7930724946dd61f1c0819757d5c0a442b4f663289703b17bdf9f728`; binding content SHA-256: `fc1cb866d228e9870e31f07d50e3e336fc89854c0fc55237c1400a0ceac97ef7`.
  - Final evidence manifest verification: PASS, projects `[banking, ekspensify, buckwheat]`, `190` files, tree digest `50f8a9e36f4a1c439505bb63e51aa410f873c89b43ce077e63c6cdc940f30238`.
- Affected regressions:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v` — PASS, `363/363`.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v` — PASS, `37/37`.
  - `node --test --experimental-strip-types tests/lib/hash-skill-tree.test.mjs tests/lib/cmd-state.test.mjs tests/lib/infer-workflow.test.mjs tests/integration/android-harmony-benchmark.test.mjs` — PASS, `55/55`.
  - `python3 -m py_compile skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py skills/migrate-android-compose-to-harmony/scripts/migration_agent.py` — PASS.
- Ticket-local two-axis review against fixed point `9c7de2795ee8d4edf3ab00e08743b93cbcbca9ea`:
  - Standards/code quality found one Minor duplicated central Skill-identity test fixture. The two older inline copies now reuse `write_capture_skill_identity`; the exact affected tests pass `3/3`.
  - Spec/acceptance/evidence review verified absent-directory acquisition, exact public URL and revision enforcement, detached final HEAD, frozen failed-path evidence, workflow start/status evidence, complete Buckwheat evidence membership, central identity binding, and tamper rejection.
  - Post-repair Standards verdict: PASS, no remaining actionable finding.
  - Post-repair Spec/acceptance/evidence verdict: PASS, no missing requirement, scope drift, or incorrect evidence claim.
- Scope guard:
  - Historical `changes/android-to-harmony-54-benchmark/evidence/` remained read-only.
  - Banking and Ekspensify changed only for the required current-change central Skill-reference refresh and reverified in the three-project manifest.
  - Ticket 05 remains unchanged.
