---
name: figma-mcp-high-fidelity
description: Implements Figma designs with high visual fidelity using Figma MCP while debugging mismatches between design context and screenshots. Use when working from Figma node links, when get_design_context is truncated or inconsistent with screenshots, or when outputs contain unresolved component IDs, variable IDs, colors, spacing, masks, or Code Connect snippets.
---

# Figma MCP High Fidelity

## Principle

Treat the Figma screenshot as the visual source of truth. Treat `get_design_context` as an implementation aid, not as final render truth.

The goal is not to fetch the largest possible context. The goal is to build a small, verifiable render tree for the exact visible node.

## Required Inputs

- A node-specific Figma URL, not a file/page URL.
- The target platform or framework.
- Whether exact visual fidelity or design-system reuse has priority when they conflict.

If the user provides only a file/page URL, ask for a node-specific URL before implementing.

## Standard Workflow

1. Parse the Figma URL into `fileKey` and `nodeId`.
2. Call `get_screenshot(fileKey, nodeId)` and save it as the source-of-truth reference.
3. Call `get_metadata(fileKey, nodeId)` to inspect the top-level node map before pulling large context.
4. Split the target into visible sections by node IDs: header, hero, cards, lists, nav, dialogs, etc.
5. Call `get_design_context` on the exact target node or on each section node.
6. Download real image/SVG assets. Do not use placeholders when assets exist.
7. Implement in the project framework using local conventions.
8. Render locally or on device, take a screenshot, and compare against the Figma screenshot.
9. Fix spacing, typography, color, clipping, image crop, and scroll exposure until the screenshots match.

## Adaptive Drilldown

Do not recursively fetch every child. Drill down only when a node is not renderable from the current response.

Continue drilling down when:

- The response is truncated.
- A section contains only `componentId`, `variableId`, style IDs, or Code Connect snippets.
- Text, colors, spacing, images, radius, or layout are missing.
- The screenshot shows content that the context omits.
- The context describes content that the screenshot does not show.
- The node is an `INSTANCE`, `COMPONENT`, variant, masked group, clipped frame, or variable-bound layer.

Stop drilling down when the section has enough computed render data:

- Position and size.
- Visible text.
- Font family, size, weight, line height.
- Fill/stroke/effect values.
- Radius and clipping.
- Auto-layout direction, padding, gaps, alignment.
- Real asset references.

## Reliability Rules

- When `get_design_context` and screenshot disagree, prefer the screenshot and record the discrepancy.
- Never infer missing visual values from `componentId`, `variableId`, or style ID alone.
- If supported, compare `get_design_context` with `disableCodeConnect=false` and `disableCodeConnect=true`.
- If the MCP provides only IDs, request a raw or computed node tree before implementing.
- Use visible `fills` and resolved variables/styles for colors; do not rely on deprecated or fallback background fields.
- Figma REST color channels are `0..1` floats; convert by multiplying by 255.
- Keep assets real: image fills, masks, crops, icons, and avatars should come from Figma export/API when possible.
- Prefer existing project components only when they can match the screenshot.
- Do not add speculative interactions or content not visible in the design.

See [REFERENCE.md](REFERENCE.md) for Code Connect checks, raw/computed tree requirements, common mismatch causes, and color parsing details.

## Agent Prompt Template

```text
Use Figma MCP for high-fidelity implementation.
First fetch get_screenshot for the exact node and treat it as visual truth.
Then fetch metadata and split the frame into visible sections.
Do not fetch the whole tree recursively unless a section is unresolved.
If get_design_context returns component IDs, variable IDs, Code Connect snippets, hidden/off-canvas nodes, or conflicts with the screenshot, drill down or request raw/computed node data.
Prefer screenshot-visible output over context prose.
Before finishing, render the implementation and compare a screenshot against the Figma screenshot.
```

## Done Criteria

- Figma screenshot saved and used as reference.
- All visible sections accounted for.
- No unresolved `componentId`, `variableId`, style ID, or placeholder asset remains in implemented visuals.
- Local/device screenshot captured.
- Visual differences are fixed or explicitly documented.
