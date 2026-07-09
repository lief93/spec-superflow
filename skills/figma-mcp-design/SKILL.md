---
name: figma-mcp-design
description: Implement or repair UI from Figma MCP with high visual fidelity when design context is noisy, too broad, truncated, or inconsistent. Use for Figma URLs, node IDs, raw Figma node trees, MCP metadata, screenshots, design-to-code work, and workflows that need deterministic summaries and screenshot box comparisons instead of trusting generated design context alone.
---

# Figma MCP Design

## Purpose

Use this skill to turn Figma MCP output into production UI without letting broad or noisy `design context` drive the implementation. The source of truth is the exact Figma node, a deterministic layer summary, and measured screenshot comparison.

## Quick Start

1. Target the exact node.
   - Prefer a node-specific Figma URL with `node-id`.
   - If context includes invisible variants, siblings, or component internals, use metadata to descend to the smallest node that still contains the visible UI you need.
   - For a full screen, target the screen frame. For one component, target that component instance or variant, not the whole page.
2. Fetch artifacts separately.
   - Use metadata/raw tree for structure and child node IDs.
   - Use screenshot for visual truth.
   - Use design context only as helper material for assets or implementation hints.
3. Summarize raw node data.
   - Save a raw Figma node/tree JSON response to `/tmp/figma-node.json` or a project scratch file.
   - Run:

```bash
python3 scripts/summarize_figma_tree.py \
  /tmp/figma-node.json --hide-vector-children --min-size 1
```

4. Implement from facts.
   - Use visible frames, text, fills, typography, radii, and spacing from the summary.
   - Treat vector children, masks, hidden nodes, and 0-size nodes as noise unless they are the target asset.
   - Reuse the repo's components and tokens where they can match the measured design.
5. Validate by measured screenshots.
   - Capture the implemented UI.
   - Compare selected boxes from the Figma screenshot and app screenshot:

```bash
python3 scripts/compare_figma_screenshot.py \
  /tmp/figma-reference.png \
  /tmp/app-current.png \
  --design-width 390 \
  --box cta=24,682,342,48 \
  --box title=24,96,260,36 \
  --left-zone 180
```

## Handling Noisy Design Context

Use this decision table before editing code:

| Symptom | Action |
|---|---|
| Context includes hidden variants or invisible layers | Ignore context; use metadata/raw tree and skip `visible=false` nodes. |
| Context includes siblings outside the target UI | Descend to the child frame/component and fetch that node only. |
| Context omits icons, masks, or small controls | Use screenshot plus raw tree; fetch the missing child node separately. |
| Context returns generated React/Tailwind | Treat it as a hint, not source of truth. Extract assets if useful, then implement in project conventions. |
| Coordinates are huge absolute canvas values | Normalize relative to the target node root. The summary script does this. |
| Vector internals flood the output | Use `--hide-vector-children`; implement icons as assets or existing icon components. |

## Raw Summary Rules

The summary script keeps the information needed for implementation and drops most noise:

- Relative `x/y/w/h` frame from `absoluteBoundingBox`, `absoluteRenderBounds`, `frame`, or direct node dimensions.
- Text from `characters`, `text`, `content`, or `value`.
- Typography from `style` and node-level font fields.
- Visible solid fills/strokes as hex values.
- Radius, layout mode, spacing, and padding when present.
- Optional filters: `--within`, `--types`, `--max-depth`, `--min-size`, `--include-hidden`.

Useful commands:

```bash
# Whole node, hide vector internals
python3 scripts/summarize_figma_tree.py /tmp/node.json \
  --hide-vector-children

# Only a component area, using Figma coordinates relative to the target node
python3 scripts/summarize_figma_tree.py /tmp/node.json \
  --within 24,120,342,180 --max-depth 5

# Text and frames only
python3 scripts/summarize_figma_tree.py /tmp/node.json \
  --types FRAME,INSTANCE,COMPONENT,TEXT,RECTANGLE
```

## Screenshot Comparison Rules

Do not ask the model to compare whole screenshots by eye. Compare meaningful boxes:

- Container/card boxes for layout and background size.
- Text boxes for typography and alignment.
- Button boxes for label centering and fill dimensions.
- Icon boxes for asset placement.
- Repeated rows/cards for spacing consistency.

Read the output this way:

| Measurement | Meaning |
|---|---|
| `dark left/top/right/bottom` | Actual dark pixels in the box, usually text or icons. |
| `color x/y/w/h` | Actual area matching the requested fill color. |
| `delta` | Difference between reference and implementation for the measured pixels. |

Fix based on measurement:

- Whole measured area shifted: adjust layout/constraints.
- Color area wrong but text right: fix background, radius, or asset crop.
- Text dark bbox wrong inside correct box: fix font, line height, padding, or alignment.
- Icon dark bbox wrong: fix icon frame or asset opaque bbox before moving the parent.
- Extra dark pixels: remove stale placeholder text, hidden overlays, debug text, or wrong state.

## Guardrails

- Never implement from `get_design_context` alone when it includes invisible or unrelated elements.
- Never claim visual parity without a screenshot and at least a few measured boxes.
- Never solve noisy context by broadening the node. Descend to the smallest useful node first.
- Do not create placeholders when Figma provides assets.
- Do not move text to compensate for transparent/shadow padding inside an image asset; inspect the asset bbox first.
- Preserve product behavior from the codebase even if Figma only shows a static state. Document intentional deviations briefly.

## Tooling

- `scripts/summarize_figma_tree.py`: Convert raw Figma node/tree JSON into a concise visible layer table.
- `scripts/compare_figma_screenshot.py`: Compare a Figma screenshot and an implementation screenshot by design-coordinate boxes.
