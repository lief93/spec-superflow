# Expected Nullability in the Target Backend

The checked FIR-to-IR pipeline can omit casts that change only nullability. A
guarded nullable Int can therefore remain an `IrGetValue` of `Int?` when passed
to the official `greater(Int, Int)` intrinsic. Safe-call receivers and the
non-null branch of Elvis have the same representation issue.

`core/ExpectedNullability.kt` subclasses the actual Kotlin 2.1.20
`AbstractValueUsageTransformer`. The official visitor supplies expected types
for call arguments and receivers, variable/field initializers, returns, and
condition/try results. The ETS-specific override adds an `IMPLICIT_CAST` only
when the actual type is nullable, the expected type is non-null, and removing
nullability makes the types exactly equal.

This pass runs after source inlining and common lowering, only after official
frontend diagnostics have passed. It is not a validator for arbitrary untrusted
IR and does not invent proof for invalid Kotlin. It does not alter conditions,
replace values, erase null checks, duplicate expressions, change declarations or
translate arbitrary object equality to reference equality. Existing language
lowering and the shared target tree/printer consume the explicit casts.

Pinned reference APIs were verified against the local 2.1.20 compiler jar with
`javap`. Source references: Kotlin `fir/backend/Fir2IrImplicitCastInserter.kt`,
`visitSmartCastExpression`, and `backend/common/lower/AbstractValueUsageTransformer.kt`.
The former omits nullability-only smart casts; the latter is the reused visitor,
not a copied dispatch table or a new data-flow engine. The common visitor's
unsupported property-reference TODOs are bypassed only to preserve the existing
source-linked target rejection for those nodes.

## Evidence

- Original public CLI failure: `tests/stdlib/.build/quantifiers.G4dqSP`, no ETS
  published. After literal-null equality was added, the same fixture exposed the
  missing expected-type conversion for a guarded Int comparison.
- Fresh public CLI: `tests/stdlib/.build/quantifiers.VawjkY`, 480 collection
  cases, seven cross-file/order checks and 30 null/safe-call/Elvis cases match
  the JVM oracle. Static target checking and input/source hashes passed.
- Fresh UI regression: `$TMPDIR/kotlin-ets-ui-tests-hB4G1X`, original/renamed
  source, helper parity, conditional UI and multi-file page emission passed.
- Additional `tests/nullability` suite and actual SDK/native acceptance are
  recorded separately in progress.md; a host oracle is not ArkVM evidence.
