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
