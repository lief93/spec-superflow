# Bounded receiver modules

## R2B scope and contracts

This lane owns `tests/modules/bounded-receivers/` and this document. No output
production gap has been demonstrated: `Modules.kt` already traverses upper
bounds on function/class parameters and recursively collects source type IDs
from their actual arguments. No production edit is made during preparation.

No new target schema/API is needed. Main owns resolving an
`EtsTypeParameterType` receiver through its declared nonnullable source-class or
source-interface upper bound, including parameter-bound chains. The resulting
`EtsMember` retains its canonical declaration ID and instantiated signature.
Neither a receiver cast nor an external-symbol/alias escape is used.

## Finite fixture

`BoundedFixture.kt` reuses the accepted generic-heritage fixture's six class and
interface modules read-only, preserving their existing source spans and target
identities. The contract runner snapshots that fixture too. Three new modules
contain only ordinary source functions/classes:

- `BoundedCalls.kt`: `readClass<R extends Middle<TokenModel>>`,
  `readInterface<R extends Readable<TokenModel>>`,
  `readParametric<V, R extends Readable<V>>`, and
  `readChain<R extends Middle<TokenModel>, S extends R>`. Each uses an explicitly
  bound `reader` parameter and a nongeneric `read` member with its original ID.
- `ReaderBox.kt`: `ReaderBox<R extends Readable<TokenModel>>` stores its explicit
  constructor parameter and calls the canonical interface member on the field's
  type-parameter receiver. Its lexical `this` remains inside the owning class.
- `Signatures.kt`: body-empty ordinary acceptance functions use source upper
  bounds only, proving imports originate from constraint metadata even when no
  member or returned source type could cause those imports indirectly.

The positives check exact file objects/spans, names and parameters, preserved
receiver type parameters, instantiated member types, original member IDs,
function/class/bound-only imports, deduplication, ordering and no import of
member/binder names. The generated modules have no UI declarations or aliases.

Fourteen negatives require source-linked `InvalidTarget` before runtime output:
unknown member name; missing member ID; a same-named member ID belonging to a different declaration;
mismatched substituted signature; absent upper bound; unknown bound identity;
external/unavailable bound; nullable bound; cyclic parameter-bound chain;
wrong generic bound arguments; hidden interface bound; hidden argument type;
hidden class-parameter bound; and conflicting same-named source-bound imports.
These cases test declared identities, not printed-name matching.

## Prepared verification

Only after main freezes bound resolution and grants the compiler/SDK slot:

```sh
node tools/kotlin-ets/tests/modules/bounded-receivers/run.mjs
node tools/kotlin-ets/tests/modules/bounded-receivers/sdk.mjs <successful-contract-evidence>
```

The target runner freezes exact target/output/runtime/fixture sources before
compilation, records their SHA256 hashes, and uses
`-XX:ActiveProcessorCount=2 -XX:+UseSerialGC`. It does not build or run the public
CLI, frontend, Language or Compose implementation.

The actual SDK runner copies every generated module byte-for-byte into a fresh
clone of an existing Harmony seed and compiles the fixed `Index.ets` consumer.
That consumer exercises class/interface/parameterized/chained bounds, a generic
class receiver, signature-only functions, and concrete model/string/number
arguments. It is a fixed SDK host, not new production UI adaptation. Override
`KOTLIN_ETS_SDK_SEED` only to select another existing seed.

All nine generated modules require matching clean typechecker/hash evidence.
Eight runtime modules must appear in `filesInfo.txt`; the pure generic
`Readable.ets` interface uses the accepted unchanged `ui-sdk-evidence.mjs`
checker/dependency proof. The interface remains covered without fake runtime
exports, stubs or edited ETS. Source/consumer/verifier hashes and ABC/HAP outputs
are recorded, and stale production inputs are rejected.

## Typed proof

Main's frozen run passed all nine modules and fourteen source-linked negatives:
`tests/modules/bounded-receivers/.work/contract-AOCwAw/result.json`.
Compilation and contract execution exited successfully; the manifest records
`passed: true`, `currentInputsMatchSnapshot: true`, and all emitted module hashes.
The frozen validator SHA256 is
`61cd0e3ccf3bde7decd52118ba44024c2955f62f10efe2add3a652df56b7aee5`;
unchanged `Modules.kt` SHA256 is
`f597bc89e6d2184a29a3dc06f9d9f2e40bf9163c7ce5de0695c79f65eadd149f`.

Actual SDK verification remains pending under main, using this contract evidence.
Source, tests and generated modules remain frozen; this update changes docs only.
This lane does not claim source-level Kotlin bound lowering, JVM differential,
ArkVM execution or native interaction acceptance. Main owns bound validation
and whole-round integration. No review, commit, push or device operation.
