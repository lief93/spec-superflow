# Source-bounded collection runtime modules

## R2B scope and inventory

This lane owns new `tests/stdlib/bounded-modules/` fixtures and this document.
Only reproduced stdlib gaps may justify editing `src/stdlib/`. Production is
currently unchanged. Shared target/language work belongs to main and the
language owner; no new UI resolver, expression parser, or collection family is
introduced.

R2A already proved generic List map/filter/Iterator flow across source helpers,
including distinct T/R identities, nullable/primitive/source-object values,
same-input JVM/host behavior, runtime closure and exact imports. This increment
adds calls to nongeneric source methods on T, where T has a source class or
instantiated source interface upper bound.

Existing `StandardLibraryRules` keeps source type-parameter identities on
map/filter helper calls; it delegates callbacks to Language. The fixed generic
runtime bodies need no bound-specific dispatch. `StandardLibraryDependencies`
already traverses function signature type-parameter bounds, class bounds and
typed expression references through `walkEts`. `Modules` already includes bound
type dependencies from both declarations and referenced generic signatures.
No missing stdlib behavior has yet been demonstrated.

## Shared contract

The fixtures use only existing `EtsTypeParameter.upperBound`,
`EtsTypeParameterType`, `EtsNamedType.arguments`, `EtsMember.symbolId`, and
`EtsFunctionType`. The typed callback's receiver remains T, with the canonical
source interface method ID and a signature substituted through
`RuntimeReadable<number>`. No cast, invented source symbol, name alias, or
duplicate bound/member resolver is used.

Main's validator must resolve members through a nonnullable source upper bound,
check canonical member identity/signatures, and reject unavailable/cyclic
bounds. Language must lower the actual source callback member calls on T.
No additional shared API was required. Compilation uses the shared contract
and requires main's explicit matching build slot.

## Source fixtures

Four original Kotlin modules are inputs to both the JVM oracle and public CLI:

| Module | Purpose | Expected runtime functions |
| --- | --- | --- |
| `BoundedModels.kt` | `BoundedReadable<R>`, source class bound, concrete number/text implementations, method tracing/failures/actions | `__etsIntDiv`, `__etsListAdd` |
| `BoundedCollections.kt` | Map/filter/filterNot callbacks invoke `read()` on source-bounded T | `__etsListMap`, `__etsListFilter` |
| `BoundedIterators.kt` | Cross-file retained List/cursor flow and `next().read()` on bounded T | `__etsArrayIterator` |
| `BoundedCases.kt` | Concrete interface/class/String paths, empty input, method exceptions and structural mutation | `__etsListGet`, `__etsListAdd` |

Only Iterators and Cases need `__etsIterator`. Imported helper implementations
must not leak into callers' runtime closures. Source bound imports include
dependencies in referenced generic signatures, even when the concrete call's
type arguments alone do not spell the bound type.

The prepared oracle has 26 records comparing values, member evaluation order,
exception prefixes and mutation effects. It includes fresh-result/source-object
identity and exact method/callback exception identity on both JVM and host.
The add-during-method fixture records the changed source length before the
bounded map/filter runtime throws. Map/filter method failures must stop before
the third element, and filtering followed by next/read must show the separate
method invocation in its trace. Empty collections do not invoke source methods.

The host runner typechecks and executes unchanged emitted ETS using the
installed SDK TypeScript parser/transpiler. It asserts exact imports and helper
inventories, and rejects two concrete type arguments that violate the interface
or class bound. This is host evidence, not an actual SDK build.

## Typed negatives

`BoundedRuntimeContract.kt` constructs four independent typed modules:
`RuntimeBoundModel`, `RuntimeBoundProject`, `RuntimeBoundFilter`, and
`RuntimeBoundConsumer`. It uses the existing emitter/provider and `walkEts` to
check canonical callback member identity, exact bound/source imports, one
provider invocation per module, the map/filter/iterator helper closure, and
file-order invariance. It writes emitted modules unchanged after assertions.

Six malformed typed callbacks must fail target validation before any provider
invocation: missing bound, unknown bound ID, cyclic bound, unknown member,
incorrect substituted signature, and foreign member identity. These test the
existing shared boundary rather than duplicating its validation algorithm.

## Reuse and limits

The pinned Kotlin v2.1.20 collection body inspection and exact ETS replacement
are documented in [generic-runtime-modules.md](generic-runtime-modules.md) and
[collection-filter.md](collection-filter.md). R2B reuses those fixed generic
helpers and the same actual-IR/runtime pipeline unchanged. No new official body
is loaded, copied, fabricated or parsed from source text by this increment.

This is the supported array-backed List/Iterable/cursor path, not arbitrary JVM
iterator interoperability. No Array map/filter, Sequence, new collection
families, multiple/nullable bounds, projected/reified generics, generic member
methods, overloads, or bound-specific runtime dispatch is added. Failure guards
remain length-based on supported mutable collections; length-restoring mutation,
general modCount semantics, concurrency and JVM exception-class compatibility
are outside the claim. Shared target/language gaps are reported to their owners,
not patched here.

## Execution gates

Main ran the frozen fixtures serially after the shared target/language updates.
Evidence paths below are relative to `tests/stdlib/bounded-modules/.work/`:

- `typed-RMmr4l/result.json`: GREEN for four typed modules, exact bound/source
  imports and runtime closure, canonical member identity, one provider call per
  module, file-order invariance, and all six malformed bound/member negatives
  rejected before runtime selection.
- `public-qpy2tK/result.json` and `host-result.json`: GREEN for 26 same-input
  JVM/public-CLI/host records, exact imports/helper closure, member order/error
  prefixes, mutation effects, source-object/error identity, and two bound type
  negatives (TypeScript diagnostic 2344 for each).

All commands exited 0 and both runs passed every snapshot/live-input hash guard.
Each result manifest records the four unchanged emitted modules, their output
directory, and SHA-256 hashes. No stdlib production changes or fixture corrections
were needed. These are main-owned execution results, not additional lane builds.
Actual SDK/native verification remains pending and main-owned (`sdk: false`).
Production and tests remain frozen; only this documentation evidence was updated.

Run only with main's explicit matching slot grant:

```sh
KOTLIN_ETS_BOUNDED_SLOT=typed node tools/kotlin-ets/tests/stdlib/bounded-modules/run.mjs typed
KOTLIN_ETS_BOUNDED_SLOT=public node tools/kotlin-ets/tests/stdlib/bounded-modules/run.mjs public
```

Typed and public slots are separate. Each run snapshots exact production,
fixture and harness inputs under ignored `.work/`, records commands/statuses
and SHA-256 hashes, and requires both snapshot and live hashes unchanged before
marking `result.json` passed. JVM commands run serially with
`JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`.
Main owns subsequent SDK/native integration after production freeze.

New files: `.gitignore`, `BoundedRuntimeContract.kt`, `BoundedOracle.kt`,
`run.mjs`, `host.mjs`, and the four original source files under
`tests/stdlib/bounded-modules/fixtures/`; plus this document. No source runtime,
shared module, or existing test file has been edited for R2B preparation.
