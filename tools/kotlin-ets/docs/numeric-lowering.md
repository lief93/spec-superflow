# Common numeric lowering

`FloatingPointRules` participates in the ordinary resolved-call pipeline and
emits typed ETS expressions consumed by the existing validator/printer. It does
not inspect page properties or rewrite Kotlin source strings.

## Official reference and ETS responsibility

Reference implementations inspected in the local official Kotlin sources:

- `ir/backend/js/lower/calls/NumberOperatorCallsTransformer.kt`: dispatch on
  resolved primitive receiver/member signatures, preserving operand evaluation.
- `ir/backend/js/lower/calls/NumberConversionCallsTransformer.kt`: reinterpret
  representable conversions and use numeric conversion intrinsics otherwise.
- `fir/backend/IrBuiltInsOverFir.kt`: `ieee754equals` has nullable formal operands
  even when the source operands are nonnullable primitives.

The frontend, resolution and IR are reused. These JS transformer classes depend
on `JsIrBackendContext` and JS intrinsics: they are references, not directly
installed ETS passes. Our backend supplies the corresponding typed ETS nodes.

## Supported main path

- Float/Double arithmetic `+ - * / %`, unary signs, increment/decrement.
- Mixed Int/Float/Double arithmetic with the declared Kotlin result type.
- `toDouble`, `toFloat`, and floating `toInt` conversion.
- Nonnullable Float/Double relational and IEEE equality operations.
- Exact widening of finite Float literals into the target number representation.

Double arithmetic uses target number operators. Float arithmetic converts
integral operands to single precision before the operation and rounds the result
with `Math.fround`. This preserves the Android/JVM source behavior, rather than
copying Kotlin/JS's choice to represent Float with double precision. Floating
`toInt` truncates and saturates; NaN becomes zero. Operands are evaluated once.

Long semantics, boxed/generic equality, numeric formatting, Float/Double
`compareTo` total ordering, and nonfinite literal emission are not claimed here.
Unsupported paths continue to report diagnostics, rather than pretend every
Kotlin number operation is an equivalent target number operation.

## Verification

Run `node tools/kotlin-ets/tests/language/numbers/run.mjs` from the repository.
The runner compares 67 JVM results against both flat and two-file generated
outputs, including exact widened float bits, negative zero, truncation,
saturation, NaN, evaluation order, default arguments and source parameter names.
It records input/output hashes and process logs in its `.work` directory.

`tests/inheritance/overloads/run.mjs` additionally promotes the historical
`UnsupportedFloatBody.kt` fixture to a positive JVM/host overload test.
These are strict host type/behavior checks, not Harmony SDK/native or visual
acceptance. SDK/native integration remains a POC milestone gate.
