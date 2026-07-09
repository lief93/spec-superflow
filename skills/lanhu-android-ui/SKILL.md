---
name: lanhu-android-ui
description: Rebuild Android screens from Lanhu/Figma exports as real native views with high visual fidelity. Use when implementing or repairing Android UI from Lanhu links, .hermes/lanhu_pages artifacts, version_json.json, or when avoiding full-page mockup images and transparent hit zones.
---

# Lanhu Android UI

## Quick Start

1. Find the page artifact:
   - Prefer `.hermes/lanhu_pages/manifest.json` for page slug, image id, and canonical directory.
   - Use `version_json.json` for coordinates, text, colors, radii, and exported slice metadata.
   - Use `artboard.png` only as visual reference or screenshot comparison; never put full-page artboards in `res/`.
2. Convert Lanhu coordinates:
   - Read `meta.sliceScale`; Android dp = JSON px / `sliceScale`.
   - For `Android xhdpi`, most pages are 720 px wide, so 360 dp wide.
3. Build native UI:
   - Use XML/Kotlin views, real text, real icons, real click targets.
   - Put reusable small assets in `res/drawable*`; keep full artboards in `ui/` or `.hermes/`.
   - Do not use full-page background mockups, overlay masks, transparent click layers, or coordinate-only hit testing.
4. Verify on device:
   - Compile resources and Kotlin.
   - Install the exact APK package shown by `aapt dump badging`.
   - Launch the correct package, take a screenshot, and compare against Lanhu with pixel measurements, not only by eye.

## Workflow

1. Establish the target page and code owner.
   - Map Lanhu slug to the Android layout/activity/fragment.
   - Check existing click bindings before editing layout.
   - State any intentional product deviation, such as hidden entrances.
2. Extract design facts.
   - Run `scripts/summarize_lanhu_json.py <version_json.json>`.
   - Record key frames, text sizes, colors, radii, and export assets.
   - Prefer actual JSON data over `ui_summary.md` when they differ.
3. Edit surgically.
   - Keep existing IDs used by ViewBinding/tests.
   - Add page-specific drawables instead of changing shared drawables unless the shared style is intentionally updated.
   - Replace old overlays with visible controls bound directly to click listeners.
4. Prove behavior.
   - Run `./gradlew compileDebugKotlin compileDebugAndroidTestKotlin`.
   - Run focused instrumentation tests for visible entries, click routes, and no-overlap checks.
   - Confirm the package installed on device matches the local APK package.
5. Capture the result.
   - Save a screenshot under `/tmp` for review.
   - Run `scripts/compare_lanhu_screenshot.py` on key boxes from `version_json.json` before judging spacing.
   - If launcher behavior differs from direct activity tests, diagnose package/entry mismatch before judging UI.

## Screenshot Comparison

Use Pillow-based screenshot comparison whenever spacing, size, crop, background, or typography is questioned.

1. Capture the current device screen:

```bash
adb -s <device> exec-out screencap -p > /tmp/current.png
```

2. Compare Lanhu `artboard.png` and the screenshot using dp boxes copied from `version_json.json`:

```bash
python3 scripts/compare_lanhu_screenshot.py \
  .hermes/lanhu_id_photo_pages/idphoto-16-home/artboard.png \
  /tmp/current.png \
  --box card1=16,333,159,80 \
  --left-zone 95
```

3. Read the output as design facts:
   - `box` is the intended component frame in dp.
   - `dark left/top` gives rendered text position relative to the component.
   - `color` gives measured background spans when `--color RRGGBB` is provided.
   - Differences under 1dp are usually rendering noise; larger differences need code or asset changes.

4. For image-backed views, check the asset before moving text:

```bash
python3 - <<'PY'
from PIL import Image
from pathlib import Path
for p in Path('app/src/main/res').rglob('*.png'):
    if 'target_name' not in p.name:
        continue
    im = Image.open(p).convert('RGBA')
    mask = im.getchannel('A').point(lambda v: 255 if v >= 200 else 0)
    print(p, im.size, mask.getbbox())
PY
```

If the opaque bbox has large transparent or shadow insets, crop or replace the asset so the visible component matches the native view frame. Do this before compensating with text margins.

## Guardrails

- Never claim a UI-only change did not affect routing until `git diff` confirms no Kotlin/manifest route changes.
- Never judge a device screenshot without confirming `adb shell pm path <package>` and local `aapt dump badging`.
- Never fix apparent padding by moving text until screenshot comparison confirms whether the text position or the asset/background bbox is wrong.
- Do not stretch full component PNGs with transparent/shadow padding into native frames. Crop the asset or rebuild the component as native background plus separate icons.
- Avoid broad refactors while matching a page.
- Preserve user-requested product changes even if Lanhu shows the removed element.
- For dialogs and sheets, outside-tap dismissal must stop active business work first.

## Tooling

Use the bundled helper:

```bash
python3 scripts/summarize_lanhu_json.py \
  .hermes/lanhu_pages/home/version_json.json
```

The output is a dp-based layer table for implementation notes and XML coordinates.
