# S1.4: KLIB collection dependency architecture

This increment audits the collection paths that previously mixed common Kotlin
algorithms, target representations and compiler intrinsics. It moves the KLIB
`Iterable.filter`, map, non-indexed flat-map and `firstOrNull` paths through
official serialized common bodies and one symbol-bound collection runtime seam. Source/JVM
compatibility adapters remain because the public source compiler does not yet
enter a `KlibSession`.

## Classification

| Path | Classification | Current boundary |
| --- | --- | --- |
| `List` / `MutableList` construction, including empty construction | Unified Kotlin-compatible ETS representation primitive | The supported representation is typed `Array<T>`. Existing source/JVM rules keep `listOf`, `mutableListOf` and sized factories working. The KLIB filter path binds the exact no-argument `ArrayList` constructor to an empty typed array. |
| `Iterable` / `List` traversal | Unified Kotlin-compatible ETS runtime primitive | The exact linked `Iterable.iterator` symbol selects `__etsArrayIterator`; the return type is the existing typed `__etsIterator<T>`. |
| `Iterator.hasNext` / `next` | Unified Kotlin-compatible ETS runtime primitive | Exact linked symbols select typed `__etsIterator` members. These calls are representation operations, not borrowed JS stdlib bodies. |
| `filter`, `filterTo`, `filterNot`, `filterNotTo` | Official common body reuse | Explicit canonical symbols authorize the four serialized bodies. After official common inlining, only empty construction, traversal and `MutableCollection.add` cross the symbol-bound runtime seam. |
| `map` / `mapTo` | Official common body reuse | The linked common bodies use symbol-bound `collectionSizeOrDefault`, capacity construction, traversal and append primitives. Capacity is evaluated once; the target array representation does not expose reserved capacity. |
| `mapNotNull` / `mapNotNullTo` | Official common body reuse | The linked closure also reuses official `forEach` and `let` bodies. Null filtering stays in common IR; the target seam only allocates, traverses and appends. |
| `mapIndexed` / `mapIndexedTo` / nullable-result variants | Official common body reuse | Common IR owns the index variable, callback order and null filtering. The exact linked `checkIndexOverflow` symbol supplies the language-level negative-index guard after ordinary Int32 increment wrapping. |
| `flatMap` / `flatMapTo` | Official common body reuse | Common IR owns callback invocation and outer traversal. The exact linked `kotlin.collections.addAll` extension crosses one typed iterable append boundary, preserving nested empties and element order. Indexed flat-map variants are outside this increment. |
| `firstOrNull()` / `firstOrNull(predicate)` | Official common body reuse | The ordinary no-argument body is emitted as a selected dependency declaration with its canonical symbol; the inline predicate overload uses the official common inliner. Exact `List.isEmpty`, `List.get` and iterator symbols cross the typed collection seam. |
| empty predicates (`isEmpty`, `isNotEmpty`) | Unified Kotlin-compatible ETS representation primitive | The array-backed collection representation supplies a typed length comparison. There is no need to interpret a platform collection implementation. |
| `repeat` | Official common inline body candidate | General KLIB lowering has no completed repeat closure in this increment. Existing UI-specific handling stays isolated; no new name rule or runtime claim is added. |
| `let` | Official common body reuse | S1 already proves explicit canonical approval and official inlining of `kotlin.let`. The source/JVM `LetRule` remains as the compatibility path. |
| `FunctionN.invoke`, `EQEQ` and compiler-generated type operations | True compiler/language intrinsic | These are handled by language lowering after inlining. They are not modeled as KLIB runtime functions. Primitive arithmetic such as `Int.rem` remains a typed target primitive (`__etsIntRem`), not an intrinsic-body claim. |

No source API is selected by a name in `KlibCollectionRuntimeRule`. Its binding
object contains canonical linked symbols for the constructors and collection
operations needed by an approved closure. Every call is selected with symbol
identity and then checked against resolved target receiver, type argument,
value argument and result types. Names such as `__etsArrayIterator`,
`__etsListAdd` and `__etsListAddAll` identify target runtime declarations only.

The official `filterTo` body includes an erased
`MutableCollection<in Any?>` cast. The adapter maps that representation only
through the exact owner class of the bound `add` symbol. It does not recognize
arbitrary collection names or admit platform collection bodies.

## Main-path proof

`tests/klib/collection-common/run.mjs` compiles the consumer to a Kotlin 2.1.20
KLIB, deletes its source directory, links the pinned JS stdlib, and discovers
the inline closure from the consumer's canonical `filter` and `filterNot`
symbols. The resulting decisions record:

- four `REUSABLE_BODY` entries from
  `common/src/generated/_Collections.kt`;
- five distinct `TARGET_REPLACEMENT` signatures from the pinned KLIB;
- direct typed runtime roots `__etsIterator`, `__etsArrayIterator`,
  `__etsIntRem` and `__etsListAdd`;
- no `__etsListFilter` and no `kotlin.js` output.

The emitted ETS passes strict TypeScript checking and produces the same three
filter/filterNot pairs as the JVM, including empty input and Int limits. This is
host evidence; SDK and device execution were not run.

The same harness reruns the lowering with the exact bound `add` symbol
deliberately declined. It requires `UNSUPPORTED_KLIB_DEPENDENCY`, the canonical
stdlib KLIB path, the `js/builtins/Collections.kt` declaration span, a call site
linked to the deleted `Consumer.kt`, and no ETS file. There is no fallback to
the old name-based filter helper.

`tests/klib/collection-map-common/run.mjs` proves the map follow-on. Its approved
closure is exactly `map`, `mapTo`, `mapNotNull`, `mapNotNullTo`, `forEach` and
`let`. The two additional residual primitives are the exact capacity
`ArrayList` constructor and `collectionSizeOrDefault`; neither is selected by a
name in production. The capacity argument and default-size argument are both
evaluated once, while the array-backed target uses `length` and does not expose
reserved capacity. Typed output contains the iterator, checked Int division and
remainder, and append roots, with no `__etsListMap` or `kotlin.js` output.

The JVM/typed-ETS oracle covers ordinary, empty and Int-boundary inputs and the
nullable callback result consumed by `mapNotNull`. A second run omits the exact
capacity-constructor binding and requires a source-linked
`UNSUPPORTED_KLIB_DEPENDENCY` with no target file. Existing source/JVM
`__etsListMap` compatibility remains until public compilation enters the KLIB
session.

`tests/klib/collection-map-indexed-common/run.mjs` proves the indexed follow-on.
Its official closure is exactly `mapIndexed`, `mapIndexedTo`,
`mapIndexedNotNull`, `mapIndexedNotNullTo`, `forEachIndexed` and `let`. Index
increment remains ordinary common IR and lowers through the shared Int32 path
as `index + 1 | 0`. The exact linked `checkIndexOverflow` symbol becomes a typed
guard that rejects a wrapped negative index with Kotlin's `ArithmeticException`
category and `Index overflow has happened.` message. No indexed-map-specific
runtime helper is introduced. Because allocating more than `Int.MAX_VALUE`
elements is not a practical host test, the harness also fault-injects an
`Int.MAX_VALUE` initial index into a copy of the generated typed program and
executes two iterations; the second iteration must take the overflow branch.

`tests/klib/collection-flat-map-common/run.mjs` proves the non-indexed flat-map
follow-on. Its official closure is exactly `flatMap` and `flatMapTo`. The exact
linked `kotlin.collections.addAll` extension maps the mutable destination and
the transformed `Iterable<R>` to the shared typed array representation, then
calls `__etsListAddAll<R>`. The helper snapshots the input length, appends in
iteration order and returns whether any element was added. No flat-map-specific
API rule or `__etsListMap` call is used.

The JVM/typed-ETS oracle covers an empty outer iterable, an empty transformed
iterable, stable nested element order and exactly one callback per outer
element. A second run declines the exact `addAll` symbol and requires a
source-linked `UNSUPPORTED_KLIB_DEPENDENCY` from
`src/kotlin/collections/MutableCollections.kt`, with no ETS file. Indexed
flat-map variants remain outside this increment.

`tests/klib/collection-first-or-null-common/run.mjs` proves ordinary dependency
body admission. The exact no-argument `Iterable.firstOrNull` declaration is
materialized as the sole declaration from its dependency file and lowered into
`_Collections.ets`; the predicate overload remains inline. Calls to either
approved symbol bypass source/JVM compatibility adapters, so the existing
name-based `__etsListFirstOrNull` helper is absent. The official no-argument
body keeps its `List` fast path and iterator fallback. Because `Iterable<T>` and
`List<T>` share the supported `Array<T>` representation, the body’s runtime
type test resolves through that shared typed representation.

The JVM/typed-ETS oracle covers empty input, first-element selection, predicate
hit and miss, and exact predicate callback counts. Removing the selected
ordinary body reports its `_Collections.kt` declaration and consumer call site.
Removing the exact `List.get` primitive reports both its builtins declaration
and the call site inside the selected official body. Both cases raise
`UNSUPPORTED_KLIB_DEPENDENCY` before any ETS file is written.

## Reproduction and frozen evidence

Use the pinned stdlib KLIB through `KOTLIN_JS_STDLIB`:

```sh
node tests/klib/collection-common/run.mjs
node tests/klib/collection-map-common/run.mjs
node tests/klib/collection-map-indexed-common/run.mjs
node tests/klib/collection-flat-map-common/run.mjs
node tests/klib/collection-first-or-null-common/run.mjs
node tests/klib/capabilities/run.mjs
node tests/klib/run.mjs
node tests/klib/portable-common/run.mjs
node tests/binary-bodies/r2e/run.mjs
node tests/binary-bodies/r2e/replay.mjs tests/binary-bodies/r2e/.work/<completed-run>
node tests/stdlib/check-filter.mjs
node tests/stdlib/check-iteration.mjs
```

The checked-in [evidence record](klib-collection-architecture-evidence.json)
plus the [map evidence](klib-collection-map-evidence.json) and
[indexed-map evidence](klib-collection-map-indexed-evidence.json) and
[flat-map evidence](klib-collection-flat-map-evidence.json) and
[first-or-null evidence](klib-collection-first-or-null-evidence.json) contain
the pinned hashes, provenance, results and completed run directories.
Only the dependency KLIB seam, its focused fixture and these documents change
across these collection increments. Compose, UI and project adapter files are
untouched.
