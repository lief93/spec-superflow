# Declaration and call normalization

This contract applies to official Kotlin IR -> typed ETS, not the legacy page
snapshot pipeline. It does not introduce a second parser or an execution engine.

## Shared rules

1. Resolve declarations by compiler symbols, not source spelling. A fake override
   must resolve to one real declaration using `collectRealOverrides`; ambiguous
   dispatch is diagnosed, never selected by name.
2. Instantiate the declaring owner's types through the receiver's full heritage
   path. Reuse `getAllSubstitutedSupertypes` and `IrTypeSubstitutor`. Accessors and
   methods share this path; a derived receiver need not equal the declaring class.
3. Retain the IR evaluation order and temporary bindings. A receiver and each
   argument execute once. Assignment yields a statement effect, not the assigned
   property's value when Kotlin expects Unit.
4. Preserve source names and ETS-native structure where semantics agree. Accessor
   calls become property reads/writes; custom accessors remain getters/setters.
   Retain backing storage separately when custom accessors need it.
5. Validate the resulting typed target tree before printing. Unsupported dispatch,
   storage, constructors or missing dependency bodies remain source-linked errors.
   An adapter must not replace a required value with void or a default placeholder.

## Official phase selection

Reference: Kotlin 2.1.20 common lowerings and `JsLoweringPhases.kt`.

| Family | Official input/output and dependencies | ETS decision |
| --- | --- | --- |
| Properties | Common `PropertiesLowering` moves fields/accessors out of `IrProperty`; removes the property container; no target runtime supplied | Preserve the container for ETS property syntax. Consume its compiler-resolved storage/getter/setter relationships directly. Do not run flattening merely to reconstruct the property afterward. |
| Default arguments | Common stub generation plus JS override patching, argument injection and cleanup; JS injector has interop/inner-class prerequisites | Existing direct ETS defaults stay. Inherited defaults need a separate semantics proof before enabling; do not inject JS stubs without their calling convention. |
| Inner/local declarations | Official capture, local popup and inner-class passes generate fields, parameters and rewritten constructor calls | Already reused; consume registered synthetic bindings and validate ownership. |
| Secondary constructors | JS lowering creates factories, then factory injection rewrites construction | Pending ETS construction/initialization design. A factory is not equivalent to merely renaming a constructor. |
| Virtual bridges | JS bridge construction supplies backend-specific dispatch machinery | Pending virtual overload/covariance design. Preserve current exclusions until declaration and call identities agree. |

## First consumer family

Inherited final instance properties: stored `val`/`var`, custom accessors, and
invariant generic properties across source-class heritage. The existing real
override resolver and receiver substitution are the normalization mechanism;
there is no property-name adapter or new target text path.

`tests/inheritance/run.mjs` compares JVM and generated-code execution, including
receiver/argument effects and custom getter/setter effects. It also checks target
types and accessor names. The same run retains failures for overridden/abstract
properties, storage shadowing, unsupported initialization and other inheritance
boundaries. Host execution is not an ArkTS SDK or device verification claim.

Still pending: interface properties, property overrides, top-level initialization,
inherited defaults, virtual overloads and secondary constructors. This contract
organizes their implementation; it does not claim they are implemented.

## Verification, 2026-09-14

- Red: `tests/inheritance/.work/run-DjyRl0` rejects the new composed property
  example at inherited dispatch, after successful JVM execution.
- Green: `tests/inheritance/.work/run-8kZgyj` passes 35 same-input JVM/host results,
  strict TypeScript semantic checking, accessor-name checks, the former plain
  inherited-property negative as a positive, and 10 unsupported boundaries.
- Generic regression: `tests/inheritance/generic/.work/run-tAzfVy` passes 31
  JVM/host results, the former generic inherited-property negative as a positive,
  two unsupported boundaries and incompatible-diamond rejection on both frontends.
- Evidence directories contain command logs, input/output hashes and results.
  No device/UI integration was run for this language-only change.
