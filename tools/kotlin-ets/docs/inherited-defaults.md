# Inherited default argument dispatch

This is the source-class default-argument consumer of the official Kotlin IR
pipeline, not an adapter-name substitution or a page-generation feature.

## Reused implementation

Pinned reference: Kotlin 2.1.20. `src/core/DefaultArguments.kt` composes:

- Common `MaskedDefaultArgumentFunctionFactory`: finds the actual default
  provider through compiler override symbols and builds mask parameters.
- Common `DefaultArgumentStubGenerator`: remaps parameter references, selects
  defaults in parameter order and calls the original virtual method.
- Common `DefaultParameterInjector`: supplies receivers, explicit arguments,
  omitted-argument sentinels and masks at actual call sites.
- Official `createStaticFunctionWithReceivers` and `moveBodyTo`, also used by
  the JVM static-default lowering: represent dispatch helpers as functions with
  an explicit receiver, preserving return targets and parameter identity.
- Official type remapping, `IrTypeSubstitutor`,
  `getAllSubstitutedSupertypes`, and JS `NameTable`: instantiate generic owners
  and methods, preserve source ownership and avoid helper-name collisions.

The JS default factory/injector requires JS undefined, prototype and super-context
conventions. ETS does not import those conventions or their runtime. The common
masked route supplies the language semantics; ETS supplies receiver placement,
typed-call normalization and target representation.

## ETS-specific work

1. Put each generated helper in the provider's source file. User methods remain
   methods with their original parameter names and bodies. Only calls omitting
   inherited arguments need the helper; fully supplied calls remain direct.
2. Use the common generator's selection hook to bind immutable local results,
   instead of JVM parameter assignments designed for bytecode inlining.
3. Lift owner and method type parameters into the helper using official copying
   utilities. Normalize both original-declaration and stub types in generated
   dispatch casts. Instantiate sentinel/result types at the call site rather
   than leaking the provider's generic `T` into an unrelated scope.
4. Retain the original-provider attribute explicitly. Kotlin's
   `defaultArgumentsOriginalFunction` has `followAttributeOwner = false`, so
   `copyAttributes` alone does not preserve it.
5. Emit masks using typed Kotlin Int `and` -> ETS bitwise `&`. This is a checked
   Int/Int standard-library rule, not a textual replacement. A mask, not a null
   test, distinguishes omitted values from explicit nullable arguments.
6. Remove only the selected source defaults and temporary instance stubs after
   injection. The helpers then use the existing language lowering, typed target
   validator, printer and multi-file emitter. No UI/text-output bypass exists.

Helpers retain the recognizable `Owner_method$default` compiler name. A collision
renames the generated helper, never the user declaration. Helpers are not forcibly
inlined: default expressions can recursively call methods with omitted arguments.
Generated Kotlin call sites supply the helper ABI; arbitrary external ETS calls
with omitted arguments are not automatically rewritten. Public source methods
remain callable with their ordinary, fully supplied parameter lists.

## Covered family and boundaries

The fixture exercises open, abstract and interface providers; virtual overrides
and inherited final methods; dependent defaults and closures; generic methods,
generic class/interface heritage and a single receiver bound; explicit null;
named-argument effects; recursive defaults; mask positions 31, 32 and 33; and a
user declaration deliberately colliding with the natural helper name.

This does not add support for inherited member extensions, suspend/inline
provider combinations, arbitrary external binary default bodies, explicit super
dispatch, projected receivers, multiple receiver bounds, or providers in local
and inner classes. The latter need capture/phase-order composition before moving
their bodies outside the class. They must not silently capture unavailable state.
Existing unsupported type/declaration checks remain active. This is not completion
of all R2 declaration or generic semantics.

## Verification

Run `node tools/kotlin-ets/tests/inheritance/defaults/run.mjs`.

The runner freezes implementation and fixture hashes and records commands/results
under `tests/inheritance/defaults/.work/run-*`. It verifies:

- Kotlin JVM versus ETS-host results for five seeds, including Int boundaries,
  across nine scenarios, both flat and multi-file output.
- Strict target TypeScript semantic checking, source method/parameter names,
  source-first collision handling and no IIFE around omitted constants.
- Identical per-file output with reversed source input order; provider-local
  private helpers remain private; callers import the dispatch helper, not its
  private dependencies.
- JVM-valid source boundaries rejected with exact source spans and no ETS output:
  star projections, multiple receiver bounds, explicit super, local and inner
  default providers.
- Actual official IR origins and provider links for ten generated helpers,
  exactly one virtual implementation dispatch per helper, two mask parameters
  for the wide method, and all eighteen omitted-argument calls targeting live
  helpers with complete argument/type bindings.

These are host/IR/module checks, not ArkTS SDK, ArkVM, native UI or visual parity
evidence. The combined SDK/native gate remains in R2 of `task_plan.md`.

Frozen GREEN: `tests/inheritance/defaults/.work/run-SX8Kmd`, 60 unchanged inputs,
45 flat plus 45 multi-file outcomes, five rejection boundaries, and the actual
IR checks above. Generated flat output SHA-256:
`14a3e1a569c6d335cc9fc6c1c47b5c0011be5de35254c4a00a6cc2a6ef68b1d7`.

Initial RED `run-3Tnxba` rejected the inherited omitted argument. Subsequent
type/IR gates caught escaped provider type parameters and a missing original
provider attribute; no target validator was weakened to make these pass.

Regression evidence: inheritance `run-01X601` (50 outcomes, the historical
default fixture now positive, nine remaining boundaries); source inliner
`run-oEZoyZ`; concatenation lowering `run-wjEgjD`. Both latter runners verify
actual Kotlin 2.1.20 common passes and JVM/ETS-host behavior.
