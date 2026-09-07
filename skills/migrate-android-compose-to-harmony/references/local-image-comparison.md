# Local image comparison

Use the comparator only after page-fact-driven visual implementation and source-driven behavior
implementation have produced the intended route and state.
It is a local diagnostic loop with a strict automated verdict, not the source of UI semantics or
the final product-acceptance decision.

## Prepare comparable captures

Capture the same route, state, locale, theme, font scale, dynamic data, and scroll position on both
platforms. With v2 page snapshots, the comparator automatically uses each side's
`viewport.content_bounds_px`, so status/navigation bars and cutouts may have different heights.
Explicit crop arguments override that metadata. Choose one explicit target size when the cropped
screenshots do not already match. Scaling makes pixel comparison possible but cannot repair a
mismatched aspect ratio; inspect `normalization.aspect_ratio_delta` before using the metrics.

## Run

Install the only non-standard-library dependency into the Python environment that will run the
Skill:

```bash
python3 -m pip install 'Pillow>=9.1'
```

```bash
python3 "$SKILL_ROOT/scripts/compare_local_screenshots.py" \
  --left android.png \
  --right harmony.png \
  --left-label android-home \
  --right-label harmony-home \
  --left-components android-components.json \
  --right-components harmony-components.json \
  --source-attributes home-source-attributes.json \
  --target-size 1080x2208 \
  --min-ssim 0.95 \
  --output-dir comparison-home
```

The output directory must not exist. The command produces:

- `comparison.json`: hashes, dimensions, crops, normalization, metrics, tools, and limitations;
- `normalized-left.png` and `normalized-right.png`: the exact normalized comparison inputs;
- `difference.png`: amplified pixel difference;
- `annotated-difference.png`: connected regions (`R`) and ranked 8–64 px hotspots (`H`);
- `side-by-side.png`: local review aid.

Keep the JSON stdout if the report needs an external integrity binding: it contains the SHA-256 of
`comparison.json`. The report in turn contains the SHA-256 of the comparator script, every image
artifact, and both input files. A changed implementation, report, or artifact will no longer match
its retained hash.

## Interpret

- `ssim_color` responds to overall color and rendered-pixel differences.
- `ssim_luma` reduces color influence and emphasizes luminance/layout differences.
- `ssim_edges` emphasizes component geometry, outlines, and text strokes.
- `ssim_score` is the minimum of those three values. This single strict score passes a threshold
  exactly when all three SSIM metrics pass it.

The comparator calculates tiled SSIM directly with Pillow. Its values form a stable baseline for
this comparator revision, but are not numerically interchangeable with ffmpeg, scikit-image, or a
different window/tile implementation.

`difference_analysis.regions` groups connected changed tiles. Because widespread viewport or
state mismatch can connect much of a page into one region, use `difference_analysis.hotspots` for
the most severe individual tiles. Every item contains normalized coordinates plus coordinates
mapped back into both original screenshot crops. Red `R` boxes and yellow `H` boxes use the same
IDs in `annotated-difference.png`. The coordinates identify where to inspect; they do not identify
an ArkUI property or source line by themselves. Correlate them with UITest component bounds and the
Compose/ArkUI semantic inventory before changing code.

## Associate hotspots with components

The optional component files use a strict, platform-neutral schema:

```json
{
  "schema": "android-to-harmony.component-bounds.v2",
  "screenshot_dimensions": {"width": 1080, "height": 2400},
  "content_insets_px": {"left": 0, "top": 72, "right": 0, "bottom": 96},
  "components": [
    {
      "id": "android-summary-card",
      "type": "Card",
      "semantic_key": "summary-card",
      "bounds": {"x": 48, "y": 420, "width": 984, "height": 360}
    }
  ]
}
```

Bounds are in the original screenshot coordinate space, before comparator cropping/scaling. The
declared screenshot dimensions must exactly match the decoded screenshot, preventing a stale UI
tree from being silently associated with a new capture. `id`, `type`, and optional `semantic_key`
accept only strict identifier characters. Unknown fields—including `text`, accessibility labels,
or content descriptions—are rejected rather than copied into the report.

Each hotspot gains up to five `left_component_candidates` and
`right_component_candidates`, ranked by geometric overlap. When candidates on both sides have the
same sanitized `semantic_key`, the hotspot also gains `semantic_pair_candidates`. This means “the
changed pixels overlap these component bounds”; it does not prove the component implementation is
wrong or name the property to edit. Use the candidate IDs to inspect the corresponding
Compose/ArkUI hierarchy, modifiers, resource tokens, and state branch.

All three metrics remain candidate diagnostics, but complete v2 page snapshots now produce a
strict `verdict.status`. The default minimum for each metric is `0.95`; override it explicitly with
`--min-ssim`. Missing/ambiguous components, hierarchy changes, geometry or style over tolerance,
one-sided or unresolved style facts, and incompatible logical viewport/orientation/font scale also
fail the verdict. Raw screenshots or older inventories always fail the complete-v2 check. Platform
font rasterization, antialiasing, native controls, dynamic content, and animation can lower a score,
so an authorized human still owns final visual acceptance.

For a faster starting point, read
`difference_analysis.component_impact_summary`. It aggregates the hotspot candidates by runtime
component and ranks them by their strongest geometric match. When the inventory supplied a
`semantic_key`, each summary item exposes it as `source_component`, for example
`AutoTrackingCard`, together with `hotspot_ids`, `hotspot_count`, `max_match_score`, and
`max_hotspot_severity`. This is the direct candidate answer to “which source component should I
inspect first”; it still does not identify the incorrect property or authorize a fix.

For complete v2 snapshots with `source_component_tree`, prefer
`difference_analysis.business_component_ssim_rankings`. It takes reusable project and third-party
component instances from `business_component_ids`, excluding Compose layout primitives such as
`Row`, `Column`, and `Box`. Each row records the component semantic key, type, source file and line,
runtime mapping method, normalized bounds, local `ssim_score`, changed-pixel ratio, and an
area-weighted `impact_score`. Read `geometry_delta_dp` for `x/y/width/height` placement differences,
`screen_position_ssim_score` for the component at its actual screen position, and
`aligned_appearance_ssim_score` for an independent-bbox comparison that removes placement before
checking internal appearance. The aligned score does not replace geometry; check
`component_aspect_ratio_delta` separately. `control_diagnostics` then lists the owned semantic
controls and their geometry/style failures beneath the business component. Layout wrappers and
content slots are excluded.

`bounds_comparability` distinguishes direct measured bounds, candidate anchor-derived bounds,
incompatible runtime scopes, and one-sided projections. If one platform does not expose a custom
component boundary, the other platform's component region is used only as a diagnostic projection;
geometry and aligned appearance remain unavailable instead of reporting false precision.
`comparison_region_basis` states that limitation. Component SSIM is a ranking signal, not additive
attribution to the global SSIM score.

Before leaving such a component unresolved, the comparator uses deterministic local Pillow
processing to enumerate large quantized connected-color surfaces. It first joins a visible surface
to the platform that has a runtime component boundary, then searches the other screenshot for a
surface with compatible size, aspect ratio, and position. A successful pair is reported as
`pillow_visual_surface_pair`, with each boundary method and `pillow_boundary_confidence`. This
recovers visible cards, buttons, and header backgrounds without image-model inference. It does not
recover transparent padding, click targets, or same-color containers; those remain unresolved and
still require a runtime layout probe.

The same output directory contains `comparison-summary.md` for human review. It states the overall
verdict, global SSIM, an area-weighted aligned-appearance summary over non-overlapping leaf business
components, counts of position/appearance/control failures, a business-component ranking table, and
the failed semantic controls nested below each component. The JSON remains the machine-readable
source of truth; the Markdown is deterministically rendered from that report and its SHA-256 is
returned by the command.

## Map a component to sanitized source attributes

Generate an attribute inventory for the exact Compose closure before comparison:

```bash
python3 "$SKILL_ROOT/scripts/generate_source_attribute_inventory.py" \
  --contract "$CONTRACT" \
  --root-source "app/src/main/java/example/HomeScreen.kt" \
  --root-composable "HomeScreen" \
  --output home-source-attributes.json
```

The inventory retains source-relative file, composable, call line, primitive component, attribute
name, Modifier index, dp/sp dimensions, resource keys, broad attribute groups, unambiguous source
parent/preorder, and allowlisted compile-time numeric layout/transform facts. It deliberately
excludes arbitrary expressions and display text. Each semantic `call_id` becomes one
deterministic `semantic_key` containing its owning composable, component type, source line, and call
ordinal. This call-level identity lets one runtime component map to exactly one source call when
page JSON drives ArkUI generation. Use those exact keys in both platforms' component-bound
descriptors; do not shorten them back to a composable-wide key.

When `--source-attributes` is supplied, every matching item in
`difference_analysis.component_impact_summary` gains `source_attribute_candidates`. Each candidate
contains the source file/composable, concrete call lines and attributes, plus
`candidate_attribute_groups` ordered by color/luma/edge metric loss. For example, an edge-heavy
comparison may rank geometry or typography above color. This is a deterministic inspection order,
not proof that the first property is wrong and never a generated patch. If a target-only semantic
key such as `LoginPanel` has no exact Compose mapping, its candidate list remains empty instead of
being guessed.

The comparator validates and hashes the inventory, rejects unknown fields such as raw source
values, and never records its host path. Retain its SHA with the comparison report so a later source
change cannot be mistaken for the analyzed revision.

Source hierarchy takes precedence over bounds containment when it is unambiguous and skips
uncaptured Compose wrappers while walking to the nearest captured ancestor. For proven rotated or
scaled components, the comparator compares the pre-transform layout/transform contract and keeps
the platform runtime AABBs as diagnostics. It does not grant that exception to partial or
unproven transform data.

## Export Android Compose component bounds

Copy `assets/android-compose-uitest-component-bounds/ComponentBounds.kt` into the Android build
copy's `src/androidTest`. Keep the original Android repository unchanged. Add stable
`Modifier.testTag(...)` values at source component boundaries, and expose those tags to Android's
accessibility tree from the screen root:

```kotlin
Modifier
    .testTag("main_screen")
    .semantics { testTagsAsResourceId = true }
```

Use an instrumentation test with `ActivityScenario` to put the app in one deterministic state,
then call the helper with sanitized source component names:

```kotlin
ActivityScenario.launch(MainActivity::class.java).use {
    waitForStableBusinessState()
    captureComponentBoundsAndScreenshot(
        screenshotFile,
        listOf(
            ComponentBoundsDescriptor("main_screen", "Box", "MainScreen"),
            ComponentBoundsDescriptor("summary_card", "Card", "SummaryCard"),
        ),
    )
}
```

The helper reads only `viewIdResourceName`, screen bounds, and the resumed Activity's runtime
`WindowInsets`; it never reads node text or content descriptions. It combines system bars and
display cutout Insets, captures the device screenshot, and emits exactly one
`ANDROID_COMPONENT_BOUNDS:` instrumentation status record. It skips a missing or ambiguous tag
instead of pairing the wrong component. The screenshot directory must already exist and the file
must not.

Prefer `ActivityScenario` plus `UiAutomation` over `createAndroidComposeRule` for capture-only
tests when permanent Compose animations keep Espresso's idle synchronization active forever.
Waiting for business readiness remains the caller's responsibility: use a deterministic state
fixture or an explicit bounded condition, not a claim that a continuously animated page is idle.

When the project's Compose version does not provide `testTagsAsResourceId`, copy
`ComposeSemanticsComponentBounds.kt` from the same asset directory instead. This compatibility
path reads only explicitly named test tags and `boundsInRoot` from the Compose test semantics tree;
it does not read node text or descriptions. Convert those root-relative bounds to screen space with
the actual `AndroidComposeView` location and freeze the test clock before a bounded readiness loop:

```kotlin
composeRule.mainClock.autoAdvance = false
repeat(300) {
    if (composeRule.onAllNodesWithTag("main_screen", useUnmergedTree = true)
            .fetchSemanticsNodes().size == 1) return@repeat
    composeRule.mainClock.advanceTimeBy(16L)
    Thread.sleep(10L)
}

captureComposeSemanticsComponentBoundsAndScreenshot(
    screenshotFile = screenshotFile,
    composeRootX = composeLocation[0],
    composeRootY = composeLocation[1],
    descriptors = descriptors,
    boundsForTag = { tag ->
        composeRule.onNodeWithTag(tag, useUnmergedTree = true)
            .fetchSemanticsNode().boundsInRoot
    },
)
```

Fail unless the readiness tag is unique before capture. The build copy must remain independent of
the original repository. Prefer the accessibility exporter whenever the Compose API supports it;
the semantics fallback requires Compose UI Test dependencies and deliberate clock control.

Require the instrumentation case to pass, retain its complete stdout, and extract the unique
sanitized marker without copying JSON by hand:

```bash
adb -s "$ANDROID_DEVICE_ID" shell am instrument -w -r \
  -e class 'example.VisualCaptureTest#capturesStableScreen' \
  example.test/example.TestRunner |
  tee android-capture.log |
  python3 "$SKILL_ROOT/scripts/extract_android_component_bounds.py" \
    --output android-components.json
```

Pull the screenshot from the test's app-specific external files directory immediately after the
test. Verify that its decoded dimensions equal `screenshot_dimensions` before comparison. Test
tags and semantic keys must be non-sensitive identifiers; never derive them from display content.

## Export HarmonyOS component bounds

Copy `assets/ohos-uitest-component-bounds/ComponentBounds.ets` into the target's `src/ohosTest`
framework directory. Give each important ArkUI boundary a stable `.id(...)`, then pass only those
explicit IDs plus sanitized source component names to `collectComponentBounds`:

```ts
const inventory = await collectComponentBounds(
  driver,
  [
    { id: 'home_auto_tracking', semanticKey: 'AutoTrackingCard' },
    { id: 'home_balance_summary', semanticKey: 'BalanceDetailsRow' },
    { id: 'home_breakdown', semanticKey: 'CategoryInsightCard' }
  ],
  mainWindow
);
const captured = await driver.screenCap(
  '/data/storage/el2/base/files/component-bounds.png'
);
if (!captured) {
  throw new Error('component-bounds screenshot was not captured');
}
console.info(`OHOS_COMPONENT_BOUNDS:${JSON.stringify(inventory)}`);
```

Obtain `mainWindow` from the test-enabled UIAbility/WindowStage rather than constructing dimensions
on the host. The exporter queries runtime ID, component type, display size, bounds, and
`Window.getWindowAvoidArea()` for system, navigation-indicator, and cutout regions. Missing,
destroyed, invisible, or wholly off-screen components are skipped; partially visible bounds are
clipped to the screenshot dimensions. The descriptor's `semanticKey` is the ArkTS source component
name used in the report. Do not derive it from display content.

Clear Hilog immediately before the one export test, run the test, and require its ordinary Hypium
result to pass. Then turn the unique log marker into comparator input without copying the JSON by
hand:

```bash
"$HDC" -t "$DEVICE_ID" shell hilog -x |
  python3 "$SKILL_ROOT/scripts/extract_ohos_component_bounds.py" \
    --output harmony-components.json
```

The extractor accepts exactly one marker, validates the same strict v2 schema as the comparator,
rejects display-content fields, refuses to overwrite output, and prints the resulting SHA-256.
Multiple markers fail so stale bounds cannot silently pair with a new screenshot; clear Hilog and
rerun the one test instead of selecting a record by position.

Capture the screenshot in the same test after collecting bounds, as in the example, and retrieve
the sandbox PNG before uninstalling the bundle. The host-visible sandbox path depends on the
selected device and bundle; discover it through that device's supported debug tooling rather than
hard-coding another project's host path. Do not assume the app remains visible after `aa test`
returns: a runner may close the tested ability and expose the launcher. If an in-test capture
cannot be retrieved and a device-level capture must follow the test, first prove the app is still
foreground, record that the pair is consecutive rather than atomic, and reject it if the screen
can animate or navigate between operations. The inventory's `screenshot_dimensions` must exactly
match the decoded screenshot.

## Private-image boundary

For private projects, do not open the source or generated PNGs through model-visible viewers,
base64/data URLs, OCR, or upload tools. Run the command locally and expose only the JSON/stdout text
allowed by the project's policy. The comparator itself performs no network request and invokes only
Pillow in the current Python process; it starts no external image executable. The report records
the Pillow version and the comparator hash.
