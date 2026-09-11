# Composable Value Classification Verification

## Frozen Candidate

- Date: 2026-09-11.
- Base commit: `3f3846f`.
- Candidate v5 identity: `18971ab0c24d686ac9970936bebb582829d843d576584666d0270a03783bc311`.
- Local frozen tree: `/tmp/composable-values-20260911/candidate-v5`.
- Native evidence: `/tmp/composable-values-20260911/evidence.json` and `build.log`.

## Regression Tests

Run from the frozen skill's `scripts` directory:

```sh
python3 -m unittest test_composable_values test_page_roots test_source_dependencies test_resource_arguments test_scoped_source_dependencies test_source_callables test_source_symbol_performance test_contract_symbol_performance test_api_adapters test_source_modules test_business_components test_component_interfaces test_component_ui_states test_keyed_resources test_existing_target test_custom_target_paths test_page_commands test_ui_migration_architecture test_component_discovery
```

Result: 215 tests passed in 191.052 seconds. Coverage includes inferred value
helpers, real UI effects, deferred and invoked lambdas/references, unknown
invocation diagnostics across files, exact source-symbol adapter lookup,
overload ambiguity, and class-member shadowing.

An additional `test_common_page_controls` run had 17 passes and one failure:
`test_indeterminate_progress_cannot_silently_be_zero` expected a failing gate but
received `pass`. The same test was independently reproduced on a clean archive
of base `3f3846f` with the identical assertion failure. This existing issue is
outside the getter/UI-classification change; the entire repository suite is not
claimed green.

## Independent Review

The persistent read-only reviewer approved frozen v5 with no findings. It
verified all 367 manifest hashes and reran tests in a separate source copy without
bytecode caches: 32 callable/value tests, 89 adjacent regression tests, and 14
symbol/scoped-dependency tests passed (these sets overlap other reported tests).
Additional probes checked cross-file unknown effects, resolved references,
deferred lambdas, string callables and cache isolation between callers.

## Full Page And Native Build

The synthetic fixture uses separate Page, Banner and Copy Kotlin files and a
hash-pinned project adapter. The public migration CLI reports
`generation_complete=true`, `verdict=pass`, and no unresolved items for this
fixture. Adapter results for distinct keys are consumed through Banner/Label
parameters and by the native button Text. No getter Builder or Copy.ets is emitted.

The generated page was compiled with the installed ArkTS SDK:

```sh
/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw assembleHap --mode module -p module=entry@default -p product=default --no-daemon
```

Exit code: 0. Build elapsed time: 7.069 seconds. Generated ETS was not edited;
its hashes before and after compilation match:

| File | SHA-256 |
| --- | --- |
| Page.ets | `88b9e13ffec526fa2d05d8364091cb8cf8c9e65d781b5170af35a52fb789472e` |
| Banner.ets | `7fbfab213208ec1c7f7351b06a47b7107b87a4ffe0ad6d670b72482853218866` |

ProjectCopyBridge.ets and the native host are fixture-owned, not generator output.
The migration result's `build_verified` remains false because compilation was a
separate verification command, not a mutation of the migration result.

## Limits

- No company source files were used or exported. This is synthetic local coverage.
- The HAP is unsigned; device installation, visual fidelity and company-page
  acceptance were not performed.
- This is bounded source/effect analysis, not full Kotlin inference or arbitrary
  business-logic translation. Unknown effects remain diagnostic.
- A separate fixture experiment with an explicit Button child text-color override
  exposed an existing target-consumption diagnostic. This change does not claim
  to fix that issue; the accepted fixture uses explicit inherited theme colors.
- Re-run source-page and downstream projection/generation for existing pages;
  previously misclassified page JSON cannot be repaired by compiling ETS alone.
