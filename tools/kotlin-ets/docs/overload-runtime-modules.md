# Overload collection runtime modules

## R2D bounded contract

This increment adds tests only under `tests/stdlib/overloads/`. No stdlib,
language, target, output, core, or UI production changes are made. Source overload
selection belongs to the official resolved `IrCall.symbol.owner`, not a stdlib
adapter, printed-source parser, or runtime `typeof` dispatcher.

Both top-level `choose` declarations are in `OverloadChoices.kt`. Member `select`
and `accept` overloads belong to one final, non-inherited class. Cross-file use
means callers and collection helpers are separate modules; overload declarations
split across multiple IrFiles are explicitly outside this increment.

Main's shared contract appends `EtsFunction.sourceName`; target `name` and
`symbol.name` remain the emitted binding. `symbol.id` uses original source name
and span. Language owns declaration-keyed collision-safe naming. Tests do not
predict suffixes or implement another declaration resolver. The producer records
actual validated binding names so the host can check exact imports and call the
selected exported overload without changing generated output.

Int and Double overloads deliberately have identical ETS signatures. A call to
the other valid declaration is therefore not intrinsically an invalid target
program. Actual source-owner-to-target binding assertions and distinct JVM/host
branch traces prove selection. Validator negatives cover inconsistent IDs,
names, signatures and callback types, not a valid alternative binding.

## Official references and reuse

Inspected the pinned local official source tree:
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`.

- `org/jetbrains/kotlin/ir/backend/js/utils/NameTables.kt`,
  `calculateJsFunctionSignature` at line 120: function signatures use declaration
  names, binders and original IR parameter types before target numeric erasure.
- `org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/JsNameLinkingNamer.kt`,
  `getNameForStaticDeclaration` at line 40 and `getNameForMemberFunction` at line
  61: emitted bindings/imports are based on declarations and member signatures.
- `org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrElementToJsExpressionTransformer.kt`,
  `visitCall`: translation consumes the resolved IrCall rather than selecting
  source overloads from runtime JavaScript values.

These JS naming implementations require backend-specific context and are not
copied into tests as an ETS mangler. The existing official frontend and common
passes are reused through `withKotlinFrontend`, followed by the shared
`EtsBackend`/`Language`/`CallRule` path. Actual bodies remain the original source
bodies. No official library body is newly loaded or fabricated in this batch.

The pinned Kotlin v2.1.20 collection source/body inspection is recorded in
[generic-runtime-modules.md](generic-runtime-modules.md). Ordered destination
construction and the bounded array-backed replacement remain unchanged:
`__etsListMap`, `__etsListFilter`, `__etsArrayIterator`, and the readonly-callback
`__etsIterator`. Dependency selection reuses `walkEts` and
`StandardLibraryRuntime` through `EtsRuntimeSupport`; there is no UI-specific or
overload-specific runtime resolver.

## Inputs and closure

The same five original Kotlin files are compiled for JVM and the public CLI:

| Source / emitted basename | Purpose | Exact helper functions |
| --- | --- | --- |
| `OverloadChoices` | Same-file Int/Double top-level overloads; distinct result/trace branches | `__etsIntDiv`, `__etsListAdd` |
| `OverloadSelector` | Final class numeric method overloads and source object | `__etsListAdd` |
| `OverloadPipeline` | Generic map, filter/filterNot and iterator producers | `__etsListMap`, `__etsListFilter`, `__etsArrayIterator` |
| `OverloadConsumer` | Generic iterator next/hasNext consumer | None |
| `OverloadCases` | Original callbacks, factories and case entry points | `__etsListGet`, `__etsListAdd` |

Only Pipeline, Consumer and Cases need the iterator runtime class. Imported
source implementation helpers must not leak into their callers. Host assertions
check the exact module inventory, imported emitted bindings, helper functions
and runtime classes. They parse emitted ETS with the existing SDK TypeScript
parser for assertions only, never for compiler adaptation or source replacement.

`OverloadOracle.kt` is JVM-only harness code. Object and thrown-object identity
checks surround the same compiled helper calls on JVM and host, avoiding any
new CLI equality or exception-language feature. `negative/Inherited.kt` must
produce a source-linked overload rejection without publishing output.

## Finite proof

`cases.json` declares 21 independent invocation records:

- Four top-level/member Int/Double selection cases with equal numeric inputs.
- Collection/transform/predicate factory evaluation order and once-only calls;
  receiver/argument order inside two map callbacks.
- Two empty pipelines and four true/false filter/filterNot combinations.
- Two add-during-callback failures and two selected-overload arithmetic failures.
- Iterator exhaustion and supported structural mutation across producer/consumer.
- Fresh result/source-object identity, unchanged source order, and two exact
  thrown-object identity cases.

`OverloadBindings.kt` runs the real frontend and backend, retaining borrowed IR
only within its session. It checks six overload declarations and 17 source calls
against target symbol IDs/names/signatures at their original spans, and verifies
the numeric overload signatures erase equally. Source IDs survive emitted name
changes; unique wrapper names remain unchanged. Reversing file visitation must
produce identical modules. The runtime provider must receive each original file
exactly once. `bindings.tsv` and `calls.tsv` retain evidence, and public CLI bytes
must match the producer modules exactly.

`OverloadRuntimeContract.kt` independently builds three typed modules with
source-name-preserving overload IDs, nested collection calls, exact import/helper
closure and one provider call per module. Six malformed variants fail before
provider invocation: unknown ID, binding-name mismatch, signature mismatch,
wrong member identity, changed declaration source identity, and wrong callback
input. It also checks file-order invariance. Main separately owns duplicate-ID
guard tests; this lane does not duplicate their implementation.

Host typechecking includes four negatives: wrong top-level argument, wrong member
argument, generic map callback input mismatch, and wrong iterator element result.

## Commands and handoff

Run only after main grants the matching serialized slot:

```sh
KOTLIN_ETS_OVERLOAD_SLOT=typed node tools/kotlin-ets/tests/stdlib/overloads/run.mjs typed
KOTLIN_ETS_OVERLOAD_SLOT=public node tools/kotlin-ets/tests/stdlib/overloads/run.mjs public
```

Both modes snapshot inputs and record commands, stdout/stderr, statuses and
SHA-256 hashes under a unique ignored `.work/` directory. Passing requires live
and snapshot input hashes unchanged. JVM processes run serially with
`JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`. The public mode
includes the actual-IR probe, JVM oracle, public CLI, unchanged-module host checks
and inherited-overload rejection. No runner performs SDK/device tests.

Manual `SdkConsumer.ets` imports only stable generated wrappers and exports
`overloadSdkCheck(): number`, expected 6452. It must remain unchanged beside all
five exact public modules in main's SDK harness. Convenient generated exports:

```ts
// OverloadCases.ets
numericCase(mode: number, trace: Array<number>): number
onceCase(trace: Array<number>): number
```

## Evidence status

Main granted a serialized integration slot. Evidence under
`tests/stdlib/overloads/.work/`:

- `typed-QLGPA5`: GREEN, three modules, six malformed target cases rejected
  before provider invocation, preserved source IDs, exact imports/helper closure
  and deterministic module order.
- `public-L7plmE`: GREEN, all 21 JVM/public-CLI/host pairs, six source overload
  declarations and 17 actual IR calls, exact source spans/IDs/emitted bindings,
  file-order invariance and identical public-CLI/producer module bytes. Four
  host type negatives and the unchanged inherited-overload source rejection
  passed. The manual SDK consumer typechecked and returned 6452 on the host.

Input hashes passed. The inherited rejection harness was corrected to parse
structured CLI JSON on stdout, as demonstrated by the retained binary public
failure; it now verifies diagnostic code, exact source file and nonempty source
span. Neither the negative fixture nor expected unsupported behavior changed.
The typed run predates that harness-only correction.

This overload test increment made no production edits. During the integration
slot, main separately approved the [Int conversion](int-double-conversion.md)
fix; public-L7plmE used Rules SHA-256
`c398838bb827664ee4fb45d9cf5416ff192665394f9f812cb2c936f1739de8d5`.
The subsequently approved Double comparison increment changes production again.
These are intermediate source-bound proofs, not final combined acceptance;
main reruns all gates on the final source hash. No SDK/native run is claimed.

## Limits

No new collection family, Array map/filter, Sequence, inherited/interface virtual
overloads, overloaded constructors/accessors, cross-IrFile overload groups,
callable-reference selection, default/vararg overload combinations, or generic
erasure-clashing overload declarations are claimed. Numeric overloads do not
imply new Double arithmetic support. Mutation/failure semantics apply only to
the existing supported array-backed mutable collection path, not arbitrary JVM
iterators, modCount interoperability, length-restoring edits or concurrency.
