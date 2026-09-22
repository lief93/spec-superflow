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

The frontend runs source inlining and official local/inner capture lowering
before inherited-default generation, following the prerequisites in Kotlin's
`JsLoweringPhases.kt`. A default body therefore already refers to bound capture
fields or the registered outer link. The official `moveBodyTo` parameter-map hook
also maps the provider class receiver to the static helper's explicit receiver:
inner lowering can retain that class receiver inside a default lambda.

The JS default factory/injector requires JS undefined, prototype and super-context
conventions. ETS does not import those conventions or their runtime. The common
masked route supplies the language semantics; ETS supplies receiver placement,
typed-call normalization and target representation.

## ETS-specific work

1. Keep class helpers in their provider class, with the source member's visibility.
   Interface helpers remain in the provider's source file because an ETS interface
   cannot contain implementation bodies. User methods remain
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
7. When a derived override widens protected access to public, put a public static
   forwarding entry on that derived class. It calls the protected provider helper;
   it neither duplicates default expressions nor publishes the original protected
   member. Official signature copying and type remapping preserve generic binders.
   The injector result is associated with its original call symbol, not matched by
   a method-name string. These entries are compiler ABI, not new Kotlin source APIs.

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
Private/protected default dependencies and public widening overrides are covered.
Unique private method names now work in a hierarchy; private name shadowing still
has an explicit source diagnostic rather than emitting an invalid ETS hierarchy.

This does not add support for inherited member extensions, suspend/inline
provider combinations, arbitrary external binary default bodies, projected
receivers or multiple receiver bounds. Explicit `super` dispatch is covered by
the language super path (`450413c`), not by expanding default-argument injection
onto super-qualified calls.
Named local Any-only providers and registered nongeneric inner providers can use
captured values in defaults, including closures. Local derived classes may forward
constructor-only captures to their base without storing another copy. This uses
the official lowering's actual field set, not a second closure analysis. Derived
classes needing stored captures before `super` are still rejected; arbitrary
captured inheritance and inner heritage are not covered by this increment.
Generated capture parameters and fields use the existing JS NameTable; generated
fields avoid descendant source members using official `isSubclassOf` relationships.
Source names win, and no capture field is widened or inferred by its spelling.
Existing unsupported type/declaration checks remain active. This is not completion
of all R2 declaration or generic semantics.

## Verification

Run `node tools/kotlin-ets/tests/inheritance/defaults/run.mjs`.

The runner freezes implementation and fixture hashes and records commands/results
under `tests/inheritance/defaults/.work/run-*`. It verifies:

- Kotlin JVM versus ETS-host results for five seeds, including Int boundaries,
  across thirteen scenarios, both flat and multi-file output.
- Strict target TypeScript semantic checking, source method/parameter names,
  source-first collision handling and no IIFE around omitted constants.
- Identical per-file output with reversed source input order; provider-local
  private helpers remain private; callers reference the provider class (or the
  interface helper), not its private dependencies.
- JVM-valid source boundaries rejected with exact source spans and no ETS output:
  star projections and multiple receiver bounds. Historical local, inner and
  explicit-super negatives now generate successfully; the behavioral scenarios also
  exercise changing shared state, independent outer instances and virtual dispatch.
- Actual official IR origins and provider links for seventeen generated helpers,
  exactly one virtual implementation dispatch per helper, two mask parameters
  for the wide method, and twenty-nine calls targeting live provider helpers with
  complete argument/type bindings. Two public widening bridges have exact argument
  symbols and their own generic return/type-argument binders. Cross-file callers
  exercise both generic and specialized derived classes without name collisions.
- Four capture-aware default helpers read exact official fields through their
  moved receiver, including inside closures; no implicit class receiver remains.
  The derived local class stores no generated capture fields. A deliberate user
  `$state` parameter/property collision verifies that user declarations survive
  unchanged and generated capture storage stays distinct.

These are host/IR/module checks, not ArkTS SDK, ArkVM, native UI or visual parity
evidence. The combined SDK/native gate remains in R2 of `task_plan.md`.

Capture-composition GREEN: `tests/inheritance/defaults/.work/run-me1TY3`, all
65 frozen inputs unchanged, 65 flat plus 65 multi-file JVM/ETS-host outcomes,
three boundaries, two historical negatives now positive and deterministic
five-file output. The seventeen provider helpers include four checked captured
receivers; twenty-nine calls retain full argument/type bindings. Flat SHA-256:
`1e88798274a28a90584a10f797d502d3150b0b92a3423eaee9ea69f9ab1db28c`.
RED `run-xwUcjE` caught a duplicate constructor parameter; `run-GDmNLf` then caught
a generated base capture field shadowing the child's source property. Both are
retained. The final fixture preserves the user's `$state` parameter and property.
Earlier `run-ZbO9c0` covered capture behavior before adding this collision case.

Frozen regressions: capture construction `run-su7vhA` passes 50 + 50 outcomes and
seven malformed-prefix checks; constructor `run-TjgMb4` passes 90 + 90 and four
boundaries. Both retain the prior flat/module output hashes. Local core
`run-NhO261` retains capture/ownership checks and the stored-capture inheritance
refusal. Source-inline `run-l3QFlx` verifies the actual official inliner, ten
inlined blocks (three library blocks), JVM/host effects and missing-body refusal.
Target suite `target-tests.zWviDp` passes constructor flow, visibility, inheritance,
binding, generic and UI-builder checks. These are not new SDK/native results.

Ownership GREEN: `tests/inheritance/defaults/.work/run-cJb0cl`, 55 flat plus
55 multi-file JVM/ETS-host outcomes, five boundaries, deterministic four-file output and
the IR assertions above. Target suite `target-tests.tUqicj` also passes, including
twelve visibility refusals. Ownership RED `run-56R12A` exposed the blanket private
method guard; `run-AAQ8IH` caught an escaped provider type parameter in a forwarding
entry. The validator was not weakened. This is not a new SDK/native acceptance.
After indentation-only cleanup in `IrEvidence.kt`, the compiler and IR proof were
rebuilt and rerun in `/tmp/kotlin-ets-default-owner-proof-hoEptE`; all other 63
frozen inputs remained identical. Final flat ETS SHA-256:
`34249a2a58647072641fa08b8e7e5bd6d9d1cb6d0579b4416bc182a1db888965`.

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
