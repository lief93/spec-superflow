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
| Default arguments | Common masked factory, stub generation and argument injection; JS injector has interop/inner-class prerequisites | Source inherited defaults use the common masked route with typed static receiver helpers. Ordinary direct defaults stay. See inherited-defaults.md for the bounded contract; no JS undefined/super-context ABI. |
| Inner/local declarations | Official capture, local popup and inner-class passes generate fields, parameters and rewritten constructor calls | Already reused; consume registered synthetic bindings and validate ownership. |
| Secondary constructors | JS lowering creates factories, then factory injection rewrites construction | Keep one native allocating root (source primary or unique directly-super-delegating secondary); reuse official IR declaration/body/type/value utilities for source-class static factories. Other allocation families remain pending; see constructors.md. |
| Virtual bridges | Common generateBridges accepts resolved FunctionHandle graphs; public IrBasedFunctionHandle and findConcreteSuperDeclaration provide resolved ownership | Reuse the common algorithm with ETS slot signatures; emit typed forwarding or required abstract declarations. Generic joined slots, inherited concrete implementations and bounded method-result covariance are supported. See virtual-overloads.md. |

## First consumer family

Inherited final instance properties: stored `val`/`var`, custom accessors, and
invariant generic properties across source-class heritage. The existing real
override resolver and receiver substitution are the normalization mechanism;
there is no property-name adapter or new target text path.

`tests/inheritance/run.mjs` compares JVM and generated-code execution, including
receiver/argument effects and custom getter/setter effects. It also checks target
types and accessor names. The same run retains failures for unrelated storage
shadowing, unsupported initialization and other inheritance
boundaries. Host execution is not an ArkTS SDK or device verification claim.

Still pending: top-level initialization, the inherited-default combinations
excluded by inherited-defaults.md, virtual-overload exclusions documented in
virtual-overloads.md, and constructor combinations excluded by constructors.md. This contract
organizes their implementation; it does not claim they are implemented.

## Interface property consumer

Abstract source interface `val`/`var` declarations now become typed `EtsField`
signatures, not empty methods. `readonly` preserves a `val` contract; concrete
stored values retain it as well. Interface inheritance composes generic arguments
through the existing target heritage substitution. Source class implementations
can provide stored fields or custom getters/setters. Virtual implementations and
abstract class implementations use the accessor family described below.

The target validator checks required types and public instance access, rejects a
readonly field or missing setter for a writable contract, and rejects writes
through readonly fields except direct initialization of an owning instance inside
its constructor. A constructor's nested lambda does not inherit that permission.
This uses the same typed target tree and printer as ordinary language output.

Default interface property bodies, extension properties and conflicting real
declarations remain diagnosed. This is not support
for all Kotlin interface behavior or runtime interface tests.

## Virtual class property consumer

Source class open/abstract `val`/`var` and concrete overrides retain their official
getter/setter bodies and invariant owner-type substitution. Official
`IrOverridableDeclaration.overrides` determines whether repeated property names
in a class chain are related; unrelated private storage shadowing stays rejected.
No source-name matching, copied getter bodies or property flatten/reconstruction
pass was introduced.

The ETS consumer emits native accessors for virtual properties, with distinct
private owner-qualified backing fields. Assigning a derived field in its
constructor does not invoke a base setter or merge base/derived state. Existing
final nonvirtual stored properties keep their direct field representation.
Default accessors have compiler-generated parameter names; explicit setter
parameters retain their source spelling. Abstract class accessors have signatures
only, and interface properties retain field contracts.

Getter/setter target symbols include their accessor kind: compiler-generated
accessors may share both name and source span, but cannot share override identity.
The target validator checks each half's instantiated signature, requires concrete
implementations for concrete classes, and rejects partial accessor overrides that
would mask the inherited half in ETS. Abstract class accessors may implement
interface contracts, but concrete descendants must provide both required halves.

Official reference: Kotlin 2.1.20 `ir/util/AdditionalIrUtils.kt:overrides`,
`backend/common/lower/PropertiesLowering.kt`, and
`backend/common/lower/optimizations/PropertyAccessorInlineLowering.kt`.
The official accessor inliner deliberately guards virtual properties; ETS also
retains virtual dispatch rather than replacing those reads with field accesses.

Readonly field/getter override results may covary through supported target
heritage; writable property contracts remain invariant. Property references carry
the declared field/getter identity, including generic-bound and cross-file reads.
See virtual-overloads.md for the composed covariance evidence.

Boundaries remain explicit: explicit `super`
member calls, delegated/extension properties, interface default bodies, and `this`
use during inherited initialization. This increment does not claim all Kotlin
property or constructor semantics, nor SDK/native acceptance.

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

Interface-property follow-up:

- Red: `tests/inheritance/.work/run-WILqZr` rejects the new interface declarations.
- Frozen green: `tests/inheritance/.work/run-rbZMBr` passes 40 same-input JVM/host
  results, strict generated-code type checks, interface/accessor spelling checks,
  the former interface-property negative as a positive, and 11 unsupported cases.
- `tests/target/run.sh` passes the complete detached target suite, including eight
  new interface-property rejection cases. Compiler evidence is in the local temp
  directory `kotlin-ets-target-tests.Zm0Lal`.
- The intervening run `run-N3P6V5` is not green evidence: its input hash guard failed
  after a fixture was renamed while it ran. The frozen run above replaces it.
- No ArkTS SDK build or native-device claim is made for this follow-up.

Virtual-property follow-up:

- RED `tests/inheritance/.work/run-ysfiZb` reaches the old class-property guard
  after successful JVM execution. `run-8tegtG` exposes the target identity
  collision between same-span default getter/setter declarations.
- Frozen GREEN `tests/inheritance/.work/run-L169IC` passes 50 JVM/ETS-host
  results at zero, negative, positive and both Int boundaries; strict host type
  checks; default/custom/abstract generic accessors; interface composition;
  receiver, argument and accessor effects; distinct backing-field names;
  the former property-override negative as a positive; and 10 source-linked
  unsupported boundaries. Earlier `run-xHiaij` passes before the interface
  composition and target masking checks were added; use the final frozen run.
- Detached target RED `kotlin-ets-target-tests.wKiGTy` exposes partial-accessor
  masking. GREEN `kotlin-ets-target-tests.tvmEya` passes the complete suite,
  including same-span accessor identities, abstract/interface composition,
  missing halves, wrong identity/type, illegal abstract bodies/classes and
  concrete parent getter/setter masking rejection.
- Module regression `tests/modules/.work/run-gA3gRG` passes 44 JVM/module
  results plus existing ownership/import/output guards. It is a shared-contract
  regression, not a new virtual-property multi-file acceptance fixture.
- Self-check and `git diff --check` pass. No SDK/ArkVM/native/UI claim; R2's
  combined platform gate is still pending.

## R2.4 module planning diagnostics

Duplicate source paths and flat output filename collisions now produce
INVALID_TARGET with the offending source file/span, instead of a generic
exception with no source. Collision messages include both source paths and the
target basename. Case-only collisions remain rejected for portable flat output.
Empty files use file-level offsets (-1), not an invented declaration location.
All module planning still precedes runtime selection and output writes; no
automatic numbered aliases, overwrite or partial output is introduced.

RED contract-n6Zx9Y records the unstructured collision exception. Earlier
contract-3MOzWq first exposed an outdated duplicate-declaration message assertion;
the assertion now matches the stricter existing symbol-identity guard.
GREEN contract-aP1xTf covers the module contract and all three file-level
refusals. Frozen run-RF23YJ passes 44 JVM/module cases, private/internal visibility,
function/type imports, dependency closure, no-overwrite/no-partial-output checks
and public CLI collision diagnostics. The CLI collision exit status is now 2
(INVALID_TARGET), not 1 (generic COMPILATION_REJECTED). The cross-file overload
runner's equivalent expectation is updated; that full suite was not rerun for
this diagnostic-only increment. No new SDK/native/UI acceptance is claimed.
