# 05 — Close the portable three-project evidence tree

**What to build:** Aggregate the verified Banking, Ekspensify, and Buckwheat tracers into one portable, content-bound evidence tree and demonstrate that the complete executable-planning foundation remains green through default repository tests.

**Blocked by:** 03 — Prove reusable capture with Ekspensify; 04 — Prove clean acquisition with Buckwheat.

**Status:** completed

- [x] One manifest enumerates every required evidence family and all three fixed public-project subtrees.
- [x] Verification rejects missing membership, unexpected artifacts, central Skill-identity drift, project artifact tampering, and historical-evidence substitution.
- [x] Optional canonical-cache comparison remains opt-in and default tests are repository-relative.
- [x] All affected Python and Node focused tests, compilation checks, and full regressions pass on the frozen byte set.
- [x] The final ticket records remaining real-environment limits without equating compilation or static evidence with business/UI fidelity.

## Evidence

- Production and test seams:
  - `skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py`
  - `skills/migrate-android-compose-to-harmony/scripts/test_tools.py`
  - `skills/workflow-start/SKILL.md`
  - `skills/build-executor/SKILL.md`
  - `scripts/infer-workflow.mjs`
  - `scripts/lib/cmd-state.mjs`
  - `scripts/lib/state-loader.mjs`
  - `tests/lib/cmd-install-workbuddy.test.mjs`
  - `tests/lib/infer-workflow.test.mjs`
  - `tests/lib/cmd-state.test.mjs`
  - `tests/lib/state-loader.test.mjs`
  - `tests/lib/vscode-agent-plugin.test.mjs`
  - `tests/lib/hash-skill-tree.test.mjs`
  - `changes/android-to-harmony-execution-plan-dag/evidence/execution-plan-dag-v1/evidence-tree-manifest.json`
- Focused RED:
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_execution_plan_evidence_tree_manifest_lists_complete_portable_membership MigrationToolTests.test_execution_plan_evidence_tree_manifest_rejects_historical_skill_identity_substitution` — expected failure, `2/2`: the first case raised `KeyError: 'required_families'`; the second showed that a consistently rebound historical/stale central Skill identity could still be newly frozen.
- Focused GREEN on the identical seam after the minimum implementation:
  - The exact RED command, before the historical case received its final current-drift name — PASS, `2/2`.
  - Final focused verifier command with explicit membership, all-project tamper, and current-drift/historical-substitution coverage — PASS, `3/3`:
    `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v MigrationToolTests.test_execution_plan_evidence_tree_manifest_lists_complete_portable_membership MigrationToolTests.test_execution_plan_evidence_tree_manifest_rejects_missing_extra_and_tampered_artifacts MigrationToolTests.test_execution_plan_evidence_tree_manifest_rejects_current_skill_drift_and_historical_substitution`.
- Focused checked-capture compatibility:
  - The ten Banking, Ekspensify, and Buckwheat success/fail-closed capture cases covering reuse, wrong-HEAD repair, clean acquisition, fixed revisions, wrong remotes, final revision mismatch, and complete Banking freeze — PASS, `10/10`.
- Selective-candidate default-test repair:
  - Focused RED reconstructed from fixed point `0bf813f` plus the original nine Ticket 05 paths: `node --test tests/lib/cmd-install-workbuddy.test.mjs tests/lib/vscode-agent-plugin.test.mjs` — FAIL, `25/27`. The committed Skill count was `14` while the WorkBuddy test expected `13`; the workflow capability test also required the missing optional Android-to-Harmony routing and build-executor handoff.
  - Minimum repair: accept the 14-Skill inventory and assert the migration Skill by name; add only the matching optional-capability detection/persistence guidance to `workflow-start` and scoped migration-Skill handoff to `build-executor`. Accepted capability assertions were preserved unchanged.
  - Identical focused GREEN in the same isolated reconstruction — PASS, `27/27`.
- Normal workflow-entry runtime repair:
  - Direct-command RED against fixed point `0bf813f` plus the 12-path candidate: `node scripts/spec-superflow.mjs infer-workflow <fixture>` returned `mode: "hotfix"` with no `capability`; `node scripts/spec-superflow.mjs state set <fixture> capability android-to-harmony` exited `1` with `Field 'capability' is not settable`; the following state get returned `null`.
  - Focused runtime RED with the six authorized tests/runtime paths split test-first: `node --test tests/lib/infer-workflow.test.mjs tests/lib/cmd-state.test.mjs tests/lib/state-loader.test.mjs` — FAIL, `48/56`; one state-command case, four capability-inference cases, and three state default/write/round-trip assertions failed.
  - Minimum implementation: infer the scoped capability only when Android source, Harmony target, and migration intent are all present; make `capability` settable and round-trip it through the state loader; consume one inference result for both mode and capability. Ordinary Android-only and Harmony-only proposals remain unaffected.
  - Identical direct-command GREEN on the same fixture: inference returned `mode: "full"`, `capability: "android-to-harmony"`, and `explicit: false`; state set/get exited `0` and returned `android-to-harmony`. The identical focused runtime suite passed `56/56`.
  - Final normal-entry RED against that frozen runtime: `node --test tests/lib/infer-workflow.test.mjs` — FAIL, `15/17`. A fresh DP-0-only migration had no capability, and an explicit migration `hotfix` was not forced to `full`; the existing ordinary non-migration explicit-hotfix case remained green.
  - Minimum final repair: include `dp_0_decisions` in the same capability input as available proposal/tasks and apply the `android-to-harmony` full-workflow override before explicit/inferred fast-path selection. The identical focused command passed `17/17`; the complete runtime focus passed `58/58`.
  - Final direct-command GREEN on a DP-0-only fixture whose current workflow was explicit `hotfix`: inference returned `mode: "full"`, `capability: "android-to-harmony"`, and `explicit: false`; state set/get returned `android-to-harmony`. Ordinary non-migration explicit `hotfix` remained `hotfix`.
- Portable Skill identity:
  - Current bundled Skill manifest: `70` files, tree SHA-256 `77c257a61cc2437943bdf4d1a19a4a9bc47e88a3e6a29745d8447fdf8091de59`.
  - Central manifest content SHA-256: `cc27df875a204ae71f4d267c23764b8f7471ff03e87152b550e3eba38527317d`.
  - Central binding content SHA-256: `7a6fa628fc9a7eed157497ced7fde9f76b1a4da9583d38be17759a237b32739e`.
  - Banking, Ekspensify, and Buckwheat references all bind those exact central artifacts through repository-relative paths.
  - `node --test tests/lib/hash-skill-tree.test.mjs --test-name-pattern="canonical skill tree manifest is path-independent|digest binding artifact ties vendored skill to the canonical tree hash|optional canonical cache comparison is skipped unless explicitly configured"` — PASS, `3/3`; canonical-cache comparison remained an explicit environment-variable opt-in.
- Authoritative three-project closure:
  - Manifest projects: `[banking, ekspensify, buckwheat]`.
  - Every project explicitly enumerates contract, capability graph, fact packs, review queue, gate report, immutable execution plan, frozen task state, command stdout/stderr/logs, exit results, test logs, source identity, and central Skill-identity reference families.
  - Final manifest verification — PASS, `190` files, tree SHA-256 `b02973a30771f8f16989593c45dd27780816b7988cbec4d1ece4d0a83b04997a`.
- Affected regressions on the frozen bytes:
  - `python3 -m py_compile skills/migrate-android-compose-to-harmony/scripts/build_capability_graph.py skills/migrate-android-compose-to-harmony/scripts/aggregate_gate_evidence.py skills/migrate-android-compose-to-harmony/scripts/build_execution_plan.py skills/migrate-android-compose-to-harmony/scripts/hash_evidence_tree.py skills/migrate-android-compose-to-harmony/scripts/capture_execution_plan_regressions.py skills/migrate-android-compose-to-harmony/scripts/migration_agent.py` — PASS.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_tools.py -v` — PASS, `364/364`.
  - `env -u TMPDIR python3 skills/migrate-android-compose-to-harmony/scripts/test_orchestrator.py -v` — PASS, `37/37`.
  - Exact affected Node command in an isolated reconstruction: `node --test --experimental-strip-types tests/lib/hash-skill-tree.test.mjs tests/lib/cmd-state.test.mjs tests/lib/infer-workflow.test.mjs tests/lib/cmd-install-workbuddy.test.mjs tests/lib/vscode-agent-plugin.test.mjs tests/lib/state-loader.test.mjs` — PASS, `88/88`.
  - Repository defaults in an isolated reconstruction of fixed point `0bf813f` plus only the final selective Ticket 05 candidate, after `npm ci`: `npm run build && npm test` — PASS, TypeScript compilation plus `507/507` tests.
  - The same default command in the live dirty worktree is not authoritative for this ticket: its `npm pack --json` subprocess scans the unrelated 603 MB untracked `artifacts/` tree and overflows the pre-existing fixed child-process buffer. The isolated selective reconstruction excludes only files outside the candidate; no unrelated artifact was modified or removed.
- Remaining real-environment limits:
  - This closure proves static planning/evidence integrity and Python/TypeScript compilation only. It does not prove a Harmony SDK build, emulator/device runtime, business-flow completion, or pixel/UI fidelity; none of those real-environment checks was executed for this ticket.
- Final Matt two-axis review against fixed point `0bf813f`:
  - Standards — PASS. The reviewer found the final 18-path candidate surgical, executable, internally consistent, and free of documented-standard violations or actionable Fowler smells; `git diff --check` passed.
  - Spec/acceptance/evidence — PASS. The reviewer independently reproduced runtime `58/58`, affected Node `88/88`, defaults `507/507`, focused evidence `3/3`, and authoritative verification at `190` files with tree SHA-256 `b02973a30771f8f16989593c45dd27780816b7988cbec4d1ece4d0a83b04997a`; no missing, partial, scope-creep, or implemented-looking-wrong requirement remained.
- Scope guard:
  - Historical `changes/android-to-harmony-54-benchmark/evidence/` remained read-only and was not staged.
  - `tests/integration/android-harmony-benchmark.test.mjs` was not included in the exact-candidate affected count: it reads the untracked historical benchmark fixture tree, which is absent from fixed point and unchanged by Ticket 05. A preliminary seven-file reconstruction therefore reported `88/92`, with all four failures being missing historical fixture files; no historical bytes were absorbed to manufacture a pass.
  - Tickets 01–04 and their historical evidence were not reopened. Banking, Ekspensify, and Buckwheat changed only for the required current central-reference refresh.
  - Management explicitly added the minimum default-test closure hunks in `cmd-install-workbuddy.test.mjs`, `workflow-start/SKILL.md`, and `build-executor/SKILL.md` to Ticket 05 scope after the first Spec review. No other dirty hunk was absorbed.
  - After the second two-axis review, management explicitly added the minimum matching capability runtime and tests in `infer-workflow.mjs`, `cmd-state.mjs`, `state-loader.mjs`, and their three focused test files. No package/plugin metadata or unrelated dirty hunk was required.
  - After the third review, management explicitly authorized DP-0-only capability detection and migration override of explicit/inferred fast paths within the same `infer-workflow.mjs` and focused test paths. No additional candidate path was required.
