# Core Profile preflight

Every successful FIR2IR/lowering session scans resolved `IrCall` nodes before
target generation. The scan is read-only: it does not select adapters, rewrite
IR or decide that an unsupported operation is safe. The normal language or
Compose generator remains authoritative and still fails closed.

Pass `--preflight-out /fresh/path/core-profile.json` to retain the scan. The
Gradle project entry accepts and forwards the same option. Existing report paths
are rejected before compilation. The CLI always runs the scan; without the
option it returns only `preflightCallCount` in its result JSON.

Each call record contains:

- `category`: `language`, `stdlib`, `compose`, `platform`, or
  `project_dependency`;
- `resolvedSymbol`: the resolved owner name plus parameter and result types, so
  overloads are not collapsed by their display name;
- `expectedTargetType`: the typed ETS result. If no ETS type exists, the report
  says `unsupported(<resolved Kotlin type>)` and generation continues to the
  more specific source-linked rejection;
- `source`: offsets plus 1-based line/column and exclusive end position, using
  the same BOM/newline/UTF-16 rules as compiler diagnostics;
- `argumentResolutions`: omitted source defaults and empty varargs. A Kotlin
  source default is preserved semantics, not a degradation or permission to
  invent a target fallback.

Category precedence is source ownership first, then known namespaces. A call to
a source declaration is `language`; resolved external Kotlin declarations are
`stdlib`; Compose packages are `compose`; Java/Android/AndroidX/KotlinX/Coil/OHOS
packages are `platform`; remaining external resolved declarations are
`project_dependency`. Classification does not imply support.

## No-silent-fallback gate

The existing `DiagnosticSink.omitUi` remains the only approved omission route:
it records capability, action, impact and source before marking IR omitted.
Unknown values and calls continue to throw `UNSUPPORTED`.

The shared core now also rejects:

- an adapter claiming a statement or UI call with an empty result;
- an emitted empty `@Builder`/`build` function without a degradation or
  unsupported record;
- an omitted UI set without a degradation record.

These checks live in the shared contract/CLI, not in Compose controls, KLIB
loading or page-specific code. Source defaults remain visible in preflight and
keep their normal Kotlin semantics. No target default is authorized merely by
appearing in the report.

## Verification

`node tools/kotlin-ets/tests/preflight/run.mjs` uses actual Kotlin compilation:

- `CoreProfile.kt` proves language/stdlib classification, a resolved source
  default, expected target types and exact 1-based locations;
- `Platform.kt` and a separately compiled `Dependency.kt` prove platform and
  project-dependency classification, source-linked failure and no target;
- the existing nontrivial `ComposableValues.kt` proves Compose classification
  with the real dependency classpath;
- `EmptyUi.kt` proves an empty builder is rejected at its source declaration.

The run retains commands, stdout/stderr, preflight JSON and outputs under
`tests/preflight/.work/run-*`. This is compiler/host evidence. It is not KLIB,
ArkTS SDK or device acceptance.

Final verification evidence:

| Coverage | Result | Evidence |
| --- | --- | --- |
| RED: option absent | `--preflight-out` rejected as unknown | `tests/preflight/.work/run-llBELG` |
| RED: empty UI | empty `@Builder` was generated silently | `tests/preflight/.work/run-ZdiDg6` |
| Core Profile and no-silent-fallback | five categories, source defaults, types, locations, negative no-target cases | `tests/preflight/.work/run-iZKbaj` |
| Full language suite | pass | `tests/language/.work/run-01EAKd` |
| Module suite | 44 JVM/module cases pass | `tests/modules/.work/run-KWHnWz` |
| Typed backend suite | pass | `tests/preflight/.work/kotlin-ets-backend-tests.SCdkSg` |
| Project launcher | 15 tests pass | `node --test tests/project-inputs/launcher.test.mjs` |
| CLI diagnostic integration | 6 tests pass | `python3 -m unittest tools.kotlin-ets.tests.integration.test_cli` |
| Compose degradation regression | pass | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-degradation-PJ4eY6` |
