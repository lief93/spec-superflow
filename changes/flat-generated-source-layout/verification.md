# Flat Source Layout Verification

## Candidate

- Base: `f93ab7a` on `andorid-to-hormony`.
- Frozen tree: `/tmp/flat-source-20260911/candidate-v1`.
- Identity: `df0a8b587ac4b6e44c8383635d85dcc0293f1c9f9a3016af8255252eabb70d35`.
- The frozen `candidate.json` records every skill/contract file hash.

## Automated Regression

Run from `skills/migrate-android-compose-to-harmony/scripts`:

```sh
python3 -m unittest test_source_modules test_business_components test_best_effort_reuse_page test_page_commands
python3 -m unittest test_component_interfaces test_component_ui_states test_component_reuse test_custom_target_paths test_existing_target test_pager test_pager_component_states test_conditional_ui_preview test_component_output_roots
```

- First command: 50 tests passed, 147.449 seconds.
- Second command: 85 tests passed, 41.248 seconds.
- An earlier command mistyped two test module names; that invocation failed to
  import those modules. The corrected commands above both passed.
- Source-module coverage includes custom output roots, flat basenames, anonymous
  slots, typed Scaffold context, cross-file imports, filename collision rejection,
  legacy nested-output retirement, user-file retention, edited-output rejection,
  shared ownership, and write-transaction rollback.

## Native SDK

Executed `/tmp/flat-source-20260911/verify.py` against the frozen candidate.
Two complete CLI pipelines use the multi-source `SourceModulesCommandsTest`
fixtures: a Shell content slot with Scaffold state, and the complete-style variant.
Both emit only `Profile.ets`, `Header.ets`, and `Shell.ets` directly under the output
root, with no `_migration`, `Builders.ets`, or `Runtime.ets` output.

- DevEco Studio SDK: `/Applications/DevEco-Studio.app/Contents/sdk`.
- Command: `hvigorw assembleHap --mode module -p module=entry@default -p product=default --no-daemon`.
- Both builds exited 0. Generated ETS hashes were identical before/after build.
- Evidence: `/tmp/flat-source-20260911/evidence.json` and `build-slots.log`,
  `build-complete.log` in the same directory.
- Existing fixture warnings concern EntryAbility exception handling, cached
  dependencies, and absent signing configuration. No device installation or
  screenshot-equivalence claim is made.

## Delivery Boundary

Existing source/version JSON and contract can be reused for this output-only
change. Regenerate ArkUI with the original target, page JSON, output directory,
and ownership metadata; use `--force` only for unchanged owned output. Old nested
entry filenames move to the output root; external host imports to their previous
locations need updating. Shared output and user files are not deleted.

## Independent Review

Persistent reviewer task `019f9f14-8207-7d60-9745-d8a2e28d7be8`, turn
`01a08e50-6c28-7090-b3ad-832f5eb576f7`: **Approved**. Independently ran 126
related regressions (192.562s), the public CLI basename-collision negative case,
both native fixtures, and an additional two-source-module shared-slot native
fixture. All passed. The eight changed skill files matched the applied patch
byte-for-byte.

One low-severity evidence-hygiene finding: verification left unmanifested Python
bytecode in candidate-v1 and did not record its identity in the build report.
The final clean copy is `/tmp/flat-source-20260911/candidate-v2`; source code is
unchanged from the reviewed candidate. The verifier now disables bytecode writes,
rejects unmanifested files, validates hashes before/after verification, and binds
each evidence record to its candidate identity. Its `candidate.json` records the
final identity, including this verification note.
