---
name: figma-compose-implementation
description: Converts Figma MCP design context into high-fidelity Jetpack Compose through an explicit visual render spec before writing code. Use when implementing Android or Jetpack Compose UI from Figma, especially when direct get_design_context-to-code generation produces poor visual fidelity.
---

# Figma Compose Implementation

## Principle

Never jump directly from `get_design_context` to Compose code. First convert Figma context and screenshot evidence into a visual render spec, then map that spec to Compose.

## Required Workflow

1. Fetch `get_screenshot` for the exact Figma node and save it as the reference.
2. Fetch `get_design_context` and `get_metadata` for the same node.
3. Build a visual render spec from screenshot-visible sections, not from the raw Figma layer tree.
4. Mark unresolved values instead of guessing: missing color, font, spacing, asset, crop, mask, or component internals.
5. Resolve unresolved values by drilling into child nodes, raw node data, variables/styles, exported assets, or screenshot measurement.
6. Only after the render spec is complete, generate Compose.
7. Run the app on emulator/device or Compose preview, capture a screenshot, and compare with the Figma screenshot.

## Visual Render Spec

Before writing Compose, produce a compact JSON-like spec:

```json
{
  "canvas": { "width": 375, "height": 812 },
  "sections": [
    {
      "name": "Header",
      "bounds": { "x": 0, "y": 44, "w": 375, "h": 80 },
      "elements": [
        {
          "type": "text",
          "x": 76,
          "y": 59,
          "text": "andy",
          "fontSize": 24,
          "fontWeight": 500,
          "color": "#111111"
        }
      ]
    }
  ],
  "unresolved": []
}
```

The spec must include visible bounds, text, fonts, fills, radius, shadows, assets, crop rules, masks/clipping, scroll exposure, and z-order.

## Compose Mapping

Use this mapping unless the project already has an exact matching primitive:

- Figma frame/group/rectangle -> `Box`
- Text -> `Text`
- Solid fill -> `Modifier.background(Color(...))`
- Gradient fill -> `Brush.linearGradient` or matching Brush
- Corner radius -> `Modifier.clip(RoundedCornerShape(...))`
- Circle image/avatar -> `Image` + `Modifier.clip(CircleShape)` + `ContentScale.Crop`
- Mask or clipped frame -> parent `Box` + `clipToBounds()` or `clip(...)`
- Shadow -> `Modifier.shadow(...)` before `clip(...)`
- Repeated item -> small private `@Composable`, not a premature generic component

## First Pass Layout

For high-fidelity mobile screens, start with a fixed Figma canvas:

```kotlin
Box(
    modifier = Modifier
        .width(375.dp)
        .height(812.dp)
        .clipToBounds()
        .background(Color.White)
)
```

Place elements with `Modifier.offset(x.dp, y.dp)` and explicit `size/width/height` until the screenshot matches. Add responsive layout only after the first visual pass is correct.

## Compose Rules

- Organize code by visible sections, not by Figma layer names.
- Preserve modifier order: shadow before clip, clip before background when matching card shapes.
- Use real exported assets for image fills, avatars, logos, and non-trivial icons.
- Do not render `componentId`, `variableId`, or style IDs as visual values.
- Keep the first implementation deterministic and visually anchored; avoid speculative state, navigation, and business logic.
- After visual parity, extract repeated rows/cards into small private composables.

See [REFERENCE.md](REFERENCE.md) for the full conversion checklist and example prompt.

## Done Criteria

- Figma screenshot saved.
- Visual render spec produced before Compose code.
- `unresolved` is empty or every unresolved item is explicitly documented.
- Compose screenshot captured from preview, emulator, or device.
- Major differences in spacing, typography, color, image crop, clipping, and z-order are fixed.
