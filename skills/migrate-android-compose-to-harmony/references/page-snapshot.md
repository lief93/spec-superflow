# Android and HarmonyOS page snapshots

`generate_android_page_json.py`, `generate_harmony_page_json.py`, and the real-device wrappers
`generate_real_android_page_json.py` and `generate_real_harmony_page_json.py` produce the same
`android-to-harmony.page-snapshot.v2` schema. The result is the migration equivalent of a design
tool's `version_json`: one deterministic route/state, its exact screenshot, logical viewport,
component hierarchy, geometry, content, visual style, asset identity, state, provenance, and
unresolved source expressions. The real-device wrappers additionally retain the raw runtime tree,
the code-derived source page, and honest coverage/timing metrics in one new output directory.

The optional `style.input` section retains `single_line`, `read_only`, `password`,
`keyboard_type`, and `ime_action`. Password masking and keyboard type are separate facts:
`KeyboardType.Password` does not imply `PasswordVisualTransformation`. The source stage
records Compose defaults when arguments are absent, but never replaces an unresolved explicit
argument with a default. The target selects TextInput/TextArea from the JSON alone. Read-only
uses keyboard suppression and a content-change veto (API 20+), not disabled styling.
Complex decoration/label/error slots and unsupported keyboard combinations still fail the gate.

`style.control` retains primitive `value`, `minimum`, `maximum`, `steps`, `active_color`,
`inactive_color`, and `stroke_width_dp`. Booleans for Checkbox/Switch/RadioButton remain in
`style.state.checked/selected`. These are the supplied page state's facts, not a substitute
for business reducers or onChange bindings. `style.typography.soft_wrap/min_lines` preserve
explicit source text-layout arguments; the renderer's supported combinations are listed in
`page-layout-support.md`. An absent or unsupported value is never replaced with a demo state.

Axis-aligned, full-bounds Clamp gradients retain all colors and stops. Nonmonotonic stops,
color/stop count mismatches and null colors are rejected. Other brushes/endpoints cannot be
silently reduced to their first color. Absolute four-corner rounding is supported; asymmetric
Start/End rounding needs a resolved layout direction.

The source-to-Lanhu stage expands supported constant size/padding chains into nested layout
nodes, retaining the original component as the innermost body. It does not use reference frames
to implement the nesting. Draw operations interleaved with padding, repeated sizes on the same
axis, intrinsic/required sizes and unresolved expressions are not covered by this expansion.
See `page-support-inventory.md` for the current boundaries; the inventory is not visual approval.

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

## Capture real pages and bind runtime nodes to source

Use the real-page wrappers when the Android and Harmony applications are runnable:

```bash
python3 "$SKILL_ROOT/scripts/generate_real_android_page_json.py" \
  --contract "$CONTRACT" \
  --root-source "app/src/main/java/example/HomeScreen.kt" \
  --root-composable HomeScreen \
  --page-id home --state-id empty \
  --package com.example.android \
  --source-root "$ANDROID_SOURCE" \
  --runtime-source-map "$ANDROID_RUNTIME_SOURCE_MAP" \
  --serial "$ANDROID_DEVICE_ID" \
  --output-dir "$NEW_ANDROID_PAGE_DIR"

python3 "$SKILL_ROOT/scripts/generate_real_harmony_page_json.py" \
  --contract "$CONTRACT" \
  --root-source "app/src/main/java/example/HomeScreen.kt" \
  --root-composable HomeScreen \
  --page-id home --state-id empty \
  --source-root "$HARMONY_TARGET" \
  --runtime-source-map "$HARMONY_RUNTIME_SOURCE_MAP" \
  --bundle com.example.harmony \
  --serial "$HARMONY_DEVICE_ID" --hdc "$HDC" \
  --density 2 \
  --output-dir "$NEW_HARMONY_PAGE_DIR"
```

Android package filtering and HarmonyOS bundle filtering exclude system and other-app windows.
The Android wrapper removes its remote layout, runs `uiautomator dump`, takes the screenshot, and
then reads the new layout. The HarmonyOS wrapper removes both remote capture files, runs
`uitest dumpLayout`, runs `uitest screenCap`, and receives both files in that order. These fixed
sequences prevent stale artifacts from being silently paired with the current page. Each output
binds the screenshot and runtime tree SHA-256.

A runtime-source map has this strict page/state-specific shape:

```json
{
  "schema": "android-to-harmony.runtime-source-map.v1",
  "platform": "android",
  "page": {"id": "home", "state": "empty"},
  "runtime_tree_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "mappings": [
    {
      "runtime_component_id": "runtime-0-1-2",
      "source_semantic_key": "HomeScreen_Icon_42_3",
      "source_call_id": "app/src/main/java/example/HomeScreen.kt:42:Icon:3"
    }
  ],
  "inactive_source_components": [
    {
      "source_semantic_key": "HomeScreen_Snackbar_80_9",
      "source_call_id": "app/src/main/java/example/HomeScreen.kt:80:Snackbar:9",
      "reason": "inactive_source_branch"
    }
  ],
  "resolved_source_facts": [
    {
      "source_semantic_key": "HomeScreen_Image_50_5",
      "source_call_id": "app/src/main/java/example/HomeScreen.kt:50:Image:5",
      "path": "style.asset.sha256",
      "value": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "origin": "source_resolved",
      "source": "app/src/main/res/drawable/empty_state.png"
    }
  ]
}
```

Prefer a unique stable `runtime_id`; it remains valid across equivalent captures. Use
`runtime_component_id` only for a capture-bound mapping and require the exact
`runtime_tree_sha256`, because positional runtime IDs can change when the tree changes. Both forms
must name one exact deterministic source semantic key and `source_call_id`. Text equality and
content-description equality are diagnostic clues, not independent source-identity proof.

`inactive_source_components` is allowed only for source calls proven unreachable in this exact
captured state, such as a closed menu or absent Snackbar branch. It cannot overlap a runtime
mapping, repeat a semantic key, or name an unknown/mismatched call. `resolved_source_facts` is
restricted to `style.asset.resource` and `style.asset.sha256`; each value must be bound to an exact
source call and a repository-relative evidence source. Duplicate paths, invalid hashes, absolute
or parent-traversing evidence paths, and conflicts with already resolved source/runtime values fail
closed.

The emitted semantic page compresses uncaptured source wrappers to the nearest captured
source-semantic ancestor and preserves source preorder for siblings. Bounds containment is only a
fallback when source hierarchy is missing or ambiguous. This keeps platform wrapper nodes and
equal-size/rotated layouts from creating false hierarchy differences.

Real-page snapshots separate component meaning from platform measurement:

- `source_component_tree` is the source/business component hierarchy for the observed route
  branch. Its nodes retain source call identity, invocation arguments, modifier order, source
  style facts, and direct runtime instance bindings.
- The tree retains every expanded source layer, including layout primitives and composable slot
  invocations. Call-site children of a `@Composable` lambda parameter are attached beneath the
  exact `toolbar()`, `content()`, or other slot invocation inside the callee definition; they are
  not flattened beside the callee's internal layout.
- The tree indexes `business_root_ids` and `business_component_ids`. Every node declares whether
  it is a `screen_root`, project component, content slot, layout primitive, or visual primitive,
  and carries both its exact implementation children, nearest business owner, and the compressed
  business-component parent/children. Layout primitives such as `Column`, `Row`, and platform `View` therefore cannot
  replace `ScreenHeader`, `AccountActionPanel`, `SavingCard`, or another project component.
- Each source node lists direct runtime instances separately from mapped runtime descendants. Each
  rendered instance carries `component_context` with a proven, candidate, or unbound business
  ownership path and the runtime evidence used to derive it. Candidate ownership improves
  component-scoped first-pass generation but is never promoted to exact source identity.
- `components` is the rendered-state visual instance graph. Source-bound instances carry their
  exact call identity. Visible text, controls, repeated items, and navigation content with no safe
  one-to-one binding remain present with `source_mapping.status=unbound` and
  `method=runtime_visual_fallback`.
- generic Android/Harmony platform containers remain measurement evidence. They are not promoted
  to business component identity. A generic node may appear as an unbound visual surface only when
  its screenshot-proven background differs from its containing surface.

An unbound text instance may reuse the closest compatible typography role declared inside the
active source component tree when its captured line box and sampled color select that role. This
remains `source_expression` candidate provenance rather than an exact source binding; it improves
the generated first pass without turning a geometry match into false ownership evidence.

A generated `runtime.<digest>` ID remains the cross-platform identity of that unbound rendered
instance and is not remapped to an unrelated source `Text` by hierarchy order. When one exact
source-owned asset record joins a runtime label to a project component, the same join may narrow
that label's candidate typography to the component's matching `.title` or `.uiTitle` source field.
For a vertically ordered source `Column` whose image branch is followed by one explicit `Spacer`
and its label, the captured image-to-label gap comes from that component-local structure rather
than a page-wide fixed offset. These joins improve component ownership and visual facts while the
label's source mapping remains explicitly unbound.

This separation prevents missing runtime IDs from deleting visible UI while keeping source
ownership honest. Use the source tree to implement component ownership and behavior; use the
runtime instance graph for the captured state's geometry, content, and sampled appearance.

`source_component_tree.layout_relationships` records non-tree layout composition that ordinary
parent/child edges cannot express. A Compose `ConstraintLayout` child with `constrainAs` retains
the complete source constraint body plus the active, instance-resolved anchor edges, margin,
draw order, and `constraint` versus `overlay` composition. For example, a panel whose top links to
a sibling cover's bottom with `-24.dp` remains a foreground overlay rather than becoming the next
item in a `Column`. Unknown conditions, targets, or margins remain explicit unresolved records;
the generator must not guess or silently convert them to normal flow.

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
          "aspect_ratio": null,
          "width_dp": 120,
          "height_dp": 48
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

## Use the source-generated Lanhu page as generation input

After generating the source-derived Lanhu-compatible page JSON for one deterministic route/state,
pass that single page-fact input to the ArkUI generator:

```bash
python3 "$SKILL_ROOT/scripts/generate_arkui_page.py" \
  --target "$TARGET" --module entry \
  --page-json "$LANHU_PAGE_DIR/version_json.json"
```

The page supplies the complete source hierarchy and source-resolved layout/style intent. Any
runtime measurement used to resolve platform defaults is joined upstream and recorded as provenance
inside this same document. The generator preserves source parents, children, sibling order, flow,
constraints, padding, arrangement, and explicit local offsets. Ordinary `frame.left/top` values are
reference geometry and do not become global ArkUI positions. Only values with resolved runtime,
source, pixel-sampled, or manually verified provenance may drive code; unresolved facts and proven
properties without a safe ArkUI emitter remain in the ordinary `unresolved` list. The generator
must not read the Android source or migration contract to fill a missing page fact.

For source-generated Lanhu documents, prefer the direct generator input:

```bash
python3 "$SKILL_ROOT/scripts/generate_arkui_page.py" \
  --target "$TARGET" --module entry \
  --page-json "$LANHU_PAGE_DIR/version_json.json"
```

This path parses and validates `version_json.json` in memory; it does not create or consume an
`implementation-page.json`, migration contract, Android source tree, or second runtime page input.
A source-generated layer carries the
`android-to-harmony.lanhu-node.v1` migration extension for source-call identity and behavior-facing
semantics. Raw Lanhu fields remain the visual authority: `frame` owns full pre-clip geometry,
`realFrame` and `combinedFrame` remain diagnostics, and a runtime-visible intersection must never
overwrite `frame`.

Generate the source-attribute inventory at call granularity. Each captured runtime component must
use the exact deterministic semantic key for one source call; a composable-wide key that aggregates
multiple `call_id` values cannot drive generation. When a proven page fact replaces the same static
modifier or typography property, the page value is emitted once rather than appended as a duplicate
modifier.

The source-attribute inventory also records a source-semantic parent and preorder for every call.
It expands a project composable across a uniquely resolved invocation, then page generation
compresses uncaptured intermediate calls to the nearest captured source ancestor. Runtime
smallest-containing-bounds inference remains only for missing or ambiguous source hierarchy. This
keeps rotated children, equal-size wrappers, and platform-native container nodes from creating
false parent or sibling differences.

The page snapshot supplies the rendered visual target for that state. The Compose contract still
owns callbacks, state transitions, scrolling behavior, and responsive layout intent. A runtime
width or position must not be treated as proof that the source intended an absolute coordinate
across every viewport. Generate and compare separate state captures whenever the rendered tree or
style changes.

The default generated Harmony Stage window keeps status and navigation bars enabled and reserves
their system-owned areas. The page snapshot tree scales uniformly by the smaller of the host/content
width and height ratios, stays top-aligned, and is centered horizontally. Fitting both axes avoids
bottom clipping and accumulated vertical drift when the Android and Harmony content aspect ratios
differ, without introducing device-specific offsets.

Accessibility may omit a project-defined surface even when its pixels remain visible. A real-page
snapshot may add a screenshot-proven surface instance only after joining the region to source
background/shadow/elevation evidence and project-owned descendants inside the same region. It may
also repair a lightly clipped repeated list item from a complete sibling with the same parent,
business owner, width, and child signature. Both operations retain candidate provenance and must
not invent a source identity from geometry alone.

A source-owned image that has no runtime node may be projected only when one exact business
surface, intrinsic asset size, parent alignment, and a statically solvable offset determine its
layout. When that layout extends beyond the app content bounds, `source_layout_bounds_dp` retains
the full pre-clip layout while ordinary `bounds_dp`/`bounds_px` retain only the screenshot-visible
intersection. Generation uses the full source layout; page comparison continues to use the visible
frame. This prevents system-bar or edge clipping from either rejecting the page JSON or stretching
the visible fragment into a different image.

## Required component facts

Every source-generated component carries `required_facts`, and the matching Lanhu layer carries
the same records under `migration.requiredFacts`. Each record names the canonical fact path, the
source argument or modifier, its exact expression, and one of these statuses:

- `resolved`: the parser materialized the source value;
- `default_resolved`: a documented framework default applies;
- `symbolic`: the exact dynamic or relationship expression is retained for target translation;
- `not_applicable`: the field does not apply to this component state;
- `unresolved`: a required constant conflicts with or is missing from the parsed facts.

Structure, text constraints, asset identity/scaling, explicit layout parameters, surface styling,
and interaction boundaries are checked by component type. Optional fields are not made mandatory
merely because the canonical style schema contains them. For example, a transparent `TextButton`
does not require an invented background or corner radius.

`generate_lanhu_source_page.py` fails before writing output when any required fact is unresolved.
Source-generated `version_json.json` files without `migration.requiredFacts` are rejected, and
`generate_arkui_page.py` repeats the gate before rendering. The command result and ArkUI migration
manifest expose `required_fact_gate` with status counts and concrete component/path failures.
Ordinary unresolved behavior remains separate and still keeps `generation_complete=false`; passing
the required-fact gate is not a claim that the whole application behavior is complete.

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

Ordinary components use runtime logical bounds and retain the 1dp tolerance. If both page
snapshots prove a non-identity rotation or scale, all transform fields, and at least one
pre-transform layout dimension, geometry comparison switches only that component to
`source_resolved_pre_transform_layout_and_transform`. The pre-transform contract is compared with
the same dp/degree/scale tolerances, while platform-specific clipped runtime AABBs remain in
`runtime_bounds_diagnostic`. Missing provenance or a partial transform cannot activate this mode.

Both `comparison.json.verdict.status` and command stdout `verdict` are `pass` or `fail`. A strict
pass requires complete v2 snapshots, equivalent component presence and hierarchy, geometry within
1dp, no style differences, no one-sided proven paths, no unresolved facts, compatible viewports,
and color/luma/edge SSIM at or above `--min-ssim` (default `0.95`). Color comparison retains the
8-channel tolerance. Exit code zero means report generation succeeded, not that the verdict passed.
