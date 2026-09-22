# S1.4: KLIB collection dependency architecture

This increment audits the collection paths that previously mixed common Kotlin
algorithms, target representations and compiler intrinsics. It moves the KLIB
`Iterable.filter` and `filterNot` path through official serialized common bodies
and one symbol-bound collection runtime seam. Source/JVM compatibility adapters
remain because the public source compiler does not yet enter a `KlibSession`.

## Classification

| Path | Classification | Current boundary |
| --- | --- | --- |
| `List` / `MutableList` construction, including empty construction | Unified Kotlin-compatible ETS representation primitive | The supported representation is typed `Array<T>`. Existing source/JVM rules keep `listOf`, `mutableListOf` and sized factories working. The KLIB filter path binds the exact no-argument `ArrayList` constructor to an empty typed array. |
| `Iterable` / `List` traversal | Unified Kotlin-compatible ETS runtime primitive | The exact linked `Iterable.iterator` symbol selects `__etsArrayIterator`; the return type is the existing typed `__etsIterator<T>`. |
| `Iterator.hasNext` / `next` | Unified Kotlin-compatible ETS runtime primitive | Exact linked symbols select typed `__etsIterator` members. These calls are representation operations, not borrowed JS stdlib bodies. |
| `filter`, `filterTo`, `filterNot`, `filterNotTo` | Official common body reuse | Explicit canonical symbols authorize the four serialized bodies. After official common inlining, only empty construction, traversal and `MutableCollection.add` cross the symbol-bound runtime seam. |
| `map` / `mapTo` | Official common body reuse | The linked common bodies use symbol-bound `collectionSizeOrDefault`, capacity construction, traversal and append primitives. Capacity is evaluated once; the target array representation does not expose reserved capacity. |
| `mapNotNull` / `mapNotNullTo` | Official common body reuse | The linked closure also reuses official `forEach` and `let` bodies. Null filtering stays in common IR; the target seam only allocates, traverses and appends. |
| empty predicates (`isEmpty`, `isNotEmpty`) | Unified Kotlin-compatible ETS representation primitive | The array-backed collection representation supplies a typed length comparison. There is no need to interpret a platform collection implementation. |
| `repeat` | Official common inline body candidate | General KLIB lowering has no completed repeat closure in this increment. Existing UI-specific handling stays isolated; no new name rule or runtime claim is added. |
| `let` | Official common body reuse | S1 already proves explicit canonical approval and official inlining of `kotlin.let`. The source/JVM `LetRule` remains as the compatibility path. |
| `FunctionN.invoke`, `EQEQ` and compiler-generated type operations | True compiler/language intrinsic | These are handled by language lowering after inlining. They are not modeled as KLIB runtime functions. Primitive arithmetic such as `Int.rem` remains a typed target primitive (`__etsIntRem`), not an intrinsic-body claim. |

No source API is selected by a name in `KlibCollectionRuntimeRule`. Its binding
object contains five canonical linked symbols: the empty constructor,
`iterator`, `hasNext`, `next` and `add`. Every call is selected with symbol
identity and then checked against resolved target receiver, argument and result
types. Names such as `__etsArrayIterator` and `__etsListAdd` identify target
runtime declarations only.

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

The next unproved collection group is `mapIndexed`/`mapIndexedNotNull` and their
`*To` variants, which add index-overflow behavior, followed by `flatMap`/`flatMapTo`,
which require a typed `addAll` or nested-traversal boundary. The non-inline
`firstOrNull` body also still needs an explicit dependency-body admission path
or a retained representation primitive.

## Reproduction and frozen evidence

Use the pinned stdlib KLIB through `KOTLIN_JS_STDLIB`:

```sh
node tests/klib/collection-common/run.mjs
node tests/klib/collection-map-common/run.mjs
node tests/klib/capabilities/run.mjs
node tests/klib/run.mjs
node tests/klib/portable-common/run.mjs
node tests/binary-bodies/r2e/run.mjs
node tests/binary-bodies/r2e/replay.mjs tests/binary-bodies/r2e/.work/<completed-run>
node tests/stdlib/check-filter.mjs
node tests/stdlib/check-iteration.mjs
```

The checked-in [evidence record](klib-collection-architecture-evidence.json)
and [map evidence](klib-collection-map-evidence.json) contain the pinned hashes,
provenance, results and completed run directories.
Only the dependency KLIB seam, its focused fixture and these documents change
across these collection increments. Compose, UI and project adapter files are
untouched.
