# Native allocation and secondary constructors

## Architecture

The Kotlin frontend resolves constructor symbols and delegation. After inherited
defaults and inlining, before local-declaration lowering, the ETS-specific IR pass keeps
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
secondary constructors remain diagnosed until target member visibility supports them.

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
minimal factory path. Protected secondaries, local/inner secondary capture
combinations, local classes in duplicated initializers and inherited initialization
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
the generated five modules unchanged with the real SDK. The verifier checks
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
