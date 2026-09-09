# Preserve Design-Library Token References

## Code Adapters For Keyed APIs

For `AndroidColors.get(key)` -> `AppColors.resolve(key)`, implement a
`KeyedResourceAdapter`, rather than a table of final color values. One implementation
handles a key namespace, not one adapter per key. It extracts the source call's key
and declared parameters with PSI/shared evaluation; it does not read the resource's
final color or text. The target library still owns theme, locale and brand behavior.

```python
from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter

class CompanyColors(KeyedResourceAdapter):
    def harmony_target(self, key, arguments):
        return {
            'module': '@company/design', 'export': 'AppColors',
            'member': 'resolve', 'arguments': [key],
        }

class CompanyText(KeyedResourceAdapter):
    def harmony_target(self, key, arguments):
        return {
            'module': '@company/i18n', 'export': 'AppText',
            'member': 'read', 'arguments': [key, arguments['name']],
        }

ADAPTERS = [
    CompanyColors('company.colors', ('company.android.AndroidColors.get',),
                  'color').declaration(),
    CompanyText('company.text', ('company.android.text',), 'string',
                parameters=('name',)).declaration(),
]
```

Register the reviewed Python file using the existing `--api-adapters` manifest
described in [project-api-adapters.md](project-api-adapters.md). The manifest only
selects trusted code; it is not a key/value mapping table. `harmony_target` is the
polymorphic extension point. Return `None` for unsupported keys; do not guess a
fallback color. A different library can implement the method differently, reorder
arguments or choose a different export/member without changing the generator.

The single page JSON preserves the key, kind and structured target call in
`source.style_token_references`. For example, the generator emits
`.fontColor(StyleToken0.resolve('text.primary'))`, with a deduplicated import, even
when `style.typography.color` is null. That null means no literal comparison value,
not a missing target expression. The backend never loads the Python extension or
reopens source/style/resource files. Raw ArkTS snippets are not accepted.

Supported keys are nonempty strings resolved from literals, known aliases/parameters
or selected branches. Additional declared arguments currently accept finite scalar
values/null; missing inputs, undeclared arguments and unsupported transformations
stay unresolved. String references support plain text, input text/placeholder
values and accessibility descriptions. Rich-text spans and composable input-label
slots still require their own UI semantics; a string reference is not a builder.
Color and numeric references support the property table below; dimensions declare
`source_unit='sp', target_unit='fp'` or `dp`/`vp` on the adapter. Image sources,
composite brushes and arbitrary object-valued expressions are separate capabilities.

### Typed Business Arguments

A resource call can be passed through arbitrary **parameter names** declared as
`String`, nullable `String`, or supported string-list/array parameters. The
`component_interface.arguments[].value` retains the typed
`platform_resource_reference` (key, return kind, target module/export/member and
literal call arguments), rather than coercing it to a string or executing it.
Numeric references must likewise match a supported declared numeric type;
color/dimension references do not implicitly become unqualified numbers/strings.

The backend emits the target call at the business invocation and forwards named
parameters through nested components. All imports use the shared resource emitter.
For example, `MyCard(customLabel = text("title"))` can become
`this.MyCard(StyleToken0.read('title'))`, while its text body uses `customLabel`.
No adapter per business parameter name is needed. At the native-property boundary,
the existing property/type rules still decide whether that value is valid for
text, accessibility, color or another supported property. Unknown model types,
arbitrary business computations and unsupported native properties remain explicit
limitations; this does not execute or migrate resource-library internals.

Tests: `python3 -m unittest test_resource_arguments test_keyed_resources -q`.

## Existing Member Mappings

Configure `tokenMappings` once in `project-style-definitions.json`. Existing style
extraction/reuse commands are unchanged. Explicit refresh preserves this configuration.
AI may draft the mappings from the two libraries' declarations; no AI completion step
or model API is called by the migration scripts.

```json
{
  "tokenMappings": {
    "company.design.AppTokens.fontSizeBody": {
      "kind": "dimension",
      "sourceUnit": "sp",
      "targetUnit": "fp",
      "target": {
        "module": "@company/design",
        "export": "AppTokens",
        "member": "fontSizeBody"
      }
    },
    "company.design.AppTokens.textPrimary": {
      "kind": "color",
      "target": {
        "module": "@company/design",
        "export": "AppTokens",
        "member": "textPrimary"
      }
    }
  }
}
```

This is a fragment to merge into the existing style definitions, not a replacement
for its schema/theme/sourceInventory fields. Prefer fully qualified Android names:
an explicit import alias is resolved before lookup. A short name can be configured
when the source has no qualifying import. Wildcard imports and ambiguous symbol
ownership are not inferred from equal literal values.

The existing pipeline is unchanged:

1. Source analysis plus fixed-state projection resolves available values and records
   configured references in each node's `source.style_token_references`.
2. `version_json.json` carries those references and the ordinary resolved style facts.
3. ArkUI generation reads only that JSON. It emits a deduplicated, aliased import and
   uses the member expression instead of baking the resolved value into the property:

```typescript
import { AppTokens as StyleToken0 } from '@company/design';
// Inside the generated component:
Text('Example').fontSize(StyleToken0.fontSizeBody)
```

Install/configure the Harmony library in the target project separately. `module` uses
normal ArkTS module resolution; relative paths are relative to the generated `.ets`
file. The script does not install packages or copy a company's private library.
Declarations, export names and actual types must pass the target native build.

## Supported References

### One Resource Adapter Interface

Use the same `KeyedResourceAdapter` for source calls and properties. Implement
`resolve(reference)` and register the source symbols it owns; no property-specific
base class or access-mode choice is needed. One instance can own both forms:

```python
from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter

class ThemeColors(KeyedResourceAdapter):
    def resolve(self, reference):
        key = reference.key
        if key is None:
            return None
        # Translate key here if the Harmony library uses a different identifier.
        return {"key": key, "target": {
            "module": "@company/design", "export": "ThemeBridge",
            "member": "color", "arguments": [key]}}

ADAPTERS = [ThemeColors("project.theme-colors",
    ("company.DeclarativeTheme.colors.*", "company.getColor"), "color").declaration()]
```

Load this module with the existing `--api-adapters` manifest. `reference` contains:

- `symbol`: the full source symbol after resolving explicit imports/aliases.
- `kind`: the declared expected resource type (`color`, `string`, `dimension`, `number`).
- `key`: a suggested key, from the configured call key parameter or the direct
  property name. This is not assumed to be the library's final canonical key.
- `arguments`: read-only evaluated arguments, including the key argument. Named
  arguments retain their names; positional arguments use `key_parameter` and
  `parameters`, with remaining positions identified by their zero-based index string.

The project can use `symbol` and `arguments` to return its own normalized `key` and
`target`. `target` is a validated expression description (import/member/call arguments),
not arbitrary ArkTS source text. For example, both `colors.primary` and
`getColor("primary")` can return a call using the normalized key `palette.primary`.

The `.*` registration matches only direct members of the exact owner; it is not a
recursive or fuzzy name search. A different owner with a same-named property does
not match. Duplicate owner registrations and conflicting matches fail explicitly.
The adapter may return `None` for an unsupported reference. The target module must be
available to the generated ArkTS project; it is not copied or executed by Python.

Existing `harmony_target(key, arguments)` overrides remain compatible on this same
class; their `arguments` excludes the key as before. New implementations should
override `resolve(reference)` when they need full source identity or custom key extraction.

The PSI-backed source path follows pure helper returns, constructor fields and
immutable property getters (including block getters) to the registered library
boundary. For example `secondaryButtonStyle().loadingTint -> Tokens.spinner ->
DeclarativeTheme.colors.compButtonColorSecondarySpinner` preserves the final
`compButtonColorSecondarySpinner` key, not the business field `loadingTint`.
Library implementations need not be scanned once this boundary is explicitly mapped.
Ambiguous, cyclic, unknown-state and unavailable source wrappers remain unresolved.

Kotlin `library.property ?: Color.Black` retains a typed `fallback` in the reference
and emits `(ThemeBridge.color(key) ?? "#FF000000")`. Unknown source values are not
treated as null. Current fallbacks are type-compatible scalar literals (color,
string, number, or a dimension with matching units); arbitrary fallback expressions
or a second unresolved resource call are not silently discarded. A target that never
returns null/undefined can implement its own equivalent defaults instead.

After updating scripts (including the PSI Java helper), regenerate source-page and
version JSON. Existing call-based `KeyedResourceAdapter` implementations are unchanged.

| JSON property | Token kind | Unit contract |
| --- | --- | --- |
| content.text | string | target runtime string, plain text controls |
| content.placeholder / content.content_description | string | input placeholder / accessibility text |
| typography.font_size_sp | dimension | numeric sp -> fp |
| typography.line_height_sp | dimension | numeric sp -> fp |
| typography.letter_spacing_sp | dimension | numeric sp -> fp |
| typography.font_weight | number | target-compatible numeric weight |
| typography.font_family | string | target-available family name |
| typography.color | color | target-compatible color value |
| surface.background | color | solid fill |
| surface.corner_radius_dp | dimension | numeric dp -> vp, uniform corners |
| asset.tint | color | Image/Icon/AsyncImage template tint |
| control.active_color / control.inactive_color | color | progress color/track; divider active color |

Supported source owners include explicit text/input arguments, named fields of a
`TextStyle(...)`, `Surface(color=...)`, `Modifier.background(...)`, a single-dimension
`RoundedCornerShape(...)`, and selected Button/Card container-color arguments.
Project `componentDefaults` expression rules can also reference a mapped token.
Explicit page settings still take precedence over project defaults.

Parameter/local alias forwarding uses the recorded source bindings. Fixed `if`/`when`
selection uses the shared PSI evaluator. Unknown branches are not guessed. Expressions
that transform a token (for example `AppTokens.body * 2`) are not replaced with the
untransformed token: keep the ordinary resolved result, and report that reference
preservation remains unresolved. This is not a general Kotlin-to-ArkTS expression
translator. Composite TextStyle/Shape objects, gradient objects, arbitrary function
calls and resource-object dimensions require additional typed adapters.

## Validation Boundaries

- Numeric unit pairs are explicit: only sp/fp and dp/vp are currently supported.
  A dimension used for the wrong property reports a type/unit problem. There is no
  implicit px conversion, arbitrary target-code evaluation or string-code injection.
- A validated, typed and consumed target reference satisfies code generation without
  a final literal. Do not mark it unresolved merely because the Android value is unknown.
  Unknown keys, invalid type/unit/target declarations and unconsumed references still
  fail completeness. This does not certify a comparison value, library export/type,
  native build or visual parity; these require their own checks.
- A reference which reaches an unsupported consumer, including an unhandled inherited
  content-color provider, is reported as unconsumed. Container content-color references
  are not yet a general replacement for Compose's `LocalContentColor` propagation;
  explicit Text color references and Text project-default references are supported.
- Style references stay on the painted/content node when layout normalization creates
  outer padding/touch wrappers. They must not paint the outer spacing accidentally.
- Import aliases are stable within a render and deduplicated by module/export.
  Changing the target library does not require regenerating the page, but Android and
  Harmony library equivalence still needs native build and UI checks.

Tests: `python3 -m unittest test_style_token_references.StyleTokenReferencesTest -q`
from the skill's `scripts` directory.
Keyed API integration tests: `python3 -m unittest test_keyed_resources -q`.
Property API integration tests: `python3 -m unittest test_property_resources -q`.
