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
  ownership to the common algorithm without a JS backend context. Both were
  inspected for the next bridge step, not integrated by this increment.

The existing OverloadNaming prepass connects real source declarations through
official override edges. A second identity-based grouping finds the overload
slots that coexist in a class scope, including inherited/fake declarations.
Each slot gets one spelling shared by its real implementations. Only conflicting
slots need fresh names; unrelated methods retain the original spelling. Existing
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

Virtual overload support as a whole is NOT complete. A generic override can join
two distinct overload declarations from the same ancestor. Coalescing their names
would break other instantiations of that ancestor. BridgeJoin.kt demonstrates this
with Joined<String> and Joined<Int>; the original JVM result is
`text:x:int:7:other:a`. It now receives a source-linked separate-target-bridges
diagnostic instead of reaching an incompatible target method. The next step must
preserve those independent slots and reuse common generateBridges to identify
the required forwarding edges. Do not turn this diagnostic into a default result
or mark the virtual-overload plan item complete.

External inherited slots, covariant override results and private method shadowing
also retain explicit diagnostics. Existing unsupported overloaded extension,
context, vararg, suspend and reified forms are not enabled by this change.
The new test initially hit unsupported Double.plus in a method body. Floating
arithmetic remains a separate R3 runtime requirement: UnsupportedFloatBody.kt
preserves its refusal. Numeric overload selection is tested using distinct
Int/Double inputs and observable override return values without requiring that
unimplemented arithmetic.

## Evidence

```sh
node tools/kotlin-ets/tests/inheritance/overloads/run.mjs
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
