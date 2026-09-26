# IrToEts split plan

This batch adds the IR → `EtsProgram` seam. It does not rewrite
`LanguageLowering.kt`.

## Target structure (Kotlin/JS 2.1.20 analogue)

```text
ETS-ready Kotlin IR
  → IrModuleToEts
  → IrFileToEts
  → IrClassToEts / IrFunctionToEts / IrDeclarationToEts
  → IrStatementToEts / IrExpressionToEts / IrTypeToEts
  → EtsProgram
```

Official JS visitors (`IrModuleToJsTransformer`, `IrFunctionToJsTransformer`,
`IrElementToJsExpressionTransformer`, `IrElementToJsStatementTransformer`)
return JS AST nodes and assume prior IR-to-IR. ETS keeps `EtsProgram` and
official `Ir*` input. There is no `KotlinEtsIr`.

## Current seam

`src/lower/IrToEts.kt` is the only production entry from `EtsBackend.lower`.
Each visitor delegates to the existing `Language` implementation
(`LanguageLowering`). File initialization and top-level properties stay on
their existing helpers (`lowerFileInitialization`, `lowerTopLevelProperty`)
because those are target-declaration assembly, not Kotlin semantic lowering.

Invariant: IrToEts must not do high-level Kotlin semantic lowering.

- `kotlin.Int.div` becoming an ETS runtime intrinsic belongs in an IR-to-IR
  phase (future) or today's `CallRule.lower`. IrToEts maps the already-present
  `IrCall`.
- Inherited defaults, local lifting, inner outer-this, constructor dispatch,
  for-loops, string concat, nullability casts, and generic-bound helpers
  already ran in `EtsLoweringPhases`.
- Ordinary function defaults remain `EtsParameter.defaultValue` /
  `EtsUndefined` at this boundary.

## Planned file split (later batches)

Move bodies out of `LanguageLowering` without changing contracts:

| File | Owns | Must not own |
| --- | --- | --- |
| `IrModuleToEts.kt` | Module list → files, adapter linking | Phase order |
| `IrFileToEts.kt` | Top-level declaration dispatch, file init | CallRule registration |
| `IrClassToEts.kt` | Class/object/interface/enum shape already accepted by `clazz` | Object-extends-class (still a fail-close) |
| `IrFunctionToEts.kt` | Function/lambda/parameter mapping | Default-argument IR expansion |
| `IrStatementToEts.kt` | Statement visitors | Loop header recognition |
| `IrExpressionToEts.kt` | Expression visitors, including `IrCall` → `adaptCall` / `EtsCall` | Numeric/stdlib semantics |
| `IrTypeToEts.kt` | `IrType` → `EtsType` | FIR capture recovery (`CallCaptures`) |

`src/core/Contract.kt` stays frozen. If `Language` must grow a visitor hook,
write `docs/ets-lowering-contract-proposals.md` instead of editing Contract.

## Tests

`tests/lowering/ir-to-ets.mjs` / `IrToEtsSeam.kt`:

- `IrClassToEts` / `IrFunctionToEts` pass the same `IrClass` /
  `IrSimpleFunction` instances into `Language`. Nested `IrCall` lowering
  stays inside `LanguageLowering`; wrapping `Language` does not intercept
  those internal visits.
- String `plus` is already gone before IrToEts (`EtsLoweringPhases`).
- Declaration names and file spans survive. `EtsBackend.lower` and
  `IrToEts.program` emit the same top-level declaration names.

## Public CLI integration proof

The baseline already called `EtsLoweringPhases.run` from the frontend and
`IrToEts.program` from `EtsBackend.lower` in language mode. Its program mapper
flattened files directly, bypassing `IrModuleToEts`. The integration now delegates
each module through that existing mapper; declaration lowering, adapter linking,
validation, and language semantics are unchanged.

`node tools/kotlin-ets/tests/lowering/run.mjs` uses the existing non-Compose
`Concatenation.kt` fixture and the public `kotlin-ets --mode language` launcher.
`CliSeamAgent.java` is a test-only JVM agent, built with the ASM classes already
bundled in Kotlin's compiler. It activates only in the launcher's `MainKt`
process and records method entry/normal return without replacing any method.
There is no production trace flag, callback, or dependency.

The test asserts this runtime order (including normal returns):

```text
EtsLoweringPhases.run
  → IrToEts.program
    → IrModuleToEts.lower
      → IrFileToEts.lower
    → EtsProgram construction
  → emitEtsProgram
```

`public-cli-seam.json` stores the actual events; `public-cli.json` stores the CLI result.
The same generated output then executes against six JVM oracle results, covering
nullable concatenation, constants, mutation, and side-effectful `toString` order.
Existing IR evidence separately verifies string-plus normalization and retained
source declaration names/offsets. The test fails if the CLI bypasses a seam even
when generated output remains semantically equivalent.

This is a JVM/host language proof, not a Compose, ArkTS SDK, or device proof.

### Verification record (2026-09-22)

Run commands from the repository root. Evidence directories below are relative
to `tools/kotlin-ets/tests/` and are ignored local artifacts.

| Command | Result | Evidence directory |
| --- | --- | --- |
| `node tools/kotlin-ets/tests/lowering/run.mjs` | PASS: actual CLI seam order, six JVM/ETS pairs, 25 String.plus calls reduced to zero, 75 declaration records retained | `lowering/.work/run-kKi6hs/` |
| `node tools/kotlin-ets/tests/lowering/pipeline.mjs` | PASS: phase order, 41 source spans, bound symbols, repeat concat lowering unchanged | `lowering/.work/pipeline-GzdS7z/` |
| `node tools/kotlin-ets/tests/lowering/ir-to-ets.mjs` | PASS: two classes and four functions retain IR identity/names through the seam | `lowering/.work/ir-to-ets-V13B7V/` |
| `node tools/kotlin-ets/tests/lowering/jvm-contamination.mjs` | PASS: no JVM backend imports in lower/target/output layers | stdout |
| `node tools/kotlin-ets/tests/language/run.mjs` | PASS: five language fixtures plus historical overload positive proof; seven unsupported cases reject with source spans and no output | `language/.work/run-THYXfy/` |
| `node tools/kotlin-ets/tests/modules/run.mjs` | PASS: 44 JVM/module cases; visibility, imports, generics, overwrite/partial-output/collision rejection | `modules/.work/run-5jeY6q/` |
| `TMPDIR="$PWD/tools/kotlin-ets/tests/lowering/.work" bash tools/kotlin-ets/tests/backend/run.sh` | PASS: separate lowering/printer compilation, typed AST contracts, deterministic printing, JVM/host differential | `lowering/.work/kotlin-ets-backend-tests.SC0wwY/` |

Before the production edit, the new CLI trace assertion failed on baseline
`9246bc3`: `lowering/.work/run-kYd7sl/cli-seam.json` lacks both
`IrModuleToEts.lower` events. After the edit, the same assertion passes. The
before/after generated `concatenation.ets` bytes are identical (SHA-256
`5abb7511f34225110ad62c3bc84b4febdd000804179e3c8e1874a04fae07eabd`).
All final commands above exited zero; unsupported-input failures are expected
test outcomes, not compiler regressions. No SDK or device acceptance is claimed.

## S1: unique language generation boundary audit

Baseline: `b9e0374`. No production language bypass was found, so this follow-up
changes tests and this audit only. The production source tree before and after is
`b5275ee09652b5760f427a9e11a7d05dcee6f802` (`git rev-parse HEAD:tools/kotlin-ets/src`).

| Entry or construction | Audited route and interpretation |
| --- | --- |
| `kotlin-ets` launcher | Compiles production sources and invokes `MainKt`; no alternate language generator |
| `project.mjs` | Collects inputs and invokes the same launcher with the selected mode/output flag; not an IR or target generator |
| `Main.kt`, language mode, either output flag | `withKotlinFrontend` → `EtsLoweringPhases.run` → `EtsBackend.lower` → `IrToEts.program` → `IrModuleToEts.lower` → file/declaration mapping → typed `EtsProgram` → `EtsValidator.validate` |
| `Backend.kt`, both lower overloads | Single-module overload delegates to module-list overload, then the same `IrToEts.program` boundary |
| `Modules.kt`, `--out` | Accepts an already-typed program, validates and prints it; no Kotlin IR input |
| `Modules.kt`, `--out-dir` | Accepts the same typed program, validates it, assembles imports/runtime support and prints files; its extra `EtsProgram` constructors are typed subsets/import headers, not a second IR translation |
| Page mode | `ComposeWidgetPipeline` reuses language declaration lowering, lowers Compose structure through the neutral Widget model and returns the same typed `EtsProgram`; the former separate page assembler was removed |

This retains the Kotlin/JS reference's phase separation: IR-to-IR passes, then
module/file AST generation, then output assembly/printing. See
`kotlin-js-backend-reference.md`, sections 2–3. ETS keeps its typed target tree;
the JS AST/printer is not used as an intermediate representation.

“Unique” here means the audited production **language and page CLI routes** and
their output modes, not one `EtsProgram` allocation or a type-system prohibition on
calling low-level public mappers. Tests can call `IrToEts`/file mappers directly;
the API does not carry an unforgeable “all phases completed” token. This audit
does not claim all Kotlin semantics have moved out of `LanguageLowering`, nor
does it establish KLIB, project-adapter, or ArkTS SDK/device acceptance.

### Five acceptance checks

1. **Before/after path:** the baseline source already has the route above and the
   previous `run-kKi6hs/cli-seam.json` records its `--out` execution. This follow-up
   leaves that source tree unchanged and extends runtime evidence to both output
   modes and whole-program target validation. There is no claimed production
   rerouting in this commit.
2. **Positive source and typed boundary:** `lowering/run.mjs` compiles existing
   `Concatenation.kt` and `language/ScopeSlice.kt` through the real CLI. Exact
   traces require one phase run, one program boundary, one module mapper, one
   file mapping per source, successful `EtsValidator.validate(EtsProgram, ...)`
   before boundary return, then the selected emitter. It compares six `--out`
   results and seven two-file `--out-dir` results with the actual JVM oracle.
   Synthetic validator lambdas/default-argument bridges are not counted as
   whole-program validation.
3. **Unsupported source fails closed:** the existing
   `language/UnsupportedExternalResult.kt` must exit 2 with `UNSUPPORTED`,
   `java.time.Instant.now`, source path and valid offsets. Its exact trace must
   stop inside file mapping: no returned program, no emitter, no fallback and
   no output file.
4. **Existing regressions:** run the lowering test, module differential suite,
   backend separation/typed-tree contracts, and JVM contamination gate. Runtime
   traces and results are retained under the test runners' `.work` directories.
5. **Branch isolation:** only the test agent, lowering runner/JVM oracle and this
   document change on `arch/ets-lowering`; no production, Compose, KLIB or adapter
   files change.

Final S1 audit commands all exited zero (2026-09-22, repository-root cwd):

| Command | Local evidence under `tools/kotlin-ets/tests/` |
| --- | --- |
| `node tools/kotlin-ets/tests/lowering/run.mjs` | `lowering/.work/run-aAssIR/`: `public-cli-seam.json`, `public-cli-modules-seam.json`, `public-cli-unsupported-seam.json`, `runtime.json`, `module-runtime.json`, and command/result JSON |
| `node tools/kotlin-ets/tests/modules/run.mjs` | `modules/.work/run-hmHBtr/result.json`: 44 JVM/module cases and failure boundaries |
| `TMPDIR="$PWD/tools/kotlin-ets/tests/lowering/.work" bash tools/kotlin-ets/tests/backend/run.sh` | `lowering/.work/kotlin-ets-backend-tests.XuZZBc/`: separate compilation, typed-tree/source/symbol checks, wrong-rule rejection, deterministic printing and JVM differential |
| `node tools/kotlin-ets/tests/lowering/jvm-contamination.mjs` | PASS on stdout |

The unsupported trace contains only phase entry/exit and entry into the
program/module/file mappers. Its diagnostic points to
`UnsupportedExternalResult.kt`, offsets 85–90 (line 3, column 61), and exits 2.
The single-file ETS output remains byte-identical to the baseline evidence.

## S1.2: all production output modes use one typed exit

Reference: `arch/kotlin-ets-v2`. The blobs for `Main.kt`, `Backend.kt`,
`IrToEts.kt`, and `Modules.kt` are byte-identical on that branch and this one.
The audit found no production bypass, so S1.2 changes regression evidence and
this record only. `tools/kotlin-ets/src` remains
`e217da3792b2b5d0da2a79dd23ac22ae057eae51`.

The production route has one typed output boundary with two serialization forms:

| Production mode | Audited runtime route |
| --- | --- |
| language `--out` | official frontend/IR phases → `EtsBackend.lower` → `IrToEts.program` → typed `EtsProgram` → validator → `emitEtsProgram` → validator → printer |
| language `--out-dir` | same language boundary → `emitEtsModules` → validator → typed per-file assembly → printer |
| page `--out` | official frontend/IR phases → `ComposeWidgetPipeline.lower` → neutral widgets → Harmony target nodes + ordinary `IrDeclarationToEts` declarations → typed `EtsProgram` → `emitEtsProgram` → validator → printer |
| page `--out-dir` | same widget pipeline → `emitEtsModules` → validator → typed per-file assembly → printer |

`ComposeWidgetPipeline` joins widget lowering with the ordinary declaration
mapper instead of maintaining a second language mapper. Its public result is
`EtsProgram`, and
`Main.kt` can publish its text only through the same emitters. The final
`Files.writeString` calls consume strings already
returned by those emitters. Other writes in `Main.kt` publish diagnostics,
preflight JSON, or resources rather than ETS source. `project.mjs` only forwards
the selected mode and output flag to the same `kotlin-ets` launcher; its
`--collect-only` path produces no target.

The test-only JVM agent now observes `ComposeWidgetPipeline`, `IrToEts`, whole-program
validation, the shared emitters, and `EtsPrinter` without adding a production
trace hook. Exact traces reject an alternate CLI generator, a missing typed
program, an emitter bypass, or printing that starts before validation. The
focused page mode is `node tools/kotlin-ets/tests/ui/run.mjs --typed-exit-only`;
the normal UI run retains the same assertions in its existing `--out` and
multi-file `--out-dir` cases.

Compiler-independent target tests intentionally continue to construct
`EtsProgram` and call `EtsPrinter` directly. This includes probes under
`tests/target`, `tests/backend`, and focused UI ownership/runtime probes. They
exercise the typed target layer and are not CLI generators. Scripts and staged
ArkTS templates under `verification/` also remain non-production acceptance
infrastructure. No `experiments/` production entry exists. These paths were
retained unchanged; none is invoked by `kotlin-ets`, `MainKt`, or `project.mjs`.

Fresh S1.2 evidence (2026-09-22):

| Command | Result and local evidence |
| --- | --- |
| `node tools/kotlin-ets/tests/lowering/run.mjs` | PASS: both language output modes traverse `IrToEts`, validate the typed program before return, then validate before printer entry; `lowering/.work/run-BMKVtw/` |
| `KOTLIN_ETS_PROBE=/tmp/kotlin-ets-ui-probe-s12d node tools/kotlin-ets/tests/ui/run.mjs --typed-exit-only` | PASS: both page output modes construct typed programs and validate before printer entry; `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-ui-tests-3Y01Ht/` |
| `node tools/kotlin-ets/tests/modules/run.mjs` | PASS: 44 JVM/module cases including imports, filename collisions, and no-overwrite behavior; `modules/.work/run-O7p53V/` |
| `TMPDIR="$PWD/tools/kotlin-ets/tests/lowering/.work" bash tools/kotlin-ets/tests/backend/run.sh` | PASS: typed AST, printer independence, deterministic printing, and JVM/host differential; `lowering/.work/kotlin-ets-backend-tests.Rdd8Oe/` |
| `node --test tools/kotlin-ets/tests/project-inputs/launcher.test.mjs` | PASS: 15 project forwarding and validation tests |
| `node tools/kotlin-ets/tests/lowering/jvm-contamination.mjs` | PASS: no JVM backend imports in lower/target/output |

The page run used an equivalent local classpath manifest recovered from the
existing project-input evidence because the documented default probe directory
was absent. This is host/compiler evidence only; no ArkTS SDK or device result is
claimed.
