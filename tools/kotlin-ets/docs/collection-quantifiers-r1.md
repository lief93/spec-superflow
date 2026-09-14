# R1 predicate quantifiers

## Finite contract

The initial inventory found map, filter/filterNot, bounded List/Iterable/array
iteration and Int progressions, but no predicate any/all/none/count adapters.
R1 adds only these four external inline standard-library signatures:

```text
kotlin.collections.any<T>(Iterable<T>, (T) -> Boolean): Boolean
kotlin.collections.all<T>(Iterable<T>, (T) -> Boolean): Boolean
kotlin.collections.none<T>(Iterable<T>, (T) -> Boolean): Boolean
kotlin.collections.count<T>(Iterable<T>, (T) -> Boolean): Int
```

These are extension receivers, not static source-call rewrites. The actual call
receiver must be non-null List<T>, MutableList<T> or Iterable<T> in the existing
array-backed representation, with exact invariant instantiated element and
predicate types. Nullable/generic elements are supported where Language maps
them. No nullability refinement is claimed.

StandardLibraryRules shares the existing filter predicate declaration validator:
external stub origin, absence of source body ownership, inline/non-suspend,
no dispatch/super receiver, one non-reified type parameter, one non-vararg
non-default predicate parameter, declared Iterable<T>/Function1<T, Boolean>,
and exact declared/instantiated result types. Validation precedes child lowering.
Receiver and predicate are each lowered once, in that order, using Language.

The typed external EtsCall selects `stdlib:__etsListAny` for any/all/none and
`stdlib:__etsListCount` for count. All seeks a false predicate result and negates
the helper result; none negates the true-match helper result. These are typed
EtsUnary nodes, not callback rewriting. Both helpers reuse the existing
`__etsArrayIterator` dependency and closure state through EtsRuntimeSupport.
The inventory is exactly **20 functions and two runtime classes**; all previous
helpers, fixtures and count/name/uniqueness assertions remain covered.

## Observable behavior

- Empty any is false, empty all/none are true, empty count is zero; no predicate
  evaluation occurs.
- Predicates run once for each visited element in source order. Any/all/none
  stop at the decisive result; count visits the complete input unless it throws.
- Exceptions propagate without conversion or continuing traversal. The helpers
  do not modify the collection; changes made by predicates remain observable.
- For the supported array-backed mutable-list path, structural add is detected
  on the next iterator read. A decisive predicate result returns immediately,
  even if that predicate added an element. This differs intentionally from an
  unconditional post-predicate length check, which would break short-circuit
  behavior. Repeated non-decisive traversal sees the existing fail-fast guard.
- Count includes an Int overflow guard with the official exception message.
  Executing more than Int.MAX_VALUE matches is not covered by the finite oracle;
  no billion-element runtime test or simulated internal counter is claimed.

This is not arbitrary Kotlin/JVM iterator interoperability or a full modCount
model. Foreign/custom Iterable implementations, concurrent access, mutation
restoring the original length and host array resizing remain outside the
existing array-backed contract. No-predicate overloads, Array/primitive-array,
String/CharSequence, Collection-typed, Set, Map and Sequence overloads are not
added. Wider contravariant predicate input types, projected receivers, and
non-local inline returns remain outside this bounded slice. Errors are target
Error values with Kotlin exception-name/message text, not JVM exception objects.

## Official inspection and reuse

The first inspection used the pinned read-only compiler archive
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`. Its
`ir/backend/js/lower/inline/JsInlineFunctionResolver.kt` delegates to the common
inliner and enables external inlining; it does not supply stdlib function bodies.

Pinned Kotlin v2.1.20 sources inspected:

- [_Collections.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/common/src/generated/_Collections.kt#L1612):
  the four predicate loops, empty checks, immediate decisions and count guard.
- [Collections.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/src/kotlin/collections/Collections.kt#L447):
  count-overflow exception behavior.
- [JS AbstractMutableList.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/js/src/kotlin/collections/AbstractMutableList.kt#L115):
  iterator state and structural-modification model. ETS retains the explicitly
  bounded existing array-backed cursor, not that complete JS implementation.

The actual official FIR2IR probe observes external inline declarations with
`body=false`. No actual stdlib IR body is fabricated, loaded from a signature or
claimed reused. Direct implementation reuse consists of Language, CallRule,
typed ETS calls/unary nodes, the filter signature checker, existing iterator
runtime and EtsRuntimeSupport dependency selection. The two fixed helper bodies
are ETS semantic replacements. No source parsing/replacement, second expression
parser, target/core edits or page-specific adaptation was introduced.

Main's R1 heritage types also require dependency collection through class base
types/interfaces and super-constructor target types. The stdlib collector now
recurses through those fields, including generic type-only runtime references.
Main owns shared tree, validator, traversal and output changes.

## Evidence

Paths are relative to `tests/stdlib`. All executed JVM work is sequential with
`JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`.

- Runtime RED: `.build/quantifier-runtime.74H466/runtime.stderr`, unknown owned
  `stdlib:__etsListAny`; the independent JVM oracle had already completed.
- Runtime GREEN: `.build/quantifier-runtime.U0xyYv/result.json`, **480** isolated
  runtime/JVM cases. Four operations, eight empty/nullable/mixed inputs, five
  predicate modes, three trigger positions; result, trace and post-call source
  contents compared. This is direct runtime evidence, not public CLI evidence.
- Symbol RED: `.build/quantifier-symbols.cM5OWi/probe.stderr`, genuine external
  Iterable.any unsupported.
- Symbol GREEN: `.build/quantifier-symbols.33oKsy/probe.stdout`, **7** supported
  actual calls, **11** unsupported real overloads/source dispatches and **105**
  malformed resolved signatures. Rejections must not lower children. The probe
  also checks typed helper identity, generic argument and Boolean polarity.
- Parent-type RED: `.build/runtime-types.I7k7gG/test.stderr`.
  GREEN: `.build/runtime-types.VEuAU9/test.stdout`, including base/interface/
  super-constructor type-only dependencies and all earlier invalid-type checks.
- Existing isolated `check-symbols.sh` GREEN after the shared traversal compile
  dependency update: 74 accepted calls, 94 malformed IR results, 30 malformed
  target-call results and all 42 filter signature mutations; the separate
  existing six-unsupported-call fixture still passes unchanged.
- Runtime inventory/dependency GREEN: `.build/runtime-tree.cx64ZT/test.stdout`;
  exactly 20 functions/two classes, isolated quantifier dependency selection,
  all 26 previous traversal paths/five function kinds and output validation.

The public CLI fixture retains unchanged `QuantifierLibrary.kt` and
`QuantifierCases.kt`, with independent JVM and cross-file/order oracles. The
null-equality regression below additionally supplies `NullEquality.kt`.
`check-quantifiers.mjs` checks all 480 cases plus seven cross-file/order values
and 30 focused null-equality/Elvis/safe-call values,
static types of unchanged emitted modules, public unsupported output rejection,
and full production/input SHA-256 stability. It requires the explicit
`KOTLIN_ETS_BUILD_SLOT=1` environment gate. Main's frozen public CLI run is
**GREEN** in `.build/quantifiers.VawjkY/result.json`: **480** quantifier cases,
**7** cross-file/order cases, **30** null cases, unchanged emitted-module static
type checking, unsupported fixture exit 2/no output, and the full production/input
SHA-256 guard. The original QuantifierCases.kt hash remains unchanged.

Exact successful outputs are in `.build/quantifiers.VawjkY/modules/`:
`QuantifierLibrary.ets`, `QuantifierCases.ets`, and `NullEquality.ets`.
Verified exported signatures suitable for main's manual SDK consumer:

```typescript
// QuantifierLibrary.ets
export function orderedAny(log: Array<number>): boolean
// QuantifierCases.ets
export function crossFileStrings(values: Array<string>): boolean
```

This is JVM/public CLI/host and static-type evidence, not actual ETS SDK or native
execution evidence. Main owns the pending SDK/UI integration. All lane writers
and JVM processes remain stopped; this evidence update changes documentation only.

## Literal-null integration fix

Main's full CLI run `.build/quantifiers.G4dqSP/cli.stdout` rejected the unchanged
`QuantifierCases.kt` span 209..221 (`value ?: -99`). The official frontend emits
`kotlin.internal.ir.EQEQ(Any?, Any?): Boolean`, with the Elvis temporary Int?
and a typed Nothing? null constant. The full official-IR regression reproduces
that exact source span in `.build/null-equality-ir.lds6NW/original-failure.txt`;
its `actual.ir` and `null-calls.txt` retain the resolved declarations/operands.

StandardLibraryRules now accepts only the literal-null fast path of that exact
builtin: official `IrBuiltIns.BUILTIN_OPERATOR` origin, no source ownership,
no dispatch/extension/super receivers, no generics, two non-default/non-vararg
Any? parameters, Boolean declaration/call result and an actual null constant
typed Nothing?. Both operands are lowered once in original order to typed
strict equality. Generic/nullable values are mapped by Language; no nullable
cast or generic value-to-value equals implementation was added.

The pinned compiler's
`ir/backend/js/lower/calls/EqualityAndComparisonCallsTransformer.kt`,
`transformEqeqOperator`, separately recognizes null constants before equals
dispatch. That semantic distinction is reused; the JS transformer itself is
not copied or invoked. ETS compares its typed null representation strictly;
foreign JavaScript undefined interoperability is not added.

Focused actual-IR signature evidence is GREEN in
`.build/null-equality-ir.dGuzmK/probe.stdout`: **11** actual literal-null calls
and **121** malformed-call rejections, including operand order, both null sides,
wrong constant type, missing operands, extra receivers, super dispatch, altered
declaration/result/origin, and removal of the literal-null boundary.

The historical full regression was **RED**, without hiding or rewriting the fixture:
`.build/null-equality-ir.dGuzmK/original-failure.txt` advances to
`kotlin.internal.ir.greater` at 422..431. The resolved formal operands are Int,
but the compiler-produced get of `value` remains Int? under a proven non-null
branch. The added String?.length case exhibits the analogous receiver issue;
Elvis result branches also retain nullable get types. Main resolved this in
`core/ExpectedNullability.kt`, invoked from Frontend after common lowerings.
It uses the actual official `AbstractValueUsageTransformer` expected-usage
traversal and adds IMPLICIT_CAST only when the expression type is nullable, the
expected type is non-null, and removing nullability yields exactly that expected
type. It preserves offsets and the original operand; this is not an API-name
rule or a general unchecked cast. LanguageLowering was not changed for this fix.
Main owns the source-phase integration, with lane2 supplying independent tests.

The subsequent original-fixture public CLI run `quantifiers.VawjkY` passed all
cases and the source hash guard. The earlier direct-probe artifacts remain
historical RED evidence; no fresh direct-probe run is claimed by this update.
The full-IR test uses withKotlinFrontend and therefore includes the new pass
when rebuilt, before backend validation and emission.

The earlier isolated quantifier/runtime regressions predate this additive
equality fix. The new combined CLI evidence comes from main's frozen run;
SDK/UI acceptance is still pending. No new tests or full CLI runs were performed
by this lane for this documentation-only update.

## Changed files and freeze

Production changed: `src/stdlib/StandardLibraryRules.kt`,
`StandardLibrarySupport.kt`, `StandardLibraryDependencies.kt`.
`IterationRules.kt` is unchanged.

Tests changed: `tests/stdlib/RuntimeDependencies.kt`, `RuntimeTypes.kt`,
`check-symbols.sh` (the shared Validator now needs Traversal.kt on its isolated
compile source list; no validator change was made by this lane).
New tests: `QuantifierOracle.kt`, `QuantifierCrossOracle.kt`,
`QuantifierRuntime.kt`, `QuantifierSymbols.kt`, `check-quantifier-runtime.mjs`,
`check-quantifier-symbols.sh`, `check-quantifiers.mjs`, and
`fixtures/quantifiers/{QuantifierLibrary,QuantifierCases,QuantifierRejected}.kt`.
Null-fix tests: `NullEqualityProbe.kt`, `NullEqualityOracle.kt`,
`check-null-equality-ir.sh`, `fixtures/quantifiers/NullEquality.kt`, and the
extended public CLI runner. The original quantifier fixture was not edited:
SHA-256 `ab755decef9c86ab8808d333918994450b3403a87a9ee3d0b4db92f218b51002`.
Documentation: this file. No review, device, commit, push or new worker was used.

Frozen production SHA-256:

```text
002718e1897bf9ab5d23cb22f9300bb186d89fa30792663c857ee423dca791ad  IterationRules.kt
db9f5eb7637970f5b8700c8b4cbfe22c4be6985adde9b623820735eb0c7f2e12  StandardLibraryDependencies.kt
cb572281b5eff51a32f9dd869770c58ab23ab8da3cdcab0f17942ed39df47116  StandardLibraryRules.kt
31e1796be944f0f62bd616f96ac47f43cdec6093b4be86974488b1d4013790ed  StandardLibrarySupport.kt
```
