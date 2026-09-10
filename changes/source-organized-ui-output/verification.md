# Verification: source-organized UI output

Date: 2026-09-11
Base: f30a209
Independent review: Approved; both first-round findings closed.
Frozen candidate identity:
`a36bd69bb12d383754c1f464177891e96341d14fb9bab050822bc3d18323f10c`

## Regression

From `skills/migrate-android-compose-to-harmony/scripts`:

```sh
python3 -m unittest test_source_modules test_existing_target test_custom_target_paths test_page_commands test_business_components test_component_interfaces test_component_ui_states test_ui_migration_architecture test_component_discovery
```

112 tests passed in 174.685 seconds. `git diff --check` passed.
Coverage includes source-relative files, nested/repeated builders, parameter names,
typed runtime context, slot dispatch, import relocation, existing target paths,
unowned/edited/shared output protection, regeneration, and transactional faults.
The reviewer independently passed five focused tests and additional name-collision
probes after independently running 79 impact tests on the first candidate.

## Native SDK

Synthetic Android sources were passed through snapshot, contract, source-page,
version JSON and ArkUI generation. The emitted modules were compiled unchanged
with DevEco SDK 6.0.0(20), `assembleHap`. Only the host entry imports and local
dependency installation were prepared outside the generator. No generated ETS was
patched. Candidate and output hashes were checked against the evidence.

- Explicit-style page: `generation_complete=true`, `verdict=pass`, unresolved 0;
  native build successful in 5.572 seconds.
- Compose callback/slot compatibility page: native build successful in 5.716
  seconds; remains partial due to the existing annotated callback mapping and
  default-style diagnostics. This is not claimed as complete migration.

Both pages include nested/repeated Header and Caption calls, a Scaffold Shell,
and Label(renderLabel), exercising the helper-name collision case.

```text
generated/screens/Profile.ets
generated/ui/Header.ets
generated/ui/Shell.ets
generated/_migration/<page-identity>/Builders.ets
generated/_migration/<page-identity>/Runtime.ets
```

Local reproducibility/evidence bundle:
`/tmp/source-organized-output-20260911/`

Files: `verify.py`, `complete-evidence.json`, `complete-build.log`,
`slots-evidence.json`, `slots-build.log`, `review-candidate-v3/candidate.json`.
The verification script takes the frozen candidate directory, with `--complete`
for the complete fixture. Native dependencies were copied from a prior local SDK
fixture; the ordinary unittest command does not depend on that fixture.

## Review Fixes And Limits

Backup cleanup now happens after the transaction commit point. A cleanup error
cannot trigger partial rollback or remove committed modules. A failed write still
restores the old set. Leftover backups after cleanup failure require inspection
before another generation run.

Global builder names avoid source bindings, imports and native calls; only
collisions receive a suffix, recorded in `source_organization.renamed_methods`.
The ArkTS SDK parser is required. This preserves supported selected-page UI
organization; it does not synthesize arbitrary business methods or domain types.
Compilation does not establish device rendering, visual parity or business parity.
No company files were requested or exported from the intranet.
