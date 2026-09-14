# Native allocation and secondary constructors

## Architecture

The Kotlin frontend resolves constructor symbols and delegation. After inherited
defaults, inlining and official local/inner capture lowering, the ETS-specific IR pass keeps
one real native allocation root and converts secondary `this(...)` chains to static
factory methods in the original class. Calls are rewritten by constructor symbol,
not by spelling, argument names or target overload guesses.

The factory's first local receives the delegated constructor/factory result.
Its remaining original body operates on that instance, and every constructor
return returns the instance. Allocation and primary property/init blocks occur
only at the native constructor, before secondary bodies unwind in order.
Ordinary methods and constructor parameter names remain source-owned. Kotlin
secondary constructors have no separate method name; the minimum synthetic
factory name is allocated by official JS NameTable, with user names reserved.

Generic class parameters are copied into static factory method parameters.
Default expressions retain their value/type bindings and evaluate at call time;
they are not virtual inherited method defaults. Native private primary
constructors remain private and are called from their owning class's factory.
Private secondary factories and private class methods also retain target private
visibility, rather than exposing an additional public construction path. Protected
primary/secondary entries now retain protected target visibility, including the
official default-argument stubs. Extensible dispatcher protocols are protected;
final-class protocols remain private. A superclass delegation never substitutes
a factory that allocates a base instance for the derived instance.

When the source has no primary constructor, the unique constructor directly
delegating to a superclass is its native allocation root. Its original IR body,
parameters, symbol and `isPrimary == false` remain intact. An official IR attribute
registers the exact constructor/owner identity for the target consumer; copied or
unrelated declarations cannot gain permission through a name or origin prefix.
Cross-class `super(...)` may target this native root, including an abstract base
with no extra constructor factories. Field/init blocks stay at the source
`IrInstanceInitializerCall`, before the root body and delegating bodies. Native
root early returns do not skip the caller's remaining secondary body.

## Official reuse

Pinned Kotlin 2.1.20 sources were inspected before implementation:

- `ir/backend.js/lower/ES6ConstructorLowering.kt`: factory/delegation structure,
  instance remapping and constructor return handling.
- `ir/backend.js/lower/ES6ConstructorCallLowering.kt`: exact-symbol call rewrite.
- `ir/backend.js/lower/SecondaryCtorLowering.kt`: the non-ES6 route also requires
  JS allocation (`Object.create`), rather than native ETS construction.
- `ir/backend/js/JsLoweringPhases.kt`: inlining precedes constructor factory
  conversion. Inlining can expand callable references into new constructor calls.
- `ir/backend.js/lower/PrimaryConstructorLowering.kt` and common
  `InitializersLowering.kt`: allocation/initializer responsibilities and phase
  prerequisites for classes without real primary constructors.

Production directly uses official `createStaticFunctionWithReceivers`,
`moveBodyTo`, `ValueRemapper`, type remapping, IR builders and JS `NameTable`.
It does not copy a parser, argument binder, initializer extractor or inliner.
The complete JS ES6 phase requires JS newTarget/prototype/box intrinsics; those
are not ETS APIs. No Reflect/prototype runtime is introduced into generated ETS.

## Boundaries and verification

This is an increment within R2.3, not completion of all constructor forms.
Multiple native allocation roots, abstract constructor families and superclass
delegation through secondaries now use the native dispatcher described in
native-constructor-flow.md. Unique-root source families retain the original
minimal factory path. Unique-root local/inner secondary capture combinations and
local classes in duplicated initializers are covered in constructor-captures.md.
Multi-entry stored captures/inner links and inherited initialization
reads/captures of `this` (including secondary bodies) remain source-linked
diagnostics with no output. Supporting a
new allocation form must not silently bypass the initialization-safety boundary.
Primary-only classes continue through the existing native constructor path.

Run `node tools/kotlin-ets/tests/constructors/run.mjs` from the repository root.
The harness freezes implementation/fixture hashes and records commands, JVM
results, flat and module ETS-host results, strict host type checks, source-bound
IR assertions and negative diagnostics under `tests/constructors/.work/run-*`.
Host checks are not ArkTS SDK, device or UI-equivalence acceptance. The combined
R2 SDK/native gate remains pending.

After a successful frozen run, use
`node tools/kotlin-ets/tests/constructors/sdk.mjs /absolute/run-evidence` to check
the generated six modules unchanged with the real SDK. The verifier checks
source/output hashes, semantic checker records, runtime module coverage and
ABC/HAP artifacts; this is compilation evidence, not native behavior acceptance.

## Recorded evidence

Earlier run-SHDgaf passed the initial 35-case family but did not cover inlined
constructor references. Expanded RED run-a0L4bN demonstrates why stage order
matters: `createReference(::ReferenceConstructed)` produced 0 instead of JVM's 7,
because inlining recreated a call to the removed secondary constructor. Its
argument list also fit the native primary constructor's defaults, so target type
checking alone could not detect this semantic error. This run is not acceptance.

The pass now follows official ordering relative to the common inliner. Final
verification must include both actual JVM/host results and a whole-module IR
check that no calls still target removed secondary declarations. Tests also
cover initialization/default/callback effects, early returns, independent object
mutation and division failure before initialization.

Final frozen run-am3R7S passes 40 flat + 40 multi-file JVM/ETS-host outcomes,
strict host types, deterministic reversed-input modules, six JVM-valid rejection
boundaries and eleven real IR factories with original source/parameter/visibility
links. The inlined-reference case is checked at five inputs, including Int limits.
All recorded implementation and fixture hashes match that run. No SDK/native
claim follows from these host checks.

No-primary RED run-HarJRs resolves valid Kotlin/JVM inputs but fails at the old
primary-only allocation guard. Frozen GREEN run-pRFuAP passes 60 flat + 60
multi-file JVM/ETS-host outcomes, strict types, deterministic reversed-input
modules and six JVM-valid/source-linked rejection boundaries. It verifies
seventeen factory identities, seven unchanged source secondary roots and exact
cross-class native super targets. The former NoPrimary negative is now a named
positive fixture, not skipped. New tests cover generic roots, private roots,
abstract base allocation, initializer/body/argument effects, inherited defaults
and native early returns at five inputs including Int limits.
All 64 frozen inputs match. Inherited-default regression run-QYxcPz also passes
45 flat + 45 module outcomes, five boundaries and official provider/dispatch
checks against the same final implementation. Main self-check and whitespace
validation pass; SDK/native acceptance is still reserved for the R2 gate.

Multi-entry final run-1kz5Yn passes 85 flat + 85 multi-file JVM/host outcomes,
six source-linked boundaries, deterministic modules, seventeen unchanged
single-root factory identities, seven original secondary roots and six tagged
multi-entry native constructors. It covers default/named argument effects,
property/init ordering, generic derived allocation, abstract bases, early return,
inline constructor references and private final-class allocation protocols.
The former MultipleRoots, SuperSecondary and Abstract negative inputs now run
explicitly as positive regressions, not skipped coverage. All 73 frozen inputs
match. SDK constructors-sdk-jxO1FE compiles the same five modules unchanged and
records clean checker inputs, runtime module coverage and ABC/HAP artifacts.
No device/runtime/UI-equivalence or whole-R2 acceptance is claimed. Detailed
contract, intermediate failures and final hashes are in native-constructor-flow.md.

## Typed member visibility

`EtsFunction` and `EtsField` share `EtsClassMember.visibility`, using
`EtsVisibility.PUBLIC/PROTECTED/PRIVATE` instead of a private boolean. The printer
only renders this contract; it does not infer permissions from names. Kotlin
declaration visibility comes from official IR. Internal declarations continue to
use the existing module-export policy; this is not Kotlin friend-module support.

Target validation checks allocation separately from member access: protected
constructors permit same-owner allocation and direct derived `super`, not external
`new`; private constructors permit only same-owner allocation. Protected instance
members require an owning/subclass scope and a compatible derived receiver;
unrelated and sibling receivers are rejected. Static access, interface contracts,
override narrowing and setter permissions are checked through declaration owners.
Properties whose getter/setter permissions differ use existing accessor lowering
and private backing storage, rather than publishing a writable field.

Official `ES6ConstructorLowering.generateCreateFunction` retains source constructor
visibility. Common `DefaultArgumentStubGenerator.defaultArgumentStubVisibility`
defaults to public: the ETS constructor pass overrides that hook (and its injector
counterpart) with the source visibility. It still reuses the official masked
argument evaluation, injection, initializer lowering and inliner unchanged.

Non-public inherited-method default helpers now retain their owning class and
visibility; public widening overrides use a derived forwarding entry. See
inherited-defaults.md for separate host/IR/module evidence. The access validator
still rejects inaccessible calls rather than widening source members.
Companion/nested-class access privileges and general local/inner secondary capture
are not claimed by this increment.

Visibility RED target-tests.hnXlFY proves that the former validator admitted an
external call to a private constructor. Source run-PspbN9 then caught backing
storage colliding with the accessor name; run-upeoy8 caught a public default stub
for a protected constructor. These are retained failures, not accepted runs.
Target GREEN target-tests.9W0mnW passes the full target suite including twelve
source-linked visibility refusals and the prior constructor-flow cases.

Final frozen source run-VDrnEa passes 90 flat + 90 multi-file JVM/ETS-host results,
four former-negative positive regressions (including Protected), five remaining
boundaries and deterministic six-module output. IR proof checks eighteen original
single-root factories, seven secondary native roots, eight native dispatchers,
protected entry ownership and exact constructor parameter/super symbols. All 74
input hashes match. Flat output SHA-256 is
`ac72e487bf1ac1c9e526bd0ab1c789bfdaa092d7326e750c88ce42ad71127dbf`.
SDK constructors-sdk-HfxCh4 checks all six unchanged modules and records clean
semantic checker coverage and ABC/HAP artifacts. This is not device execution or
the combined R2/native/UI gate.

Inner-chain regression green-weKarR passes 20 JVM results against both flat and
module output, strict host types, reversed-input determinism, owner-link checks
and eight source-linked exclusions. Earlier green-5fhmyw failed only its stale
secondary-constructor diagnostic expectation: the earlier capture-aware allocation
guard now reports the constructor span instead of the old primary-only class
guard. The updated test requires that exact reason and constructor span; no
exclusion is skipped. Main self-check and `git diff --check` pass. No independent
reviewer or device run is claimed.
