# 03 — Prove reusable capture with Ekspensify

**What to build:** Run the same checked evidence path for the fixed Ekspensify revision, including reuse of an existing source and deterministic repair of a wrong-HEAD checkout before workflow execution.

**Blocked by:** 02 — Freeze one complete Banking evidence tracer.

**Status:** completed

- [x] A verified reuse source is accepted without mutating the read-only candidate.
- [x] An existing wrong-HEAD working copy is fetched, detached at the fixed revision, and verified before migration starts.
- [x] Wrong remote or final revision mismatch fails closed and records command/exit evidence.
- [x] Ekspensify freezes the same complete evidence family and central Skill-identity reference as Banking.

## Evidence

- Production and test seams:
  - `skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py`
  - `skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
- Focused RED:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_capture_execution_plan_regressions_reuses_candidate_and_repairs_wrong_head` — FAIL, `1/1`: the checked public capture rejected `--project ekspensify` before any workflow action because only Banking was registered.
- Focused GREEN on identical command:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_capture_execution_plan_regressions_reuses_candidate_and_repairs_wrong_head` — PASS, `1/1`.
- Review-repair RED/GREEN:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_capture_execution_plan_regressions_rejects_nonfixed_ekspensify_revision` — RED, `1/1`: a valid-looking non-authoritative SHA reached source-remote validation instead of being rejected as a non-fixed project revision.
  - The identical command — GREEN, `1/1`: Ekspensify now rejects every revision other than `0292c62e267a8b9cbc0d9dc580d80c549701661c` before creating evidence or invoking Git acquisition.
- Focused acceptance and compatibility:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_capture_execution_plan_regressions_rejects_nonfixed_ekspensify_revision MigrationAgentTests.test_capture_execution_plan_regressions_reuses_candidate_and_repairs_wrong_head MigrationAgentTests.test_capture_execution_plan_regressions_rejects_wrong_ekspensify_remote_with_evidence MigrationAgentTests.test_capture_execution_plan_regressions_rejects_final_head_mismatch_with_evidence` — PASS, `4/4`.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_execution_plan_evidence_tree_manifest_lists_complete_portable_membership MigrationToolTests.test_execution_plan_evidence_tree_manifest_rejects_missing_extra_and_tampered_artifacts` — PASS, `2/2` for exact Banking-plus-Ekspensify membership and missing/extra/tamper rejection.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v MigrationAgentTests.test_capture_execution_plan_regressions_freezes_complete_banking_evidence MigrationAgentTests.test_capture_execution_plan_regressions_rejects_wrong_banking_remote` — PASS, `2/2`.
- Authoritative Ekspensify capture:
  - Remote: `https://github.com/dilipsuthar264/ekspensify-android.git`.
  - Revision: `0292c62e267a8b9cbc0d9dc580d80c549701661c`.
  - Reused verified read-only candidate: `/Users/lief123/harmonyos-learning/projects/android-to-harmony-form-candidates-20260803/sources/ekspensify-android`.
  - Candidate pre/post content archive SHA-256: `69cb877f100b83b0a8c20a62e9d8cff3e3694999384487727eff65d9b31cfdef`; candidate remained clean at the fixed revision.
  - Separate existing source began at wrong HEAD `5a17334fee7dc37832432f49a2a34894abcaf366`, recorded `git fetch origin 0292c62e267a8b9cbc0d9dc580d80c549701661c`, detached-checkout, and final verification at the fixed revision before `01-start`.
  - Plan identity: `261315eb1d0fb7dcccdca0167fae824363430342eb2f1da3843ca3073398d2a6`.
  - Frozen task-state identity: `1cbe907b7ad4e80b2117fa32148546c036aac7cadb526f24accad0328674adec`.
  - Portable Skill-tree identity: `67ca0525163cec7b73299868009d305cc8d02df53fa3b93497e6bb5d12deefa9`, `70` files.
  - Evidence manifest verification: PASS, projects `[banking, ekspensify]`, `126` files, tree digest `973e62152fcc3b5e99f9b3f0ed1ebf8dae87a1aafbcb0c4b5a956623a7a00304`.
- Affected regressions:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v` — PASS, `362/362`.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v` — PASS, `33/33`.
  - `node --test --experimental-strip-types tests/lib/hash-skill-tree.test.mjs tests/lib/cmd-state.test.mjs tests/lib/infer-workflow.test.mjs tests/integration/android-harmony-benchmark.test.mjs` — PASS, `55/55`.
  - `python3 -m py_compile skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py skills/migrate-android-compose-to-harmony/scripts/migration_agent.py` — PASS.
- Scope guard:
  - Historical `changes/android-to-harmony-54-benchmark/evidence/` remained read-only.
  - Banking project evidence was preserved except for the strictly required content-bound central Skill-reference digest refresh; the complete two-project tree reverified afterward.
  - Tickets 04 and 05 were not modified.
- Ticket-local two-axis review against fixed point `2e394b6d6131eee9ce88d651130414b0263a8e8d`:
  - Standards/code quality initially found three Minor test-maintainability issues. Shared Git/evidence fixtures were extracted and the two-project manifest tests were renamed to match their scope.
  - Spec/acceptance/evidence initially found that the Ekspensify URL was fixed but its revision was not enforced, and that the ticket had not reached its terminal local status. The exact revision guard now fails closed under its own RED/GREEN test, and this ticket is marked `completed`.
  - Post-repair Standards re-review: PASS, no remaining documented-standard violation or actionable smell.
  - Post-repair Spec/acceptance/evidence re-review: PASS, no remaining missing requirement, scope creep, or incorrect behavior.
