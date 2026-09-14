# Compose basic controls

Each control family lives in its own file under `src/ui/controls/`. A family
can recognize the Material 2 and Material 3 versions of the same control; no
file combines unrelated controls. Column, Row, Box and Spacer are separate,
as are horizontal and vertical dividers. HorizontalPager's native construction
has also moved out of the coordinator.

All rules still use `CallRule.lowerUi` / `adaptCall`, construct typed
`EtsUiElement` nodes and use the shared validator/printer. No string-source
parsing or page-specific control detection was added.

## Added coverage

| Source | Target | Explicit parameters supported |
| --- | --- | --- |
| Foundation BasicText (String overload) | Text | text, modifier, maxLines |
| Material3 HorizontalDivider, legacy Material Divider | Divider | modifier, thickness, color |
| Material3 VerticalDivider | Divider.vertical(true) | modifier, thickness, color |
| Material Checkbox | Checkbox | checked, onCheckedChange, enabled, modifier |
| Material Switch | Toggle with ToggleType.Switch | checked, onCheckedChange, enabled, modifier |

Checkbox/Switch state expressions use ordinary language lowering. Their
`(Boolean) -> Unit` callbacks also use that same lowering, preserving parameter
names and state writes. The target `onChange` Boolean signature is checked
separately from Swiper's numeric `onChange` signature.

The previously supported Column/Row/Box/Spacer/Text/Button/HorizontalPager
families retain their existing parameter limits. Splitting files does not
increase their overload or Modifier coverage.

## Boundaries

- This is bounded native-control mapping, not complete Material emulation.
  New controls retain native default colors, typography, dimensions and touch
  behavior unless explicitly mapped. No visual-equivalence claim is made.
- Divider defaults to a 1 vp stroke. Supported explicit colors and dp dimensions
  use existing shared framework value lowering. Thickness must currently be a
  literal or a lowered parameter reference: its value is used for both stroke
  and layout, so an effectful call cannot be duplicated silently.
- Nullable selection callbacks are explicitly rejected. Removing a callback
  from a native interactive control is not equivalent to Compose's passive
  checkbox/switch semantics.
- Custom Checkbox/Switch colors, interaction sources, Switch thumbContent,
  BasicText style/AnnotatedString/onTextLayout and other explicit unsupported
  arguments reject with source location. They are not discarded.
- Image/Icon, text input, progress controls, lazy lists and Scaffold are not
  added by this increment.
- The new real-IR fixtures use Material3. Material2 resolved symbols share the
  corresponding rules but were not separately SDK/visual tested in this batch.

## Adding a control

For a normal control, add one independent `ComposeControlRule` subclass. This
base class implements `CallRule`, routes `lowerUi` and applies the shared ordered
modifier handling. The control implements `control`, not another parser/printer.
It still needs registration and tests; adding a class alone does not activate it.

| Change | Additional work beyond the rule class |
| --- | --- |
| Uses existing target controls and supported value types | Register the class and add real-IR positive/negative tests. |
| Introduces an ArkUI API or overload | Add its typed signature to ArkUiCalls and verify with the SDK. |
| Introduces a platform value type or value-producing call | Use the shared CallRule.mapType/lower contract and test target consumption. |
| Requires resources, state or runtime behavior | Implement that capability through the shared services; do not hide it in emitted text or drop it. |

1. Add its own `controls/<Control>Rule.kt`, implementing `ComposeControlRule`
   (or `CallRule` when the API requires a different result kind).
2. Match the resolved official IR symbol, validate supported arguments, lower
   values/closures through `Language`, and construct typed target nodes.
3. Declare target signatures in `ArkUiCalls` if new ArkUI APIs are needed.
4. Register the rule in the coordinator's existing scoped rule list.
5. Add real-IR positives, source-linked negatives and target checks. New target
   syntax requires a focused SDK check, not an automatic device/visual run.

## Verification

```sh
bash tools/kotlin-ets/tests/ui/basic-controls.sh
bash tools/kotlin-ets/tests/ui/typed-program.sh
node tools/kotlin-ets/tests/ui/basic-controls-sdk.mjs /absolute/evidence/BasicControls.ets
```

The scripts use installed compiler/Compose dependencies, never substitute
source stubs. `KOTLIN_ETS_PROBE` selects the local classpath probe directory for
the basic-control test. `KOTLIN_ETS_SDK_SEED` selects an existing SDK host template.

Evidence from this increment:

- `$TMPDIR/kotlin-ets-basic-controls.DaLnoO`: real-IR RED for unsupported BasicText.
- `$TMPDIR/kotlin-ets-basic-controls.4QNLJ8`: negative-test RED showing that a
  thickness call could be duplicated. The rule now rejects that case.
- `$TMPDIR/kotlin-ets-basic-controls.OQZrcL`: typed control/state/parameter
  assertions, seven source-linked negatives and executed emitted Boolean
  callbacks (true/false/true) passed.
- `/private/tmp/kotlin-ets-basic-controls-sdk-yQrHbD/result.json`: the exact
  generated ETS passed the actual SDK, with unchanged bytes and ABC/HAP output.
- `$TMPDIR/kotlin-ets-typed-ui.BVJRzT`: original typed state/slot/Pager/runtime
  checks and shared ordinary/UI registration passed without the printer.
- `/tmp/kotlin-ets-controls-regression.jLcsho/Page.ets`: public CLI output is
  byte-identical to accepted native-06, SHA-256
  `4ec023d7a5fcf3e9a7ff4b6c4669a7633e35008fe38d043f443b38930d0cef89`.

SDK API signatures were checked against installed `checkbox.d.ts`,
`toggle.d.ts` and `divider.d.ts`. Compose's nullable callback behavior is
documented in the [official Checkbox API](https://developer.android.google.cn/reference/kotlin/androidx/compose/material3/Checkbox.composable).

Device interaction and visual equivalence remain untested for these additions.
