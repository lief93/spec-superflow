# Virtual overload identity and target spelling

## Official reuse and target responsibility

Pinned Kotlin 2.1.20 sources inspected:

- ir/util/IrUtils.kt: allOverridden walks resolved override symbols, including
  multiple interface edges. This API is called directly; the ETS backend does
  not infer overrides by comparing source names or parameter type strings.
- ir/backend/js/utils/NameTables.kt: JS resolves fake overrides before computing
  its backend-specific signature. The ETS backend reuses NameTable allocation,
  but not the JS signature hash, runtime suffix or JS-specific type erasure.
- backend/common/bridges/bridges.kt and ir/backend/js/lower/BridgesConstruction.kt:
  generateBridges separates the callable signatures from their implementation.
  Public IrBasedFunctionHandle already adapts IR declaration/abstract/override
  ownership to the common algorithm without a JS backend context. Both are now
  called directly. findConcreteSuperDeclaration resolves concrete fake-override
  implementations; the resulting ETS calls still use virtual member dispatch.

The existing OverloadNaming prepass connects real source declarations through
official override edges. A second identity-based grouping finds the overload
slots that coexist in a class scope, including inherited/fake declarations.
Each slot gets one spelling shared by its real implementations. When one generic
override joins distinct ancestor slots, the prepass preserves those slots and
chooses one body spelling. Common generateBridges supplies the other forwarding
entries. Only conflicting slots need fresh names; unrelated methods retain the original spelling. Existing
NameTable reservations protect source fields, methods and generated helpers.
Top-level/package-private overload allocation remains on its existing path.

Declarations and calls consume this one mapping. Canonical source symbol IDs,
parameter names and method sourceName remain unchanged. The typed target checker
continues to require exact override signatures and matching call identities.
An Int and a Double overload may both have target number parameters but still
have different source IDs and target names; runtime argument inspection is not
used to rediscover Kotlin overload selection.

## Accepted increment and remaining work

The non-bridging source family includes ordinary open-class overloads, interface
contracts, inherited overloads, class and method generic substitution, overrides
joining compatible interface declarations, inherited default providers, and
unchanged inherited implementations. It composes with existing constructor and
default-helper consumers; no new evaluator or UI path is involved.

Generic joined slots now have typed forwarding entries, including the unchanged
BridgeJoin.kt former-negative fixture. Joined<String> and Joined<Int> retain the
original JVM result `text:x:int:7:other:a`; their independent interfaces are not
coalesced. A forwarding method has its own generated identity and source span,
exact parameter binding and one typed virtual call, not a duplicated source body.
Void implementations forward as statements; value implementations return values.

Concrete inherited implementations also use the common bridge calculation.
Official heritage substitution instantiates their signatures in the receiving
class, while the member call retains the original implementation symbol. A later
subclass override remains observable through both interface and base-class views.
Already inherited bridges are not re-emitted. No JS prototype/newTarget/arguments
runtime is introduced.

The common algorithm intentionally emits no abstract bridge bodies. ETS requires
explicit abstract entries for an abstract class's interface contract, including
when Kotlin has no explicit override declaration. The backend materializes only
missing signatures, with no body, using the resolved ancestor declarations.
The target validator now rejects a class that relies on an interface signature
alone as if it were an inherited class member. A historical bounded-receiver
fixture was corrected to declare that method; its inherited-generic check remains.

External inherited slots, covariant override results and private method shadowing
also retain explicit diagnostics. Existing unsupported overloaded extension,
context, vararg, suspend and reified forms are not enabled by this change.
The new test initially hit unsupported Double.plus in a method body. Floating
arithmetic remains a separate R3 runtime requirement: UnsupportedFloatBody.kt
preserves its refusal. Numeric overload selection is tested using distinct
Int/Double inputs and observable override return values without requiring that
unimplemented arithmetic.
Bottom-typed nullable string conversion is also outside this increment:
UnsupportedBottomText.kt retains a source-linked kotlin.Nothing? refusal. Nullable
String values still pass through generic/nullable bridge tests. R3 owns the
remaining string-conversion runtime semantics.

## Evidence

```sh
node tools/kotlin-ets/tests/inheritance/overloads/run.mjs
node tools/kotlin-ets/tests/inheritance/bridges/run.mjs
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/language/overloads/probe.mjs
bash tools/kotlin-ets/tests/target/run.sh
```

RED run-bzTIcK compiles and executes the original JVM fixture, then reaches the
old overloaded-inheritance guard. run-KJDBVY records the subsequent Double.plus
dependency boundary. run-AV49IQ is the first 25 + 25 host comparison. The expanded
run-r3CDVR adds inherited implementations, method generic binders and typed IR
identity proof before the explicit separate-bridge diagnostic was added.

Frozen run-jawUJj passes 30 flat + 30 module JVM/ETS-host results, strict host
types, two-file reversed-input determinism and all 63 frozen input hashes.
The probe checks 18 actual official override edges, 24 exact typed member calls,
source method/parameter names, the unchanged unrelated choose method, and a
source choose_0 name reserved against generated overload spelling. Four JVM-valid
declaration boundaries and the separate floating-body boundary have exact source
files, positive spans and no emitted ETS. BridgeJoin's original JVM behavior is
also executed, not merely type-checked.

Flat SHA-256: eb7645d54b5eaf845bbf606707cb4bca57990be5caa224f300881cccf9701adb.
Base.ets: 7d2037e94a112acfd933b377ce69e6e0afdb91e9e9f97500338ddc46e8d763c8.
Child.ets: a171c49e8932956f7c984f667620995c12391bb1bcfac4ffda3ef1675849fd16.

Regressions: legacy probe-MYKake passes its 30 JVM/host results and the unchanged
open/inherited/interface fixtures now generate successfully. Public-WOX202 passes
45 original/public-CLI results, including cross-file and legacy consumers. Target
qOWcdI passes the complete target suite with wrong-overload and stale-name
refusals. Inherited-default run-Clbp2s retains 65 flat + 65 module results, three
boundaries and 29 actual helper calls. These runs use the same compiler sources.

This is compiler-IR and host evidence, not ArkTS SDK, ArkVM or UI acceptance.
R2.3, R2.4 and the combined R2 gate remain incomplete.

## Joined-slot bridge evidence

RED run-N5jHaG records the original separate-bridge refusal after successful JVM
execution. run-Hdcaqg and run-eU2dkX expose ETS's explicit abstract-entry
requirement, with and without an original abstract override. run-pvnAi9 records
the concrete fake-override call refusal. These are preserved, not overwritten.
run-V9zyMF separately records bottom-typed nullable string conversion; its precise
refusal remains tested rather than being disguised as a bridge failure.

Frozen run-SXU2DE passes 45 flat + 45 module JVM/ETS-host outcomes over 60 pinned
source/test inputs. Three-file output is unchanged when input order is reversed.
The IR/target probe checks 14 actual common bridge edges, including four inherited
implementation edges, exact original method identities and parameter names,
single typed forwarding, and four malformed-target refusals. Void, nullable and
method-generic values, class-generic substitution, receiver/argument effects,
abstract contracts, later overrides, and already inherited bridges are covered.

Output SHA-256:
- Bridges.ets: 1987ace086f7ae41076b8c80ceced20a58f9aaf6a9eb5c606466f668e0dc74da
- BridgeJoin.ets: 25f1adc6372bf91416a012860f2d8cdf12f85a39c4f044b6be0ef78e704bb993
- Cases.ets: be02a6e9c86f2c62e17efbcb904b15a125335159a15aca55c0efd3daf6bce3f8
- FakeJoin.ets: 9b6806010d8ab121c7fcc9ba4e78b62b174cf6cde625ddf963ab3863acdae2b9

Overload regression run-7fboeZ retains 30 + 30 outcomes, 18 override edges and
24 typed calls. Its three output hashes are identical to run-jawUJj above;
BridgeJoin is now an unchanged-source positive. Target suite CzNQES passes after
the abstract-entry negative first failed in bWf44t. No SDK or native runtime
acceptance is implied.
Inherited-default run-OHKB8f additionally passes 65 flat + 65 module outcomes,
three boundaries and 29 official helper calls. All accepted frozen compiler/test
inputs were rechecked before commit.
