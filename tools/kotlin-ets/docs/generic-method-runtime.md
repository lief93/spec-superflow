# Generic member collection runtime

## R2C scope

New fixtures live only in `tests/stdlib/generic-methods/`. No production,
shared target/language/module, existing test, or UI file is changed. The finite
family remains array-backed List map/filter/filterNot and Iterator. Generic
source member calls are Language's responsibility, not new stdlib adapters.

The existing target contract is sufficient: separate class/method binder IDs,
`EtsFunctionType.typeParameters`, `EtsCall.typeArguments`, and canonical
`EtsMember.symbolId`. Class substitution remains `memberType`/`etsSubstitute`;
method arguments instantiate at the call. Main's `sameMethodSignature` compares
only method-owned binders positionally, including substituted bounds, parameters
and result. Call/member identities remain exact. The fixtures deliberately use
R/B/D method binder names and different declaration IDs across interface/base/
derived methods, while their class binders remain independent.

`walkEts`, `StandardLibraryRuntime` and `EtsRuntimeSupport` already traverse class
and method signatures/bounds, nested callbacks, references, and call type
arguments. No missing stdlib behavior is demonstrated by preparation, and no
runtime or guard change is made speculatively.

## Official references and reuse

Read the requested cached official compiler source root
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`:

- `org/jetbrains/kotlin/ir/types/IrTypeSubstitutor.kt`: substitutions are keyed by
  `IrTypeParameterSymbol`; unknown parameters are retained only under its explicit
  allow-empty policy. Replacement recursively handles arguments/nullability.
- `org/jetbrains/kotlin/ir/util/IrUtils.kt`, `getTypeSubstitutionMap` and
  `makeTypeParameterSubstitutionMap`: class receiver arguments and function
  arguments map to their own symbols; declaration remapping uses positional
  symbol correspondence rather than matching names.
- `org/jetbrains/kotlin/ir/util/IrTypeParameterRemapper.kt`: moved declarations
  remap references through explicit old/new parameter identities.

The pinned collection body inspection is recorded in
[generic-runtime-modules.md](generic-runtime-modules.md): official Kotlin
v2.1.20 [map/mapTo/filter bodies](https://raw.githubusercontent.com/JetBrains/kotlin/refs/tags/v2.1.20/libraries/stdlib/common/src/generated/_Collections.kt)
use ordered destination construction. This increment reuses the existing typed
adapter calls and fixed ETS array-backed helpers. No official body is newly
loaded, copied, fabricated, or replaced by parsing source strings. Official
source inspection is not a claim that a dependency body is loadable here.

## Exact source inputs

Both JVM and public CLI compile the same five original files under
`tests/stdlib/generic-methods/fixtures/`:

| Source / emitted basename | Contract | Exact runtime functions |
| --- | --- | --- |
| `MethodContracts` | `MethodProjector<C>.project<R>` and `MethodItem` | None |
| `MethodProjectors` | Base implementation with B, derived override with D; observable dispatch markers | `__etsListAdd` |
| `MethodPipeline` | Generic member `mapped<R>` composes map/filter/iterator; selection predicates call `project<Boolean>` | `__etsListMap`, `__etsListFilter`, `__etsArrayIterator` |
| `MethodConsumers` | Cross-file generic member `next<R>` / `more<R>` | None |
| `MethodCases` | Direct/base/interface invocation, concrete instantiation, order/mutation/failure workflows | `__etsIntDiv`, `__etsListGet`, `__etsListAdd`, `__etsListMap` |

Only Pipeline, Consumers and Cases require `__etsIterator`. Runtime dependencies
must not leak from imported source implementations into consumers. `host.mjs`
asserts exact imports as well as helper/class inventories using the existing
SDK TypeScript parser, not a source-name resolver. Generated module text is
typechecked and executed unchanged.

`MethodOracle.kt` is JVM-only test code, not a CLI source input. Object/error
identity checks live in that oracle and the host harness around the same compiled
helpers; no source `===` operation is added to CLI fixtures.

## Finite case manifest

`cases.json` lists every invocation and original scalar argument; the host checks
that the JVM records match this independent manifest before invoking outputs.
The prepared set has 22 records:

- Four dispatch modes: direct derived, derived through base/interface views, and
  a base instance; map transforms Int to String with distinct dispatch markers.
- One Int-to-source-object generic pipeline; map completes before filtering, and
  a separate generic member consumer advances the shared cursor.
- One empty pipeline, two mixed filter/filterNot selections, and four all-true/
  all-false polarity combinations with complete callback traces.
- Two add-during-callback mutations, two callback arithmetic failures, and two
  cursor exhaustion/structural-mutation failures, preserving observed prefixes.
- One receiver/argument/callback-construction order case; every effect must run
  once before the method callback as specified by original Kotlin evaluation.
- One fresh-result/source-object identity case and two exact thrown-object
  identity cases on JVM and host.

The host also rejects four generic type errors: callback result, class-bound
input, cross-file cursor element, and method type-argument arity.

## Typed contract

`MethodRuntimeContract.kt` independently constructs four modules:
`RuntimeMethodPort`, `RuntimeMethodBase`, `RuntimeMethodDerived`, and
`RuntimeMethodCalls`. Base/derived implementations each own exactly one map
helper. The direct/base/interface caller module owns filter, iterator factory,
and iterator class, but no imported map implementation.

Assertions use the existing validator/emitter/provider and `walkEts`: distinct
R/B/D binders, exact canonical member IDs, exact source imports, one provider call
per original module, fixed runtime closure, and file-order invariance. Seven
malformed cases must fail before any provider invocation: absent method type
argument, method/class binder confusion, incompatible callback input, incorrect
class substitution, foreign member identity, incompatible override bound, and
an override result capturing the class binder instead of its method binder.

## Runners and SDK handoff

No builds are authorized by this document. Main must grant each serialized mode:

```sh
KOTLIN_ETS_METHOD_SLOT=typed node tools/kotlin-ets/tests/stdlib/generic-methods/run.mjs typed
KOTLIN_ETS_METHOD_SLOT=public node tools/kotlin-ets/tests/stdlib/generic-methods/run.mjs public
```

Each run snapshots exact production, fixtures, manifest, harness and launcher
inputs in an ignored unique `.work/` directory. It records commands, statuses,
stdout/stderr, input/output SHA-256 hashes and pass status in `result.json`.
Success requires frozen and live input hashes unchanged. JVM commands run
serially with `JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`.

The five public `.ets` outputs and four independent typed `.ets` outputs have
distinct basenames for combined SDK use. `SdkConsumer.ets` is a separate manual
consumer, never substituted for generated output; it imports the unchanged
public modules and exports `genericMethodSdkCheck(): number`. Host typechecking
includes it. Main may include it alongside exact public output in the actual SDK.
Convenient concrete generated exports are `pipelineCase(trace: Array<number>):
number` and `dispatchCase(mode: number, trace: Array<number>): string`.

## Verification evidence

Main executed the frozen runners serially. Paths below are relative to
`tests/stdlib/generic-methods/.work/`:

- `typed-oz33ff/typed.stderr`: retained fixture failure, "Source class requires
  one target constructor". The derived super call correctly required an explicit
  base constructor, but the typed base fixture declared only its generic method.
  The owned test fix added an empty no-argument base constructor; no validator
  bypass, positive method change, or negative-expectation change was made.
- `typed-u4vQXI/result.json`: GREEN for four typed modules, distinct override
  binders, exact canonical calls/imports/helper closure, one provider per module,
  order invariance, and all seven malformed cases rejected before the provider.
- `public-Qa2R0X/result.json` and `host-result.json`: GREEN for 22 same-input
  JVM/public-CLI/host pairs and four type negatives (2345, 2345, 2345, 2558).
  Includes dispatch/evaluation/mutation/error traces, source-object and exception
  identity, exact imports/runtime closure, and typechecking the unchanged manual
  SDK consumer beside the five generated modules.

All GREEN commands exited 0 and their snapshot/live-input hash guards passed.
Each manifest records unchanged emitted module paths and SHA-256 hashes. Stdlib
production remained unchanged; only the missing typed fixture constructor needed
correction. Main owns these executions; no additional lane build was run.
Source and tests remain frozen. Actual SDK/general regressions are in progress
under main; SDK/native acceptance is not claimed by these results (`sdk: false`).

## Unsupported boundaries

No new collection families, Array map/filter, Sequence, arbitrary JVM iterator
interoperability, reified/binary generic members, overloaded methods, generic
constructors/accessors, or new UI resolution is included. Length-change failure
checks remain restricted to the existing supported array-backed mutable path;
length-restoring mutation, arbitrary modCount/concurrency, and JVM exception-class
compatibility are not promised. Source/target integration gaps are routed to
their owners; stdlib changes require a reproduced stdlib-specific failure.
