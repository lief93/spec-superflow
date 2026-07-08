# Figma MCP High Fidelity Reference

## Common Causes Of Context / Screenshot Mismatch

- `get_design_context` describes the component abstraction, not the final rendered instance.
- Code Connect maps the node to a code component and hides visual internals.
- The MCP output includes children outside a mask or clipped frame.
- Hidden layers, inactive variants, or off-canvas children leak into the context.
- Variables or styles are returned as IDs instead of resolved values.
- Image fills, gradients, masks, and opacity are simplified incorrectly.

## Code Connect Checks

If supported, run an A/B comparison:

```text
get_design_context(fileKey, nodeId, disableCodeConnect=false)
get_design_context(fileKey, nodeId, disableCodeConnect=true)
```

If the disabled version is closer to the visual tree, use it for high-fidelity implementation. Use Code Connect only to map known design-system components to existing code components.

Signals that Code Connect is active:

- `CodeConnectSnippet` appears.
- Real repository imports or component paths appear.
- Props are returned instead of visual layout/style details.
- Large parts of an instance collapse into a single code component.

## Raw / Computed Tree Requirement

If the MCP provides only IDs, request or implement a raw-node tool backed by Figma REST file nodes:

```text
get_raw_node_tree(fileKey, nodeId, depth=2, visibleOnly=true)
```

The raw tree should expose:

- `id`, `name`, `type`, `visible`
- `absoluteBoundingBox`, `absoluteRenderBounds`
- `clipsContent`, masks, opacity
- `fills`, `strokes`, `effects`
- `layoutMode`, padding, item spacing, alignment
- `characters`, text style
- `componentId`, `componentProperties`, `overrides`
- `styles`, `boundVariables`
- child count and child IDs

For implementation, prefer a computed tree:

```text
get_render_tree(fileKey, nodeId, visibleOnly=true, resolveVariables=true, expandInstances=true)
```

It should preserve raw references but also return usable values:

```json
{
  "rawRef": { "componentId": "123:456", "fillVariableId": "VariableID:789" },
  "computed": { "background": "#ffffff", "paddingLeft": 24, "radius": 16 }
}
```

## Color And Variable Rules

Figma color channels from REST are `0..1` floats. Convert them to CSS/Android values by multiplying by 255.

Use this priority:

1. Visible `fills`.
2. Resolved `boundVariables`.
3. Resolved styles.
4. Parent/background fallback only when the node has no visible fill.

Do not treat `{ "r": 1, "g": 1, "b": 1 }` as `rgb(1,1,1)`. It is white.

Do not render unresolved variable IDs, style IDs, or component IDs as visual values.
