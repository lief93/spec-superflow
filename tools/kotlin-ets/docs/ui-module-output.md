# UI module output

## R1 output lane

The output lane owns `src/output/Modules.kt` and the focused multi-file target
fixtures below. It does not change target contracts, UI lowering, CLI wiring,
language lowering, or runtime implementations.

The current `EtsProgram` already represents component declarations and their
builder methods. Module output preserves their file ownership, declaration and
parameter names, decorators, fields, and method boundaries. Imports are derived
from typed references, not emitted text. No render aliases or preview bridges
are introduced here.

## Shared integration boundary

- Standalone builders, for a later sub-batch: currently
  `EtsFunction(builder = true)` is accepted only with `kind = METHOD`. Main must
  approve and implement top-level `kind = FUNCTION, builder = true` validation
  before UI lowering relies on exported global builders. The printer already
  has the function and decorator syntax. This does not authorize hoisting
  methods that capture a page's state, slots, or lexical `this`.
- Custom component calls: a component class symbol is a named class type, but
  `EtsUiElement.call` requires a function type. Please define a checked target
  representation for a source component invocation before cross-file component
  calls are generated. Do not mark a source component reference external or
  reconstruct a callable symbol from its printed name to bypass validation.
- Main owns the approved inheritance fields. Output collects `baseClass`,
  `interfaces`, and super-constructor types by identity. Member
  identities are not standalone declarations and must not become named module
  imports; member accesses depend on their typed receivers.

These requests do not block testing existing component declarations with
builder methods, cross-file value/type dependencies, and an actual SDK consumer.
The output lane does not use the unapproved builder/component-call forms.

Main's first page `--out-dir` increment preserves ordinary helper source-file
ownership while retaining one entry component containing builders and slot
methods. Splitting those methods according to their original Kotlin files is
not implemented and is unsafe without explicit context ownership.

Independently emitted source components need a shared checked invocation node
(or an equally explicit existing-node contract) connecting a non-external
component declaration ID to typed parameter/property bindings, builder slots,
and state ownership. Validation must check these against the declared component
interface; traversal must visit all bound values and captures; printing must
format the invocation only. Export policy and any required context bridge belong
to UI lowering, not output. There is no name-derived callable symbol, implicit
`this` hoist, arbitrary method splitting, or external-class escape hatch here.

## Bounded output changes

- Runtime providers receive the single owning `EtsFile` plus its assembled
  imports, including explicit SDK imports and source-symbol imports.
- External value references cannot acquire a source import merely because
  their ID string equals a source declaration ID. Non-external source type
  references, including component types and UI argument types, retain their
  exact declaration identities.
- Heritage types and super-constructor types use the same recursive dependency
  collection as signatures, expressions, defaults and fields. Super arguments
  are visited by the main-owned exhaustive target traversal.

`EtsProgram.imports` is still a program-wide list without symbol-bound per-file
ownership. Explicit imports are retained in every emitted file, not pruned by
spelling. The current runtime provider returns declarations, not new imports;
its caller must supply required SDK imports. Runtime helpers remain selected
per module from typed dependencies, with their provider-owned transitive closure.

## Focused verification

Run `node tools/kotlin-ets/tests/modules/ui-contract.mjs`. The runner copies
target/output/runtime inputs into a unique frozen test directory, records SHA256
hashes, and uses `-XX:ActiveProcessorCount=2 -XX:+UseSerialGC`. It compiles no
frontend or UI lowering and does not build or overwrite the production compiler.
The result records whether live inputs still match the tested snapshot.

The typed fixture produces five UI/helper modules and five heritage modules.
It checks component and builder-method names/parameters, state/default model
types, conditions and ForEach bodies, nested event/value imports, deduplication,
per-module runtime closure, explicit SDK imports, module-provider context,
deterministic output, signature-only imports, hidden exports, import collisions,
external identity isolation, heritage imports and inherited member identities.
Component type-only imports are also tested without inventing component calls.

Initial RED: `tests/modules/.work/ui-contract-OJJGUP` failed because runtime
selection lost explicit imports. First GREEN:
`tests/modules/.work/ui-contract-ZE7gtt` passed the output and heritage cases.
Later focused runs, if any, are recorded by their own `result.json` manifests.

Actual SDK consumer, prepared but not run by this lane:

```sh
node tools/kotlin-ets/tests/modules/ui-sdk.mjs <successful-ui-contract-evidence>
```

After main freezes production writers, rerun the focused contract, then invoke
the SDK runner in the serialized build slot. Set `KOTLIN_ETS_SDK_SEED` when the
existing default Harmony seed is unavailable. The runner copies generated ETS
bytes unchanged into a fresh seed clone, imports the two components and inherited
value consumer from `UiSdkIndex.ets`, compiles a HAP, and requires actual ETS input
records plus ABC/HAP artifacts. It verifies source, snapshot, consumer and emitted
module hashes; stale evidence is rejected. It never starts a device or patches
generated ETS. Full compiler/CLI regressions remain main-owned and deferred.

This target fixture is not Compose source-to-multi-file lowering acceptance,
JVM/ArkVM behavioral parity, native interaction, or visual equivalence evidence.
