# Typed project state adapters

Project adapters map external state-holder or dependency-injection calls to a
typed ETS value. They are ordinary build-time `AdapterModule` providers. The
core has no registry of framework API names.

Register each source call with `AdapterProjectInput` (`AdapterProjectCall`
remains a source-compatible alias for existing state adapters). Its
`AdapterCallIdentity` contains the resolved declaration's complete shape:

- fully qualified symbol;
- generic arity;
- optional dispatch and extension receiver types;
- value-parameter types;
- declaration return type;
- suspend flag.

The binding adds the concrete resolved generic source return, declared target
parameters and return type, value/statement/UI consumption, input kind,
optional content slot and target call/value ID, and optional required ambient
scope. All concrete returns for one declaration identity belong to one module.
Duplicate bindings, split declaration ownership, legacy FQName claims for the
same symbol, and duplicate target call/value IDs fail when modules are loaded.

The module's `CallRule` may return an injectable reference through
`AdapterTargetApi.value`, a constructed target value, or another typed ETS
expression. Target value types are checked structurally. An exact symbol ID in
the registration stays exact; omitting it permits the adapter's named target
type to match the source-derived symbol identity. Source and dependency
functions with usable bodies are lowered from those bodies before project
adapters are considered.

The supported project-input kinds are token, color, font, dimension, string
resource, image resource, business component, and target dependency. One
generic source declaration may have multiple bindings selected by concrete
source return and target return type. A value binding cannot declare or emit
`void`; statement and UI bindings must declare `void`.

A business-component adapter validates ordinary target parameters and an
optional `() -> Unit` content slot. It passes parameter expressions to
`Language.expression` and slot content to `AdapterUiServices.content`.
Conditionals, loops, captures, and ordinary Kotlin evaluation therefore stay
in the shared lowering pipeline.

`AdapterModules.manifestJson()` deterministically exports the validated module
IDs, complete source identities, target signatures, slot contract, imports and
all eight input kinds. The portable schema is
`docs/project-adapter-manifest.schema.json`.

Preflight classifies every failed project binding at the source call:

| Diagnostic | Preflight kind |
| --- | --- |
| `PROJECT_ADAPTER_MISSING` | `project_adapter_missing` |
| `PROJECT_ADAPTER_VOID_RESULT` | `project_adapter_void_result` |
| `PROJECT_ADAPTER_RETURN_TYPE` | `project_adapter_return_type` |
| `PROJECT_ADAPTER_ARGUMENTS` | `project_adapter_arguments` |
| `PROJECT_ADAPTER_SCOPE` | `project_adapter_scope` |

`tools/kotlin-ets/tests/project-adapters/run.mjs` covers cross-file output,
generic `StateHolder` and `Box<StateHolder>` returns, a constructed value,
same-name overload rejection, source-body priority, real ETS parsing/type
checking, and exact line/column reporting for all five failure kinds. Final
compiler evidence is under `tests/project-adapters/.work/run-y7GyqM`.

The generated `Models.ets`, `Calls.ets`, and `InjectionHost.ets` also compile
with the real DevEco SDK. The SDK evidence at
`/private/tmp/kotlin-ets-project-adapter-sdk-tkgvnX` contains per-module
compiler output, `modules.abc`, and `entry-default-unsigned.hap`.

The Architecture Samples proof uses a fixture provider for the exact generic
`androidx.hilt.navigation.compose.hiltViewModel` declaration and concrete
`StatisticsViewModel` result. Evidence under
`tests/preflight/.work/architecture-samples-XCI20N` shows the call becomes
supported and project-dependency coverage improves from 6/13 to 7/13. The next
backend blocker is `androidx.compose.runtime.remember` returning unsupported
`androidx.compose.material3.SnackbarHostState` at line 48, column 44.

The unified project-input fixture under `tests/project-input-contract` uses one
synthetic example adapter and contains no private project or API names. It
proves all eight input kinds, six target-return variants of one generic source
declaration, a structured business-component slot whose `if` and `repeat`
become shared ArkTS `if` and `ForEach`, and source-linked missing, parameter
type, return type, and void-as-value failures. Compiler evidence is under
`tests/project-input-contract/.work/run-4YUcSp`. DevEco evidence under
`/private/tmp/kotlin-ets-project-input-sdk-1glt1T` contains per-file compiler
artifacts, `modules.abc`, and a HAP.
