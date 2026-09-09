# Material Default Styles

Framework defaults are distinct from project defaults. Resolve source attributes and
state, apply framework defaults for absent attributes, then project overrides where
source does not own the property. The final single page JSON contains those facts.

`frontend/material_defaults.py` owns these baseline defaults. `material_items.py`
retains app-bar, chip and list-item slot rules. `api_adapters/material.py` resolves
color objects. `material_controls.py` resolves selection/progress color tokens and
geometry. The backend never rereads Kotlin to select appearance.

| Control | Covered facts |
| --- | --- |
| Button / TextButton / OutlinedButton | Full round shape, content padding, theme colors, disabled opacity, outlined border; 58x40dp painted minimum, separate 48dp interactive minimum |
| IconButton / IconToggleButton | Transparent container, normal/checked/disabled content colors, 48dp minimum; outer modifier padding retained |
| Card / Surface | Theme container/content colors, medium/rectangular shape; explicit shapes and colors retained |
| OutlinedTextField | 280dp minimum width, 56dp container, 8dp label space, 16dp content insets, transparent container, corners, state-dependent border/text/label colors, expanded simple label |
| TextField | Base dimensions, content insets, typography/colors, simple expanded label, bottom indicator; floating/compound decoration remains incomplete |
| Text / BasicText | Explicit TextStyle versus inherited theme typography defaults |
| TopAppBar | Existing slots/insets plus direct TopAppBarColors constructor |
| Divider / HorizontalDivider / VerticalDivider | Theme outlineVariant color, explicit color preserved |
| Checkbox | checked/unchecked/disabled colors, check mark color, 20dp visual size and minimum interactive wrapper |
| RadioButton | selected/unselected/disabled colors, indicator color, 20dp visual size and minimum interactive wrapper |
| Switch | selected/unselected/disabled track/thumb colors, 52x32dp track, 24/16dp thumb diameters and minimum interactive wrapper |
| LinearProgressIndicator / CircularProgressIndicator | Primary foreground, baseline track, 4dp stroke, 240x4 / 40x40dp default size; explicit size/stroke/color wins |
| ListItem / FilterChip / ExtendedFloatingActionButton | Existing slot-aware sizes, insets, gaps, shape and theme colors in material_items.py |

All sizes above are logical dp, not screenshot pixel estimates. A controls fixture verifies
that selection controls and progress indicators compile and expose those dimensions in
Harmony's runtime tree. This does not certify identical platform-native mark/track drawing.
The checkbox profile uses the classic Material3 20dp visual checkbox, not the newer
Expressive 18dp token. Version-specific variants must not be described as covered by it.

`colors(...)` adapters preserve partial overrides: setting only `checkedColor` or
`contentColor` still resolves the other entries from the framework profile and selected
theme. Unknown explicit colors stay unresolved; explicit transparent/zero/null-border
values do not receive a replacement default. Empty project `componentDefaults` is enough
to use framework defaults. No per-project adapter or AI completion stage is needed.

The shared theme extractor includes the `ColorLightTokens`/`PaletteTokens` v0_210
light-color roles, including outlines, on-colors and surface-container levels. They
fill only omitted arguments of a known `lightColorScheme()` constructor; unknown
explicit arguments do not silently become framework colors. Existing saved project
style definitions are still reused unchanged until an explicit refresh. Runtime
theme facts can supply the active dark/dynamic palette.

Generation/consumption regressions live in `test_framework_control_defaults.py` and
`test_material_defaults.py`, including explicit overrides, disabled colors, one-dp
dividers, theme resolution, touch-vs-painted geometry and single-JSON output.

Official rule sources:
- [TextFieldDefaults](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/TextFieldDefaults.kt)
- [Button](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/Button.kt)
- [Text](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/Text.kt)
- [SpanStyle](https://github.com/androidx/androidx/blob/androidx-main/compose/ui/ui-text/src/commonMain/kotlin/androidx/compose/ui/text/SpanStyle.kt)
- [Checkbox](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/Checkbox.kt)
- [RadioButton](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/RadioButton.kt)
- [Switch tokens](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/tokens/SwitchTokens.kt)
- [Light-color tokens](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/tokens/ColorLightTokens.kt)
- [Palette tokens](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/tokens/PaletteTokens.kt)

This is a baseline profile, not certification for every historical Material version or
Expressive variant. Only independently verified states can be reported as passing.

## Remaining Boundaries

The label emitter covers empty, unfocused simple labels. Floating labels,
compound label slots and full filled-field decoration remain unresolved. Fixtures can
specify `__focused_component_id`; this does not implement reactive focus transitions.

Pressed/hovered/ripple animations, elevated variants, indeterminate progress, continuous
Slider fidelity and custom Switch thumb slots are not completed by these default rules.
Disabled Card elevation-dependent compositing is unresolved without an explicit color.
Material2 and every Material3/Expressive version are not interchangeable profiles.
Do not turn this property table into a claim that every property/state of every common
Compose component has passed pixel comparison.

Network images, monetary formatting and custom drawing are separate capabilities.
Native comparison must use the same state/crop and count empty-input `hint` text as
displayed content, not silently discard those labels from the runtime inventory.
