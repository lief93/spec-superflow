# Bounded Double relations

## Demonstrated gap

The original binary overload replay, after the separately approved Int.toDouble
fix, failed on `kotlin.internal.ir.greater` at original `Application.kt:721..732`.
Evidence is retained at
`tests/binary-bodies/r2d/.work/run-Yyeyt3/public-hIX9py/combined-cli.json`.
Main then explicitly approved only nonnullable Double `<`, `<=`, `>`, `>=`.
The binary fixture and original JARs remain unchanged.

## Exact adaptation and official reuse

`StandardLibraryRules.kt` matches actual `kotlin.internal.ir.less`,
`lessOrEqual`, `greater`, and `greaterOrEqual` symbols with the observed official
`IrBuiltIns.BUILTIN_OPERATOR` origin. Declaration and call must each have two
exact nonnullable Double operands, an exact nonnullable Boolean result, no
dispatch/extension/super receiver, no type arguments/binders, and no default or
vararg parameters. Checks precede lowering either operand.

The result is a typed Boolean `EtsBinary`, with the left and right operands each
lowered once in source order. No helper, coercion, compareTo call, equality rule,
or runtime-type dispatcher is introduced. Existing Int relational behavior and
fixed runtime helper inventories remain unchanged.

Inspected pinned official files under
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/`:

- `org/jetbrains/kotlin/ir/backend/js/lower/calls/EqualityAndComparisonCallsTransformer.kt`,
  lines 39-42: official relational builtin maps select `jsLt`, `jsLtEq`, `jsGt`,
  `jsGtEq` for non-Long primitive types. Long has a separate comparison path.
- `org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/JsIntrinsicTransformers.kt`,
  lines 45-48: those four intrinsics become the corresponding native operators.

Reuse is the official symbol/type-driven lowering architecture and native
primitive comparison semantics for this explicitly bounded Double subset. The
JS-backend-context-dependent transformer is not loaded into ETS, and its broader
type/equality policies are not copied. No source bodies are parsed or fabricated.

## Original-source proof

Tests live under `tests/stdlib/double-relations/`:

- `DoubleRelations.kt` declares four Boolean functions and two operand factories.
  Each factory records its evaluation; all values arrive as Double parameters.
- JVM-only `Oracle.kt` and `host.mjs` exercise every pair from negative infinity,
  -1, negative zero, positive zero, 1, positive infinity and NaN for all four
  operators: 196 pairs. Host/JVM agree on results and the exact `[1,2]` effect
  trace. Nonfinite values are not emitted as compiler source literals.
- `Symbols.kt` checks actual resolved builtin declarations, typed result/operator,
  child identity/order, target validation and zero comparison runtime. Fourteen
  malformed shapes per operator cover receiver dispatch, absent operands,
  nullable/mixed operand shapes, invalid results, changed declaration signatures
  and nonofficial origins: 56 negatives before child lowering.
- `Rejected.kt` keeps six actual excluded APIs: Float and Long comparison,
  Double compareTo, primitive Double equality, boxed Number equality, and generic
  equality. This does not redefine the existing Int comparison family.

The public host executes/typechecks generated output unchanged. Its only helper
is `__etsListAdd` for the explicit test traces. Slot-gated runners snapshot
production/test inputs, retain commands and stdout/stderr, and require unchanged
live/frozen hashes. All JVM jobs are serialized with two active processors and
SerialGC. No SDK or native tests run here.

```sh
KOTLIN_ETS_RELATION_SLOT=symbols node tools/kotlin-ets/tests/stdlib/double-relations/run.mjs symbols
KOTLIN_ETS_RELATION_SLOT=public node tools/kotlin-ets/tests/stdlib/double-relations/run.mjs public
```

## Evidence status

Evidence under `tests/stdlib/double-relations/.work/`:

- `symbols-5GdV0k`: retained RED at the actual official
  `less(Double,Double):Boolean` call.
- `symbols-ZteuHH`: GREEN, four actual operators, six excluded APIs, all 56
  malformed signature cases before children, typed Boolean/operator checks and
  empty comparison runtime closure.
- `public-iLskMO`: GREEN, all 196 JVM/public-CLI/host pairs, unchanged output
  typechecking, NaN/infinities/signed zeros, exact operand order/count and fixed
  trace-helper inventory. Frozen/live input hash guards passed.

These GREEN runs use StandardLibraryRules SHA-256
`5167d21ad317388e43f08739a7872cc89dda3150deaa7c18e5d974c4bc5b0889`.
The unchanged original binary replay is GREEN on this revision:
`tests/binary-bodies/r2d/.work/run-Yyeyt3/public-NoJAG9/complete.json` records
three layouts, nine JVM/public-CLI/host pairs, all three selected-overload
rejections, and unchanged production hashes. `runtime.json` records exact input
traces and module hashes. Combined, split and reversed layouts emitted identical
SHA-256 `c415941610f09810f3ca9ead148e5621cdcf2bf01688d8beb7ee1c81e4f5cb79`.
Original `public-jWy0iD` and `public-hIX9py` failures remain intact. The source
Application SHA-256 remains
`c40c744aa4334f71950d539fdf24d5126b3c9be439844d0e604a7de71b665ed6`.

All owned JVM/runner processes exited and were reaped. Production and tests are
frozen; no runtime helper definitions were changed. Main owns final combined
source acceptance and SDK/native gates. Earlier conversion/overload evidence
predates the relation change and is explicitly intermediate, not final
all-source acceptance.

## Limits

No boxed/generic equality, IEEE equality operator, Double.compareTo total order,
Float/Long/mixed resolved operand signatures, nullable primitive comparisons,
numeric coercion family or nonfinite literal generation is added. NaN and signed
zero behavior is native primitive relational behavior, not boxed ordering.
