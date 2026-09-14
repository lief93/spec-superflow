# Bounded Common Loop Lowering

## Official Pass and Hook

`src/core/ForLoops.kt` exposes the internal hook
`lowerForLoops(input: JvmFir2IrPipelineArtifact)`. The frontend owner calls it
after `lowerLocalDeclarations(translated)` and before
`lowerStringConcatenations(translated)`. This lane does not edit `Frontend.kt`.

The hook invokes actual Kotlin 2.1.20 `ForLoopsLowering` using the existing real
compiler context, with `CommonBackendContext.preferJavaLikeCounterLoop = false`.
This selects the common form rather than JVM/HotSpot-specific update placement.
The official pass owns range recognition, induction variables, cached bounds,
empty-range guards, overflow-safe last-element termination, step checks and
break/continue retargeting. No source parser, hand-written loop recognizer,
or copied JVM/JS emitted code is introduced.

Pinned references are present under
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/org/jetbrains/kotlin/backend/common/lower/loops/`:

- `ForLoopsLowering.kt`: `lowerHeader`, `lowerWhileLoop`, and `lower` preserve
  transparent composites and remap jump targets.
- `ProgressionLoopHeader.kt`: `loopInitStatements` preserves bound/step evaluation
  order; `buildLoop` tests the original iteration value when induction can overflow.
- `JavaLikeCounterLoopBuilder.kt`: explains the JVM-only condition/update shapes
  deliberately not selected by this wrapper.
- `handlers/StepHandler.kt`: produces last-element and argument-error calls that
  remain the standard-library lane's responsibility.
- `IndexedGetLoopHeader.kt`: arrays use indexed reads and cached size, not a
  materialized copy; later element replacements remain visible.
- `HeaderProcessor.kt` and `handlers/DefaultIterableHandler.kt`: not every
  iterable is optimized. Ordinary List/Iterable loops retain the actual resolved
  iterator/hasNext/next protocol. This wrapper does not fabricate index loops.

Official loop builders can introduce a generic member call whose result still
contains the member owner's type parameter beneath an instantiated implicit
cast. The wrapper records original call identities before the pass, then uses
official `getTypeSubstitutionMap` and `IrTypeSubstitutor` only on newly created
calls. Generic receiver substitution requires the actual receiver classifier to
match the declaration parent. Existing calls, symbols, offsets and outer casts
are untouched; unsupported receiver shapes still fail in ordinary lowering.

## Target Adaptation

`IrComposite` statements have transparent scope and lower into the current
`Scope`; nonempty `IrBlock` statements still retain an `EtsBlock` and nested scope.
This is a typed IR distinction, not a printed-brace rewrite.

An official overflow-safe do-while condition can reference the immutable
`FOR_LOOP_VARIABLE` declared in its body. ETS block-scoped const declarations are
not visible in the trailing condition. The language lane therefore preserves the
original per-iteration const and assigns its value to a separate, typed condition
snapshot immediately after initialization. Only the condition's symbol binding
is redirected to that snapshot. No initializer is duplicated, no default value
is invented, and original body/lambda references continue to bind the per-iteration
const. A native `continue` reaches the same official condition with the current
snapshot. Nested jumps use official loop identities.

Snapshots are allowed only for immutable `FOR_LOOP_VARIABLE` declarations lowered
directly in the loop body. Other body-local condition references fail source-linked
rather than hoisting mutable or conditional bindings unsafely. No target AST,
validator or printer extension is required.
Nested functions are not inspected by this condition-scope scan; their parameters
and captures are resolved by ordinary lambda lowering in their own lexical scope.

## Boundary and Checks

The positive slice includes Int `..`, `until`, `downTo`, `step`, stored/composed
progressions and `reversed`; source List/Iterable backed by the supported list
representation; Array<T> and IntArray iteration. Ordinary while/do-while and
native closures remain covered. Existing residual stdlib adapters are resolved
`kotlin.internal.ProgressionUtilKt.getProgressionLastElement(Int, Int, Int): Int`
and `kotlin.internal.ir.illegalArgumentException(String): Nothing`.

Collection loops retain their official iterator protocol, while array/progression
loops use the official lowering when recognized. The stdlib lane owns exact
resolved residual adapters and pinned runtime behavior, not this wrapper.
Runtime iterator types are `EtsNamedType("__etsIterator", [T],
"stdlib:__etsIterator", external = true)`; `__etsArrayIterator` is a factory, not
the type name. Progression types use `__etsIntProgression` with the corresponding
`stdlib:` identity and `external = true`. Source classes remain nonexternal.
Typed runtime collection includes type-only references and validates exact owned
identity/name/arity; no raw-output scanning or target namespace whitelist is used.

Long ranges, Sequence, arbitrary source-defined Iterable implementations, other
primitive-array adapter families and general collection mutation APIs are not
claimed. Their unsupported shapes fail source-linked rather than becoming
Object or assumed generic iterators. List structural-mutation checking is bounded
by the supported operations; this is not a complete Java collection runtime.

Run from the repository root:

```sh
node tools/kotlin-ets/tests/loops/typed.mjs
node tools/kotlin-ets/tests/loops/run.mjs
node tools/kotlin-ets/tests/iteration/typed.mjs
node tools/kotlin-ets/tests/iteration/run.mjs
```

The typed test retains actual pre/post official IR and resolved call inventory,
verifies removal of iterator variables, source/name/symbol preservation, original
jump targets remapped to retained loops, and preservation of native lambdas/loops.
It then validates the independent target tree and immutable snapshot bindings.
The public CLI test compiles the same `Loops.kt` on JVM, compares 38 host results
(including invalid step errors), accepts the two historical List/composed RED
inputs, and retains the Long rejection with source offsets and no output file.
Cases include MIN/MAX endpoints, empty ranges,
positive/negative step direction, effect order, nested jumps, deferred per-iteration
closures, lambdas within do-while conditions, and official shared mutable capture.
Generated code is never edited.

The iteration suite compares the same input on JVM and generated host output:
generic and empty collections/arrays, replacement visibility, evaluate-once,
nested labeled jumps, deferred iteration captures, official mutable shared
captures, cursor exhaustion and modification checks, composed step direction,
adjusted endpoints, invalid-step effect order and extreme nonmaterializing
progressions. A separate real-IR check records the exact compiler jar and calls,
array result-type instantiation, preserved names/source/symbols, collection
iterators retained versus optimized loops, and typed runtime dependency closure.
Type-only runtime declarations and Sequence/custom-Iterable rejections are tested
at the public CLI boundary.

Each runner retains commands and errors in its `.work` directory. These tests are
not an SDK certification; the integration owner compiles unchanged generated ETS
with the actual Harmony SDK separately. No device operations are part of this lane.
