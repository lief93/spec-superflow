# Project API Adapters

Use this extension point when two source APIs produce the same supported semantic
value, such as an image reference, font family, brush, size or shape. Do not add a
project-name branch to the generator. The renderer still consumes only
`version_json.json`; it never imports project Python or rereads Kotlin source.

## Project Component Defaults

Use `componentDefaults` in the existing `project-style-definitions.json` for styling
differences that do not require a new API. This is declarative data, not Python:

```json
{
  "componentDefaults": {
    "Button": {
      "surface.background": {"expression": "MaterialTheme.colorScheme.primary"},
      "surface.corner_radius_dp": {"value": 12}
    },
    "Text": {
      "typography.font_size_sp": {"value": 14}
    }
  }
}
```

Merge this section into the style file; it is not a separate input document. To give
only buttons a project-specific red background, use `{"value":"#FFFF0000"}`;
another project can use `#FF0000FF`. Normal theme variations need only their own theme.
Keys match source component types exactly, with no project-name checks or wildcard overrides.

Priority is explicit source property > project component default > existing framework
default rules. Explicit transparency and zero values win. Unresolved explicit source
expressions also win: they remain unresolved rather than silently acquiring a default.
An unresolved project expression does not fall back to a framework value either.
Whole explicit `style`, `colors` or modifier expressions conservatively retain ownership
of their related properties. These defaults do not rewrite source modifiers or visibility.

Supported override paths are `surface.background`, `surface.corner_radius_dp`,
`surface.border`, `typography.color`, `typography.font_size_sp`,
`typography.font_weight`, `typography.line_height_sp`, `typography.letter_spacing_sp`.
Each property accepts exactly `value` (normalized page-style data) or `expression`
(the shared Kotlin value evaluator). Background accepts an ARGB color shorthand;
corner radius accepts uniform dp or the four-corner object. `componentState.enabled`
and other available fixed-state fields may be used in expressions. Missing state is
unresolved, not assumed. Unknown fields and invalid literal values fail validation.

Existing style caches without this section remain valid. Explicit theme refresh
preserves project overrides. The projected values and their provenance are embedded
in the single Lanhu page JSON; the backend does not read the style file separately.

To add an override property, register its source argument/modifier ownership in
`frontend/component_defaults.py`, ensure the page schema and backend consume it, and
test precedence plus generated output. This mechanism does not claim that all Material
controls already have complete default appearances, nor does setting a parent text
property introduce a new descendant-inheritance rule.

## Layer Responsibilities

| Layer | Responsibility | Not its responsibility |
| --- | --- | --- |
| PSI and source scopes | Calls, imports, parameters, wrappers, fixed-state branches | Guessing runtime business data |
| API registry | Qualified-symbol/import-alias and typed-receiver dispatch | Coordinates or component visibility |
| Capability adapters | Bounded values using the shared evaluator | Emitting nodes or ArkTS |
| Page contracts | Layout/style/hierarchy and unresolved provenance | Executing project extensions |
| ArkUI backend | Consume the one page JSON | Selecting source fallback paths |

Builtin capability files live in `scripts/ui_migration/frontend/api_adapters/`:
`resources.py`, `typography.py`, `graphics.py`, `layout.py`, and `state.py`.
The registry and trusted loader are separate modules. Core Kotlin operators,
modifier ordering, component/slot expansion, theme inventories and asset
materialization retain their existing owners; they are not all API adapters.

## Scan First

After the normal safe snapshot, repository analysis and source-page extraction:

```bash
python3 "$SKILL_ROOT/scripts/scan_api_adapters.py" \
  --source-page "$RUN/source-page.json" --output-dir "$RUN/api-scan"
```

This scan covers the selected page expressions and their collected bindings, not
every business API in the app. Run it on each selected page; it never executes
project extensions. Its API rows distinguish builtin handlers, source wrappers,
core modifier candidates, business/state calls and candidate value APIs. A
candidate is a triage item, not proof of unsupported functionality or correctness.
The generated Python skeletons are disabled and return `UNRESOLVED` until implemented.

Also inspect the generated page's `unresolved-worklist.json`. Missing list-builder
expansion or slot ownership is a core frontend issue, not an image/font adapter.
Custom drawing and third-party components must keep their explicit unsupported
status. Do not bypass these gaps by returning an invented layout from an adapter.

## Implement A Small Extension

An extension module exports `ADAPTERS`. Its handler receives a PSI call object,
read-only environment view, shared value/render functions and the recursion path.
Arguments must be resolved with that shared evaluator, not reparsed with regex.

```python
from ui_migration.frontend.api_adapters.registry import ApiAdapter
from ui_migration.frontend.page_model import UNRESOLVED

def photo(call, context, seen):
    argument = call.argument('id')
    return context.value(argument, seen) if argument is not None else UNRESOLVED

ADAPTERS = [ApiAdapter(
    'company.photo', 'image', ('com.company.design.photo',), photo,
)]
```

Prefer fully qualified symbols. Imported aliases resolve to the same handler.
Short aliases are optional fallbacks for incomplete source scope; ambiguous aliases
and duplicate symbols are errors, not priority-based silent overrides. Typed
members can declare `receiver_kind`, for example `text_style` plus `copy`, without
colliding with `color.copy`. Read the already resolved value from `context.receiver`
instead of evaluating the receiver again; chain dispatch evaluates each link once.
No class-name substring matching is needed.

Return scalar values, dimensions or supported semantic records. `UNRESOLVED` means
unknown, not `null` or invisible. The registry rejects non-finite values and
component-tree, bbox or visibility overrides. The existing value evaluator may
raise `LayoutExpressionError` when an unresolved value is requested; projection
records it as a local unresolved fact and retains the source component.

Only return kinds already understood by the contract. A genuinely new semantic
capability requires coordinated contract/backend support, not just an adapter.
For color/font/dimension/text APIs whose key should survive as a target-library
call, subclass `KeyedResourceAdapter` and implement `harmony_target(key, arguments)`;
see [keyed resource code adapters](style-token-references.md). No final resource
value is needed. The structured reference travels in the same page JSON; the backend
does not execute the extension. Existing value adapters remain available for actual
literal/asset materialization.
Add tests for aliases, layered parameters, unknown inputs and the final generated
property. Then validate one native page without editing generated output.

## Explicit Registration

Hash each reviewed module with `shasum -a 256 company_assets.py` and register it:

```json
{
  "schema": "ui-migration.api-adapters.v1",
  "modules": [{"path": "company_assets.py", "sha256": "THE_ACTUAL_64_HEX_DIGEST"}]
}
```

```bash
python3 "$SKILL_ROOT/scripts/generate_lanhu_source_page.py" \
  --source-page "$RUN/source-page.json" --state-fixture "$RUN/state.json" \
  --viewport-width-dp "$WIDTH_DP" --viewport-height-dp "$HEIGHT_DP" \
  --api-adapters "$RUN/extensions/adapters.json" --output-dir "$RUN/lanhu"
```

`generate_ui_state_previews.py` also accepts `--api-adapters`. Existing invocations
without that option keep builtin handlers. Changes to an extension require an
updated digest. JSON records the explicitly loaded module identities in the
migration state projection so generated output can be traced to its adapters.

Extensions are **trusted Python code, not sandboxed code**. Scanning a repository
does not authorize executing its modules. Review the module and its imports before
registering; the SHA pins listed entry modules, not their transitive dependencies.
The loader verifies all listed files before executing any and does not auto-discover
or install packages. Vendor required dependencies for offline environments.

## Limits And Gates

Existing Harmony business components have a separate `COMPONENT_ADAPTERS` export
in the same trusted module. See [business component reuse](business-component-reuse.md)
for source-definition selection, parameter conversion and `@BuilderParam` slots.
Scalar API adapters still cannot return or replace UI trees.

- This is an extension mechanism, not a claim of complete Kotlin/Compose coverage.
- Component emitters, static resource materializers and runtime-dependent defaults
  have separate contracts; a successful value adapter does not certify those stages.
- New projects can still expose core source-scope, DSL or default-style gaps.
- Scanner counts and Python tests are not native visual acceptance. Preserve the
  partial-generation verdict, native logs and paired screenshots when a page fails.
