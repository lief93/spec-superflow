# Portable Kotlin body → KLIB → ETS experiment

This is a bounded experiment, not automatic stdlib replacement or public KLIB
CLI support. It answers whether pure Kotlin control flow and a generic
higher-order collection body can survive official KLIB serialization/linking
and lower to ETS with a small, explicit target boundary.

## Route and scope

`tests/klib/portable-common/Bodies.kt` contains equivalent pure Kotlin bodies for
an ascending, inclusive, unit-step Int range, its stateful iterator, and a generic
`mapBody` loop. It is a deliberately small source port, not a claim to have
extracted or transplanted the complete official stdlib. The iterator uses the
common `IntProgressionIterator` termination order: return the final value once,
mark the iterator exhausted, and never increment that final value. The map loop
allocates its destination, visits the source in order, and appends each callback
result, as common `Iterable.map` does.

The JVM oracle compares these bodies to actual JVM `IntRange` / `Iterable.map`,
not merely a second execution of the same implementation.

```
Signature-only primitives + portable bodies + consumer
  → Kotlin 2.1.20 K2JSCompiler → three independent KLIBs
  → delete temporary producer sources
  → production KlibLoader / official loadIr / JsIrLinker
  → original bodies + consumer IrModuleFragments
  → existing EtsBackend / typed target validation / module printer
  → strict DevEco TypeScript host checking and Node semantic execution
```

The pinned `kotlin-stdlib-js` KLIB is still needed for the official producer and
linker type/signature universe. Its JS function bodies are not selected for
translation. There is no JS compiler output, JS runtime import, per-map rule,
new parser, synthetic combined IR module, or general-purpose stdlib inliner.
`mapBody` is intentionally non-inline, so emitted ordinary generic calls prove
that this route does not depend on the official inliner.

## Explicit actual boundary

The signature-only `Primitives.kt` KLIB exposes exactly three external functions.
The proof adapter matches their canonical deserialized symbols. It is confined
to the experiment and is not registered in the production compiler.

| Primitive | JVM actual used by oracle | ETS actual |
| --- | --- | --- |
| `newList<T>()` | `mutableListOf<T>()` | typed empty `Array<T>` expression |
| `append<T>(list, value)` | `MutableList.add` | existing `__etsListAdd<T>` |
| `exhausted()` | throw `NoSuchElementException` | existing target throwable representation |

No new collection runtime is necessary. Kotlin integer operations and function
invocation remain language intrinsics. `Int.rem` in the nullable-output test
uses the existing checked remainder helper; this is not part of the map body.
The backend also emits its existing object identity `hashCode` implementation
for source classes, using native `Math` operations. No JS stdlib hash body is
consumed; identity-hash behavior is not an acceptance claim of this experiment.

## Reproduce

From `tools/kotlin-ets`:

```sh
KOTLIN_JS_STDLIB=/absolute/path/kotlin-stdlib-js-2.1.20.klib \
  node tests/klib/portable-common/run.mjs
```

Prerequisites match `tests/klib/run.mjs`: pinned compiler in the existing Gradle
cache, Java, Node, and the installed DevEco TypeScript host. No dependencies are
downloaded. The run retains commands, IR, closure classification, runtime
references, hashes, and oracle results in `tests/klib/portable-common/.work`.

The harness also removes every materialized function body from the dependency-only
stdlib module and lowers again with a fresh backend. It requires byte-identical
ETS output after removal. A residual-call allowlist rejects anything beyond the
selected pure bodies, the three exact primitive symbols, and observed language
intrinsics. The emitted map function must retain its generic parameter and loop;
its runtime declaration allowlist cannot contain map/filter/progression helpers.

Reversing selected modules is checked modulo a bijective renaming of generated
loop labels. The current lowerer numbers labels across the whole session, so
this fixture does **not** claim byte-identical output under module reordering.
With unchanged module order, repeated lowering is byte-identical. This existing
label allocation behavior was left outside the experiment's implementation scope.

The ascending unit-step range is the entire range contract. Descending or
stepped progressions, `Long`/`Char` ranges, and full `Iterable`/`Collection`
implementations are outside this experiment. The API uses `IntSpan.mapBody`
explicitly; it does not intercept source calls to `kotlin.collections.map`.

## Boundaries that cannot be copied blindly

- JS `ArrayList` constructors eventually call `kotlin.js.js`. Allocation and
  append therefore terminate at an explicit target actual; JS implementation
  bodies are not translated.
- `Iterable`, collection storage, iterator protocols, and mutability cannot be
  assumed to share one target representation. This experiment owns its range
  and iterator classes and only maps destination lists to ETS arrays. It makes
  no claim about arbitrary custom collections or fail-fast mutable iterators.
- `Function1.invoke`, integer operators, comparisons, equality, and `Any`
  constructor delegation require language lowering. A missing IR body for these
  symbols is not a missing collection implementation.
- `Nothing`/throwing and exception construction require target runtime behavior.
  The exhausted-iterator primitive supplies it without entering JS Throwable
  constructors. Callback exceptions must propagate by identity.
- Reified operations, non-local returns, inline-only contracts, default argument
  lowering, and `expect`/`actual` resolution are not proved here. The external
  primitive KLIB is an explicit actual seam, not a multiplatform compiler setup.
- This does not justify deleting existing map/filter CallRules. Automatic
  ownership-aware source selection, full collection contracts, and target SDK
  acceptance would need their own proof before production substitution.

Host execution is evidence for the tested pure-language semantics. It is not
ArkTS SDK, ArkVM, device, UI, or full Kotlin standard-library acceptance.

## Recorded verification

Frozen run: `tests/klib/portable-common/.work/run-Y3cB1x`.

- 24 real linked function bodies, including constructors, accessors, lambdas,
  iterator methods, and the non-inline generic map body.
- 36 JVM/ETS value comparisons across nine range inputs: ordinary, empty,
  negative-to-positive, singleton, `Int.MIN_VALUE`, `Int.MAX_VALUE`, and overflow
  of the callback's `Int + 1`. Generic outputs include Int, String, and nullable Int.
- Nine exhausted-iterator cases check exception category and null source message;
  separate checks cover independent cursors and callback exception identity with
  exact visitation trace `1,2,3,` (no fourth callback after failure).
- Strict DevEco TypeScript host checks pass. Generated modules import only the
  selected body module. The generic map body retains its own iterator loop.
- Removal of **1,335** materialized stdlib function bodies leaves generated ETS
  byte-identical. Reversed module input changes only generated loop-label names.
- All source/compiler implementation and KLIB hashes remain unchanged during the
  run. The temporary producer sources no longer exist when the loader runs.
- Existing `tests/klib/run.mjs` also passes in `tests/klib/.work/run-iBvEuF`:
  four JVM/ETS results, preserved cross-library names/types, exact output-order
  stability for that original fixture, and missing transitive-library rejection.

Generated output SHA-256:

| File | SHA-256 |
| --- | --- |
| `Bodies.ets` | `a681b734fe89d76b87376bf7926e44f96821d9956018c29ce0645af5bb182f3f` |
| `Consumer.ets` | `6bcd737adc2f42eceb93d87e0f3980ba5605663ae33e5fb5d112d22537ba240b` |

Conclusion: **the bounded pure-body route works with the existing loader and
backend**. The range/iterator/map algorithms can live in ordinary portable Kotlin
bodies; only storage and exhaustion cross the explicit actual boundary. The
experiment adds no production CallRules and requires no new runtime library.
It establishes a viable implementation route for carefully selected portable
bodies, not automatic compatibility with all common or JS stdlib declarations.
