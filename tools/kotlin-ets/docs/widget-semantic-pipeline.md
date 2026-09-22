# S2.4: resolved Compose → ordered modifiers → Harmony

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
val ets = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
    .compile(module, "example.CoreProfile")
```

`ComposeWidgetPipeline` is the production orchestration boundary. It selects a
resolved top-level entry, binds its parameters with the ordinary language
lowerer, invokes `ComposeWidgetAdapter`, passes the neutral children to
`HarmonyWidgetBackend`, builds an exported typed builder, validates the
`EtsProgram`, and emits it through `emitEtsProgram`/`EtsPrinter`.

- `dev.ets.widgets`: `Widget<V, S>`, `ImageSource<V, S>`,
  `WidgetModifier<V, S>`, and `Children<V, S>`.
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

The lower-level adapter still requires callers to bind entry values in `Scope`;
unbound parameters fail at their source declaration. The production pipeline
performs that binding itself. Both APIs consume pre-Compose-lowering IR, as does
the existing compiler. They neither reparse Kotlin text nor execute composable
functions on the JVM. Values/callbacks remain typed expressions from the
existing language compiler, not serialized strings or callback IDs.

## S2.6 production-pipeline regression

`tests/ui/widgets/CoreProfile.kt` is compiled by the official Kotlin frontend
and contains Row, Column, Box, Text, Image, Button, TextField, layout child
slots, and Button content. `CoreProfilePipelineProbe.kt` calls only the
production pipeline; it does not construct `Widget`, `Children`, or
`EtsProgram`, and it has no dependency on the legacy page lowering.

The test-only `PipelineSeamAgent` records the actual bytecode route. The runner
asserts adapter completion before Harmony lowering, typed program construction
before validation, and validation before `EtsPrinter.program`. Static guards
also reject direct target/model construction in the probe and legacy text/page
lowering references in the pipeline. The emitted artifact is an exported
`@Builder` with typed source parameters, so the regression does not fabricate
sample values or an entry component.

## Closed semantic contract

| Source form | Neutral model | Harmony interpretation |
| --- | --- | --- |
| Material 2/3 String `Text` | `Widget.Text(text)` | native Text |
| foundation `Image(painterResource(...))` | `Widget.Image(ImageSource.Resource(...))` | native Image with typed Resource |
| Coil `AsyncImage(String, ...)` | `Widget.Image(ImageSource.Url(...))` | native Image with typed String URL |
| Material 2/3 `Button` | enabled + callback + `content` slot | native Button with a Row content host |
| foundation `BasicTextField` | `Widget.TextField(value, onValueChange, enabled)` | native TextInput |
| Material 2/3 `TextField` / `OutlinedTextField` | the same `Widget.TextField` | the same native TextInput |
| layout `Row` / `Column` | ordered `children` slot | corresponding native layout |
| layout `Box` | children slot, including the content-free overload | native Stack |
| scalar Dp `size` | one ordered `Size(width, height)` element | one wrapper with width and height |
| `width`, `height` | distinct ordered elements | distinct size wrappers |
| scalar Dp `padding` overloads | start/top/end/bottom | padding wrapper, LTR mapping |
| solid-color `background` | typed ARGB `Background(color)` | backgroundColor wrapper |
| `clickable(enabled, onClick)` | typed `Click(onClick, enabled)` | enabled/onClick wrapper |
| `Modifier`, `then` | identity and ordered concatenation | no element erased or overwritten |

Button content is never reduced to a text label: nested Row/Box/Text content
remains a slot. Children after a slot stay siblings of the Button. Modifier
lists retain duplicates and order; `width → padding → width` and
`padding → width` have different target nesting.

Size, background, click, and padding use the same model and backend operations
for every widget. Each operation becomes one wrapper around the result of the
next operation, so `size → background → click → padding` targets different
layers than `click → background → size`. Uniform and two-axis `size` overloads
both retain their width/height values. Background color, click callback, and
click enabled state remain typed expressions; the adapter contains no native
control or attribute choice.

Image source kind crosses the semantic seam explicitly. A materialized
`painterResource` stays a typed `Resource`; a Coil String model stays a typed
URL expression. The adapter never serializes either expression or selects the
native Image control. Literal URLs must be HTTP(S), have a host, and contain no
credentials. Arbitrary Painter objects and non-String Coil models fail closed.
The backend maps a String content description to `accessibilityText` and an
explicit null to a disabled accessibility level.

Basic, Material, and outlined text fields converge on one model record. Their
String value, `(String) -> Unit` event, and Boolean enabled state keep their
typed expression identity through the backend. Decoration slots, labels, rich
text values, and other unmodeled arguments fail rather than being dropped.

The closed path uses Harmony's native presentation defaults. It does not claim
Material theme/typography/color parity or full Compose constraint/measurement
semantics. In particular, preserving repeated preferred-size wrappers does not
implement Compose's entire constraint algorithm. RTL, clipping, touch expansion,
recomposition, and native rendering parity are outside this acceptance.

Values must be stable scalars or statically resolved event values. Mutable
builder locals, effectful scalar factories, dynamic event factories,
unsupported widgets/modifiers/arguments, conditional children, arbitrary
Painters, rich text, decoration slots, invalid literal URLs, and nonterminal or
nonlocal UI returns fail with `Unsupported` and source spans. The adapter never
substitutes an unknown call with empty children. Ordinary function bodies inside
supported events still belong to `Language`, not this adapter.

Explicit empty children are valid; ignored behavior is not. Local Modifier
aliases and the empty identity are accepted. Source composable helper calls,
forwarded/dynamic content lambdas, state APIs, Material styling parameters,
scoped weight/alignment, and arbitrary modifier functions are not implicitly
expanded by this first interface. The legacy default path keeps those existing
capabilities until they are deliberately migrated.

The modifier subset does not yet model Brush or shaped backgrounds, click label,
role, indication or interactionSource semantics, combined/double/long click,
fill and range constraints, offset, clip, border, graphics transforms, weight,
alignment, scroll, pointer input, or semantics modifiers. Explicit arguments
from these categories fail with their source span; they are not discarded.

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
model records, source-linked diagnostics, `output/WidgetPage.ets`,
`core-profile-output/CoreProfile.ets`, and the production seam trace.

For SDK validation, use the existing harness with a complete Harmony seed:

```sh
KOTLIN_ETS_SDK_SEED=/absolute/path/to/harmony-project \
  node tools/kotlin-ets/tests/ui/basic-controls-sdk.mjs \
  /absolute/path/to/generated/WidgetPage.ets
```

The harness copies the seed, compiles the generated file unchanged, and requires
ABC/HAP output. It does not install or run a device application.

## Acceptance evidence (five completion criteria)

1. **Resolved-call structure.** `tests/ui/widgets/.work/run-2iMWe5` compiles
   against real AndroidX and Coil artifacts and asserts all seven widget kinds.
   Resource/URL source kinds, TextField value/event/enabled symbols, aliased Text,
   nested Button content, siblings, empty Box, Modifier identity/then, duplicate
   widths, and all size/background/click/padding values retain their structure.
   It proves different ordered chains on Text and Image through the same model
   and backend. `model.txt` records the result. The model compiles alone; the
   adapter compiles without Harmony; the backend compiles and runs without
   compiler or Compose classes.
2. **Harmony → typed ETS.** The same run validates the actual `EtsProgram`, emits
   distinct ordered modifier wrappers around native controls and copies
   `WidgetPage.ets.resources/base/media/widget_logo.svg`. The unchanged generated
   file, SHA-256
   `a0789d846d3d5f3dabc82c624f959a088a3b56873be2378ff4b9542f9a878c35`,
   passes the installed DevEco SDK in
   `/private/tmp/kotlin-ets-basic-controls-sdk-9VTNE4`. The SDK copy contains the
   media file and produces ABC
   `a2eeffa6abd98bc36987a00e45fff801de89dd3f22ea5bb2cc08fdae5ca71dac`
   plus `entry-default-unsigned.hap`. No generated ETS was edited.
3. **Explicit rejection.** Twenty-four source-linked failures are recorded in
   `diagnostics.tsv`. The S2.2 cases remain, joined by Brush background, shaped
   background, click label/role semantics, dynamic click callback factory,
   negative size, and effectful background factory. Empty UI is never used as a
   recovery value.
4. **Existing regressions.** Target suite `kotlin-ets-target-tests.zBcFI1`,
   modifier argument suite `kotlin-ets-modifier-arguments-12wrqX`, Material
   Button suite `kotlin-ets-material-button-4A8hhg`, and forwarded slots suite
   `kotlin-ets-forwarded-slots-8gWb6z` pass. No legacy UI implementation changed.
5. **Branch scope.** Changes are confined to the three semantic pipeline modules,
   widget fixtures/harness, and this report. Language lowering, KLIB loading,
   project adapters, shared target/core contracts, and default CLI behavior are
   untouched.

The evidence proves the static semantic/compiler/SDK path. It does not establish
recomposition, Material visual parity, device interaction, or permission to
remove the existing default UI path.
