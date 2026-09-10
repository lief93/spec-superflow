# Reuse An Existing Harmony Business Component

Reuse can be discovered from an existing target or explicitly registered. Without a
matching component, source-definition-to-page-local-builder translation remains
unchanged. Reuse does not automatically port Android callback/network business code.

## Automatic Matching (Default For The Page Command)

`migrate_compose_page.py` now scans `<target>/<module>/src/main/ets` before projection.
Use `--component-dir` to narrow that scan and `--page-output-dir` to independently
place generated pages. Paths are absolute or relative to the target project root,
inside the selected module's ETS tree. The output subtree is excluded and imports
are relocated automatically. See [custom directories](source-page-workflow.md#custom-component-and-page-directories).
No per-component registration is required. A new target with no components simply
uses normal generation. `--no-auto-component-reuse` disables discovery.
For the individual `generate_lanhu_source_page.py` command pass
`--harmony-target /path/to/harmony --harmony-module entry` (module defaults to entry).
The source JSON command is unchanged; discovery runs during projection, not in the
single-JSON backend. Existing component files are read-only and never replaced.

The SDK ArkTS syntax-tree parser reads named, directly exported `@Component` /
`@ComponentV2` structs and top-level exported `@Builder` functions. It does not execute
their bodies. Generated directories, dependency/build directories, symlinks, private
declarations, and `@Entry` pages are excluded. Default exports, barrel re-exports,
external packages, inherited/aliased model types and generic signatures are not
automatically resolved; use explicit adapters for these cases.

Matching uses the component's simple name, every Android parameter's name and its
supported equivalent ArkTS type. Callback argument names do not affect type identity.
String/Boolean/numeric primitives, nullable primitives, Color -> ResourceColor,
Dp/TextUnit -> numeric vp/fp, explicit empty no-argument callbacks and no-argument
content slots are supported. Struct slots must be `@BuilderParam`; function calls
use target declaration argument order, while struct calls use named properties.
Literal string/number/boolean initializers can supply omitted target type annotations.
Internal `@State`/`@Local` and storage/context state are not caller parameters.
Additional target struct properties are allowed only when optional/defaulted.
Two-way bindings, Modifier, arbitrary model objects, collection values, nonempty
business callbacks and parameterized slots require separate adaptation; they are not
dropped or replaced with guessed values. A matching declaration is not proof of a
valid target project: native build checks, including ArkUI reserved names, still apply.

Explicit `COMPONENT_ADAPTERS` take priority. Without one, exactly one compatible
target is required; type mismatch, unresolved arguments or ambiguity retain the
Android body and report incomplete reuse, never silently choosing the first match.
`lanhu/component-discovery.json` records scanned declarations and per-definition
`matched`, `not-found`, `explicit` or `incompatible` decisions. A `matched` decision
means signature selection; successful argument binding is separately recorded in
the generated JSON / `reused_business_components` manifest.

Parser dependencies use `DEVECO_HOME` / `DEVECO_SDK_HOME` where available. For another
installation set `ARKTS_TYPESCRIPT_PATH` to the SDK's
`ets/build-tools/ets-loader/node_modules/typescript` directory (or its library file),
and optionally `ARKTS_NODE` to the Node executable. Standard npm TypeScript does not
parse ArkTS structs. The local macOS DevEco installation is a fallback, not a pinned
SDK version; no dependency is downloaded. Missing parser dependencies produce an
actionable error rather than an empty successful scan.

## Register Once Per Project

Use the same reviewed, hash-pinned Python module manifest passed to `--api-adapters`.
Export `ADAPTERS = []` when the module contains only component adapters:

```python
from ui_migration.frontend.component_reuse import ComponentAdapter

ADAPTERS = []
COMPONENT_ADAPTERS = [
    ComponentAdapter(
        id='company.account-card',
        android='com.company.accounts.AccountCard',
        module='@company/design-system',
        export='AccountCard',
        parameters={'accountName': 'title', 'balance': 'balance'},
        slots={'actions': 'actions'},
    ),
]
```

The Android signature in this example has exactly `accountName`, `balance`, and
`actions: @Composable () -> Unit`. Every parameter must be accounted for; a missing
mapping, unresolved argument, duplicate target property, or ambiguous source identity
is reported at `source.component_reuse`. The original component body is retained on
mapping failure, and the translation remains incomplete. Do not treat that fallback
as successful reuse.

Selectors use the resolved fully qualified Android definition name, not display text,
simple-name similarity, or screen geometry. If that selector identifies multiple
source declarations, add `source='path/AccountCard.kt'` and/or `declaration_id` from
the source component definition. Two matching adapters are an error, not a priority rule.

## Code-Polymorphic Parameter Adaptation

Subclass `ComponentAdapter` and override `properties(arguments)` when the target
library needs a different value representation. Arguments come from the existing
fixed-state evaluator, including defaults and caller parameter forwarding:

```python
class SizeAdapter(ComponentAdapter):
    def properties(self, arguments):
        size = arguments['size']
        if size.unit != 'dp':
            raise ValueError('expected dp')
        return {'diameter': size.value}  # Target property uses vp.
```

Supported output values are string, boolean, finite number, null, or a structured
resource-library reference. A `platform_resource_reference` returned by an existing
keyed resource API adapter is retained as a target call, not forced to a literal.
No arbitrary ArkTS code is accepted in the JSON. Callback bodies, arbitrary model
objects, and Modifier chains do not silently disappear: they need a separate supported
mapping and otherwise remain unresolved.

## Content Slots

The first supported slot form is explicit caller-supplied, no-argument composable
content, mapped to an ArkUI `@BuilderParam`. Caller root IDs are captured before
Android implementation expansion and survive fixed-state/list expansion. The target
call includes all mapped slot roots exactly once, in source order. Android component
internals are replaced by the library; caller content is still translated normally.

Named/forwarded callable references without explicit caller roots, receiver-scoped or
parameterized slots are not claimed supported; they produce a reuse diagnostic. Do not
replace them with an empty builder. Multiple ordinary inline named slots are supported.

## Single JSON And Output

Run the existing page command with `--api-adapters /path/to/adapters.json`.
The selected record is embedded in `migration.source.component_reuse` in
`version_json.json`, containing Android definition identity, target module/export,
resolved properties, and slot child IDs. The ArkUI backend reads only that JSON;
it neither loads the Python module nor rereads Android source.

For the example above, generated code calls the imported `AccountCard` with mapped
properties and typed slot-builder closures. Nested caller parameters are forwarded
through the enclosing generated builder, not frozen into the slot method. It does not generate another AccountCard
implementation. Target symbols stay readable; aliases/suffixes disambiguate collisions.
The `.migration` result includes `reused_business_components` with each selected
adapter, source definition, target, properties and slots. Local generated builders
remain reported separately under `business_components`.

The target library owns measurement and drawing of the reused component. Source-side
artboard frames are not proof of its target geometry. Translation and field-consumption
gates prove the declared call was emitted, not that both libraries look identical.
Verify the actual library version/import/parameter types with a native build; use
paired runtime screenshots for visual acceptance. No target library is installed or
invented automatically.

## Regression Checks

```bash
cd "$SKILL_ROOT/scripts"
python3 -m unittest test_component_interfaces test_component_reuse test_component_discovery test_business_components test_keyed_resources -q
```

Tests cover explicit identity, no same-name guessing, ambiguity, parameter defaults
and forwarding, key references, code-level unit conversion, inline slots, repeated
list instances, nested local builders, missing parameters, and unsafe JSON values.
Generation tests delete the source JSON and Python extension before the ArkUI step.

## Generated Component Interfaces

When no external-library adapter matches, the source-body generator now emits the
original component name and complete ordered parameter declaration, rather than an
interface inferred only from currently rendered text/images:

```kotlin
@Composable fun AccountCard(title: String, accountId: Int, loading: Boolean) {
    Text(title)
}
```

```typescript
@Builder
export function AccountCard(title: string, accountId: number, loading: boolean) {
  renderAccountCard({ title: title, viewId: 'AccountCard_Text' })
}
```

The example's `accountId` and `loading` are retained even though the selected UI body
does not use them. Actual calls pass every parameter. Source defaults remain in JSON
and are materialized at calls; emitted builder declarations currently require all args.
Names are unchanged when legal/unambiguous; collisions need disambiguation. These are
source-file builders, not verified general-purpose shared-library APIs. Their source
relative paths are retained under the page output directory; same-file functions stay
together and cross-file calls use generated imports. A typed auxiliary context parameter
is added only when a builder transitively accesses page-owned state or runtime helpers.
The manifest's `source_organization` records file/method mappings. Identical owned modules
can be reused by another page; different selected-state bodies cause a conflict rather
than silently overwriting another page's component.

Type spelling follows ArkTS, while the JSON retains the original Kotlin declaration:

| Kotlin declaration | ArkTS declaration | Boundary |
| --- | --- | --- |
| String / Boolean | string / boolean | No value-based type guessing |
| Byte / Short / Int / Float / Double | number | Integer source bounds checked on captured arguments |
| T? | (T) \| null | Null does not erase the underlying type |
| List<T> / MutableList<T> / Array<T> | ReadonlyArray<T> / Array<T> | Nested type/value validation |
| Set<T> / Map<K,V> and mutable forms | ReadonlySet / ReadonlyMap / Set / Map | Signature only; captured value materialization still unresolved |
| (T) -> R | (arg0: T) => R | Signature retained; arbitrary business callback bodies not translated |

Unknown model classes, Long (no silent precision loss), Modifier and annotated
`@Composable` callback types do not become `any` or string. Their full source signature
remains in JSON, the report identifies each unsupported parameter, and a `preview*`
helper retains known UI without falsely claiming a compatible business interface.
Existing `BusinessSlot` preview rendering is not an equivalent public Kotlin slot type.
An explicit source empty callback can be emitted; an unknown/nonempty business callback
is never replaced by a guessed no-op. Callback wiring/business logic remains separate.

`source.component_interface` stores declaration types, defaults and typed arguments.
The backend recomputes the signature from the embedded definition and rejects changed
types or missing arguments. `.migration` reports `business_components.declared_interfaces`.
`render_scope=selected-source-state` means only selected/observed UI states are generated;
it does not prove arbitrary business-state transitions. If two observed layouts cannot
be distinguished by supported source state parameters, both previews remain and the
report is unresolved. Semantic IDs inside shared helpers are definition-relative, not
proof of unique per-instance runtime anchors. Use native builds for target type checks;
this contract and those builds do not replace runtime visual or business acceptance.

## Business UI Alternatives

Add `--preserve-component-ui-states` to the existing `migrate_compose_page.py` command,
or to `generate_lanhu_source_page.py` when running individual stages. No new business
state fixture is required. The flag is opt-in; the existing fixed-state behavior is
unchanged without it. ArkUI still consumes one `version_json.json` and never reopens
source or executes a business expression.

The entry function is the page. Project component calls below it are business
definitions, identified by declaration/source identity, not a `Screen` name suffix.
Only callee-owned UI branches are collected. A page can stay in its basic state while
its `AccountCard` retains loading/error/content UI. This is not a page-state gallery
or a new page-level state machine.

The first supported form is one `if/else-if/else` or `when` UI branch group in a
business component. Each alternative is projected in the caller's theme context,
preserves shared content/layout, and is embedded under
`meta.migration.componentUiStates`. Known selected page inputs determine the initial
component state; if unknown, an explicit UI placeholder default uses `else` when
available, otherwise the first source branch. The recorded source condition is
provenance only, not translated business logic. State IDs/names are never drawn into UI.

Generated example:

```typescript
private AccountCard(account: UiBusinessArgument | null, uiState: string = "else") {
  if (uiState === "then") { /* loading UI helper */ }
  else if (uiState === "else-if-1") { /* error UI helper */ }
  else if (uiState === "else") { /* content UI helper */ }
}
```

`uiState` is an auxiliary component parameter (renamed on a source-name collision),
not an Android business parameter. Source parameter names are retained; supported
types are nullable at this UI-placeholder boundary. Unknown model types use the
opaque `UiBusinessArgument | null`, never `any`, and are not dereferenced. Missing
display values use provenance-marked sample text; declared layout/style is not
replaced by guessed values. Callbacks/state-transition business remains separate.
Repeated instances use the same source-named builder and select a branch at the call.
Different instance-specific UI facts that cannot be forwarded through supported
parameters are reported as incomplete, not silently treated as the first instance.

Current limits are explicit: multiple/nested independent branch groups, dynamic
style expressions that still need values, unresolved callable slots, custom drawing,
and missing image resources may leave diagnostics. A PSI/collected-branch inventory
mismatch fails coverage rather than claiming all states were preserved. Unsupported
nonselected states also fail generation; they are not hidden by a working default.
This mode does not prove all business states are reachable or port their transitions.

Verification must cover each component alternative, not duplicate page variants:
source branch IDs and child inventory, generated branches/parameter signatures,
native build, and native UI assertions for each rendered state. The manifest's
`business_components.component_ui_states` includes per-instance/state component
counts and missing rendered IDs. Runtime visual fidelity is a separate check.

```bash
python3 -m unittest test_component_ui_states test_component_interfaces test_business_components -q
```
