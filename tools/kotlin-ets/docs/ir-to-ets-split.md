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

`cli-seam.json` stores the actual events; `public-cli.json` stores the CLI result.
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
