# Bounded receiver dispatch

R2B language implementation with focused and public CLI evidence. SDK/native
integration remains pending with main. No shared target/output/UI source was
modified in this language lane.

## Finite scope

Source type parameters constrained by one nonnullable source class/interface,
including instantiated generic ancestors and chains of type-parameter bounds,
may invoke nongeneric member methods. Preserve source names, canonical real
member IDs, receiver/argument evaluation order and returned object identity.
Multiple bounds, nullable/unavailable/cyclic resolution, variance, generic member
methods and overload expansion remain outside this batch. The real Kotlin
frontend rejects invalid bound cycles independently.

## Approved contract

No new target fields. Keep the actual receiver as `EtsTypeParameterType`; do not
insert an unchecked cast to its bound. Its enclosing `EtsTypeParameter.upperBound`
records either a source `EtsNamedType` with full argument list and symbol ID, or
another type parameter ID. `EtsMember` retains the canonical real declaration ID
and receiver-instantiated function signature. Main owns target resolution and
checking of those bounds before reusing inherited-member signature validation.

The language-side change is bounded to resolving an `IrTypeParameterSymbol`
receiver's single bound before existing generic owner substitution. Traverse by
declaration identity with a visited set, reject missing/multiple/nullable/cyclic
paths, and preserve all generic arguments. Do not pick the first bound or first
incompatible ancestor path. Nongeneric declared parent methods must use the same
target validation path, even though they need no class-parameter substitution.
Named F-bounds such as `T : Self<T>` terminate at the named `Self` bound; the
argument `T` is preserved, not followed as another bound-chain edge or rejected
as a direct cycle.

## Official reuse

Pinned Kotlin 2.1.20 cache:
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`.

- `org/jetbrains/kotlin/ir/util/IrTypeUtils.kt:56-68`: official
  `IrClassifierSymbol.superTypes()` exposes class and type-parameter bounds
  without reconstructing declarations or selecting a first bound.
- `org/jetbrains/kotlin/ir/util/IrTypeUtils.kt:189-223`: reuse
  `getAllSubstitutedSupertypes` after resolving the constrained class type,
  as already integrated in R2A.
- `org/jetbrains/kotlin/ir/types/IrTypeSubstitutor.kt:27-112`: preserve official
  parameter-symbol substitution and nullability handling through the existing
  owner substitution; do not erase bounds to `Any`/`Object` for member lookup.
- `org/jetbrains/kotlin/ir/util/IrFakeOverrideUtils.kt:38-88`: keep the existing
  `collectRealOverrides` binding to real declarations. No name-only lookup or
  source-text rewrite is introduced.

## Tests

`tests/inheritance/bounds/BoundedReceivers.kt` and `JvmOracle.kt` exercise 40
same-input outcomes across five seeds, including signed overflow endpoints:
interface-bound read, generic class-bound override dispatch, nongeneric interface
bound, instantiated generic ancestor, a two-parameter bound chain, returned
object alias identity, named F-bound dispatch, and effectful receiver/argument
callbacks. `Factory.order` observes receiver-before-argument execution and
duplicate evaluation. Both alias tests mutate the original object after the
generic method returns, then read through the returned alias; a value clone
would retain the previous field value and fail.

Four valid-Kotlin unsupported fixtures retain multiple bounds, nullable bounds,
generic member methods and variance. `InvalidBoundCycle.kt` is a separate
Kotlin/frontend rejection case; it must not be relabeled as a backend success.

Approved serial commands from `tools/kotlin-ets`:

```sh
node tests/inheritance/bounds/probe.mjs
node tests/inheritance/bounds/public.mjs tests/inheritance/bounds/.work/probe-DF5LCl/result.json
```

The public runner takes a successful focused manifest, verifies its recorded
input hashes, invokes the actual launcher and checks both unchanged output bytes
and all original JVM outcomes. Focused negatives invoke the compiled production
entry point; they are not mislabeled as public launcher invocations. Both
runners retain commands/errors/hashes and use
`JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`.

## Initial bounded receiver evidence

- RED: `tests/inheritance/bounds/.work/probe-qsVBE9/result.json`. Original source
  compiles to IR, then the old producer rejects generic member receiver bounds.
  Pre-edit production snapshot: `/tmp/kotlin-ets-bounds-baseline-sQkjUd/src`;
  replay the probe with `KOTLIN_ETS_SOURCE_ROOT` pointing there.
- Focused GREEN: `tests/inheritance/bounds/.work/probe-DF5LCl/result.json`.
  Eight real IR bounded calls preserve uncast type-parameter receivers and
  canonical member IDs; binder chains, named F-bounds, signatures and detached
  validation pass. All 40 JVM/host outcomes, four source-linked unsupported
  boundaries and invalid-cycle JVM/frontend rejections pass.
- Public CLI GREEN: `tests/inheritance/bounds/.work/public-aP2TYj/result.json`.
  All 40 JVM/host outcomes pass and complete generated bytes equal the focused
  output. Production input hash guards pass in both runs.

```text
20b5aafe096841289157f262eaec1248dc94cf7d7eedde17d9ffef6e05063921  src/language/LanguageLowering.kt
2a226fa542a0970b1f6c754713bca94f4bbd672d3dc2d7e6e147f8ab893bd1e6  src/target/Validator.kt (main-owned dependency)
d930db6c46d3e18069dc582faa12e3350ff8fa00b22714366da89368d67e064d  tests/inheritance/bounds/BoundedReceivers.kt
1c6d22d7a60f100851eca7c30d7bf9a55dae702b56de8b7f28e7a27aa6ebb645  BoundedReceivers.ets (both GREEN runs)
```

These hashes record the initial bounded receiver run, before the integration
binding fixes below. Actual SDK/native checks remain pending with main; host
evidence is not an SDK/native acceptance claim.

## Integration binding fix and final freeze

The pinned official `org/jetbrains/kotlin/ir/inline/FunctionInlining.kt:848-888`
creates extension receiver temporaries with
`IR_TEMPORARY_VARIABLE_FOR_INLINED_EXTENSION_RECEIVER`, including a copied
parameter named `this`. Language binding and source-name reservation now share
the exact generated-origin predicate. Repeated uses retain one IR-symbol-keyed
target name; no source-name matching or broad synthetic-origin exemption exists.

After generated-origin classification, only main's shared
`etsRestrictedValueBinding` predicate triggers syntax-required aliases for
`eval` and `arguments`. The existing collision-safe allocator uses readable
`eval_` / `arguments_` prefixes and preserves source provenance and symbol
identity. Legal field, method and type-parameter names stay unchanged.

`TemporaryOrigins.kt` and the expanded real-IR `BoundedReceiverProbe.kt` prove
two actual official extension receiver temporaries, repeated reads of the same
`IrValueSymbol`, and collision avoidance with a source `__etsTmp0` parameter.
That collision case deliberately uses the language seam only: the public source
prefix guard is unchanged. Strict aliases become `eval_1` and `arguments_3`,
avoiding original locals `eval_0` and `arguments_2`; repeated references, original
binding spans and legal fields/methods/type binders are asserted independently.

Retained integration failures:

- `tests/binary-bodies/r2b/.work/run-UUuwgl/public-abhj5I/combined-cli.json`:
  same-producer public RED, reserved `this` binding.
- `tests/binary-bodies/r2b/.work/run-UUuwgl/public-vETIRJ`: the origin-only fix
  emitted ETS, but unchanged generated constructor binding `arguments` failed
  strict host syntax. Its diagnostic and generated-file hash remain in
  `tests/inheritance/bounds/.work/strict-red-Ard2Kh/syntax-error.json`.
- `tests/inheritance/bounds/.work/probe-mF65HV`: test-only internal constructor
  API failure, corrected to the actual declaration's `factory.createBlockBody`.

Final serial checks, all exit zero:

```sh
node tests/inheritance/bounds/probe.mjs
node tests/binary-bodies/r2b/replay.mjs tests/binary-bodies/r2b/.work/run-UUuwgl
node tests/inheritance/bounds/public.mjs tests/inheritance/bounds/.work/probe-1WrbEO/result.json
```

- `tests/inheritance/bounds/.work/probe-1WrbEO/result.json`: eight bounded
  real-IR calls, exact-origin/strict-binding tests, 40 JVM/host outcomes, four
  source-linked unsupported cases and invalid-cycle JVM/frontend rejection.
- `tests/binary-bodies/r2b/.work/run-UUuwgl/public-k7DNH6/complete.json`: both
  unchanged binary producer layouts, six JVM/host pairs, twelve exact-object
  identity checks and nine fail-closed cases. Final production hash guard passed.
- `tests/inheritance/bounds/.work/public-RDPJrE/result.json`: actual public CLI,
  all 40 JVM/host outcomes, byte-identical focused output, final input hash guard.

```text
c20690c34477fd29329beba5f49fc5e11ffc392a1f296b43a3c1fcc463030d89  src/language/LanguageLowering.kt
61cd0e3ccf3bde7decd52118ba44024c2955f62f10efe2add3a652df56b7aee5  src/target/Validator.kt (main-owned dependency)
30c8b5f1874f32c168f53cd33bf82e28b7910fe03a496f1cfbab4851971067cc  tests/inheritance/bounds/TemporaryOrigins.kt
85bce8612e979a6a81e9084e51f5ca0cddcbc5790f0e48c54e38c1ef02e5b60e  tests/inheritance/bounds/BoundedReceiverProbe.kt
1c6d22d7a60f100851eca7c30d7bf9a55dae702b56de8b7f28e7a27aa6ebb645  BoundedReceivers.ets (focused/public)
6caac7f995681684665dcf16af3fa21679d054c11d2601c83a04c719ba8ee98c  combined.ets / second-jar.ets
```

Production and tests are frozen; all lane children completed and the sole heavy
compiler slot was explicitly released to main. SDK/native integration remains
pending. No binary producer, stdlib, shared target, output or UI file was edited.

## Retained equality limitation

The first current-producer attempt, `probe-ofQifv`, encountered unsupported
`kotlin.internal.ir.EQEQEQ(arg0: Any?, arg1: Any?): Boolean` on source objects.
Its `actual.ir` and `probe.stderr` are retained. The exact original source is
`/tmp/kotlin-ets-bounds-baseline-sQkjUd/BoundedReceivers-reference-equality.kt`,
SHA-256 `cbe1c13a20bb30ebaabf54c663cd536b0657b622bfed9ebb76dea8fad5e116f9`.

This is an R3 equality limitation, not newly supported `===` behavior. Main
approved mutation-based alias observation for this bounded-receiver slice.
No equality adapter, stdlib edit or source-string rewrite was introduced.
