# Bounded array-backed iteration

## Contract

This approved follow-on to [collection-filter.md](collection-filter.md) changes
only the standard-library adapter/runtime, its tests and documentation. It is
reusable collection support, not page-specific lowering.

`IterationRules` uses the actual resolved external declarations and official
`getTypeSubstitutionMap` / `IrTypeSubstitutor`. It validates receiver ownership,
nullability, invariant arguments, declaration/call arity, instantiated result,
parameter types and dispatch before lowering any children. Only observed
standard-library fake-override receiver shapes are allowed. Altered receiver
declarations, missing non-varargs, super dispatch and unsupported symbols fail
closed. An omitted official vararg is an empty array, not a fabricated body.

Accepted bounded families:

- List, MutableList and Iterable `iterator`; Iterator and MutableIterator
  `hasNext` / `next`; IntIterator `hasNext` / `next` / `nextInt`.
- Array and IntArray `iterator`, `get`, `set` and `size`; `arrayOf` and
  `intArrayOf`, including omitted empty varargs. Existing list get/size/add
  adapters remain in place.
- Int `rangeTo`, Int `until` / `downTo`, IntProgression `step` / `reversed`,
  first/last/step properties and IntRange/IntProgression iteration. Composed
  progressions are lazy cursors, not materialized arrays.

The exact runtime types are external named types with IDs
`stdlib:__etsIterator` (one argument) and `stdlib:__etsIntProgression` (zero).
The dependency provider validates ID, name, external flag, arity and arguments,
including type-only references and nested record/function/nullable/tuple types.
Unknown owned IDs and malformed shapes are rejected. Source types are not
recognized by spelling alone.

Per-file runtime declarations are independently emitted. Iterator callback
fields are public **readonly**, so independently emitted types remain
structurally compatible across source files. The mutable cursor, expected size
and progression state remain captured in shared closures. Reading or calling a
cursor in another module advances the same state; callbacks cannot be assigned
through the generated static type. No shared runtime module is introduced.

## Semantics and limits

Array-backed List/Iterable iteration visits values once in source order.
`hasNext` does not advance. `next` advances only on success and fails when
exhausted; repeated exhausted calls stay exhausted. Supported list structural
mutation (`add`) is detected by the cursor's captured length on `next`, not on
`hasNext`. Array element replacement remains visible to an existing cursor;
array read/write operations check Kotlin index bounds.

These are the supported array-backed mutable collection semantics, not a claim
of arbitrary JVM iterator or modCount compatibility. Custom Iterable/Iterator
implementations, foreign iterators, Sequence, sets/maps, iterator remove,
structural mutation that restores the original size, concurrent access and
host-side array resizing are outside the contract. Array constructors, spread
arguments, primitive arrays other than IntArray and projected receiver element
types are not added. Generic and nullable elements depend on the shared
language's supported type mapping. Target errors carry Kotlin exception names
and messages; they are not JVM exception objects or a class hierarchy.

Int progression arithmetic reuses the previously tested final-element helper,
with explicit Int wrapping at overflow points and number-safe intermediates.
Constructors reject zero and MIN_VALUE steps; `step` rejects nonpositive input.
`until` handles a MIN_VALUE exclusive endpoint without subtracting past MIN.
The cursor terminates on the final element before incrementing, including
MIN/MAX boundaries. Long/unsigned progressions are not supported.

## Official reuse versus replacement

The first inspection used the requested read-only pinned compiler sources at
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`, including the official
common IterableLoopHeader and ProgressionLoopHeader and IR substitution APIs.
Lane2 integrates the actual common ForLoops pass. Its bounded post-pass repair
uses official substitution only for pass-created reads whose generic receiver
matches the resolved owner; source calls and outer casts are retained.

Actual frontend probes report **FunctionBody.Unavailable** for these external
stdlib calls. No official stdlib IR body was linked or copied, no body was
fabricated, and no Kotlin-source or emitted-source string replacement is used.
`Language`, `CallRule`, typed ETS nodes, tree traversal and `EtsRuntimeSupport`
are the shared compiler contracts reused directly.

Pinned Kotlin v2.1.20 reference algorithms inspected:

- [ProgressionIterators.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/src/kotlin/ranges/ProgressionIterators.kt):
  Int final-element, has-next and cursor update algorithm.
- [Progressions.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/src/kotlin/ranges/Progressions.kt):
  Int constructor validation, first/last/step and iterator semantics.
- [ArrayIterator.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/jvm/runtime/kotlin/jvm/internal/ArrayIterator.kt):
  successful cursor increment and stable exhaustion behavior.
- The filter and Int final-element sources and hashes remain in the preceding
  filter document.

ETS replacements are fixed typed array/cursor/progression runtime declarations
selected by exact symbols/types. Kotlin iterator objects become callback-backed
runtime classes; arrays replace the bounded collection representation; Kotlin
exceptions become target Error throws. No Kotlin/JS backend body reuse or
arbitrary runtime interoperability is claimed.

## Verification

All paths below are relative to `tests/stdlib`. JVM processes run sequentially
with `JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`.

- Public CLI RED: `.build/iteration.86X6wV/cli.stdout`, unsupported actual
  Array.get; lane2 supplied the pass-created type normalization in its module.
- Type-only RED: `.build/runtime-types.Xrzfs7/test.stderr`, omitted runtime
  declaration; initial GREEN `.build/runtime-types.MJwofT/test.stdout`.
- Signature RED: `.build/iteration-probe.tz3yPs/probe.stderr`, altered List
  dispatch receiver accepted; `.build/iteration-probe.cnL4he/probe.stderr`,
  actual empty-array factory unsupported. Both reproduce from actual frontend IR.
- `check-iteration.mjs` compares 69 public CLI/JVM same-source cases: empty and
  generic/nullable inputs, cursor order/state/exhaustion, mutation, array bounds
  and replacement, lazy MIN/MAX cursors and composed progression operations.
  Frozen GREEN: `.build/iteration.eDishr/result.json` (69 cases).
- `probe-iteration.sh --verify` records exact actual symbols/body availability
  and mutates resolved declarations/calls, asserting rejection without lowering
  children. GREEN `.build/iteration-probe.Yc28NJ/probe.stdout`: 47 accepted
  actual calls and 248 malformed signatures rejected.
- `check-iteration-modules.mjs` uses three unchanged Kotlin producer/consumer/
  bridge files for JVM and public CLI. It checks generated cross-file types,
  rejects callback assignments, and executes five JVM-parity cases including
  shared state, nulls and lazy extreme ranges. `sdk/IterationModules.ets` consumes
  those generated modules; main owns the actual SDK harness and evidence.
  Frozen GREEN: `.build/iteration-modules.z1XsCo/result.json` (five cases,
  cross-file static checking, both readonly callbacks). The unchanged `modules/`
  directory in that run was supplied to main for actual SDK integration.
- `check-runtime-types.sh` checks type-only selection and malformed identities;
  `check-runtime-tree.sh` retains the previous traversal/dependency tests and
  asserts every one of exactly 18 helper functions plus two runtime classes.
  Frozen inventory/traversal GREEN: `.build/runtime-tree.dcH859/test.stdout`
  (26 paths, five function kinds, shared output and pre-emission validation).
  Frozen type-only GREEN: `.build/runtime-types.yFeZaz/test.stdout`.
- Lane2's independently run `../iteration/.work/run-VP7tFg/result.json` is
  GREEN on these frozen stdlib hashes: 47 JVM/host cases, two public CLI
  rejections (Sequence/custom Iterable) and a type-only fixture. This is lane2
  integration evidence, not another suite run by lane3.

Host execution uses the installed SDK TypeScript parser on unchanged generated
text. It is not actual ETS SDK acceptance. No device tests, review, commit or
push were performed by this lane. Main owns frozen full regression and SDK.

## Changed files

Production: `src/stdlib/IterationRules.kt`, `StandardLibraryRules.kt`,
`StandardLibrarySupport.kt`, `StandardLibraryDependencies.kt`.

Tests: `IterationProbe.kt`, `IterationOracle.kt`, `IterationModuleOracle.kt`,
`RuntimeTypes.kt`, `RuntimeDependencies.kt`, `probe-iteration.sh`,
`check-iteration.mjs`, `check-iteration-modules.mjs`, `check-runtime-types.sh`,
`check-symbols.sh`, `fixtures/Iteration.kt`, the three files in
`fixtures/iteration-modules/`, and `sdk/IterationModules.ets`.

Documentation: this file and the historical scope/freeze link in
`collection-filter.md`. Earlier fixtures and oracles remain intact.

The shared external-type and UI-tree work was supplied by main, and the
official loop-pass integration/type normalization by lane2. Neither required
this lane to edit outside its ownership boundary.

## Production freeze

Production is frozen at the following SHA-256 values; only focused test evidence
and this document may be updated during main's final integration run.

```text
002718e1897bf9ab5d23cb22f9300bb186d89fa30792663c857ee423dca791ad  IterationRules.kt
3b5bd2446f1c523c87cb16a1a929ab1406cfdeba1975e2d830268743f540eb87  StandardLibraryDependencies.kt
cdcad4b39a4adcd68273cb29f1d7ec127ea6c33e6b5c6b141e86bac82f5146a6  StandardLibraryRules.kt
d20a96935d35063c96422b613cf1e5092b32a64cc573f4087f57cd3978292cdb  StandardLibrarySupport.kt
```
