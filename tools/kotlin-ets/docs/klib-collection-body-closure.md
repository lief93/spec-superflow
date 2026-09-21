# filter / map / firstOrNull body-closure spike

Status: research only. Stdlib `CallRule`s are **not** deleted.

Goal: decide whether `kotlin.collections.filter`, `map`, and no-arg `firstOrNull`
can converge through official KLIB IR + inlining to a small primitive set, instead
of one ETS helper per API.

## Commands

From `tools/kotlin-ets`, with the pinned 2.1.20 JS stdlib KLIB:

```sh
KOTLIN_JS_STDLIB=<kotlin-stdlib-js-2.1.20.klib> node tests/klib/run.mjs
KOTLIN_JS_STDLIB=<kotlin-stdlib-js-2.1.20.klib> node tests/klib/closure/run.mjs
```

The second command compiles `tests/klib/closure/Consumer.kt` with official
`K2JSCompiler` to a KLIB, deletes producer sources, then loads the KLIB with
`KlibLoader` and walks reachable bound `IrFunctionSymbol`s from:

- `klibclosure.filterEven` → `Iterable.filter`
- `klibclosure.mapPlusOne` → `Iterable.map`
- `klibclosure.firstOrNullValue` → `List.firstOrNull`

Identity is `function.symbol` / `IdSignature`, recorded beside display FQNames.
JS stdlib is a linker dependency, not a translated ETS module.

JVM oracle for the consumer (must match before IR claims):

| kind | input | JVM result |
| --- | --- | --- |
| filter even | `[1,2,3,4]` | `2,4` |
| map +1 | `[1,2,3,4]` | `2,3,4,5` |
| firstOrNull | `[1,2,3,4]` | `1` |
| firstOrNull | `[]` | `null` |

Live run: `tests/klib/closure/.work/run-nMWV9W`.
`PASS closure spike JVM oracle ["2,4","2,3,4,5","1","null"]`.

## Official stdlib bodies (Kotlin 2.1.20 common)

Source: `libraries/stdlib/common/src/generated/_Collections.kt` at tag `v2.1.20`.

```text
filter
  -> filterTo(ArrayList<T>(), predicate)
    -> for (element in this) if (predicate(element)) destination.add(element)
      -> iterator / hasNext / next
      -> MutableCollection.add
      -> ArrayList.<init>

map
  -> mapTo(ArrayList<R>(collectionSizeOrDefault(10)), transform)
    -> collectionSizeOrDefault
    -> for (item in this) destination.add(transform(item))
      -> iterator / hasNext / next
      -> MutableCollection.add
      -> ArrayList.<init>(capacity)

firstOrNull() on List
  -> if (isEmpty()) null else this[0]

firstOrNull() on Iterable
  -> iterator(); if (!hasNext()) null else next()
```

`firstOrNull` is **not** inline. `filter` and `map` are inline. The consumer
calls the `List` overload of `firstOrNull`; the Iterable iterator fallback is
not on this graph.

## Classification policy

| Kind | Meaning |
| --- | --- |
| `COMMON_IR_BODY` | Official deserialized body present; not `external` |
| `TARGET_NEUTRAL_PRIMITIVE` | No body, but the operation is a collection/int primitive ETS already models (`iterator`, `add`, `get`, `size`, `isEmpty`, `Int.plus`/`rem`) |
| `JS_SPECIFIC` | `kotlin.js` package or JS intrinsic origin |
| `MISSING_BODY` | Bound declaration, no IR body, not classified as a primitive |
| `UNSUPPORTED_EXTERNAL` | `isExternal` |

A body on `ArrayList.<init>` is still not an ETS primitive: walking it reaches
`kotlin.js.js`. Presence of a KLIB body is not permission to emit JS stdlib.

## Live official graph (run-nMWV9W)

Linked modules: `<kotlin>`, `<consumer>`. Translated: `<consumer>` only.

### filterEven

Entry: `klibclosure/filterEven|filterEven(kotlin.collections.List<kotlin.Int>){}[0]`

| kind | signature | fqName | body | inline |
| --- | --- | --- | --- | --- |
| COMMON_IR_BODY | `klibclosure/filterEven\|filterEven(kotlin.collections.List<kotlin.Int>){}[0]` | `klibclosure.filterEven` | true | false |
| COMMON_IR_BODY | `kotlin.collections/filter\|filter@kotlin.collections.Iterable<0:0>(kotlin.Function1<0:0,kotlin.Boolean>){0§<kotlin.Any?>}[0]` | `kotlin.collections.filter` | true | true |
| MISSING_BODY | `kotlin.internal.ir/EQEQ\|EQEQ(kotlin.Any?;kotlin.Any?){}[0]` | `kotlin.internal.ir.EQEQ` | false | false |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin/Int.rem\|rem(kotlin.Int){}[0]` | `kotlin.Int.rem` | false | false |
| COMMON_IR_BODY | `kotlin.collections/filterTo\|filterTo@kotlin.collections.Iterable<0:0>(0:1;kotlin.Function1<0:0,kotlin.Boolean>){0§<kotlin.Any?>;1§<kotlin.collections.MutableCollection<in\|0:0>>}[0]` | `kotlin.collections.filterTo` | true | true |
| COMMON_IR_BODY | `kotlin.collections/ArrayList.<init>\|<init>(){}[0]` | `kotlin.collections.ArrayList.<init>` | true | false |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin.collections/Iterable.iterator\|iterator(){}[0]` | `kotlin.collections.Iterable.iterator` | false | false |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin.collections/Iterator.hasNext\|hasNext(){}[0]` | `kotlin.collections.Iterator.hasNext` | false | false |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin.collections/Iterator.next\|next(){}[0]` | `kotlin.collections.Iterator.next` | false | false |
| MISSING_BODY | `kotlin/Function1.invoke\|invoke(1:0){}[0]` | `kotlin.Function1.invoke` | false | false |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin.collections/MutableCollection.add\|add(1:0){}[0]` | `kotlin.collections.MutableCollection.add` | false | false |
| COMMON_IR_BODY | `kotlin.collections/ArrayList.<init>\|<init>(kotlin.Array<kotlin.Any?>){}[0]` | `kotlin.collections.ArrayList.<init>` | true | false |
| COMMON_IR_BODY | `kotlin/emptyArray\|emptyArray(){0§<kotlin.Any?>}[0]` | `kotlin.emptyArray` | true | true |
| COMMON_IR_BODY | `kotlin.collections/AbstractMutableList.<init>\|<init>(){}[0]` | `kotlin.collections.AbstractMutableList.<init>` | true | false |
| UNSUPPORTED_EXTERNAL | `kotlin.js/js\|js(kotlin.String){}[0]` | `kotlin.js.js` | false | false |
| COMMON_IR_BODY | `kotlin.collections/AbstractMutableCollection.<init>\|<init>(){}[0]` | `kotlin.collections.AbstractMutableCollection.<init>` | true | false |
| COMMON_IR_BODY | `kotlin.collections/AbstractCollection.<init>\|<init>(){}[0]` | `kotlin.collections.AbstractCollection.<init>` | true | false |
| COMMON_IR_BODY | `kotlin/Any.<init>\|<init>(){}[0]` | `kotlin.Any.<init>` | true | false |

The even-predicate is not a separate IR function: `Int.rem` and `EQEQ` sit on
`filterEven`'s own body.

### mapPlusOne

Entry: `klibclosure/mapPlusOne|mapPlusOne(kotlin.collections.List<kotlin.Int>){}[0]`

| kind | signature | fqName | body | inline |
| --- | --- | --- | --- | --- |
| COMMON_IR_BODY | `klibclosure/mapPlusOne\|mapPlusOne(kotlin.collections.List<kotlin.Int>){}[0]` | `klibclosure.mapPlusOne` | true | false |
| COMMON_IR_BODY | `kotlin.collections/map\|map@kotlin.collections.Iterable<0:0>(kotlin.Function1<0:0,0:1>){0§<kotlin.Any?>;1§<kotlin.Any?>}[0]` | `kotlin.collections.map` | true | true |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin/Int.plus\|plus(kotlin.Int){}[0]` | `kotlin.Int.plus` | false | false |
| COMMON_IR_BODY | `kotlin.collections/mapTo\|mapTo@kotlin.collections.Iterable<0:0>(0:2;kotlin.Function1<0:0,0:1>){0§<kotlin.Any?>;1§<kotlin.Any?>;2§<kotlin.collections.MutableCollection<in\|0:1>>}[0]` | `kotlin.collections.mapTo` | true | true |
| COMMON_IR_BODY | `kotlin.collections/ArrayList.<init>\|<init>(kotlin.Int){}[0]` | `kotlin.collections.ArrayList.<init>` | true | false |
| COMMON_IR_BODY | `kotlin.collections/collectionSizeOrDefault\|collectionSizeOrDefault@kotlin.collections.Iterable<0:0>(kotlin.Int){0§<kotlin.Any?>}[0]` | `kotlin.collections.collectionSizeOrDefault` | true | false |
| TARGET_NEUTRAL_PRIMITIVE | iterator / hasNext / next / add | (same signatures as filter) | false | false |
| MISSING_BODY | `kotlin/Function1.invoke\|invoke(1:0){}[0]` | `kotlin.Function1.invoke` | false | false |
| COMMON_IR_BODY | `kotlin.collections/ArrayList.<init>\|<init>(kotlin.Array<kotlin.Any?>){}[0]` | `kotlin.collections.ArrayList.<init>` | true | false |
| COMMON_IR_BODY | `kotlin/emptyArray\|emptyArray(){0§<kotlin.Any?>}[0]` | `kotlin.emptyArray` | true | true |
| COMMON_IR_BODY | `kotlin/require\|require(kotlin.Boolean;kotlin.Function0<kotlin.Any>){}[0]` | `kotlin.require` | true | true |
| MISSING_BODY | `kotlin.internal.ir/greaterOrEqual\|greaterOrEqual(kotlin.Int;kotlin.Int){}[0]` | `kotlin.internal.ir.greaterOrEqual` | false | false |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin.collections/Collection.size.<get-size>\|<get-size>(){}[0]` | `kotlin.collections.Collection.<get-size>` | false | false |
| COMMON_IR_BODY | AbstractMutableList / AbstractMutableCollection / AbstractCollection / Any constructors | | true | false |
| UNSUPPORTED_EXTERNAL | `kotlin.js/js\|js(kotlin.String){}[0]` | `kotlin.js.js` | false | false |
| MISSING_BODY | `kotlin/Boolean.not\|not(){}[0]` | `kotlin.Boolean.not` | false | false |
| MISSING_BODY | `kotlin/Function0.invoke\|invoke(){}[0]` | `kotlin.Function0.invoke` | false | false |
| COMMON_IR_BODY | `kotlin/IllegalArgumentException.<init>\|<init>(kotlin.String?){}[0]` | `kotlin.IllegalArgumentException.<init>` | true | false |
| MISSING_BODY | `kotlin/Any.toString\|toString(){}[0]` | `kotlin.Any.toString` | false | false |
| COMMON_IR_BODY | RuntimeException / Exception constructors | | true | false |
| UNSUPPORTED_EXTERNAL | `kotlin/Throwable.<init>\|<init>(kotlin.String?){}[0]` | `kotlin.Throwable.<init>` | false | false |

### firstOrNullValue

Entry: `klibclosure/firstOrNullValue|firstOrNullValue(kotlin.collections.List<kotlin.Int>){}[0]`

| kind | signature | fqName | body | inline |
| --- | --- | --- | --- | --- |
| COMMON_IR_BODY | `klibclosure/firstOrNullValue\|firstOrNullValue(kotlin.collections.List<kotlin.Int>){}[0]` | `klibclosure.firstOrNullValue` | true | false |
| COMMON_IR_BODY | `kotlin.collections/firstOrNull\|firstOrNull@kotlin.collections.List<0:0>(){0§<kotlin.Any?>}[0]` | `kotlin.collections.firstOrNull` | true | **false** |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin.collections/List.isEmpty\|isEmpty(){}[0]` | `kotlin.collections.List.isEmpty` | false | false |
| TARGET_NEUTRAL_PRIMITIVE | `kotlin.collections/List.get\|get(kotlin.Int){}[0]` | `kotlin.collections.List.get` | false | false |

## Can existing CallRules be deleted?

| Rule | Helper | Delete now? | Blocker from this dump |
| --- | --- | --- | --- |
| `kotlin.collections.filter` / `filterNot` | `__etsListFilter` | **No** | Residual graph is not a small primitive set. Walking `ArrayList.<init>` reaches `UNSUPPORTED_EXTERNAL kotlin.js.js`. `Function1.invoke` and `kotlin.internal.ir.EQEQ` have no body. ETS does not run official stdlib inlining over KLIB stdlib, does not emit `ArrayList`, and does not implement `Iterable.iterator` as a general protocol. The current helper is an array-backed primitive. |
| `kotlin.collections.map` | `__etsListMap` / `__etsSetMap` | **No** | Same `kotlin.js.js` constructor path, plus `collectionSizeOrDefault` → `require` → `Throwable.<init>` (`UNSUPPORTED_EXTERNAL`) and missing `Boolean.not` / `Function0.invoke` / `Any.toString`. KLIB `Iterable.map` also does not encode the ETS List vs Set helper split. |
| `kotlin.collections.firstOrNull` | `__etsListFirstOrNull` | **No** | Function is **not** inline. The List overload body exists (`isEmpty`/`get`), but ETS has no general List protocol beyond the array-backed helper, and this spike did not lower the body through the production pipeline or the JVM/ETS oracle. |

Theoretically later, **if and only if** all of the following are proved with
JVM/ETS differential oracles on the existing fixtures:

1. Official inliner consumes the KLIB `filter`/`map` bodies at the call site
   without selecting JS stdlib for emission.
2. Remaining callees are only primitives ETS already lowers (`add`, `get`,
   `isEmpty`, `iterator` on array-backed lists, `Int` ops) or existing CallRules.
3. `ArrayList` construction does not require `kotlin.js.js`.
4. `filterNot`, empty input, predicate exceptions, and concurrent-modification
   checks match the current documented array-backed contract.
5. No JS-specific intrinsic remains on the residual graph.

Until that proof exists, keep the rules. Do not change semantics to make the
route look complete.

## What this spike is not

- Not an increase in stdlib API support.
- Not permission to run `JsLoweringPhases`.
- Not a claim that JS stdlib collection classes are ETS `Array`.
- Not a public CLI.
- Not an ETS lowering of these three consumer functions; the oracle is JVM-only
  for the spike, plus official IR inspection after producer sources are deleted.
