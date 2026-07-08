# Figma Compose Implementation Reference

## Conversion Checklist

Use this checklist between `get_design_context` and Compose code.

1. Canvas
   - Record frame width and height.
   - Decide whether to keep a fixed Figma canvas for first pass.
   - Record root background and clipping.

2. Sections
   - Split by visible UI areas, not by raw layer grouping.
   - Give each section a bounding box.
   - Preserve z-order where sections overlap.

3. Text
   - Record text content exactly, including typos shown in the design.
   - Record x, y, width, font size, line height, weight, color, alignment, and max lines.
   - If Figma font is unavailable, choose the closest project font and verify screenshot.

4. Shape and layout
   - Record x, y, width, height, radius, background, stroke, opacity, and shadow.
   - Record parent clipping and masks.
   - For horizontal overflow, place the child outside the canvas and rely on parent clipping.

5. Assets
   - Export real images/SVGs for avatars, logos, photos, and custom icons.
   - Record crop mode: crop, fit, fill, or tile.
   - In Compose, use `ContentScale.Crop` for circular avatars and image fills that cover bounds.

6. Repetition
   - Convert repeated visible items into a small private composable only after coordinates are stable.
   - Keep parameters visual: title, subtitle, icon, amount, color, asset.

## Bad Flow

```text
get_design_context
  -> generate Compose from layer tree
  -> hope it looks right
```

This tends to fail because Figma component trees, Code Connect snippets, unresolved variables, masks, and hidden/off-canvas nodes are not the same thing as the rendered UI.

## Good Flow

```text
get_screenshot + get_design_context + get_metadata
  -> visual render spec
  -> Compose mapping
  -> device/preview screenshot
  -> screenshot diff and correction
```

## Prompt Template

```text
Implement this Figma node in Jetpack Compose.

Do not generate Compose immediately.
First produce a visual render spec with canvas, visible sections, elements, coordinates, typography, colors, assets, masks, clipping, shadows, and unresolved values.

Use get_screenshot as visual truth.
Use get_design_context only as supporting data.
If componentId, variableId, styleId, or Code Connect snippets appear, do not guess. Drill down or list unresolved.

After the visual render spec is complete, generate Compose.
For the first pass, use a fixed frame-sized Box and absolute offsets.
Then verify with a Compose preview, emulator, or real-device screenshot.
```

## Compose Modifier Order

Cards commonly need:

```kotlin
Modifier
    .offset(x.dp, y.dp)
    .size(width = w.dp, height = h.dp)
    .shadow(elevation.dp, RoundedCornerShape(radius.dp))
    .clip(RoundedCornerShape(radius.dp))
    .background(backgroundColor)
```

Circular images commonly need:

```kotlin
Image(
    painter = painterResource(...),
    contentDescription = null,
    contentScale = ContentScale.Crop,
    modifier = Modifier
        .offset(x.dp, y.dp)
        .size(size.dp)
        .clip(CircleShape)
)
```

## When To Stop Using Absolute Positioning

Keep absolute positioning while chasing visual parity. Refactor to `Row`, `Column`, `LazyColumn`, or responsive layout only after:

- Element positions match the screenshot.
- Text sizes and weights are close.
- Asset crops are correct.
- Scroll or overflow exposure matches.
- There is a clear repeated structure worth extracting.
