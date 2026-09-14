# Global builder modules

## R1B scope

Output test ownership is limited to `tests/modules/global-builders/` and this
document. `Modules.kt` has not been changed: its existing top-level declaration
owner map and typed traversal cover global builder functions without a special
UI import path. Main owns validator/target changes; Compose source ownership is
implemented separately by the UI lane.

The approved target form is `EtsFunction(kind = FUNCTION, builder = true)` at
file scope. References use that declaration's actual non-external function
symbol. Invocations are `EtsUiElement(EtsCall(...))`, never fabricated external
globals, renamed aliases, printed-source substitutions, or hoisted `this` calls.

## Finite fixture

- `source/Model.kt`: exported `LabelModel`, field and constructor.
- `source/Labels.kt`: ordinary `labelFor(model)` with typed stdlib runtime use.
- `source/Values.kt`: ordinary `labelLength(label)`.
- `source/Badge.kt`: exported global `Badge(model, onSelect)` builder using
  `Text`, the model type and source value helper.
- `source/Dashboard.kt`: exported global `Dashboard(model)` builder invoking
  `Badge` inside `Column`; its event callback captures the explicit parameter
  and calls the two ordinary cross-file value helpers.

The target fixture checks exact declaration ownership and source spans, method
and parameter names, actual referenced symbols, required imports and runtime
closure, deterministic file ordering, no component envelope/implicit receiver,
and unrelated same-named builders remaining distinct. Negative cases cover a
hidden builder, hidden callback helper, missing builder/helper declarations,
local/import collision and an unknown symbol with the same display name. Every
failure must retain the source span and precede runtime provider invocation.

This is a hand-constructed typed target fixture, not a claim that Kotlin source
builders have already been split by the frontend/Compose lane. It does not
hoist page-owned state or builder slots. `onSelect` is an ordinary void callback,
not a composable builder slot.

## Shared contract boundary

Main now enforces source builder calls as UI invocations, rejects ordinary
functions in source UI invocation positions, and rejects ownerless `this`.
The fixture uses builders only through `EtsUiElement`; shared positive and
12-rejection contract evidence is main-owned (`tests5ISchC`). Unknown builder
symbols fail at the declared-builder check before ordinary reference lookup.
This lane does not invent a new effect/type contract or widen builder-slot
semantics.

## Prepared verification

After main declares the target API ready and grants a build slot:

```sh
node tools/kotlin-ets/tests/modules/global-builders/run.mjs
node tools/kotlin-ets/tests/modules/global-builders/sdk.mjs <successful-contract-evidence>
```

The contract runner freezes target/output/runtime inputs into a unique test
directory and records hashes. It uses `-XX:ActiveProcessorCount=2
-XX:+UseSerialGC`, compiling only the target-level test, not the whole backend.
The SDK runner requires those inputs still match, clones the existing Harmony
seed, copies every emitted module unchanged, and uses the fixed `Index.ets`
consumer to invoke the imported `Dashboard`. The seed can be supplied through
`KOTLIN_ETS_SDK_SEED`.

Every fixture module must have a runtime SDK input record and matching clean
typechecker/hash evidence. The runner records ABC/HAP artifacts and verifies
unchanged source, consumer, verifier and emitted bytes. It does not invoke a
device, inspect images, rewrite generated ETS, or use runtime stubs to force
coverage. SDK compilation is not native interaction or JVM/ArkVM parity.

## Verification results

After main's explicit isolated target/output SDK slot grant:

- First target run `tests/modules/global-builders/.work/contract-AQ54WX` reached
  the positive checks, then failed a negative-test diagnostic expectation. Main's
  new declared-builder check rejects missing UI symbols before ordinary reference
  lookup. The two affected expected messages were updated; rejection and source
  evidence checks were not weakened. No production change was needed.
- Target GREEN: `tests/modules/global-builders/.work/contract-IaasaM/result.json`.
  Source ownership, exact symbols/names/parameters, nested callback value/type
  imports, runtime closure and all six source-linked negatives passed. Live
  target/output/runtime inputs matched the frozen snapshot.
- Actual SDK GREEN: `/private/tmp/kotlin-ets-global-builders-sdk-p4AJqu/manifest.json`.
  All five unchanged generated modules have clean hashed checker evidence and
  runtime input records. `ohpm-install` and `sdk-assemble` exited zero; ABC and
  signed/unsigned HAP outputs are recorded with hashes.

The exclusive build slot was released immediately after SDK completion. No
public CLI, ComposeLowering, target, shared UI fixture, or production output
file was changed by this lane. SDK/target evidence is complete for this finite
fixture; source-level Compose splitting remains the UI lane's separate result.
