# Core Profile preflight

Every successful FIR2IR session scans resolved `IrCall` nodes before target
generation. The scan is read-only: it does not select adapters, rewrite IR or
decide that an unsupported operation is safe. The normal language or Compose
generator remains authoritative and still fails closed. If generation rejects
a node, the retained report is annotated with that first observed failure before
the CLI returns it.

Pass `--preflight-out /fresh/path/core-profile.json` to retain the scan. The
Gradle project entry accepts and forwards the same option. Existing report paths
are rejected before compilation. The CLI always runs the scan; without the
option it returns only `preflightCallCount` in its result JSON.

Each call record contains:

- `category`: `language_semantics`, `standard_library`,
  `neutral_compose_widget`, `modifier`, `resources`, or
  `project_dependencies`;
- `resolvedSymbol`: the resolved owner name plus parameter and result types, so
  overloads are not collapsed by their display name;
- `expectedTargetType`: the typed ETS result, or `null` when type lowering is the
  first unsupported node;
- `source`: offsets plus 1-based line/column and exclusive end position, using
  the same BOM/newline/UTF-16 rules as compiler diagnostics;
- `argumentResolutions`: omitted source defaults and empty varargs. A Kotlin
  source default is preserved semantics, not a degradation or permission to
  invent a target fallback;
- `finalRecognizedNode`: the resolved call, promoted to `typed_call` when its
  result has a target type, with the same exact source location;
- `firstUnsupportedNode`: the first source-linked type or generation failure
  within that call, including its resolved field/object/call symbol when one is
  available, otherwise `null`. A type diagnostic without its own compiler
  source offset is anchored to the containing resolved call;
- `responsibleModule`: the production lowering or adapter source file that owns
  the category. Resource calls identify `StringResources.kt` or
  `ImageResources.kt` separately.

The top-level `coverage` object repeats all six groups, including empty groups.
`recognized` counts calls whose target type was recognized and which do not own
the first observed generation failure. `unsupported` counts recorded failures;
`percentage` is `recognized / total`, or `null` when the group has no calls.
This is coverage of the attempted entry, not a claim that every argument shape
or runtime behavior for the same API is supported.

Category precedence is source ownership first, then resource and Modifier
semantics, Compose widgets, external Kotlin declarations, and other project or
platform dependencies. Classification does not imply support.

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
- `Platform.kt` and a separately compiled `Dependency.kt` prove project-
  dependency classification, source-linked failure and no target;
- the existing nontrivial `ComposableValues.kt` proves Compose classification
  with the real dependency classpath;
- `Coverage.kt` proves neutral widget, Modifier and resource grouping and
  attaches the first resource failure to its containing call;
- `EmptyUi.kt` proves an empty builder is rejected at its source declaration.

The run retains commands, stdout/stderr, preflight JSON and outputs under
`tests/preflight/.work/run-*`. This is compiler/host evidence. It is not KLIB,
ArkTS SDK or device acceptance.

The pinned public-project baseline is reproducible from an existing checkout
whose object database contains the selected revision:

```bash
node tools/kotlin-ets/tests/preflight/mars-photos.mjs \
  /absolute/path/to/basic-android-kotlin-compose-training-mars-photos
```

The runner creates a detached worktree at Google Mars Photos revision
`8399c839ce5f4be66e0ae1103ed0e04121c97fe4`, uses the production Gradle input
collector offline, and runs the production Core Profile CLI for
`com.example.marsphotos.ui.screens.LoadingScreen`. It records commands, logs,
the schema-2 report and `public-project-baseline.json` under
`tests/preflight/.work/mars-photos-*`.

The accepted baseline has two neutral widget calls at 100%, one Modifier call at
100%, and two resource calls at 50%. Language semantics, standard library and
project dependency have no calls in this selected entry and therefore report a
`null` percentage. The first conversion gap is
`R.drawable.loading_img` at line 73, column 46, owned by
`ImageResources.kt`; no target is emitted. The public project pins Kotlin 2.1.0
while the production project launcher requires 2.1.20, so the runner records
that version mismatch as a separate P0 project-dependency gap and uses the fixed
2.1.20 CLI only for the coverage attempt. It does not claim project generation
compatibility.

A second public-project baseline exercises a broader dependency graph:

```bash
node tools/kotlin-ets/tests/preflight/architecture-samples.mjs \
  /absolute/path/to/architecture-samples
```

The runner creates a detached worktree at Android `architecture-samples`
revision `ee66e1526b84c026615df032c705842b7d2a521f`, formally collects the
`:app:compileDebugKotlin` inputs offline, and runs the fixed 2.1.20 Core Profile
CLI for
`com.example.android.architecture.blueprints.todoapp.statistics.StatisticsScreen`.
The collected project inputs contain 85 Kotlin sources and 89 classpath entries.
The report contains 124 resolved calls with this baseline:

| Category | Total | Recognized | Unsupported | Coverage |
| --- | ---: | ---: | ---: | ---: |
| Language semantics | 32 | 31 | 1 | 96.87% |
| Standard library | 51 | 51 | 0 | 100% |
| Neutral Compose widget | 15 | 12 | 3 | 80% |
| Modifier | 7 | 7 | 0 | 100% |
| Resources | 6 | 6 | 0 | 100% |
| Project dependencies | 13 | 7 | 6 | 53.84% |

All calls retain a 1-based source span, `finalRecognizedNode`, optional
`firstUnsupportedNode`, and `responsibleModule`. The generated
`public-project-baseline.json` preserves all ten unsupported call records. The
earliest preflight capability gap is `remember` returning
`SnackbarHostState` at line 48, column 44. The actual backend attempt fails
closed earlier, at the `openDrawer` entry parameter on line 45, column 5,
because it has no source default; no ETS target is emitted. The baseline records
these as separate facts.

This project pins Kotlin 2.1.10, so production project generation rejects its
compiler environment before frontend execution. The fixed 2.1.20 direct CLI run
measures only compiler/host Core Profile coverage over the collected JVM
classpath. Its 100% standard-library result establishes recognition for the
calls in this entry; it does not establish target KLIB body availability,
ArkTS SDK compatibility, or device behavior.

Final verification evidence:

| Coverage | Result | Evidence |
| --- | --- | --- |
| RED: option absent | `--preflight-out` rejected as unknown | `tests/preflight/.work/run-llBELG` |
| RED: empty UI | empty `@Builder` was generated silently | `tests/preflight/.work/run-ZdiDg6` |
| Core Profile and no-silent-fallback | six groups, ownership, source defaults, locations and negative no-target cases | `tests/preflight/.work/run-gcipOx` |
| Mars Photos public baseline | widget 100%, Modifier 100%, resources 50%; two explicit P0 gaps; no target | `tests/preflight/.work/mars-photos-Lh41tH` |
| Architecture Samples public baseline | 124 calls across all six groups; ten explicit unsupported calls; no target | `tests/preflight/.work/architecture-samples-35FMMz` |
| Full language suite | pass | `tests/language/.work/run-01EAKd` |
| Module suite | 44 JVM/module cases pass | `tests/modules/.work/run-KWHnWz` |
| Typed backend suite | pass | `tests/preflight/.work/kotlin-ets-backend-tests.SCdkSg` |
| Project launcher | 15 tests pass | `node --test tests/project-inputs/launcher.test.mjs` |
| CLI diagnostic integration | 6 tests pass | `python3 -m unittest tools.kotlin-ets.tests.integration.test_cli` |
| Compose degradation regression | pass | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-degradation-PJ4eY6` |
