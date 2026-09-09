# Registered Compose Controls

The controls in this document use one implementation file per control under
`scripts/ui_migration/controls/`. This is the implemented boundary, not a claim
that every Compose overload, state or library version is equivalent.

## Extension Contract

1. Add a `Control` subclass in its own file, declaring `name`, named `slots` and
   scalar `arguments`.
2. Implement `project(ProjectionContext)` to consume evaluated arguments and emit
   `source.control` facts. Reuse the shared PSI evaluator and API adapters; do not
   scan source text in a renderer. Report unknown facts through `context.issue`.
3. Implement `render(RenderContext)` using only the single page JSON. Return lines,
   consumed fields and, when needed, a finalizer for a popup/modal attachment.
4. Register the instance in `controls/registry.py`. The scanner, native slot inventory,
   required-fact collector, fixed-state projector and backend use this registry.
5. Add source-to-JSON-to-code tests and a native build/runtime case. Include explicit
   and default values, multiple children, selected/hidden states and an unresolved case.

`ProjectionContext` exposes expression evaluation, theme/color helpers and diagnostics.
`RenderContext` exposes child rendering, lengths, quoting, native length metrics and
builder declaration. It does not expose the whole renderer. Shared dimensions,
ordered modifiers and styles remain in their existing owners. Shared modal mechanics
are in `modal.py`; tab/navigation/grid variants reuse their family implementation.
Adding a control does not require another branch in `arkui/renderer.py`.

## Implemented UI Boundary

| Controls | Mapping and supported facts | Remaining boundary |
| --- | --- | --- |
| `Dialog`, `AlertDialog` | Native content cover, dim layer, content/title/body/icon/action slots, outside/back dismissal policies | Application dismissal callback logic is not migrated |
| `ModalBottomSheet` | Native sheet, content, default/custom handle, container color, default corners | Custom anchors, partial expansion and some gesture policies remain unresolved |
| `DropdownMenu`, `DropdownMenuItem`, `ExposedDropdownMenuBox` | Native popup after anchor measurement, fixed expanded state, anchor/content, text/leading/trailing slots, enabled colors | Android `menuAnchor`/focus modifiers, advanced offsets/position providers and source event handlers are not fully mapped |
| `Tab`, `TabRow`, `PrimaryTabRow`, `SecondaryTabRow` | Equal-width tabs, selected indicator, icon/text/content slots and colors | Default indicator geometry differs by Material version; label-width primary indicators are not yet equivalent |
| `NavigationBar`, `NavigationBarItem`, `NavigationRail`, `NavigationRailItem` | Native rows/columns, header/icon/label, selected indicator, label visibility, enabled colors | Source navigation actions are not migrated |
| `NavigationDrawer` | Open/closed in-page overlay, drawer/content slots, scrim, local outside dismissal | Edge swipe/back integration remains unresolved. This registry name does not imply every Material drawer variant is supported |
| `FlowRow`, `ContextualFlowRow` | Wrapping Flex, horizontal distribution, line/item gaps, resolved contextual item count | Finite line/item caps and vertical surplus-space distribution remain unresolved |
| `LazyVerticalGrid`, `LazyVerticalStaggeredGrid` | Grid/WaterFlow, fixed or adaptive equal-width tracks, gaps, finite items, scroll-enabled flag | Reverse scroll origin, custom spans and arbitrary multi-root item grouping are not complete |

Adaptive tracks are recalculated from native available width, minimum cell size,
padding and gap. This is layout measurement, not screenshot/bbox reconstruction.
`GridCells`/`StaggeredGridCells`, `Arrangement.spacedBy`, drawer state and Material
color constructors are shared expression adapters, not project-name special cases.

Existing legacy controls have not all been moved into this directory. This extension
keeps their behavior in place and gives the new controls a separate maintenance boundary.

## Verification

Run from `scripts/`:

```sh
python3 -m unittest test_registered_controls test_overlays -v
```

Tests cover all 19 registered names, unique implementation files, duplicate registration,
slots, fixed visibility/selection, item expansion, 1dp content, spacing, color APIs,
adaptive tracks, and explicit diagnostics without deleting known content.
Code/phase tests are not visual acceptance. Native checks must independently build,
open the generated scenes and verify visible content and geometry. Compare screenshots
against the same Android scene for any fidelity claim; a successful screenshot capture
alone is not a pass.
