# Android and HarmonyOS page snapshots

`generate_android_page_json.py` and `generate_harmony_page_json.py` produce the same
`android-to-harmony.page-snapshot.v2` schema. The result is the migration equivalent of a design
tool's `version_json`: one deterministic route/state, its exact screenshot, logical viewport,
component hierarchy, geometry, content, visual style, asset identity, state, provenance, and
unresolved source expressions.

## Device and screenshot rules

Android and HarmonyOS devices do **not** need identical physical pixel dimensions or density.
Geometry comparison uses Android `dp`/`sp` and HarmonyOS `vp`/`fp` as platform logical units.

Whole-screen pixel metrics are meaningful only when both captures represent the same logical
content viewport. Align all of the following:

- route, business state, scroll position, selected state, and deterministic data;
- orientation and cropped content aspect ratio;
- system-bar and cutout policy, captured as runtime Insets or deliberately overridden;
- font scale, locale, theme, and light/dark mode;
- animation frame or a frozen stable state.

Different examples such as Android `1080x2400 @3x` and HarmonyOS `720x1600 @2x` can compare as the
same `360x800` logical viewport. Two captures with different aspect ratios must use explicit crops
that identify equivalent content. Scaling a tall page into a short page without equivalent crops
does not create valid pixel evidence.

When both v2 page snapshots are supplied, the comparator automatically crops each screenshot to
its own `viewport.content_bounds_px`, excluding status/navigation bars and cutouts without assuming
a fixed height. Explicit `--left-crop` or `--right-crop` takes precedence. Component `x/y` geometry
is compared relative to the corresponding content origin, so different system-bar heights do not
become false application-layout deltas. The report records `crop_source` for both inputs.

The comparison report exposes `viewport_compatibility` with physical-size, logical-content-size,
orientation, aspect-ratio, and pixel-comparison compatibility facts. Geometry/style facts remain
independently comparable when physical dimensions differ.

## Required inputs

- `--components`: exact `android-to-harmony.component-bounds.v2` captured with the screenshot.
  Legacy v1 remains accepted but has no automatic content Insets.
- `--visual-facts`: `android-to-harmony.component-visual-facts.v1` for resolved runtime/source
  values. Match components through the same stable `semantic_key` used by the bounds capture.
- `--source-attributes`: optional display-content-free source inspection index.
- `--density`: Android px/dp or HarmonyOS px/vp scale for this capture.
- `--font-scale`: Android font scale or the equivalent HarmonyOS text scale.
- `--orientation`: `portrait` or `landscape`; the generator rejects a value inconsistent with the
  PNG dimensions.
- `--insets-px`: optional `left,top,right,bottom` override. When omitted, v2 component inventory
  runtime Insets produce safe-area and content bounds in both pixels and logical units. A legacy v1
  inventory falls back to zero Insets.

The generator refuses stale screenshots, mismatched component dimensions, duplicate semantic
keys, unknown style fields, invalid colors or hashes, impossible insets, and cross-platform visual
fact inputs. It derives logical asset dimensions from pixel dimensions and capture density when
they are not supplied. It does not overwrite an existing output.

## Visual facts schema

Every visual-fact component contains a stable semantic key and these sections:

```json
{
  "schema": "android-to-harmony.component-visual-facts.v1",
  "platform": "android",
  "components": [
    {
      "semantic_key": "PrimaryButton",
      "style": {
        "layout": {
          "padding_dp": {"left": 16, "top": 12, "right": 16, "bottom": 12},
          "margin_dp": {"left": 0, "top": 8, "right": 0, "bottom": 8},
          "layout_direction": "ltr",
          "z_index": 2,
          "alignment": "center",
          "horizontal_arrangement": null,
          "vertical_arrangement": null,
          "aspect_ratio": null
        },
        "surface": {
          "background": {
            "type": "linear_gradient",
            "colors": ["#FF3366FF", "#FF8844FF"],
            "angle_degrees": 90
          },
          "corner_radius_dp": {
            "top_left": 12,
            "top_right": 12,
            "bottom_right": 12,
            "bottom_left": 12
          },
          "border": {"width_dp": 1, "color": "#22000000", "style": "solid"},
          "shadows": [{
            "color": "#33000000",
            "offset_x_dp": 0,
            "offset_y_dp": 4,
            "blur_radius_dp": 12,
            "spread_radius_dp": 0
          }],
          "alpha": 1,
          "clip": true
        },
        "typography": {
          "font_size_sp": 16,
          "font_weight": 600,
          "font_style": "normal",
          "font_family": "sans-serif",
          "letter_spacing_sp": 0,
          "line_height_sp": 22,
          "text_align": "center",
          "max_lines": 1,
          "overflow": "ellipsis",
          "color": "#FFFFFFFF",
          "decoration": null
        },
        "asset": {
          "resource": "app.media.primary_icon",
          "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "width_px": 48,
          "height_px": 48,
          "width_dp": 24,
          "height_dp": 24,
          "content_scale": "fit",
          "tint": "#FFFFFFFF"
        },
        "transform": {
          "translation_x_dp": 0,
          "translation_y_dp": 0,
          "scale_x": 1,
          "scale_y": 1,
          "rotation_degrees": 0
        },
        "state": {
          "visible": true,
          "enabled": true,
          "selected": false,
          "checked": false,
          "clickable": true
        },
        "content": {
          "text": "Continue",
          "placeholder": null,
          "content_description": "Continue",
          "role": "button",
          "locale": "en-US"
        }
      },
      "provenance": [{
        "paths": ["style.surface.background", "style.surface.corner_radius_dp"],
        "origin": "source_resolved",
        "source": "Home.kt:42"
      }],
      "unresolved": [{
        "path": "style.surface.background.dynamic_theme",
        "expression": "MaterialTheme.colorScheme.primary",
        "reason": "theme value is state dependent"
      }]
    }
  ]
}
```

Eight-digit colors use `#AARRGGBB`, matching Android color literals and generated ArkUI resources.
Accepted provenance origins are `runtime`, `source_resolved`, `source_expression`,
`pixel_sampled`, and `manual_verified`.

All standard fields are materialized in the page snapshot. Missing values remain `null`; dynamic
or unresolvable values belong in `unresolved`. Never invent a resolved value merely to remove a
null. Canvas, WebView, video, maps, custom shaders, and device-dependent theme effects still need
local pixel evidence.

Because the visual facts may include product display strings, keep v2 page JSON local under the
same privacy boundary as its screenshots. Continue using the separate source-attribute inventory
when display-content-free diagnostics are required.

Capture code must resolve normal runtime properties directly and copy source-only properties from
the exact component declaration or resolved resource. Emit exactly one compact marker from the
same deterministic state used for bounds and screenshot capture:

```text
ANDROID_VISUAL_FACTS:{...component-visual-facts.v1...}
HARMONY_VISUAL_FACTS:{...component-visual-facts.v1...}
```

Extract and validate those records without hand-copying JSON:

```bash
adb ... | python3 "$SKILL_ROOT/scripts/extract_android_visual_facts.py" \
  --output "$NEW_ANDROID_VISUAL_FACTS"

hdc ... | python3 "$SKILL_ROOT/scripts/extract_harmony_visual_facts.py" \
  --output "$NEW_HARMONY_VISUAL_FACTS"
```

Do not claim complete extraction when a platform inspection API does not expose a property.
Android accessibility and HarmonyOS TestKit reliably expose geometry but not every visual style;
resolve the missing style from the exact XML/Compose/ArkTS declaration, record
`origin=source_resolved`, and retain dynamic expressions under `unresolved`. This distinction is
required for a reviewable result.

## Generate both page files

```bash
python3 "$SKILL_ROOT/scripts/generate_android_page_json.py" \
  --page-id home --state-id default \
  --screenshot "$ANDROID_SCREENSHOT" \
  --components "$ANDROID_COMPONENT_BOUNDS" \
  --visual-facts "$ANDROID_VISUAL_FACTS" \
  --source-attributes "$SOURCE_ATTRIBUTE_INVENTORY" \
  --density "$ANDROID_DENSITY" --font-scale "$ANDROID_FONT_SCALE" \
  --orientation portrait \
  --device-id "$ANDROID_DEVICE_ID" --device-model "$ANDROID_DEVICE_MODEL" \
  --os-version "$ANDROID_OS_VERSION" \
  --output "$NEW_ANDROID_PAGE_JSON"

python3 "$SKILL_ROOT/scripts/generate_harmony_page_json.py" \
  --page-id home --state-id default \
  --screenshot "$HARMONY_SCREENSHOT" \
  --components "$HARMONY_COMPONENT_BOUNDS" \
  --visual-facts "$HARMONY_VISUAL_FACTS" \
  --source-attributes "$SOURCE_ATTRIBUTE_INVENTORY" \
  --density "$HARMONY_DENSITY" --font-scale "$HARMONY_FONT_SCALE" \
  --orientation portrait \
  --device-id "$HARMONY_DEVICE_ID" --device-model "$HARMONY_DEVICE_MODEL" \
  --os-version "$HARMONY_OS_VERSION" \
  --output "$NEW_HARMONY_PAGE_JSON"
```

Create one pair for every route and visible state. A default page JSON cannot stand in for loading,
empty, error, dialog, selected, keyboard-open, or scrolled states.

## Comparison output

Pass the v2 page files as `--left-components` and `--right-components` to
`compare_local_screenshots.py`. The report verifies both screenshot hashes and includes:

- `component_presence`: explicit missing, ambiguous, and untagged components;
- `component_hierarchy_deltas`: parent, child-order, and sibling-index differences;
- `component_geometry_deltas`: `x/y/width/height` differences in logical units;
- `component_style_deltas`: property-level values and tolerances for spacing, surfaces,
  typography, assets, transforms, state, and content;
- color maximum-channel deltas and exact asset SHA/resource equality;
- proven-only paths on either side and unresolved expressions from both sides;
- `viewport_compatibility` explaining whether whole-screen pixel metrics are valid;
- local normalized, absolute-difference, annotated-difference, and side-by-side PNGs.

The comparator rejects different page/state identities before creating output. It sets
`pixel_comparison_compatible=false` when logical content bounds, orientation, font scale, or crop
aspect are incompatible. Physical asset pixels are retained but asset dimensions are compared in
logical `dp/vp` units, so equivalent `72px @3x` and `48px @2x` resources do not fail.

Both `comparison.json.verdict.status` and command stdout `verdict` are `pass` or `fail`. A strict
pass requires complete v2 snapshots, equivalent component presence and hierarchy, geometry within
1dp, no style differences, no one-sided proven paths, no unresolved facts, compatible viewports,
and color/luma/edge SSIM at or above `--min-ssim` (default `0.95`). Color comparison retains the
8-channel tolerance. Exit code zero means report generation succeeded, not that the verdict passed.
