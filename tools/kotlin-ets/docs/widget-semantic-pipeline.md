# S2.1: resolved Compose → widget semantics → Harmony

This is an opt-in production compiler interface for a closed static widget
subset. The existing default `page` CLI remains unchanged; switching all of its
Material, state, scrolling, and project-adapter behavior is a separate migration.
No language lowering, KLIB loader, shared compiler contract, or project adapter
is changed by this slice.

Redwood remains the architecture/schema reference from
[the spike](redwood-harmony-reference.md). The implementation does not link
Redwood, a Compose runtime, a coroutine runtime, or the spike's source shims.
These are static compiler records, not an applier, mutable UI tree, event-ID
runtime, or recomposition engine.

## Interfaces and dependency direction

```kotlin
val model = ComposeWidgetAdapter(language, diagnostics).lower(function, scope)
val children = HarmonyWidgetBackend().lower(model)
// Put children into the existing typed builder/component, validate and print.
```

- `dev.ets.widgets`: `Widget<V, S>`, `WidgetModifier<V, S>`, and `Children<V, S>`.
  This module has no imports and compiles against Kotlin stdlib alone. Values
  and source locations are generic. There are no native control strings or
  compiler IR objects in the schema.
- `dev.ets.compose.ComposeWidgetAdapter`: accepts official, resolved Kotlin IR,
  uses existing `Language`/`Scope`/`DiagnosticSink`, and returns
  `Children<EtsExpression, SourceSpan>`. It recognizes the resolved AndroidX
  symbols, reshapes arguments, and recursively retains semantic children slots.
  It cannot construct a native UI node and has no Harmony dependency.
- `dev.ets.harmony.HarmonyWidgetBackend`: consumes the model plus typed language
  values and produces `EtsUiElement`s. It alone selects native controls,
  attributes, layout wrappers, and Button content presentation. It compiles and
  runs with only the model, existing target module, and Kotlin stdlib.

The caller binds entry value parameters in `Scope`; unbound parameters fail at
their source declaration. This API consumes pre-Compose-lowering IR, as does the
existing compiler. It neither reparses Kotlin text nor executes composable
functions on the JVM. Values/callbacks remain typed expressions from the
existing language compiler, not serialized strings or callback IDs.

## Closed semantic contract

| Source form | Neutral model | Harmony interpretation |
| --- | --- | --- |
| Material 2/3 String `Text` | `Widget.Text(text)` | native Text |
| Material 2/3 `Button` | enabled + callback + `content` slot | native Button with a Row content host |
| layout `Row` / `Column` | ordered `children` slot | corresponding native layout |
| layout `Box` | children slot, including the content-free overload | native Stack |
| `width`, `height` | distinct ordered elements | distinct size wrappers |
| scalar Dp `padding` overloads | start/top/end/bottom | padding wrapper, LTR mapping |
| `Modifier`, `then` | identity and ordered concatenation | no element erased or overwritten |

Button content is never reduced to a text label: nested Row/Box/Text content
remains a slot. Children after a slot stay siblings of the Button. Modifier
lists retain duplicates and order; `width → padding → width` and
`padding → width` have different target nesting.

The closed path uses Harmony's native presentation defaults. It does not claim
Material theme/typography/color parity or full Compose constraint/measurement
semantics. In particular, preserving repeated preferred-size wrappers does not
implement Compose's entire constraint algorithm. RTL, clipping, touch expansion,
recomposition, and native rendering parity are outside this acceptance.

Values must be stable scalars or statically resolved callback values. Mutable
builder locals, effectful scalar factories, dynamic callback factories,
unsupported widgets/modifiers/arguments, conditional children, and nonterminal
or nonlocal UI returns fail with `Unsupported` and source spans. The adapter
never substitutes an unknown call with empty children. Ordinary function bodies
inside supported callbacks still belong to `Language`, not this adapter.

Explicit empty children are valid; ignored behavior is not. Local Modifier
aliases and the empty identity are accepted. Source composable helper calls,
forwarded/dynamic content lambdas, state APIs, Material styling parameters,
scoped weight/alignment, and arbitrary modifier functions are not implicitly
expanded by this first interface. The legacy default path keeps those existing
capabilities until they are deliberately migrated.

## Reproduce

From the repository root:

```sh
node tools/kotlin-ets/tests/ui/widgets/run.mjs
bash tools/kotlin-ets/tests/target/run.sh
node tools/kotlin-ets/tests/ui/modifier-arguments/run.mjs
node tools/kotlin-ets/tests/ui/material-button/run.mjs
node tools/kotlin-ets/tests/ui/forwarded-slots/run.mjs
```

The new runner requires the same pinned Kotlin 2.1.20 compiler cache and real
AndroidX classpath as existing UI tests. `KOTLIN_ETS_PROBE` can point to a directory
containing `classpath.json`; the default is `/tmp/kotlin-official-frontend-probe-06`.
It emits a fresh `.work/run-*` directory with exact commands, source hashes,
model records, source-linked diagnostics, and `output/WidgetPage.ets`.

For SDK validation, use the existing harness with a complete Harmony seed:

```sh
KOTLIN_ETS_SDK_SEED=/absolute/path/to/harmony-project \
  node tools/kotlin-ets/tests/ui/basic-controls-sdk.mjs \
  /absolute/path/to/generated/WidgetPage.ets
```

The harness copies the seed, compiles the generated file unchanged, and requires
ABC/HAP output. It does not install or run a device application.

## Acceptance evidence (five completion criteria)

1. **Resolved-call structure.** `tests/ui/widgets/.work/run-GjId7A` compiles
   against real AndroidX artifacts and asserts all five widget kinds, aliased
   `Text` import resolution, parameter/callback symbol identity, nested Button
   content, post-slot siblings, empty Box, Modifier identity/then, duplicate
   widths, and both width/padding orders. `model.txt` retains the semantic result.
   The model compiles alone; the adapter compiles without Harmony; the backend
   compiles/runs without compiler or Compose classes.
2. **Harmony → typed ETS.** The same run validates the actual `EtsProgram` and
   emits `WidgetPage.ets`. The unchanged file passes the installed DevEco SDK
   in `/private/tmp/kotlin-ets-basic-controls-sdk-oMpZ9X`, producing ABC and an
   unsigned HAP. Its SHA-256 is
   `6b1368711ec0127ff81233e37fd97b73a67259902687d86de5c5a2c8b45c6da0`.
   The SDK seed was copied from the repository's Harmony stage template into
   `.work/sdk-seed`, with SDK `6.0.1(21)`, bundle `dev.ets.widgetproof`, project
   label `WidgetProof`, and no signing configuration. No generated ETS was edited.
3. **Explicit rejection.** Ten source-linked failures are recorded in
   `diagnostics.tsv`: unknown widget, modifier and argument, conditional children,
   source composable helper, effectful value, callback factory, negative literal
   padding, mutable local, and early return. The early-return case first failed
   with `Accepted unsupported fixture EarlyReturn` in
   `run-v1Nwnb/early-return-red.json`; it now fails closed before any target result
   is returned. Empty UI is never used as a recovery value.
4. **Existing regressions.** Target suite `kotlin-ets-target-tests.owCR34` passes,
   as do UI suites `kotlin-ets-modifier-arguments-bOo2eH`,
   `kotlin-ets-material-button-ZDcLfZ`, and `kotlin-ets-forwarded-slots-hKa1Bi`
   under the system temporary directory. The forwarded-slots assertions were
   stale: they expected context-free builder signatures and literal typography.
   A compiler jar excluding every new module produced byte-identical output
   (`run-v1Nwnb/baseline-slots.json`), confirming this predates the change. The
   test now asserts the existing explicit Material context, slot forwarding,
   and label/body typography roles; no legacy UI implementation was changed.
   These are focused related regressions, not a claim that every UI suite ran.
5. **Branch scope.** Changes are confined to the three new UI modules, widget
   fixtures/harness, this report and its index link, plus the corrected existing
   slot regression assertions. Language lowering, KLIB, project adapters, shared
   target/core contracts, and default CLI behavior are untouched.

The evidence proves the static semantic/compiler/SDK path. It does not establish
recomposition, Material visual parity, device interaction, or permission to
remove the existing default UI path.
