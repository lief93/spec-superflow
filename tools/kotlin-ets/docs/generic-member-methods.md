# Generic member methods

R2C language implementation has baseline, focused and public CLI evidence.
Language owns the producer and focused source tests; main owns target validation
and integration. Main's old-suite regressions and scoped eight-module SDK check
have passed; UI, combined SDK and native verification remain pending.
No JavaScript ABI bridge is introduced.

## Finite contract

Use existing `EtsFunction.typeParameters`, `EtsFunctionType.typeParameters`,
`EtsMember.symbolId` and `EtsCall.typeArguments`. A member's class arguments are
substituted through actual ancestry; its method-owned binders remain declared in
the callee signature until the resolved call arguments instantiate them. Preserve
source method/parameter/binder names and canonical real declaration IDs.

Language keeps method binders on abstract signatures. Override comparison first
uses the existing official class-owner substitution, then the official
`makeTypeParameterSubstitutionMap` and IR type substitution to align method
symbols by position. Bounds, parameter types and return type must match exactly.
Method binders do not erase or capture class binders. Main's hierarchy-only
alpha-equivalence comparison mirrors this contract; member lookup and call-site
types remain exact. No shared tree fields or frontend hook are needed.

## Official references

Pinned Kotlin 2.1.20 source root:
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`.

- `org/jetbrains/kotlin/ir/overrides/IrOverrideChecker.kt:93-145`: method-binder
  arity, positional equivalence, upper bounds and parameter-type comparison.
- `org/jetbrains/kotlin/ir/types/IrTypeCheckerUtils.kt:13-35`: additional axioms
  pair actual type-parameter symbols, not their printed names.
- `org/jetbrains/kotlin/ir/util/IrUtils.kt:920-927`: directly reused method
  parameter-symbol substitution map; caller checks equal arity first.
- `org/jetbrains/kotlin/ir/util/IrTypeUtils.kt:106-147`: directly reused IR type
  substitution preserves unrelated binders, nested arguments and nullability.
- `org/jetbrains/kotlin/ir/types/IrTypeSubstitutor.kt:72-99` and
  `org/jetbrains/kotlin/ir/util/IrTypeUtils.kt:189-223`: existing official
  class-owner and ancestry substitution remains the first step.
- `org/jetbrains/kotlin/ir/util/IrFakeOverrideUtils.kt:38-88`: existing real
  declaration identity resolution remains unchanged.
- `org/jetbrains/kotlin/ir/backend/js/lower/BridgesConstruction.kt:68-100,145-151`
  and `JsBridgesConstruction.kt:25-45`: JS bridges depend on JS signatures,
  names and backend intrinsics. Reference their symbol/substitution discipline,
  not their ABI bridge emission, for this same-name exact-signature ETS subset.

## Prepared tests

`tests/inheritance/methods/Control.kt` preserves the already-supported plain-class
generic method path, including explicit/inferred arguments and object aliasing.
`GenericMethods.kt` adds interface/overridden/inherited calls, two generic class
ancestry edges, combined class/method/callback types, method bounds on class
binders and other method binders, calls through constrained receivers, and
receiver/argument/callback evaluation order. Returned aliases are observed by
mutating originals, without claiming source object `===` support.

`JvmOracle.kt` provides 35 outcomes from the original sources at five seeds,
including Int overflow endpoints. The real-IR probe independently checks emitted
method binders, names, canonical member/override IDs, resolved type arguments,
instantiated result types and validation after leaving the compiler session.

Thirteen valid-source negative inputs retain overloads, nesting, variance/star
projections, multiple bounds, member extensions/default arguments in hierarchy,
default interface bodies, super calls, covariance, binder-name shadowing,
reified methods and suspend methods. Five invalid-source fixtures require both
original JVM and frontend rejection for binder-count, bounds, parameter/result
type and incompatible-diamond errors. Invalid Kotlin is not a backend rejection
success. The shadowing boundary is a source-linked target-name diagnostic.

The unchanged historical inputs `bounds/UnsupportedGenericMember.kt` and
`generic/UnsupportedMemberGeneric.kt` passed focused and public checks before
migration. Only after `public-QGPUk6` completed were they renamed to
`bounds/SupportedGenericMember.kt` and `generic/SupportedMemberGeneric.kt`, with
byte-identical contents and explicit positive checks added to both old runners.
Original files remain under the baseline snapshot's `previous-inputs/` folder;
their original rejection logs and raw IR remain in the baseline run. No negative
was silently skipped. Main's migrated old-suite results are recorded below.

The third historical fixture, `tests/inheritance/UnsupportedGenericMethod.kt`,
permanently retains its original filename and bytes as an explicit legacy
positive. It contains only `interface GenericMethod { fun <T> read(value: T): T }`.
The normal inheritance runner requires original JVM compilation and fresh public
output AST proof before excluding this exact file from negative enumeration.
Assertions require the interface, method-owned `T`, `value: T`, result `T` and no
body. No runtime behavior or artificial consumer is attributed to this source.
Original source SHA-256 is
`593e06ce5751bff7e7d29cc59d72926bfa4b3407988e683f2639827902e2243d`.
The stale negative assertion from `run-yWhx9P`, original bytes and successful
public output remain retained in `/tmp/kotlin-ets-third-interface-6REWxQ`.

## Reproduction and evidence

Frozen pre-edit production snapshot:
`/tmp/kotlin-ets-methods-baseline-jUvYS8/src`.

With an explicit compiler slot, run serially from `tools/kotlin-ets`:

```sh
KOTLIN_ETS_SOURCE_ROOT=/tmp/kotlin-ets-methods-baseline-jUvYS8/src node tests/inheritance/methods/probe.mjs --baseline
node tests/inheritance/methods/probe.mjs
node tests/inheritance/methods/public.mjs CURRENT_RESULT_JSON BASELINE_RESULT_JSON
```

The baseline retains five successful control outcomes and genuine hierarchy
rejections rather than claiming every generic-method case was unsupported.
Public verification requires complete output equality to focused output and
unchanged baseline control bytes. Runners retain source hashes, commands, raw
IR, generated output, stdout/stderr and comparison results under `.work/`, with
`JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`. Remaining
integration gates are listed separately from the completed scoped checks below.

- `tests/inheritance/methods/.work/baseline-ZfFfBk/result.json`: expected baseline
  outcome passed. Five previously supported control outcomes and complete ETS
  bytes retained; hierarchy and both exact historical inputs rejected. The
  original JVM oracle compiled and supplied all 35 outcomes independently.
- `tests/inheritance/methods/.work/probe-vKXcqz/result.json`: focused GREEN before
  migration; 35 JVM/host outcomes, 12 generic member declarations and 16 real IR
  calls, both original historical inputs accepted, 13 valid-source unsupported
  boundaries and five invalid-input JVM/frontend rejections. Input hash guard
  passed.
- `tests/inheritance/methods/.work/public-QGPUk6/result.json`: public GREEN before
  migration; all 35 JVM/host outcomes, both outputs byte-identical to focused
  generation, existing control bytes identical to baseline, and both unchanged
  historical inputs accepted by the actual public launcher. Input hash guard
  passed. This proof precedes test-only path migration, not a production change.
- `tests/inheritance/methods/.work/probe-gXTSzd/result.json`: post-migration
  focused GREEN, same 35 parity outcomes and complete typed/negative coverage,
  both renamed exact inputs accepted, final input hash guard passed. Both old
  runners passed `node --check`; their complete regression runs remain main-owned.
  No further public replay or old-suite JVM runs were started by this lane.

Main-reported integration evidence, with local result manifests confirmed:

- `tests/inheritance/.work/run-1Goc2U/result.json`: GREEN, 30 JVM/host pairs,
  11 unsupported boundaries and mandatory legacy interface-positive proof.
- `tests/inheritance/methods/.work/interface-XCkmme/result.json`: GREEN original
  interface JVM compilation and public AST signature checks; no runtime claim.
- `tests/inheritance/generic/.work/run-ltVlGm/result.json`: GREEN, 31 pairs and
  the explicit migrated generic-member positive.
- `tests/inheritance/bounds/.work/probe-lYzqaz/result.json`: GREEN, 40 pairs and
  the explicit migrated bounded generic-member positive.
- `/private/tmp/kotlin-ets-generic-methods-sdk-MLKL9o/manifest.json`: main reports
  actual SDK GREEN for eight unchanged generated modules, including interface-only
  coverage. This scoped module check is not combined SDK or native acceptance;
  detailed SDK coverage evidence is in `docs/generic-method-modules.md`.

```text
7bf06e6123cf4ebcc2136c5040dbd1cd53c90007c41430bce6486848acfbe9ef  src/language/LanguageLowering.kt
50a8e437c4165e63957103be978f4e894051e9809a82e0d3f66d07c10bf995fb  src/target/Validator.kt (main-owned dependency)
b43bb0804eace8a0e2bb43e942493c6b715c9992d70966b069a976c4248ec3bb  tests/inheritance/methods/Control.kt
9b5be3e23208133baf4efdbd3616c4f8d14c4b41270e0eab611fef1809b567dc  tests/inheritance/methods/GenericMethods.kt
fc566f383970cd1b840f04ba19d32f27ed16999ed01e1caf4741ecc92b4fe336  bounds/SupportedGenericMember.kt (unchanged former negative bytes)
3983f0bbc29a90aa6a6dab4202dc4208275c4b77c245f2745b187796c2c9107f  generic/SupportedMemberGeneric.kt (unchanged former negative bytes)
b36261cb5e44d81a1ea2ed0d38302397f2817b8f2defb2f8386229a81f7ea3fe  Control.ets (baseline/focused/public)
02ad5c86eacc7e49f267fc8ead89c48d0f434ca6411f5979f1b34006078282ee  GenericMethods.ets (focused/public)
```

All lane child processes completed. The sole JVM slot was explicitly released
to main after `probe-gXTSzd` exited zero. Production/tests/docs are frozen and
writes have stopped. Main owns the remaining UI, combined SDK and native gates;
the completed scoped checks do not imply those remaining gates have passed.
