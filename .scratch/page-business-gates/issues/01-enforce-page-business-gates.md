# Enforce page business gates

Status: completed

## Work

1. Add public CLI RED tests for source and target behavior gates.
2. Reuse the generated effective page scope with the existing behavior validator.
3. Report source readiness and page-scoped business verification without claiming application
   completion.
4. Run focused and related regression suites.

## Constraints

- Do not change UI output or invoke device tooling.
- Do not add a behavior schema, state machine, or analyzer.
- Preserve all pre-existing working-tree changes and cache directories.

## Evidence

- RED: missing page behavior specification returned the old successful AI handoff instead of
  failing before target creation.
- GREEN: `test_page_commands` passed 32 tests in 167.733 seconds.
- Related regression: behavior contract, collection, source closure, effective closure, existing
  target, and source dependency suites passed 75 tests in 86.421 seconds.
- `git diff --check` passed.
- No device tooling, UI generator, commit, push, tag, or release was run.

## Entry-to-evidence repair — 2026-10-08

Implemented directly in the current task at the user's request; independent review is deferred.
Both page and project entry points now use `migration_agent.build_run_state` for the existing
run record. The evidence runner accepts referenced snapshot/contract locations while retaining
manifest/path identity, recorded hashes, contract-owner, external target ownership, copied-contract
and batch checks. Page runs return `evidence_run_root`; no extra initialization command is needed.
Successful handoffs clear `failed_stage`.

Python: `/opt/homebrew/opt/python@3.14/bin/python3.14` (3.14.5).
Commands ran from the skill's `scripts/` directory with `PYTHONDONTWRITEBYTECODE=1`.

- RED: `-m unittest test_page_commands.PageCommandsTest.test_default_command_accepts_current_page_behavior_specification test_page_commands.PageCommandsTest.test_page_business_completion_accepts_current_attested_scenario_evidence`
  failed both tests in 9.537s: residual failed_stage and `owned agent state is missing`.
- GREEN/regression: `-m unittest test_page_commands test_behavior_contract_v2 test_behavior_collection test_behavior_source_closure test_effective_page_closure test_existing_target test_source_dependencies`
  passed 108/108 in 263.286s, exit 0.
- Evidence/project regression: `-m unittest test_evidence_runner test_orchestrator.MigrationAgentTests.test_start_creates_owned_resumable_run test_orchestrator.MigrationAgentTests.test_start_resume_and_status_preserve_execution_plan_identity test_orchestrator.MigrationAgentTests.test_resume_rejects_tampered_snapshot_without_overwriting_target test_orchestrator.MigrationAgentTests.test_resume_rejects_missing_contract`
  passed 32/32 in 13.347s, exit 0.

The positive test starts with the actual page CLI-created target, then invokes the real evidence
runner and page target validation. Only the external HDC executable/HAP inputs are controlled test
fixtures; no run ownership is preconstructed. Wrong target identity, stale contract hash and target
source changed after signed evidence capture are rejected. This proves the command integration,
not a newly migrated page's device or visual correctness. No emulator/device was accessed and no
commit or push was performed.
