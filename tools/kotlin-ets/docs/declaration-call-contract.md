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

## R2.4 ownership and regression closure

The existing official ownership data is sufficient for the checked families;
no parallel symbol registry or source-location reconstruction was added.
Kotlin 2.1.20 FakeOverrideCopier anchors generated constraint members at their
owning bound declaration and retains original override symbols. Default helpers
use defaultArgumentsOriginalFunction; constructor factories use attributeOwnerId;
bridge targets follow the official override graph. The additional constraint
probe checks both the emitted bound location and the original source contracts.

This consolidation exposed a regression in the official-query boundary:
defaults run-fh7jzS fails because captureFromArguments calls extractTypeParameters
on an inner class already relocated under an IrFile by official local lowering.
The original parent-as-IrClass prerequisite no longer holds. SourceTypes now
returns no-argument/invariant types unchanged before invoking capture, matching
the official identity branch. Actual in/out/star capture and subtype queries
still delegate to Kotlin. The session lifetime guard remains first.
The existing inner-default fixture verifies the relocated parent and identity
result; no new generic family or target runtime was introduced.

Frozen evidence on the same production inputs:

| Family | Evidence | Checked result |
| --- | --- | --- |
| Bounds and projections | variance/run-pNnkNQ | 160 flat + 160 module JVM/host outcomes; eight-file determinism, constraint/member source links and closed-session guards |
| Inherited defaults | defaults/run-LaKYjq | 65 + 65 outcomes; five-file determinism, original providers, explicit receivers, captured inner methods and 29 call bindings |
| Constructors | constructors/run-pDvEKk | 90 + 90 outcomes; six-file determinism, 18 factories, seven original roots, eight multi-entry constructors, protected ownership and exact super symbols |
| Virtual bridges | bridges/run-Bq6qP6 | 70 + 70 outcomes; six-file determinism, 19 official edges, single forwarding, original methods/parameters and property identities |
| Cross-file overloads | overloads/r2e-green-KOYKS1 | 15 flat + 15 module outcomes and five private-scope outcomes; exact imports, no added aliases, reversed-input equality and two collision refusals |
| Serialized members | r2e/run-IFMcOW and replay-NJ6rIq | 26 official inline blocks retain binary provenance; three JVM/host outcomes, explicit receiver replacements and seven source-linked unavailable/unsupported boundaries |

The first cross-file invocation stopped at its required exclusive-build-slot
guard, before compilation. The recorded successful invocation explicitly sets
KOTLIN_ETS_BUILD_SLOT=1 after the other Kotlin suites finish. Default run-Daao8S
was stopped after a test import error was noticed; it is not accepted evidence.

Current variance, default and bridge module bytes match their previous accepted
runs AHwTko, OHKB8f and n2dIZP. Constructor outputs differ from VDrnEa because an
earlier change moved default helpers into the original classes and updated their
callers; they cannot inherit that older SDK build claim. Fresh
constructors-sdk-r7kmWt checks all six unchanged current modules and builds
ABC/HAP. Input/output hashes were rechecked. This is SDK legality, not native
execution, UI fidelity or acceptance of all R2 capture compositions. The combined
R2 gate remains pending.

Separate native smoke follow-up: the existing HarmonyKitPhone emulator was
started with data-preserving coldboot after snapshot boot failed to expose HDC.
On OpenHarmony-6.1.1.125, device 127.0.0.1:16555, the unchanged signed HAP from
constructors-sdk-r7kmWt was installed with hdc install -r and EntryAbility launched.
uitest dumpLayout -b com.joker.kit captured its actual pages/Index Text node.
At seed 7, construct, nativeRoot, dispatchRoots, dispatchInheritance,
dispatchGeneric, dispatchDefaults, dispatchEarly and protectedConstruction match
the concatenation of the corresponding eight JVM oracle results exactly.
The assertion verifies the bundle/ability/page, visible Text, all SDK input/module/
HAP hashes and the passed oracle. It does not extrapolate to the other seeds,
other R2 families, physical devices or UI fidelity.

- HAP SHA-256: 2d9349adc900569f905758180fec363dcff1f797afd8b92dbbf723bfb4e1530c
- Layout: /private/tmp/kotlin-ets-constructors-sdk-r7kmWt/native-layout.json
- Layout SHA-256: dfba9ab779cca403aea1b5d743e05dd9e88b0155a215d634a57d11bd8c1f02bc
- Oracle: tests/constructors/.work/run-pDvEKk/result.json, expected offsets
  36 + [0, 7, 11, 12, 13, 14, 15, 16], matching Oracle.kt and SdkIndex.ets.

## Joint declaration SDK and native evidence

`tests/integration/r2-declarations-sdk.mjs` consumes the five frozen default,
constructor, bridge, variance and serialized-member replay reports above. It
rejects incomplete, failed, stale-implementation and mismatched JVM/host evidence
before creating output. Five negative tests verify those entry guards. It pins
source, fixture, report, generated-module and test-host hashes. Older default
evidence without module hashes is regenerated with its recorded public CLI
command and checked byte-for-byte against both recorded input orders.

The script copies 27 unchanged ETS modules into one disposable SDK application.
The five corpus directories and import aliases isolate test exports only; they
do not change the compiler's flat product output. Existing module coverage checks
require checker input hashes, clean semantic records and runtime build coverage,
or the verifier's explicit referenced interface-only exception. The binary
receiver classes are declared target test replacements, not translated classes.
Only the test host selects existing exports and calls them; it contains no
replacement implementations of the translated methods.

GREEN `/private/tmp/kotlin-ets-r2-declarations-bmObZN/result.json` records SDK
legality for all 27 modules and 388 exact JVM/native outcomes on the existing
HarmonyKitPhone emulator (HDC 127.0.0.1:16555). It installs the recorded signed
HAP and reads the actual `r2-native-results` node from the matching bundle and
page through uitest. Defaults contribute 65, constructors 90, bridges 70,
variance 160 and binary-inline replay three results. Source and copied module
hashes are checked again after execution. No native case is dropped.

Earlier attempts remain as failed evidence: `asqaMr` used the SDK runtime JDK
without `jar` for Kotlin regeneration; `R2PX0H` failed SDK checks because the test
host passed an argument to a zero-argument export and rethrew an untyped caught
value. The host now reads actual export arity and throws a typed test failure for
unexpected constructor exceptions. Generated ETS modules were not patched.

- ABC SHA-256: c73742513c49ac476f2462485763cf8427343b63103c3fbf3f9608d20a25a420
- HAP SHA-256: a4ac7bac0256e8ff81643e516601a50706b45faded8ba68a8e7c9710cafe98c0
- Layout: /private/tmp/kotlin-ets-r2-declarations-bmObZN/layout-0.json
- Layout SHA-256: 89bcaaec8831e9c9db113f5657af00d696e8c3da1495ef393d5a56bef6242c5e

Reproduce from repository root after producing successful host reports:

```sh
node --test tools/kotlin-ets/tests/integration/r2-declarations-sdk.test.mjs
node tools/kotlin-ets/tests/integration/r2-declarations-sdk.mjs <defaults-run> <constructors-run> <bridges-run> <variance-run> <composition-run> <binary-replay-run> --device <hdc-key>
```

Omitting `--device` proves SDK legality only. This joint corpus does not cover
all earlier R2 dependency/language families, the remaining capture compositions,
physical-device behavior or UI fidelity. It closes the separate-module/native
evidence gap for these five families, not the entire R2 exit gate.

The current runner also requires the six-scenario composition report introduced
by 5005016, adding its unchanged module and 30 JVM results. Its required corpus
is now 28 modules and 418 results. The earlier bmObZN evidence above remains a
27-module/388-result historical result, not a claim that this enlarged gate ran.
