# Redwood Harmony architecture reference

**Verdict: PARTIAL.**

Spike branch: `spike/redwood-harmony` (worktree, baseline `arch/kotlin-ets-v2`).
Primary source: Cash App Redwood **0.19.0** (`e12c0f3`). Clone: `/tmp/redwood-0.19.0`.
kotlin-ets is pinned to Kotlin **2.1.20**. Redwood 0.19.0 uses Kotlin **2.2.21**,
Compose runtime **1.9.4**, coroutines **1.10.2**. The production compiler is
not upgraded.

Reuse Redwood Schema, generated Widget/Modifier APIs, and a Harmony
`Widget` backend. Do not execute Redwood's Compose Runtime / Applier /
Recomposer inside kotlin-ets. Do not invent a new UiTree/UiNode runtime.
Do not continue Compose API → large CallRule → ArkUI.

Related:

- [blocker matrix](redwood-harmony-blockers.md)
- [Harmony backend](redwood-harmony-backend.md)
- [Compose compatibility](redwood-harmony-compose-compat.md)
- [S2.1 resolved-call production interfaces](widget-semantic-pipeline.md)
- experiment: `experiments/redwood-harmony/`

CHANGELOG 0.19.0: **final release; development discontinued.**

## Pipeline

Desired:

```text
Android Compose API
  -> thin compatibility (library and/or symbol remap)
  -> Redwood Schema-generated Compose / Widget model
  -> Harmony Widget backend
  -> existing EtsProgram / EtsUiElement
```

Anti-pattern (do not extend):

```text
androidx.compose.material3.Button
  -> ComposeButtonRule.lowerUi
  -> ArkUI Button wrapping Row, then Stack(enabled)
```

Redwood cannot consume an arbitrary Material3 Button. Generated
composables come from Schema members.

A and B are independent and both currently fail as drop-ins:

- **A.** Can Redwood generated Compose frontend enter kotlin-ets? **No.**
- **B.** Can original Android Compose APIs thin-adapt onto Redwood APIs? **Not automatically.**

## C1 answers from 0.19.0 source

### 1. Schema

Source: `redwood-schema/.../annotations.kt`,
`redwood-ui-basic-schema/.../RedwoodUiBasic.kt`,
`redwood-layout-schema/.../schema.kt`.

An otherwise unused interface is annotated `@Schema(members, dependencies,
reservedWidgets, reservedModifiers)`. Members are `@Widget(tag)` or
`@Modifier(tag, vararg scopes)` classes.

Widgets are data classes. Properties use `@Property(tag)`. Child slots use
`@Children(tag)` with type `() -> Unit` or `Scope.() -> Unit`. Events are
lambda properties (`onClick: (() -> Unit)?`) that codegen treats as Event.

Tags are protocol-stable. `@Widget(internalComposable = true)` hides the
generated composable (used by LazyList).

### 2. Codegen

Source: `redwood-tooling-codegen/.../composeGeneration.kt`, `widgetGeneration.kt`.

| Target | Output |
| --- | --- |
| Compose | `@Composable fun WidgetName(...)` calling `RedwoodComposeNode` |
| Widget | `XxxWidgetFactory<W>`, per-widget interface, `XxxWidgetSystem<W>` |
| Modifiers | `Modifier.xxx()` extensions plus `Modifier.Element` impls |
| Testing | mutable recording widgets |
| Protocol guest/host | serialization (out of scope) |
| WidgetComposeUi | Compose UI bindings (out of scope) |

Generated composable shape:

```kotlin
@Composable
fun Row(..., modifier: Modifier = Modifier, children: @Composable RowScope.() -> Unit) {
  RedwoodComposeNode<..., Row<Any>, Any>(
    factory = { it.RedwoodLayout.Row() },
    update = {
      set(modifier, WidgetNode.SetModifiers)
      set(margin) { recordChanged(); widget.margin(it) }
    },
    content = { Children(Row<Any>::children) { RowScopeImpl.children() } },
  )
}
```

### 3. Generated composable and node updates

`RedwoodComposeNode` uses `currentComposer.startNode` / `createNode` /
`useNode` / `endNode`. `NodeApplier` is an `AbstractApplier<Node<W>>`.
The tree alternates `WidgetNode` and `ChildrenNode`. This path requires
the Compose compiler plugin. kotlin-ets `compiler-environment.mjs`
**strips** that plugin.

### 4. WidgetSystem / WidgetFactory

```kotlin
interface WidgetSystem<W : Any> {
  fun apply(value: W, element: Modifier.UnscopedElement)
}
```

The factory is the only place native widgets are constructed. Harmony
implements the factory; it does not parse Compose IR.

### 5. Children insert / remove / move

`Widget.Children`: `insert`, `move`, `remove`, `onModifierUpdated`, `detach`.
Platforms: `MutableListChildren`, `ViewGroupChildren`, `UIViewChildren`,
`HTMLElementChildren`. `move(1, 3, 1)` on `A B C D E` yields `A C B D E`.

### 6. Property changes

Generated `set(text) { recordChanged(); widget.text(it) }` calls the widget
setter. Platform widgets write native state. `ChangeListener.onEndChanges()`
batches layout. Setters are not coroutine based.

### 7. Events / callbacks

Schema lambda → widget `onClick` → native listener invoking the Kotlin
lambda (`setOnClickListener`, UIButton target, DOM `click`). Harmony stores
`HarmonyNode.onClick` and emits `onClick=callback`.

### 8. Modifier model

Ordered immutable Element chain. `then` concatenates; empty companion is
identity. Real Redwood annotates Modifier `@Stable` and `@ObjCName`. The
spike runtime omits those.

### 9. Scoped vs unscoped modifiers

Scoped: parent reads `child.modifier` in `Children.insert` /
`onModifierUpdated` (Width/Height/Grow/Margin/alignment).
Unscoped: `WidgetSystem.apply(value, element)`. Compose adapters must not
consume modifiers.

### 10. Layout Row / Column / Box

Schema `RedwoodLayout`: Row, Column, Box, Spacer plus Width/Height/Margin/
Grow/Shrink/Flex/alignment. Android/iOS: Yoga. DOM: CSS flex. Harmony
Column maps to ArkUI `Column` and applies scoped width/height as attributes.

### 11. Lazy lists

`LazyList` / `RefreshableLazyList`, `internalComposable = true`. Viewport
widget (placeholder + items), not a full Compose LazyColumn. Out of Phase 1.

### 12. Android View backend

`ViewButton` wraps `android.widget.Button`. `ViewText` wraps `TextView`.
`ViewFlexContainer` hosts YogaLayout + `ViewGroupChildren`. `W = View`.

### 13. UIView backend

`UIViewButton` wraps `UIButton`. `UIViewText` wraps `UILabel`.
`UIViewFlexContainer` / `YogaUIView`. `W = UIView`.

### 14. DOM backend

HTMLElement widgets. `HTMLFlexContainer` sets `display: flex`.
`W = HTMLElement`.

Harmony should look like these three: wrap ArkUI nodes, implement Children,
apply modifiers. Not like `ComposeButtonRule`.

### 15. Compose Runtime usage

Required: `@Composable`, Composer node APIs, Applier, Recomposer,
Snapshot observer, remember/mutableStateOf, `@Stable`, collectAsState,
MonotonicFrameClock, Compose compiler plugin.

kotlin-ets today: plugin excluded; source `@Composable && Unit` becomes
ETS builder methods; `remember { mutableStateOf(...) }` only; unknown
library Unit UI APIs fail (`Unsupported resolved UI API`).

Generated Redwood composables cannot run as Compose Runtime inside kotlin-ets.

### 16. Coroutines

`RedwoodComposition` requires a CoroutineScope with MonotonicFrameClock,
constructs Recomposer + Composition, Snapshot apply via `scope.launch`,
and `recomposer.runRecomposeAndApplyChanges()`. Widget setters are
synchronous. kotlin-ets maps `launch` only for remembered pager scopes.
Coroutines artifact is 1.8.0, not 1.10.2.

### 17. What Harmony does not need

Treehouse, Zipline, protocol guest/host, leak detector, snapshot testing,
`redwood-widget-composeui`. Harmony is an in-process platform backend.

### 18. Minimum Harmony interfaces

Phase 1 under `experiments/redwood-harmony/`:

1. `HarmonyNode` — ArkUI-shaped `{type, attributes, children, onClick}`
2. `HarmonyWidgetFactory` — Text / Button / Column
3. `HarmonyWidgetSystem.apply` — unscoped Padding
4. `HarmonyChildren` — insert/move/remove + scoped Width/Height
5. Static `emitEts` → local `EtsUiElement` (does not modify `src/target`)
6. Host page `CounterPage`: state, property update, click, children

Not in Phase 1: Recomposer on device, Yoga port, LazyList, protocol.

## C2 experiment

`tools/kotlin-ets/experiments/redwood-harmony/`

```sh
python3 -B tools/kotlin-ets/experiments/redwood-harmony/tests/test_spike.py
python3 -B tools/kotlin-ets/experiments/redwood-harmony/tests/test_kotlin_ets_compat.py
```

Width/height reuse Redwood layout scoped modifiers. Padding maps to ArkUI
padding as an unscoped element consumed by the backend.
No MaterialTheme, LazyColumn, TextField, Image, Pager.

## C3 kotlin-ets intake

See [redwood-harmony-blockers.md](redwood-harmony-blockers.md) and
`experiments/redwood-harmony/evidence/`.

Categories: `KOTLIN_LANGUAGE_GAP`, `COMPOSE_RUNTIME_GAP`, `COROUTINE_GAP`,
`REDWOOD_RUNTIME_GAP`, `BINARY_DEPENDENCY_BODY_GAP`, `TARGET_ETS_GAP`,
`PLATFORM_BACKEND_GAP`. No new CallRule was added.

## C4 Harmony backend

See [redwood-harmony-backend.md](redwood-harmony-backend.md).
Harmony-specific code is only the factory, Children, and emitter.
Modifier consumption is backend-side.

## C5 Compose compatibility

See [redwood-harmony-compose-compat.md](redwood-harmony-compose-compat.md).

**Recommend HYBRID.** COMPAT_LIBRARY for the closed schema; THIN_IR only
for symbol-level remap. Forbidden: Material Button Rule creating ArkUI
Stack/Row/Button.

## Version pin

| Component | kotlin-ets | Redwood 0.19.0 |
| --- | --- | --- |
| Kotlin | 2.1.20 | 2.2.21 |
| coroutines | 1.8.0 | 1.10.2 |
| Compose runtime | AndroidX on probe classpath; plugin stripped | 1.9.4 / JB 1.9.2 |
| Compose compiler plugin | excluded | required for generated composables |

Isolating a Gradle experiment under `experiments/redwood-harmony/` is
allowed. Upgrading the production compiler is not.

## Verdict

**PARTIAL**

| Claim | Result |
| --- | --- |
| Schema/Widget/Modifier/Children is the right common UI model | Yes |
| Harmony should implement Widget backend, not UiTree | Yes |
| Generated Compose frontend drop-in to kotlin-ets 2.1.20 | No |
| Android Compose APIs automatically become Redwood widgets | No |
| Continue CallRule → ArkUI | No |

GO would require Compose Runtime + Kotlin 2.2 in the production compiler,
which is forbidden. NO-GO would mean the widget model is wrong; it is not.
PARTIAL means: reuse the architecture, statically lower or host-run the
Compose frontend, implement Harmony as a Redwood platform.
