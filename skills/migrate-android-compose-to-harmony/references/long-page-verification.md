# Long-page verification

Use `scripts/check_long_page.py` for every migrated page state whose content can
scroll. This is a local Pillow + runtime-tree check, not model image recognition,
OCR, or business acceptance. Dependencies: Python 3.10+, Pillow, ADB for Android,
HDC for Harmony. Comparison alone needs neither a device nor Kotlin PSI.

## Fixed workflow

1. Choose one page and one deterministic state. Freeze display data, theme, font
   scale, animation/loading state, and the APK/HAP. Do not compare different states.
2. From the source/page JSON, inventory **all components in the intended coverage
   scope**, including repeated instances, footer, buttons, and nested scroll areas.
   Use semantic/business components as the primary unit, not only individual text.
   Record the inventory basis in `coverage_basis`. A one-component inventory does
   not prove the rest of a page; reports explicitly say "declared components".
3. Write a profile. Map each component to both runtime trees, selecting its real
   container. For inaccessible layout nodes, obtain app-local measured bounds;
   do not guess them from a screenshot, use an ImageView as its parent, or drop it.
4. Verify device size, density, font scale, theme and content bounds. Exclude system
   bars and sticky overlays from the scroll-content ROI. These are explicit,
   device-verified inputs, not guessed status-bar heights. Capture logs retain them;
   the analyzer independently checks screenshot size and logical viewport equality.
5. Capture each declared scroll stream on both devices. Vertical content and each
   horizontal carousel are **different streams**. Configure setup taps/swipes to
   reach each stream, runtime entry assertions, its actual scroll-container selector,
   and a scroll gesture inside that container. Use overlapping movements (typically
   less than half the visible content length). No single full-height fling.
6. Compare recorded components and declared adjacent gaps. Fix the parser/generator
   when the report exposes missing content or layout defects; regenerate and capture
   again. Never patch generated page coordinates or raise tolerances to get green.
7. Keep raw screenshots/trees, command logs, config, recording manifests and reports.
   A passing script result is scoped UI evidence, not complete behavior migration.

Fixed headers and bottom bars should be verified separately with
`compare_local_screenshots.py` / page JSON checks. Do not repeatedly count them in
each scroll segment. If they change on scroll, that is another explicit visual state.

## Commands

```bash
python3 "$SCRIPTS/check_long_page.py" capture \
  --config long-page.json --platform android --output evidence/android
python3 "$SCRIPTS/check_long_page.py" capture \
  --config long-page.json --platform harmony --output evidence/harmony
python3 "$SCRIPTS/check_long_page.py" compare \
  --config long-page.json \
  --android evidence/android/recording.json \
  --harmony evidence/harmony/recording.json --output evidence/comparison
```

Every output directory must be new. Capture **installs the hash-pinned APK/HAP**,
restarts only the configured app for each stream, and executes the profile's explicit
tap/swipe actions. It never stops emulators, clears app data, builds apps, or contacts
other devices. Route setup must be safe for the test state; do not use production
accounts or destructive business actions. There is no automatic coordinate discovery.

Capture exit `0` means all declared stream ends were observed, not visual success.
Comparison exit `0` means **pass**, `1` means **fail**, `2` means invalid evidence or
execution failure. JSON stdout always identifies the outcome. Never treat successful
PNG creation or a capture exit code as visual acceptance.

## Profile format

The following is a structural example; replace paths/IDs/geometry with measured
values from the selected project and device. There is no project name in the engine.

```json
{
  "schema": "long-page-check.v1",
  "page_id": "feed",
  "state_id": "loaded",
  "coverage_basis": "source-page: loaded feed, all 12 items and footer",
  "min_ssim": 0.95,
  "geometry_tolerance_dp": 1,
  "canvas_background": "#FFFFFF",
  "components": [
    {
      "id": "footer",
      "selectors": {
        "android": {"match": {"text": "End of list"}, "parent": {"clickable": "true"}},
        "harmony": {"id": "feed-footer"}
      }
    }
  ],
  "gaps": [],
  "streams": [{"id": "main", "end_component": "footer"}],
  "capture": {}
}
```

Add all component entries; the abbreviated example does not claim full coverage.
For each pair of relevant neighbors, add
`{"id":"card-gap","before":"card-1","after":"card-2","axis":"y"}` to `gaps`.
Use `axis:"x"` for horizontal spacing. A gap without a co-visible observation on
both sides fails; the tool does not infer it from incompatible scroll positions.

Selectors compare exact runtime attributes: `id`, `type`, `text`, `description`,
`clickable`, `scrollable`, `bounds`. `match` selects a child; optional `parent`
selects its nearest ancestor satisfying the given attributes. Android resource-id,
class and content-desc are normalized to id, type and description. Selector queries
also support `contains_text`, `without_text` (exact descendant text), and `not` with
a nested query. Repeated text needs a qualified parent, not "take the first match".
Ambiguous matches fail. An optional component `stream` limits it to that capture stream.

When Android reports a full-width container touching the viewport's left/right edges,
`known_viewport_edges:["left","right"]` is allowed **only with source layout evidence**
that those are real component edges. This must not be used to waive clipped top/bottom
content. Otherwise edge-touching bounds without `origBounds` remain unverified.

Fill `capture.android` and `capture.harmony` with:

```json
{
  "tool": "/absolute/path/to/adb-or-hdc",
  "artifact": "/absolute/path/to/app.apk-or-app.hap",
  "artifact_sha256": "64-lowercase-hex-digits",
  "package": "org.example.app",
  "entry": "org.example.app/.MainActivity",
  "device": {
    "serial": "explicit-device-serial",
    "size_px": [1080, 2400],
    "density": 3,
    "font_scale": 1,
    "theme": "light",
    "content_bounds": [0, 264, 1080, 2328]
  },
  "settle_seconds": 1.5
}
```

Harmony `entry` is an ability name, such as `EntryAbility`. `content_bounds` uses
`[left, top, right, bottom]` physical pixels, not x/y/width/height. Density and font
scale are verified by the device operator/preflight and recorded explicitly; the
capture tool does not claim to auto-detect all vendor settings. For Android, retain
`wm size`, `wm density`, and `settings get system font_scale` outputs. For Harmony,
retain the device profile or an app-local Display/UIContext measurement.

For each stream, add `capture.android` / `capture.harmony` plans:

```json
{
  "entry_assertions": [{"description": "Feed"}],
  "container": {"id": "feed-list"},
  "setup": [],
  "scroll": {
    "type": "swipe", "from": [500, 1900], "to": [500, 1100],
    "duration_ms": 850, "velocity": 1200
  },
  "max_frames": 20
}
```

`setup` supports `tap` with `point:[x,y]`, and `swipe` with `from/to`.
Android uses duration_ms; Harmony uses velocity. A stream end needs the configured
end component and unchanged declared component geometry after an actual scroll.
Hitting the frame limit is incomplete. The capture driver checks that the selected
container is uniquely scrollable and that both gesture endpoints are inside it.

## Existing/probe recordings

Existing raw evidence or an app-local probe can be imported without recapturing.
Use `long-page-recording.v1`, with `platform`, `page_id`, `state_id`, `device`,
`artifact_sha256`, and `frames`. Each frame contains:

```json
{
  "id": "main-002",
  "stream": "main",
  "after_scroll": true,
  "screenshot": "main-002.png",
  "screenshot_sha256": "64-lowercase-hex-digits",
  "tree": "main-002.xml",
  "tree_sha256": "64-lowercase-hex-digits"
}
```

Paths are relative to the recording manifest, cannot escape its directory, and hashes
are rechecked. XML is UIAutomator output; JSON uses Harmony's
`{"attributes":{...},"children":[...]}` shape. Probes can add authoritative
`origBounds` in that shape. Do not fabricate it from clipped bounds.

## Comparison and gates

- Same page/state, logical viewport, font scale and theme are mandatory. Different
  pixel density is normalized by density only, never by fitting a component to its peer.
- Each component is matched by selectors and compared in its own coordinate system.
  Absolute screen y positions on different scroll frames are not comparable.
- Components taller/wider than a viewport are stitched **only** when original runtime
  bounds are stable and known. Every pixel must be covered. Overlap changes above
  RGB/luma noise tolerance are flagged instead of silently merging different states.
- Preserve unequal sizes: pad to a common canvas, report width/height delta, do not
  stretch one side to hide the error. Default size/gap tolerance is 1dp.
- Reuse local tiled SSIM routines: color, luma, and blurred edge channels. All three
  must reach the configured threshold (default .95). No average across components can
  override a failing component, missing item, uncovered stream, or gap.
- `report.json` includes each status, diagnostic, runtime geometry, frame references,
  input/config/package hashes, coverage, and final verdict. `index.html` is the human
  report with paired component images. Raw screenshots remain in recording folders.

PASS means all declared components, streams, and gaps passed. It does not automatically
cover undeclared controls, every state, runtime behavior, or inaccessible geometry.
Keep unresolved components in the inventory so their missing/partial status fails the
gate. Do not replace them with explanatory exemptions.

## Regression

```bash
cd "$SCRIPTS"
python3 -m unittest test_long_page -v
```

Fixtures cover missing/ambiguous controls, hash drift, wrong page state, logical size,
font scale, cross-density equivalence, oversized stitching and holes, unstable overlap,
pixel mismatch, geometry mismatch, missing streams/gaps and unproven end-of-scroll.
After changes to the collector, also replay one real project with a vertical list and
a horizontal nested region. A correct rejection of a known bad migration is required
evidence, not a reason to weaken the checker.
