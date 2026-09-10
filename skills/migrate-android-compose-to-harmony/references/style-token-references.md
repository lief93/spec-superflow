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

## Type-Based Fallback

Every `KeyedResourceAdapter` receives unresolved expressions of its declared type
by default; there is no opt-in flag, second adapter class, or need to register each
token. Explicit symbol matching still takes priority. For example:

```python
from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter

class ProjectResources(KeyedResourceAdapter):
    def resolve(self, reference):
        prefix = 'company.Theme.colors.'
        if reference.symbol.startswith(prefix):
            key = reference.symbol[len(prefix):]
            return {'key': key, 'target': {
                'module': './ThemeBridge', 'export': 'ThemeBridge',
                'member': 'color', 'arguments': [key]}}
        return None

ADAPTERS = [ProjectResources('project.colors', (), 'color').declaration()]
```

Matching the prefix above is project-owned key extraction inside the handler, not
generator registration. The resolver is offered any unresolved expression with a
supported known type. `reference.expression`, `source_type`, `source_file`, and
`reason` describe the expression at the reached source boundary. `symbol` is the
import-qualified property/call identity when available; composite expressions have
no invented symbol. In type-fallback mode `key` is `None`: a field name is not proof
of a library key. The implementation must return its own nonempty key/target or None.
Returning None retains the unresolved diagnostic; the existing target visual-default
policy may still produce a candidate page with a reported degradation.

Type evidence comes from source parameter/constructor-field declarations, immutable
property declarations, explicit helper return types, or supported native property
contracts. Arbitrary business names such as `abc: Color` work. No Color/Dp inference
is made from a name containing `color`, `statusHeight`, or `Fixed200`. Currently
supported fallback types are Color, String, Dp, TextUnit and Int/Long/Float/Double;
dimensions retain dp/vp or sp/fp. Custom types/type aliases need additional resolution.
Adapters of the same kind/unit pair are tried in registration order. Returning None
continues to the next adapter; the first resolved result wins. If all decline, the
existing target default policy applies. Duplicate explicit symbols remain errors.

Known constants, fixture/framework context and normal explicit-symbol adapters are
tried before type fallback. Source wrappers/getters are evaluated before falling
back on their outer expression. Selected branches preserve their selected expression;
an unknown condition is offered as a whole expression, never one guessed branch.
Cyclic or ambiguous resolution is not hidden by a type fallback. The handler returns
the same validated target call/property description, never raw ArkTS snippets.

System-derived dimensions use the same interface: a declared Dp expression may map
to a target-side system bridge rather than a fixed Android-device height. Existing
known inset fixtures and consumed-inset accounting remain unchanged. This does not
add every system API or every dimension consumer: the property table above remains
the supported target-reference surface (arbitrary runtime height/padding references
are not enabled by registering a fallback). Target system bridges own their runtime
updates; resource conversion must not duplicate an existing safe-area adjustment.
For a nonnullable source Color, the target bridge must return a usable ResourceColor,
not undefined, unless the source reference carries a valid explicit fallback.

Regenerate analysis/contract and source-page JSON when declaration type metadata is
missing in an older inventory, then regenerate Lanhu JSON with `--api-adapters`.
The backend still needs only the resulting page JSON. Type-based fallback tests:
`python3 -m unittest test_typed_resource_fallback -q`.

## Project Object Types

The same adapter supports named project/framework object types, including Compose
TextStyle, without an additional adapter class. Declare the source type identity
and the exported target type explicitly; identical short names are not proof of
cross-platform compatibility.

```python
class Styles(KeyedResourceAdapter):
    def resolve(self, reference):
        if reference.symbol != 'company.Typography.body':
            return None
        return {'key': 'body', 'target': {
            'module': './ThemeBridge', 'export': 'ThemeBridge',
            'member': 'style', 'arguments': ['body']}}

ADAPTERS = [Styles('project.styles', (), 'object',
    source_type='androidx.compose.ui.text.TextStyle',
    target_type={'module': './ThemeBridge', 'export': 'BusinessTextStyle'}
).declaration()]
```

An explicitly mapped business component can receive this object intact, for
example `Caption({ appearance: ThemeBridge.style('body') })`. The page JSON retains
the structured call, source type and target type; the backend needs neither the
Android sources nor the Python adapter. A native ArkTS build checks the bridge's
actual return type against the consuming component. The project must supply the
bridge and target component; the adapter does not generate their implementation.

This is an extensible named-type boundary, not a universal Kotlin-to-ArkTS type
compiler. Generic/structural/function type signatures are not accepted here.
Automatic same-name component discovery does not yet use object type mappings;
use an explicit component mapping for object-valued parameters. Native `Text`
cannot consume an arbitrary target TextStyle object just because it has that name:
native property projection still requires a supported consumer mapping. Returning
None keeps the unresolved argument rather than fabricating an object. Scalar
visual defaults do not invent business objects, callbacks or model values.

Verification: `python3 -m unittest test_object_resource_adapter -q`.

### Object Property Mappings

Object adapter results may also contain `properties`, keyed by Android member name.
Each value is a validated resource reference specification (`kind`, `target`, units
for dimensions, or `sourceType`/`targetType` and optional nested `properties` for
objects). This works for arbitrary named business objects, not just text styles.
The whole-object `target` remains usable by explicit component reuse. Undeclared
members are unresolved, never inferred from target field names or JSON metadata.

Native Text consumes mapped Compose TextStyle members through its existing typed
typography properties. Explicit Text arguments override `copy` arguments, which
override the original style. Opaque target objects without declared member mappings
remain unsupported by native Text; this does not imply support for every native
consumer or Kotlin type. No new adapter class or raw target-code format is added.

See the [complete owner-based example](../examples/object-properties/README.md),
including the executable Python adapter and Harmony bridge. It handles a token family
without enumerating individual members. Tests load the same example file:
`python3 -m unittest test_object_property_adapter -q`.

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
