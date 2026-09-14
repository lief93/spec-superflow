# Bounded collection filtering and approved loop adapters

## Scope and ownership

Lane 3 changes only `src/stdlib/*`, `tests/stdlib/*`, and this document. No
frontend, language, target, output, CLI, or page-specific code is changed here.
This document records the original filter and two residual official Int-loop
adapters. The subsequently approved reusable array-backed iteration increment,
current inventory and freeze are recorded in [collection-iteration.md](collection-iteration.md).

## Filter contract

`StandardLibraryRules` accepts the resolved external inline declarations
`kotlin.collections.filter` and `kotlin.collections.filterNot` only when their
actual declaration has the shape `Iterable<T>.(predicate: (T) -> Boolean): List<T>`.
It checks declaration origin, type-parameter identity, receiver, parameter and
result types, and absence of dispatch/super receivers before lowering children.
The instantiated call must have exactly matching `T` in receiver, predicate and
result, one invariant type argument, one non-null predicate, and a non-null
`List<T>`, `MutableList<T>`, or `Iterable<T>` receiver.

The shared `Language` lowers the receiver and predicate. The rule returns a typed
`EtsCall` with an external `stdlib:__etsListFilter` identity, concrete generic
type argument, `Array<T>` result and Boolean polarity. Both APIs share this one
runtime helper, selected through the existing `StandardLibraryRuntime` /
`EtsRuntimeSupport` tree traversal. There is no source parsing, generated Kotlin
body, binary-body claim, private AST, or printer rewrite.

The helper traverses the supported array-backed receiver in order, evaluates the
predicate once per visited element, and appends the original element to a fresh
result when its Boolean result matches the operation's polarity. Empty input
does not evaluate the predicate. The helper itself does not mutate the receiver.
Predicate exceptions propagate and stop further predicate evaluation.

Nullable elements remain nullable; generic elements retain their mapped type.
`filter` does not refine `T?` to `T`. Language-supported captures, ordinary lambda
returns, and function-valued arguments reuse the shared language implementation.

## Deliberate limits

- `Iterable` means the existing array-backed language representation. This is
  not an iterator framework or support for arbitrary custom Iterable classes.
- Array, primitive-array, String, Collection-typed, Set, Map and Sequence filter
  overloads are not adapted. Nullable receivers require an independently
  supported source-language null check/safe call first.
- Star/projected arguments, widened contravariant predicate input types,
  dispatch/super calls, altered declarations/signatures, non-local inline
  returns, and unsupported language element types remain unsupported.
- A source function merely named `filter` or `filterNot` is not captured; the
  ordinary resolved-source-call path remains responsible for its real body.
- Structural mutation detection checks receiver length after each predicate,
  as the existing bounded list-map runtime does. The tested add-during-predicate
  case throws `ConcurrentModificationException` on this supported array-backed
  mutable collection path. No arbitrary iterator/modCount behavior, concurrent
  access semantics, or mutation that restores the original length is promised.
- Target failures are `Error` values with Kotlin exception-name/message text,
  not Kotlin/JVM exception classes or an exception-class hierarchy.

## Official source inspection and exact reuse

First inspected the requested read-only compiler source archive:
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`.
`org/jetbrains/kotlin/ir/backend/js/lower/inline/JsInlineFunctionResolver.kt`
delegates to the common inliner and enables external inlining. The common
`ir/inline/FunctionInlining.kt` obtains the actual callee through its resolver.
Those compiler sources do not include the stdlib collection/progression bodies.
They do not establish a loaded JVM dependency body for the current frontend.

Then read the pinned official Kotlin v2.1.20 runtime sources, without modifying
the compiler archive or adding downloaded sources to the repository:

- [_Collections.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/common/src/generated/_Collections.kt#L773),
  lines 773-775, 826-828, 854-866: filter/filterNot allocate a destination and
  delegate to filterTo/filterNotTo, whose loops test then append each element.
  SHA-256: `eb25ad97a03e2d7727ccdcf72370a759a0d2c58bd00f52c1112d8fd814c2a9dc`.
- [progressionUtil.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/src/kotlin/internal/progressionUtil.kt#L8),
  lines 8-20 and 42-45: Int mod, differenceModulo and final-element branches.
  SHA-256: `eb165869ce4547ca1714751e44f69cd5646a4b74448dee27c7a36f8c54e042e1`.
- Local `org/jetbrains/kotlin/backend/jvm/JvmSymbols.kt`, lines 605-638,
  constructs the exact JVM-context progression symbol used by the loop pass.
  The JS exception transformer routes official intrinsics to JS runtime symbols;
  ETS instead needs its own typed runtime entry.

**Direct implementation reuse:** the existing official frontend/common passes,
`Language`, `CallRule`, typed ETS nodes, and `EtsRuntimeSupport` are unchanged and
reused. No official JS transformer or standard-library IR body is copied/linked.

**ETS replacement:** the filter destination/iteration algorithm is implemented
as one fixed array-backed ETS helper; `ArrayList`/iterator/add become array
allocation/indexing/push, with the explicitly bounded length guard above. The
Int progression helper is a semantic port of the official Int arithmetic, not
the JS backend's emitted text. Exception intrinsics become a `never`-returning
typed runtime call that throws a target `Error` with preserved message text.

## Approved loop integration

Exact accepted resolved static symbols/signatures:

- `kotlin.internal.ProgressionUtilKt.getProgressionLastElement(Int, Int, Int): Int`
- `kotlin.internal.ir.illegalArgumentException(String): Nothing`

Both rules check the actual declaration and instantiated call: no source-module
body, dispatch/extension/super receiver, generics, varargs, defaults, suspend, or
fake override; parameter and result classifiers must exactly match. The Long,
unsigned and differently named variants are not adapted.

`__etsProgressionLastElement` preserves official mod/differenceModulo, positive
and negative branches, empty-direction branches and zero-step failure. Every
Int-overflow point explicitly wraps via `| 0`. Intermediate arithmetic stays
within exact IEEE-754 integer range, including MIN/MAX endpoints and negation of
MIN_VALUE. This also matches the internal JVM helper's MIN_VALUE-step behavior;
it does not authorize a Kotlin progression constructor to accept that step.
The official loop pass still validates positive source `step` arguments.

The zero-step path selects `__etsIllegalArgumentException` transitively. Runtime
helper inventory grows from 7 to exactly 10; the count, every helper name,
uniqueness, dependency order, and filter-only selection remain asserted.

## Verification evidence

Paths below are relative to `tools/kotlin-ets/tests/stdlib/` unless noted.

- Filter RED: `.build/filter.rzlNyX/cli.stdout`: public CLI exit 2, unsupported
  `kotlin.collections.filter`; JVM oracle compiled and produced expected values.
- Filter tracer GREEN: `.build/filter.VW7teJ/result.json`, two same-input cases.
- Expanded filter GREEN: `.build/filter.HsKDqB/result.json`, 34 same-input
  JVM/public-CLI cases plus host checks for fresh result and element identity.
- Rejections GREEN: `.build/filter-rejections.IrSAZf/result.json`, six valid
  Kotlin fixtures rejected with source-linked diagnostics and no output, plus
  two same-named source functions that execute their own bodies.
- `bash tools/kotlin-ets/tests/stdlib/check-symbols.sh`: 74 accepted calls,
  94 malformed IR results, 30 malformed target-call results and 42 malformed
  filter dispatch/signatures checked; original 6 unsupported calls preserved.
- Loop RED: `.build/loop-symbols.ph9rlE/test.stderr` and
  `.build/loop-adapters.uLWVjm/cli.stdout`: actual official intrinsic unhandled.
- Loop oracle GREEN: `.build/loop-adapters.tc18rD/result.json`, 1,300 direct
  installed Kotlin 2.1.20 JVM runtime comparisons (edge Cartesian product and
  300 seeded random triples) plus 22 same-input JVM/public-CLI loop cases.
- Loop symbols GREEN: `.build/loop-symbols.69hlBu/test.stdout`, four actual
  official calls and 28 malformed declaration/call signatures and dispatches.
- Runtime tree GREEN: `.build/runtime-tree.IUck3N/test.stdout`, 26 traversal
  paths, five function kinds, exact 10-helper inventory, transitive progression
  failure helper, existing dependencies, identity/order and output validation.
- Lane 2 separately reports `tests/loops/.work/run-TYvZPq/result.json` GREEN:
  35 same-source JVM/public-CLI/host cases and three rejected boundaries. Its
  `typed-23bNqu` run reports 12 official iterators eliminated and eight snapshots.
  These are coordination reports, not an additional full-suite run by lane 3.

Host execution parses/transpiles the unchanged public CLI ETS output with the
installed SDK TypeScript parser and executes that output. It is separate from
actual ETS SDK acceptance. Main owns the frozen full regression and SDK harness
(including Filter.kt and Loops.kt). This lane runs no device tests, reviews,
commits, or pushes and makes no device/runtime-compatibility claim.

## Changed files and freeze

Production files modified:

- `src/stdlib/StandardLibraryRules.kt`
- `src/stdlib/StandardLibrarySupport.kt`

Existing tests extended without replacing the old fixtures/oracles:

- `tests/stdlib/ResolvedCalls.kt`
- `tests/stdlib/RuntimeDependencies.kt`
- `tests/stdlib/check-symbols.sh`

New tests:

- `tests/stdlib/FilterOracle.kt`
- `tests/stdlib/check-filter.mjs`
- `tests/stdlib/check-filter-rejections.mjs`
- `tests/stdlib/fixtures/Filter.kt`
- `tests/stdlib/fixtures/FilterSymbols.kt`
- `tests/stdlib/fixtures/FilterShadow.kt`
- `tests/stdlib/fixtures/filter-rejected/Array.kt`
- `tests/stdlib/fixtures/filter-rejected/IntArray.kt`
- `tests/stdlib/fixtures/filter-rejected/String.kt`
- `tests/stdlib/fixtures/filter-rejected/Collection.kt`
- `tests/stdlib/fixtures/filter-rejected/Predicate.kt`
- `tests/stdlib/fixtures/filter-rejected/NonLocal.kt`
- `tests/stdlib/LoopAdapterOracle.kt`
- `tests/stdlib/LoopAdapterSymbols.kt`
- `tests/stdlib/check-loop-adapters.mjs`
- `tests/stdlib/check-loop-symbols.sh`
- `tests/stdlib/fixtures/LoopAdapters.kt`

Documentation added: `docs/collection-filter.md` (this file).

Historical filter/loop-adapter freeze SHA-256 (superseded by the iteration increment):

```text
92bccc9202fd2a71004b5ab2627a5f3507a767478ea64e6b013a78d955891da3  StandardLibraryRules.kt
96ce46c106b842eff8dda3696142098f76ad4f2bf9b36c0918d9a3cf266fb336  StandardLibrarySupport.kt
```

At that historical freeze `StandardLibraryDependencies.kt` was unchanged, with SHA-256
`7428fa75c1d85c992dc67e71df6902ee9046678cbe469269abec684313faff28`.
No cross-lane code conflict required an out-of-scope edit. The official loop
frontend hook and shared validator/output integration were supplied by their
owners. Full frozen regression and actual SDK results belong to main.
