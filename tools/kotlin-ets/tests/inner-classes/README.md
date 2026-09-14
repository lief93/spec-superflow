# Ordinary Inner Class Language Proof

This directory owns the R2H language consumer proof. The `core/` subdirectory and
the shared `docs/inner-classes.md` contract are owned by main.

## Scope

Three named nongeneric inner classes are emitted from their original source
files. `Outer.kt` covers shared outer identity, explicit outer access, mutation,
property/init/default evaluation, and private inner visibility. `Collisions.kt`
forces generated outer field/parameter collisions with source fields, parameters,
and an officially allocated overload name. A top-level `Item` and two lexical
`Item` classes exercise canonical class identity independently of emitted names.
`Calls.kt` constructs them across files and checks named argument ordering and a
side-effectful outer receiver evaluated once. `Oracle.kt` covers five Int seeds,
including both signed boundaries: 20 outcome lines per output mode.

Outer aliasing is observed through mutation and read-back via returned outer
references, sibling inner instances, and independent outer instances. Direct
source `===` is not used: its existing unsupported EQEQEQ intrinsic is outside
this consumer requirement.

`Probe.kt` verifies the registered field/constructor/parameter identities,
canonical outer types and constructor calls, source names, effective visibility,
typed member IDs, valid source spans, and registered-source fallback for absent
field/parameter/reference offsets. Fourteen malformed-IR cases retain exact
diagnostic source checks: missing/duplicate/late initialization; wrong field,
parameter or receiver; same-text spoofed field/parameter origins; wrong field or
parameter type; static/mutable storage; transferred field ownership; and an IR
copy with no transferred registration. Every mutation is restored.

## Running

From `tools/kotlin-ets`, after an exclusive compiler slot grant:

```sh
KOTLIN_ETS_BUILD_SLOT=1 node tests/inner-classes/run.mjs --baseline-language tests/local-classes/captures/.work/green-I5AG8s/frozen/src/language/LanguageLowering.kt
KOTLIN_ETS_BUILD_SLOT=1 node tests/inner-classes/run.mjs
KOTLIN_ETS_BUILD_SLOT=1 node tests/local-classes/captures/run.mjs
KOTLIN_ETS_BUILD_SLOT=1 node tests/local-classes/captures/shadow.mjs
```

The runner snapshots all production Kotlin sources, owned test inputs and the
compiler launcher, checking live and frozen hashes before and after each child.
All JVM children use `-XX:ActiveProcessorCount=2 -XX:+UseSerialGC`. Module imports
must resolve to exported declarations without a source-text alias pass. Reversed
source input order must produce byte-identical modules. Generated ETS is parsed
and transpiled directly for Node execution, never edited. This is host parity,
not actual SDK typechecking, a native build, or round completion.

## Evidence

- `.work/red-zZBW2W`: retained initial failure on unsupported source EQEQEQ;
  not an inner-field semantic RED. The fixture was changed to a mutation-based
  aliasing witness without changing production operator support.
- `.work/red-zLZWX4`: original JVM executes; the preserved R2G language consumer
  rejects the official outer field. Its original undefined field offsets are
  retained in the diagnostic evidence, not replaced after the run.
- `.work/green-dObjSt`: initial 20-outcome/14-negative GREEN before adding direct
  absent-offset reference assertions.
- `.work/green-THZBKn`: final inner suite GREEN, all 20 JVM outcomes matching both
  flat and three-module output, 14 source-linked negatives, explicit absent-offset
  reference checks, canonical field/type/constructor identities, and deterministic
  module bytes.
- `tests/local-classes/captures/.work/green-gMBwjK`: R2G capture regression GREEN,
  30 JVM outcomes matching flat/modules and eight source-linked negatives.
- `tests/local-classes/captures/.work/shadow-green-DO0E9b`: R2G retained/fresh
  generated-name and imported-overload regression GREEN, 15 JVM outcomes matching
  flat/modules with canonical source identities preserved.

Final consumer `LanguageLowering.kt` SHA-256:
`59fbaef94806ce338b1d28be5ae6df3e43cf6e09df3cfd6a0b911b103c86b62c`.
Full source hashes and commands are recorded in each result manifest.

Generic enclosing/inner binders, non-Any inner heritage, secondary constructors,
anonymous objects, and local-capture combinations remain excluded
by the fixed core contract. This lane does not alter that contract, target nodes,
validation rules, output modules, or the printer.

R2I adds named nongeneric inner chains in `chains/`; run `node
tests/inner-classes/chains/run.mjs` from the tool root. See `docs/inner-chains.md`
for semantic typechecking, immediate outer-link and multi-level mutation evidence.
