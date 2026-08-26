# Android UI to ArkUI mapping

## UI structure

`ui.primitive_component_mapping_catalog` is the executable candidate index for the global
Compose/Material-to-ArkUI baseline. A call's `primitive_mapping_id` links to the semantics, state,
geometry, and target-component checklist that must be reconciled. It does not authorize copying a
sample style, and it does not establish the Material version or active theme. Resolve imports and
dependencies first; keep project-defined composables in the target-local mapping knowledge and
apply the global baseline only to the primitive calls reached inside their call graph. An explicit
`androidx.compose...` import is recorded as stronger candidate evidence; an explicit non-Compose
import with the same simple name is rejected. Wildcard-import and implicit-scope calls remain
unresolved candidates until source reconciliation.

| Jetpack Compose | ArkUI | Migration note |
|---|---|---|
| `Column` / `Row` / `Box` | `Column` / `Row` / `Stack` | Preserve child order, alignment, weight, and constraints. |
| `Spacer` | `Blank` | Preserve explicit width/height, weight, alignment, and its position as a real layout node. |
| Compose `ConstraintLayout` | `RelativeContainer` | Preserve reference IDs, links, bias, guidelines, barriers, chains, and dimension behavior. |
| `LazyColumn` / `LazyRow` | vertical / horizontal `List` | Preserve stable keys, source ordering, `reverseLayout`, viewport anchoring, and end-of-list trigger guards. |
| `LazyVerticalGrid` | `Grid` | Preserve fixed/adaptive cell policy, spans, stable keys, both spacing axes, padding, and scroll restoration. |
| `LazyVerticalStaggeredGrid` | `WaterFlow` | Preserve lane policy, stable keys, item spacing, padding, scroll state, and masonry item bounds. |
| `Scaffold` | Page-level `Column`, `Navigation`, bars | Recreate slots explicitly; verify safe areas. |
| `TopAppBar` | `Navigation` title bar or explicit `Row`/`Stack` | Preserve navigation/title/actions, content insets, full-bar centering, colors, and scroll behavior. |
| `Divider` / `HorizontalDivider` | `Divider` | Preserve orientation, thickness, color, and start/end insets. |
| `Text` / `ClickableText` | `Text` | Map resource, size, weight, line limit, overflow, alignment, color, annotation ranges, layout callbacks, and click-offset behavior. |
| `Image` / `Icon` | `Image` / `SymbolGlyph` | Preserve scale, alignment, clipping, alpha, tint, RTL mirroring, and content-description semantics. Use opaque copied assets or verified native symbols; never inspect protected images. Custom `*Image` findings remain candidate-only. |
| `Button` / `IconButton` / `TextButton` / `OutlinedButton` | styled `Button` | Resolve Material-version defaults; preserve variant-specific container, border, padding, touch target, enabled state, and interaction state. |
| `TextField` / `OutlinedTextField` | `TextInput` / `TextArea` | Select single-line versus multi-line target from source semantics; preserve label/placeholder decoration, keyboard type, validation, focus, masking, and IME actions. |
| `Card` / `ElevatedCard` / `OutlinedCard` / `Surface` | styled `Column` / `Stack` container | Preserve variant-specific color/content-color, shape, border, elevation/shadow, clipping, click behavior, and child hierarchy instead of applying a sample-project card style. |
| `TabRow` / `PrimaryTabRow` / `SecondaryTabRow` / `Tab` | `Tabs` / `TabContent` | Preserve selected index, item distribution, indicator/divider geometry, enabled state, colors, and restoration. |
| `NavigationBar` / `NavigationRail` and items | `Tabs`, `TabContent`, explicit `Row` / `Column` | Preserve orientation, header, safe areas, selection indicator, label policy, colors, and touch targets. |
| `FilterChip` | styled `Button` / `Row` | Preserve selected/unselected states, label/icons, border, elevation, colors, and touch target. |
| `ExposedDropdownMenuBox` | anchored `Stack` / `Menu` | Preserve expansion callback, anchor geometry, focus, width matching, dismissal, and window position. |
| `TimePicker` / `TimeInput` | `TimePicker` and explicit input composition | Preserve picker state, 12/24-hour and period semantics, locale, layout mode, colors, focus, and validation. |
| Compose `Canvas` | ArkUI `Canvas` | Preserve coordinate space, density, layout direction, clipping, draw order, and redraw triggers; drawing code still requires explicit transcription. |
| `Dialog` / `AlertDialog` | `CustomDialogController` / dialog APIs | Preserve dismissal and back behavior. |
| `CircularProgressIndicator` / `LinearProgressIndicator` | `LoadingProgress` / `Progress` | Distinguish indeterminate and determinate overloads; preserve progress range, track, color, stroke, direction, and visibility state. |
| `AnimatedVisibility` | visibility/transition APIs | Verify start/end states and interruption behavior. |

`CenterAlignedTopAppBar` centers its title against the full bar, independently of unequal
navigation and action widths. In ArkUI, use a full-width centered overlay such as `Stack` with a
separate full-width action row. A single `Row` whose title uses `layoutWeight` is not equivalent:
one navigation action on the left and two actions on the right shift the title away from the screen
center. Add a bounds assertion comparing the title center with the bar center.

A Compose `Box` overlay does not imply bottom alignment for every ArkUI `Stack` child. Preserve
each child's source `align`, `offset`, padding, and z-order explicitly. In particular, translate a
top-start logo or badge with an explicit Stack position/alignment; relying on the Stack's default
child alignment can move it to a different edge even when its size is correct.

## Android Views and XML

| Android Views/XML | ArkUI | Migration note |
|---|---|---|
| `ConstraintLayout` | `RelativeContainer`, `Stack`, `Row`, `Column` | Translate each constraint edge and bias; do not infer layout only from child order. |
| `RecyclerView` + `GridLayoutManager` | `Grid` | Preserve span count, item spacing/decoration, stable identity, pagination threshold, restoration, and loading guard. |
| `RecyclerView` (linear) | `List` | Preserve orientation, item spacing, adapter ordering, scroll position, and end-of-list behavior. |
| `NestedScrollView` | `Scroll` | Preserve the single content hierarchy and nested scrolling behavior. |
| `ProgressBar` | `LoadingProgress` / `Progress` | Translate visibility bindings and determinate/indeterminate state separately. |
| `Toolbar` / app bar | page `Row`/`Column` or `Navigation` title bar | Preserve height, content insets, title style, back action, elevation, and safe-area behavior. |
| `<include layout="…">` | shared ArkUI component | Preserve the included layout as a separate component and keep parent-supplied ID/layout overrides. |
| DataBinding `<variable>` / `@{…}` | typed page/controller state | Keep expression polarity and nullability; do not replace derived expressions with unrelated booleans. |
| `@BindingAdapter` | controller/component behavior | Inspect the implementation and preserve behavior such as pagination, visibility, events, dynamic palette, or adapter submission. |
| Navigation XML destination/action | typed `NavPathStack` route | Preserve graph start, included graphs, destination identity, action target, arguments, deep links, pop-up behavior, single-top behavior, and platform Back. |
| Activity + explicit Intent extras | typed `NavPathStack` route, or `Want` at an Ability boundary | Preserve launch mode, argument key/type, direct entry, and platform Back. |

Treat style and resource qualifiers as part of the contract. Merge inherited styles explicitly,
translate `dp` to `vp` and `sp` to `fp`, retain locale/API/night variants, and record any runtime
theme or overlay choice the static inventory cannot resolve. XML attributes are not an unordered
style bag: parent constraints, child size, padding, margins, clip behavior, and scroll behavior
must remain attached to the original component boundary.

For a hybrid Fragment/Compose application, the Fragment Navigation XML remains the route
authority even when the destination bodies are Compose. Use
`ui.android_navigation_inventory.graphs` together with the project composable call graph. Resolve
included graphs and generated Safe Args call sites before implementing the ArkUI back stack; a
zero Compose-route count does not mean the application has no navigation.

## Modifier order

Compose modifier order is semantic. Translate the ordered chain rather than treating it as an
unordered style bag:

- size/constraints;
- layout weight and alignment;
- padding;
- background/border/shape/clip;
- click/gesture;
- semantics/test tag.

When ArkUI applies properties in a different phase, add a focused layout test or manual check.
Read only the top-level ordered chain: a call such as `Color.copy()` inside `background(...)` is
an argument expression, not another Modifier. Preserve trailing-lambda modifiers such as
`offset { ... }`, `drawWithCache { ... }`, and `clickable { ... }` as explicit translation work.

Do not flatten layout values across component boundaries. `LazyVerticalGrid(contentPadding =
PaddingValues(horizontal = 12.dp))` and a child card's `Modifier.padding(horizontal = 12.dp)` are
two separate layers; preserve both even when they happen to use the same value. Use
`ui.semantic_translation_candidates.calls[].parent_call_id`, `semantic_arguments`, and
`ordered_modifier_chain` as the candidate source contract, then reconcile its documented static-
scanner limitations before implementation.

Keep explicit `Spacer` calls as ordered layout nodes. Replacing a sequence of unequal or
conditional spacers with one `Column(space = ...)` changes first/last gaps and can change spacing
around branches that disappear at runtime. Use uniform parent spacing only when the source proves
that every adjacent pair has the same unconditional gap.

A component declared on `RowScope` or `ColumnScope` can receive parent data through
`Modifier.weight(...)`. Preserve that contract on the ArkUI component root with
`.layoutWeight(...)` in the equivalent parent. Do not let the component collapse to content width
and give the remaining width to an unrelated `Blank`. Preserve an internal weighted `Spacer` or
`Blank` separately; parent allocation and child arrangement are two different layout contracts.
Add a device bounds assertion for the weighted component's width relative to its parent.

Preserve whether padding is outside or inside the sized component. For example,
`Modifier.padding(horizontal = 20.dp).fillMaxWidth()` creates outer horizontal insets. ArkUI
`.width('calc(100% - 40vp)')` alone is not equivalent because a `ListItem` can anchor that child to
the leading edge; retain the inset with a margin or a full-width wrapper and verify both left and
right bounds on a device.

Treat `height(IntrinsicSize.Min)` as a parent measurement constraint, not as `height('100%')` on a
child. In particular, a Compose `VerticalDivider` that fills an intrinsic-height `Row` must not
become an unconstrained ArkUI divider whose percentage height determines the `ListItem` height.
Constrain the ArkUI row/divider from the translated content dimensions and add a bounds assertion
that the result remains content-height rather than viewport-height.

For project-defined Compose components, use `ui.custom_composable_call_graph` to build the full
screen closure before writing ArkUI. Preserve each call as a distinct component boundary unless a
documented platform adaptation makes that impossible. Invocation arguments are behavior and state
wiring, not optional hints; retain their values, callbacks, and conditional branches. A visually
plausible replacement component does not satisfy semantic transcription when the source component
is resolvable.

Accumulate project-defined component mappings as target-local migration knowledge. Once a custom
component has been expanded into its primitive closure and translated, reuse that mapping for every
call site in the same project, including its parameters, states, theme tokens, and verified ArkUI
boundary. Do not use a public sample project's custom component as a global visual template for an
unrelated company project. The global baseline should map versioned Compose/Material primitives to
ArkUI semantics; only a de-branded, behavior-neutral pattern proved by independent projects is a
candidate for later promotion.

The additional animation, flow-layout, pager, navigation, form, menu, picker, staggered-grid,
canvas, card, tab, chip, and clickable-text families in the catalog were exercised against fixed
revisions of multiple unrelated public Compose projects. That evidence supports candidate
recognition and migration checklists only. It does not make generated ArkUI complete, resolve
project-private wrappers, or prove visual parity without the normal build, behavior, device, and
authorized visual gates.

Treat `reverseLayout` as a compound state-and-viewport contract, not as permission to reverse an
array in isolation. Preserve the source collection's chronological ordering and insertion edge,
then choose the ArkUI render projection that presents the same visible order. Anchor the initial
viewport to the same logical edge and restore that anchor after an inserted item when the source
does so. Keep date separators and stable keys attached to source chronology. Test both the first
render and an insertion; either check alone can pass while the other remains reversed.

## Dimensions and typography

- Start from `ui.compose_theme_token_inventory`, not from a sample-project palette. Translate
  light/dark color-scheme roles as one paired project-local token set, preserve the source runtime
  selector, and retain explicit `MaterialTheme` arguments. A declared `Shapes` or typography set
  that is not passed to the active theme remains a candidate declaration, not proof that it is
  applied at runtime.
- Preserve every typography role separately, including font family, weight, size, line height, and
  letter spacing. Translate code-defined font resource keys only through the approved opaque-font
  copy path; `FontFamily.Default` should resolve to the target platform default instead of copying
  an unrelated font.
- Preserve shape roles as project-local tokens. Map corner type and each corner radius explicitly;
  do not reduce `CutCornerShape`, asymmetric shapes, or zero-radius roles to one global rounded
  rectangle rule.
- Use `generate_harmony_theme_resources.py` only after selecting the active candidate theme. It
  creates paired base/dark role names so Harmony qualifier selection can preserve the source
  light/dark switch, emits `vp`/`fp` values without unit loss, and records typography, shape, and
  font-copy work that cannot safely be represented as a generated scalar resource. A font plan is
  not a copied font; use the manifest-approved opaque asset path separately. If separate source
  declarations normalize to the same Harmony resource name with different values, the generator
  omits that name, records every candidate value as `resource_name_collision`, and marks the
  skeleton incomplete. It also omits empty resource-category files because Harmony compilation
  rejects empty resource arrays.
- Translate Compose `dp` layout dimensions to ArkUI `vp` values.
- Translate Compose `sp` text dimensions to ArkUI `fp` values. Preserve `fontScale` behavior.
- For a Web/RichText CSS boundary that only accepts physical pixels, derive pixels from Android
  `scaledDensity` or an explicitly equivalent runtime scale. Never rewrite `16.sp` as `16px`.
- Keep resource-backed dimensions resource-backed. Do not replace
  `dimensionResource(R.dimen.key)` with a guessed literal when the resource can be translated.
- Preserve units in the intermediate contract until the target API boundary is known; a bare
  number is not an adequate typography contract.
- Do not infer Material control geometry from the component name alone. Defaults such as a
  one-line `OutlinedTextField`'s 56 dp minimum height and a button's minimum height, content
  padding, text style, and touch target are library contracts. Resolve them from the pinned
  Material version or measure them with component bounds, then encode the equivalent ArkUI
  geometry. An `OutlinedTextField` remains one outlined input with an internal floating/placeholder
  label; an external `Text` plus a plain `TextInput` is a different hierarchy and interaction.

## Images and source-defined states

Translate each source image component branch independently: loading, placeholder, success,
failure/error, retry, and content description. The candidate contract records recognized named
state slots and whether their source expressions actually contain a progress indicator.

Map Compose `ContentScale.FillWidth` from its scaling semantics, not from its name alone. ArkUI
`ImageFit.Cover` is equivalent only when the target image box has the same constrained width and
height, aspect ratio is preserved, and overflow is clipped at the same boundary. If the source
height is derived from the scaled intrinsic image or permits uncropped overflow, retain that
measurement behavior instead of applying `Cover` unconditionally.

Do not add a spinner, fallback icon, error illustration, retry button, animation, or decorative
surface unless that element exists in the source branch. A neutral source placeholder remains a
neutral placeholder. If a library hides behavior outside the safe source, mark it unresolved
instead of inventing a target state.

For manifest-approved Android VectorDrawable XML, run the deterministic vector converter before
considering a native symbol or handwritten SVG. A native symbol is acceptable only when the source
explicitly uses the corresponding platform icon or when a reviewed deviation is recorded.
When the conversion ledger reports `requires_target_tint: true`, map its single
`dynamic_color_tokens` value to the equivalent Harmony color resource and apply that tint at the
ArkUI image boundary. `currentColor` preserves tintable geometry; it does not choose the target
theme color by itself.
An explicit Compose `Icon(tint = ...)` is an independent call-site requirement. Apply its mapped
color with ArkUI `Image.fillColor(...)` (or the equivalent native-symbol color) even when the
converted vector has a static fill and its ledger says `requires_target_tint: false`; that ledger
field describes the asset conversion, not a tint supplied by the invoking component.
When it reports `requires_auto_mirroring: true`, apply `matchTextDirection(true)` at the same Image
boundary so RTL behavior remains equivalent.

## State and lifecycle

| Android | HarmonyOS approach |
|---|---|
| `ViewModel` + `StateFlow` | Explicit state holder/controller plus observed ArkUI state |
| `collectAsStateWithLifecycle` | Start/stop subscriptions in page/component lifecycle |
| `LaunchedEffect(key)` | Lifecycle method or observed-key task with cancellation |
| `remember` | Component-local state |
| `rememberSaveable` | Persistent state or navigation parameter, only when source restores it |
| coroutines | `Promise`, async functions, TaskPool where CPU isolation is needed |

Model state as explicit transitions. Keep I/O behind interfaces so pending, success, error, empty,
retry, and concurrency behavior can be unit-tested with deferred promises.

Do not replace a source state machine with a handful of UI booleans unless the behavior contract
proves equivalence.

When the source repository exposes `Flow`/`StateFlow`, preserve observation or add an explicit
invalidation mechanism that reaches every return path. Refreshing only from a custom back button is
not equivalent: system Back, gesture Back, restored navigation stacks, and mutations on another
page must not reveal a stale list. Test a mutation followed by the platform Back action.

Set initial loading state before the first asynchronous read. A later `isLoading = true` assignment
does not prevent an empty-state flash on the first frame. Unit-test the pending initial read with a
deferred fake, then verify the rendered loading state where applicable.

## Navigation

Map each Compose destination or Android Activity navigation edge to a typed HarmonyOS route contract:

- route identifier;
- arguments and defaults;
- result type;
- launch mode/back-stack behavior;
- deep links;
- system back behavior;
- direct test entry strategy.

Resolve statically provable custom composable wrappers, constant/string-template route
expressions, and enum-backed route properties before implementation. Mark runtime-built routes
unresolved instead of recording the first literal fragment as a destination.

Use `Navigation`/`NavPathStack` for in-app routes. Use `Want` only for Ability boundaries or an
intentional test harness. A page need not be reachable from the production home page solely for
testing; a debug/test-only typed entry is acceptable when it cannot ship in release behavior.

Pass the source route arguments through the destination contract. Do not replace
`task/{taskId}`-style arguments with a component-global selected ID: stack restoration, direct
entry, process recreation, and multiple instances then have different semantics. Verify argument
round-tripping and system Back, not only button-driven navigation.

## Resources

- Preserve string keys and locale variants; use `$r('app.string.key')`.
- Map colors and dimensions to element resources when shared.
- Match an Android resource key to an opaque asset path through the safe manifest.
- Keep protected images out of source context and copy them locally by verified hash.
- Treat Android adaptive/layered icons, nine-patch assets, and animated vectors as explicit
  conversion tasks rather than blind renames. Manifest-approved `.ttf`/`.otf` fonts may be copied
  opaquely into `resources/rawfile` with their extension and hash preserved.

## Code-only fidelity checklist

For each screen, compare the source and target contracts for:

- hierarchy and conditional branches;
- spacing, alignment, constraints, scroll behavior, and safe area;
- text resource, typography, line count, and overflow;
- input validation, focus, keyboard, accessibility, and test identifiers;
- loading, empty, success, partial content, error, and retry states;
- navigation arguments/results and back behavior;
- asset key-to-hash mapping.

Mark visual appearance that cannot be derived from code as requiring authorized human review.

Parity migration and product redesign are separate operations. Do not mix a perceived usability
improvement into semantic translation. Record requested improvements as explicit deviations after
the source-equivalent implementation can be verified.

Memory fakes prove controller and repository contracts, not production adapters. Add device or
integration coverage for RelationalStore, Preferences, Ability initialization, and other concrete
platform bindings, and keep those gates unverified until they actually execute.
