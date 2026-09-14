# Native allocation and secondary constructors

## Architecture

The Kotlin frontend resolves constructor symbols and delegation. After inherited
defaults and inlining, before local-declaration lowering, the ETS-specific IR pass keeps
one real primary constructor and converts secondary `this(...)` chains to static
factory methods in the original class. Calls are rewritten by constructor symbol,
not by spelling, argument names or target overload guesses.

The factory's first local receives the delegated constructor/factory result.
Its remaining original body operates on that instance, and every constructor
return returns the instance. Allocation and primary property/init blocks occur
only at the native primary constructor, before secondary bodies unwind in order.
Ordinary methods and constructor parameter names remain source-owned. Kotlin
secondary constructors have no separate method name; the minimum synthetic
factory name is allocated by official JS NameTable, with user names reserved.

Generic class parameters are copied into static factory method parameters.
Default expressions retain their value/type bindings and evaluate at call time;
they are not virtual inherited method defaults. Native private primary
constructors remain private and are called from their owning class's factory.
Private secondary factories and private class methods also retain target private
visibility, rather than exposing an additional public construction path. Protected
secondary factories remain diagnosed until target member visibility supports them.

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
No-primary construction, abstract/sealed secondary constructors, delegation to
superclass secondary constructors and local/inner secondary capture combinations
still require further work. They must
produce source-linked diagnostics and no output, not allocate the wrong class.
Primary-only classes continue through the existing native constructor path.

Run `node tools/kotlin-ets/tests/constructors/run.mjs` from the repository root.
The harness freezes implementation/fixture hashes and records commands, JVM
results, flat and module ETS-host results, strict host type checks, source-bound
IR assertions and negative diagnostics under `tests/constructors/.work/run-*`.
Host checks are not ArkTS SDK, device or UI-equivalence acceptance. The combined
R2 SDK/native gate remains pending.

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
