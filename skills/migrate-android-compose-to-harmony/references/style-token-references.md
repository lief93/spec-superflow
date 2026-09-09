# Preserve Design-Library Token References

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

| JSON property | Token kind | Unit contract |
| --- | --- | --- |
| typography.font_size_sp | dimension | numeric sp -> fp |
| typography.line_height_sp | dimension | numeric sp -> fp |
| typography.letter_spacing_sp | dimension | numeric sp -> fp |
| typography.font_weight | number | target-compatible numeric weight |
| typography.font_family | string | target-available family name |
| typography.color | color | target-compatible color value |
| surface.background | color | solid fill |
| surface.corner_radius_dp | dimension | numeric dp -> vp, uniform corners |

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
- An unknown current value stays unresolved even if the target reference is known.
  Generating compilable code does not certify a comparison value or visual parity.
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
