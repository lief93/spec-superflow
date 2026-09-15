# Nullable models and collection composition

This increment exercises ordinary multi-file Kotlin programs, not a page-specific
translation path. Existing data classes, copy/default arguments, property access,
filter/map, iteration, nullable storage and conditional expressions are reused.

## Gaps found and fixed

- Collection `isEmpty`/`isNotEmpty` calls were not covered by the public backend.
  `CollectionEmptinessRules` now handles the resolved standard declarations for
  the existing array-backed List, MutableList and Collection representation.
  It emits a typed length comparison with one receiver evaluation and requires
  no new runtime helper. Source methods with the same simple name stay ordinary
  source calls. Arbitrary custom collections, Set, Map, arrays and nullable
  receivers are not added by this rule.
- Ordinary `kotlin.let` calls lacked a usable binary IR body in the installed JVM
  standard library. `LetRule` provides a bounded ETS implementation: evaluate the
  receiver, evaluate the function argument, invoke that function once and retain
  its result. Both arguments use the shared language lowerer. The typed call
  preserves evaluation order even when producing the function has side effects.
  Nullable receivers and Unit-returning blocks are covered; safe-call skipping
  still comes from the original Kotlin conditions, not this adapter.
- The existing expected-nullability visitor used a generic declaration's raw
  parameter type instead of the call's instantiated type. It now uses the
  official `IrTypeSubstitutor` in `AbstractValueUsageTransformer`'s argument hook.
  This applies to generic calls generally, not just let. Only the existing
  nullability-only cast rule is applied; explicitly nullable instantiations remain
  nullable. No frontend diagnostic or target type check is bypassed.

## Official references and limits

Kotlin 2.1.20 [Collections.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/src/kotlin/collections/Collections.kt)
defines `isNotEmpty` in terms of the collection's empty predicate.
[Standard.kt](https://github.com/JetBrains/kotlin/blob/v2.1.20/libraries/stdlib/src/kotlin/util/Standard.kt)
defines let's argument/result behavior. The target rules supply implementations
for our ETS representations; they do not claim to load those stdlib function
bodies or reuse the Kotlin/JS collection runtime.

The existing common inliner still runs first for source or supported binary
bodies. The bounded let fallback is not a replacement for full inline lowering:
non-local returns remain source-linked errors and publish no ETS. Other scope
functions, general contract lowering and arbitrary Kotlin objects are not newly
claimed here. These remaining gaps do not disappear merely because this fixture
passes.

## Verification

```sh
node tools/kotlin-ets/tests/language/models/run.mjs
node tools/kotlin-ets/tests/nullability/run.mjs
bash tools/kotlin-ets/tests/backend/run.sh
```

The model runner compares 70 JVM results with flat and multi-file ETS host
execution. Coverage includes empty/populated filtered lists, copied source
objects, preserved originals, nullable selection/reset/update, defaults,
safe-call skipping, ordinary nullable let, Unit callbacks, and effectful receiver
and function-argument evaluation. Guarded and explicitly nullable generic calls
are tested separately. It checks source class/method/parameter names, strict host
types, reversed input determinism, and non-local-return rejection with a source
line and no target output. Hashes and command logs are retained under `.work`.

These checks are not Harmony SDK compilation, ArkVM execution or UI acceptance.
Those remain integration-milestone gates.

## Compose consumption check

`node tools/kotlin-ets/tests/ui/model-composition/run.mjs` reuses the same model
sources in a small Compose consumer. The original page compiles with the official
2.1.20 Compose JVM plugin. A detached typed target check verifies the source
`ModelPage(minimum, extra)` parameters, String-returning calls consumed by Text,
both conditional branches and the actual button callback. Public CLI multi-file
output must be byte-identical to this checked program's emitted modules.

The runner exports the actual typed callback body into a host-only projection,
alongside unchanged ordinary declarations. Thirty callback invocations across
empty/populated and selected/unselected cases replace the equivalent ordinary
JVM helper calls; all 70 resulting values match the original JVM oracle. The
projection passes strict host type checking. Production/input/output hashes and
logs are retained in `tests/ui/model-composition/.work/run-r54CGE`.

This check adds no compiler implementation or page-specific rule. The projection
is test-only, not delivered UI. It does not execute ArkUI builders, establish
observable-state invalidation, or prove native redraw or visual fidelity. The
ordinary mutable model storage in this fixture is not claimed as reactive state.
