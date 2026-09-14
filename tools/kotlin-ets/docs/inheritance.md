# R1 Source Inheritance

## Finite Subset

The language lane supports non-generic source interfaces containing abstract
method signatures, interface extension, one source class base, implementation of
source interfaces, abstract classes and exact-signature method overrides. Real
primary constructors forward the actual resolved argument expressions to their
direct base. Existing standalone generic classes and property accessors retain
their earlier behavior; this is not generic dispatch support.

Calls through interface/base parameters and calls to inherited methods retain
native virtual dispatch. Source method/parameter names and declaration boundaries
are preserved. No inherited bodies, stubs, constructors, function-name bridges or
default field values are invented.

Explicit boundaries are source-linked rejections: default interface bodies,
generic heritage/members, inherited default method arguments, covariance,
overloads/ambiguous real overrides, explicit `super.method`, inherited property
access, abstract/overridden properties, private methods in the hierarchy, storage
name shadowing, secondary constructor chains, singleton inheritance and runtime
interface checks/casts. Constructor/initializer expressions may not expose their
own `this` in a hierarchy. This prevents Kotlin's default-initialized derived
storage from being confused with ETS pre-initialization behavior. Fields read
inside ordinary methods of their declaring base class remain supported.

## Official Binding

`IrCall.symbol.owner`, `overriddenSymbols`, `superTypes` and the real
`IrDelegatingConstructorCall` determine lowering. Official Kotlin
`collectRealOverrides()` resolves fake methods; only one unambiguous real owner
is accepted. The target member references the emitted declaration's exact
`etsFunctionSymbol` ID using its original source span, not the fake override's
span or a name lookup. Overrides carry real declaration IDs. Parameters and
return types must match the inherited Kotlin signatures exactly.

The integration owner provides `EtsClass.kind/baseClass/interfaces/abstract`,
`EtsFunction.abstract/overrides`, `EtsMember.symbolId`, and
`EtsSuperConstructorCall`. Heritage types retain source declaration IDs.
Interfaces/abstract methods use signature-only nodes, never empty implementation
bodies. The validator follows declaration identity for subtyping/member binding
and checks direct leading constructor delegation. Language lowering does not
replace graph validation with a cast or the context-free `etsAssignable` helper.

## Pinned Kotlin References

The cached official source root is
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/org/jetbrains/kotlin/`.
Tests execute the installed `kotlin-compiler-embeddable:2.1.20` on the JVM.

- `ir/util/IrFakeOverrideUtils.kt:40-109`: `collectRealOverrides` and removal of
  overridden ancestors are reused directly. `resolveFakeOverride` at line 125
  permits an interface-first fallback; this bounded lane instead requires one
  real result, so ambiguous ownership cannot silently become a name choice.
- `ir/backend/js/transformers/irToJs/JsClassGenerator.kt:43-54,94-124`: the JS
  backend derives base classes from official supertypes and preserves the
  constructor declaration boundary. This is an architectural reference, not a
  reusable ETS printer or prototype runtime.
- `ir/backend/js/transformers/irToJs/IrElementToJsExpressionTransformer.kt:177-200`:
  real delegating constructor calls use translated arguments; ES6 output uses
  a super invocation. ETS follows that typed semantic shape, not emitted JS text.
- `ir/backend/js/lower/BridgesConstruction.kt:149-153,245-251` and
  `ir/backend/js/transformers/irToJs/JsClassGenerator.kt:311-355`: bridge/interface
  default handling depends on JS signatures, naming and metadata. It is not
  directly reused. Those forms remain rejected rather than approximated with
  piecemeal wrappers.

## Verification

```sh
node tools/kotlin-ets/tests/inheritance/probe.mjs
node tools/kotlin-ets/tests/inheritance/run.mjs
```

The isolated probe compiles only target/language/rule dependencies, runs real
FIR-to-IR, retains `actual.ir`/`bindings.txt`, then validates interface signatures,
heritage, canonical fake-override bindings and real super nodes. It does not run
the CLI, frontend lowering chain or SDK. The initial source RED is retained at
`tests/inheritance/.work/probe-DQyRMn`: the previous language rejected interfaces.

The public CLI runner is reserved for the integration owner's production freeze.
It compiles the same `Inheritance.kt` with an independent JVM oracle and compares
30 outputs across zero, negative, ordinary and Int.MIN/MAX inputs. Cases cover
interface/base/inherited/overridden/abstract dispatch, argument and receiver
effects, constructor forwarding and initialization order, plus branch-selected
subtype returns. Negative inputs must produce source-linked `UNSUPPORTED` and no
output file. TypeScript AST checks preserve source names/signatures; host
transpilation is not an ArkTS legality check.

Both runners retain commands, compiler errors and source hashes in `.work`.
Actual Harmony SDK integration belongs to the main lane. No devices, review,
commits or generated-source edits are part of this lane.

### Frozen R1 Evidence

- Isolated actual-IR/typed GREEN: `tests/inheritance/.work/probe-3NV8JY`.
  Three inherited calls bind canonical declarations; four actual super calls,
  abstract/interface signatures and the complete typed hierarchy validate.
- Main's full public CLI GREEN: `tests/inheritance/.work/run-rXyioO/result.json`.
  All 30 same-input JVM/host results match; all 13 source-linked negatives pass;
  the production/input hash guard is unchanged.
- Unmodified generated output: `tests/inheritance/.work/run-rXyioO/Inheritance.ets`,
  SHA256 `1fbd583933d18bf931f193aa017c264579b98bd534b5bff00e14c0cb75eebbe2`.

SDK and native integration remain pending. These GREEN results certify the
specified IR/typed and JVM/host boundaries, not ArkTS legality or ArkVM behavior.
