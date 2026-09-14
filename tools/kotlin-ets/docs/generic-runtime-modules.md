# Generic collection runtime modules

## R2A scope and inventory

This increment owns `src/stdlib/` only for reproduced gaps and new tests under
`tests/stdlib/generic-modules/`. No target, language, frontend, module emitter,
UI resolver, or unrelated collection family changes are authorized here.

Existing support before this increment:

- List/MutableList `map<T, R>` selects `__etsListMap<T, R>`.
- List/MutableList/array-backed Iterable `filter<T>` and `filterNot<T>` select
  `__etsListFilter<T>` with a Boolean polarity.
- Array/List/array-backed Iterable iteration uses exact external
  `stdlib:__etsIterator<T>` and the separate `stdlib:__etsArrayIterator<T>` factory.
- Generic Array get/set and list access use existing typed helper calls.
- `fixtures/iteration-modules/` already covers cross-file generic cursor
  production/consumption for Int and nullable Int. This increment adds distinct
  map input/output types, composed generic helpers, and source-object values.

Array map/filter, Sequence map, Iterable-typed map, and star-projected filter
remain explicit negative cases. Source member functions named map/filter must
be declined by the stdlib adapter, leaving their actual bodies to Language.
No new shared API or generic heritage behavior is required by these fixtures.

## Implementation reuse

First inspected `/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`; its
compiler sources do not contain the generated collection runtime bodies.
The pinned official Kotlin v2.1.20
[_Collections.kt](https://raw.githubusercontent.com/JetBrains/kotlin/refs/tags/v2.1.20/libraries/stdlib/common/src/generated/_Collections.kt)
defines map with separate T/R parameters, creates a destination, and invokes
mapTo, whose loop transforms and appends in iteration order. The filterTo loop
tests each original element before appending it.

The tests reuse the existing `Language`/`CallRule` boundary, `EtsCall` type
arguments, `walkEts`-based provider, and fixed array-backed runtime unchanged.
The existing ETS runtime replaces collection allocation/iterator/add operations
with arrays, indexing/push, and its documented length-change guard. No official
body is newly linked, fabricated, parsed from text, or substituted into source.
Actual declaration bodies/signatures are reported by the resolved-IR probe;
reading official source alone is not a claim of a loadable dependency body.

## Fixtures and contracts

Four same-input source modules:

| Module | Role | Expected runtime functions |
| --- | --- | --- |
| `GenericModels.kt` | Plain source item and invariant generic box | None |
| `GenericCollections.kt` | Generic map/filter/filterNot, List/Array cursors, Array get/set | ListMap, ListFilter, ArrayIterator, ArrayGet, ArraySet (all `__ets` prefixed) |
| `GenericConsumers.kt` | Generic next/hasNext, map-then-filter cursor composition, identity transformation | None |
| `GenericCases.kt` | Int, String, nullable Int, source item and nested generic box instantiations | IntDiv, ListGet, ListAdd (all `__ets` prefixed) |

All except Models require the iterator runtime class through typed references;
Consumers must not acquire the producer module's helper functions. Module
imports and helper inventories are exact assertions, not substring presence
checks. The public host test parses and typechecks unchanged emitted modules,
then uses the installed SDK TypeScript transpiler only to execute those modules.
This is not an SDK build.

The prepared differential matrix contains 32 cases covering eager map-before-
filter order, callback counts/prefixes, empty collections/cursors, result values,
source collection preservation, callback exceptions, add-during-map/filter,
add-before-next, and live array element replacement after cursor creation.
Host checks also assert fresh collection allocation, retained source-object
identity, exact propagated callback exception identity, and two cross-file
generic type mismatches rejected by the TypeScript checker.

`GenericSymbols.kt` uses official FIR2IR declarations and mutates/restores only
actual resolved map calls/declarations. It expects seven adapted APIs, seven
unsupported boundaries, and seventeen malformed signature/dispatch cases to
decline without lowering children. Successful calls must retain distinct source
T/R identities in helper arguments, validate as typed generic functions, and
select exactly the expected runtime helper plus its required class. Its small
recording Language records child requests/types; it does not lower or invent
function bodies or parse expressions.

## Gates and evidence

Symbols-only RED/GREEN completed. Paths below are relative to
`tests/stdlib/generic-modules/.work/`:

- `symbols-qX5ITN`: initial probe compiled and exposed seven accepted malformed
  map cases, then stopped on a test attempt to mutate the immutable FIR2IR lazy
  `isInline` flag. The test now mutates the actual call's missing output type
  argument instead; all seventeen independently asserted mutations remain.
- `symbols-cshzm6/symbols.stdout` and `symbols.stderr`: complete canonical RED.
  Seven valid generic APIs passed typed validation/runtime selection, seven
  unsupported APIs declined, but dispatch, super, wrong input-type identity,
  declared result/transform/receiver, and source-origin mutations were accepted
  and each lowered two children. The final assertion failed on those seven
  cases. The production snapshot is retained.
- `symbols-l50rWZ/result.json`: GREEN. Seven actual generic APIs, seven
  unsupported boundaries and all seventeen map mutations passed. Invalid calls
  lowered zero children. Generic T/R identity, helper/class closure and target
  validation passed. Compile/probe commands exited 0; all snapshot/live-input
  SHA-256 guards passed. A pre-existing `core/Contract.kt` opt-in compiler warning
  was not changed by this lane.

The only production change is `StandardLibraryRules.kt`: map now validates the
actual external inline `Iterable<T>.(transform: (T) -> R): List<R>` declaration,
its own T/R parameter identities, and the instantiated non-null invariant
List/MutableList receiver, callback and result before lowering children. It
checks absent dispatch/super, correct arities, and no defaults/varargs/reified
parameters. Receiver coverage is not expanded to Iterable-typed map or arrays.
Runtime definitions and the provider are unchanged. The inspected official
stdlib map body was unavailable on the actual resolved external declaration;
no new body-loading or source rewrite path was introduced.

Main subsequently ran `public-s9GRyF/result.json`: GREEN for all 32 same-input
JVM/public-CLI/host cases, exact module imports/runtime closure, source-object
and callback-error identity, fresh collection allocation, and two rejected
cross-file generic type mismatches. `host-result.json` records the differential
values and identity/type checks. All commands exited 0 and the runner's frozen/
live source hash guards passed. The four unchanged emitted modules and their
SHA-256 hashes are recorded in `result.json`, under `public-s9GRyF/modules/`.
This is main's integration execution, not another lane-owned compiler run.
SDK/native verification remains pending and main-owned (`sdk: false`).

After main grants the matching exclusive build slot:

```sh
KOTLIN_ETS_GENERIC_SLOT=symbols node tools/kotlin-ets/tests/stdlib/generic-modules/run.mjs symbols
KOTLIN_ETS_GENERIC_SLOT=public node tools/kotlin-ets/tests/stdlib/generic-modules/run.mjs public
```

These are separately gated; an isolated slot does not authorize public CLI.
Each runner uses a unique ignored `.work/` evidence directory, snapshots exact
production/fixture/harness inputs, runs JVM work serially with
`JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`, and records
command output/status plus SHA-256 hashes in `result.json`. Final success also
requires frozen and live inputs unchanged. Failed runs retain their snapshots
and logs, with `passed: false`; no failure is reclassified as a skip.

## Boundaries

Generic support does not imply arbitrary JVM iterator interoperability,
projected/captured/reified generics, widened callback input types, custom
Iterable implementations, or new array overloads. Mutation/error evidence is
restricted to the supported array-backed mutable collection path; restoring
length after mutation, arbitrary modCount behavior, concurrency, and JVM
exception-class compatibility are not promised. Typed source class construction
and generic substitution remain owned by the existing language/target layers;
any integration gap there is reported to main, not patched by this lane.

## Changed files and freeze

Production: `src/stdlib/StandardLibraryRules.kt` only.

New tests under `tests/stdlib/generic-modules/`:

- `.gitignore`, `run.mjs`, `host.mjs`
- `GenericSymbols.kt`, `GenericRejected.kt`, `GenericOracle.kt`
- `fixtures/GenericModels.kt`, `fixtures/GenericCollections.kt`
- `fixtures/GenericConsumers.kt`, `fixtures/GenericCases.kt`

Documentation: `docs/generic-runtime-modules.md`.

Production and tests frozen; exclusive compiler slot released to main at
2026-09-13 20:40:37 UTC (2026-09-14 04:40:37 Asia/Taipei). No compiler process
remained. Only this final documentation evidence update followed the release.

```text
002718e1897bf9ab5d23cb22f9300bb186d89fa30792663c857ee423dca791ad  IterationRules.kt
db9f5eb7637970f5b8700c8b4cbfe22c4be6985adde9b623820735eb0c7f2e12  StandardLibraryDependencies.kt
474829b2b4706626ab6f33dc23d7323483671611aa8b616a47a9cf29e2262215  StandardLibraryRules.kt
31e1796be944f0f62bd616f96ac47f43cdec6093b4be86974488b1d4013790ed  StandardLibrarySupport.kt
```
