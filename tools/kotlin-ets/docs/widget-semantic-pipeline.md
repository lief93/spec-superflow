# Production Compose semantics → neutral Widget IR → Harmony output

This is the production compiler interface for the current bounded widget subset.
The `page` CLI enters this pipeline directly; there is no legacy page assembler
fallback. Unsupported Material, state, scrolling or project-adapter behavior
fails with source evidence. The interface provides typed values, explicit state
bindings, conditions, eager/lazy iteration, content slots and ordered modifiers.
Supported framework calls never emit ArkUI directly from the Compose adapter.

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

The CLI's `page` mode enables the pipeline's target-packaging policy. It retains
the source entry name and parameters as a component Builder method and adds only
the ArkUI-required `build` container. Direct pipeline consumers can keep a
stateless entry as a top-level Builder.

- `dev.ets.widgets`: `Widget<V, S>`, `WidgetValue<V, S>`, `WidgetTextStyle<V, S>`,
  `WidgetValueType`, `WidgetValueProvenance`, `ImageSource<V, S>`,
  `WidgetModifier<V, S>`, `WidgetLayoutScope`, and `Children<V, S>`.
  This module has no imports and compiles against Kotlin stdlib alone. Values
  and source locations are generic. There are no native control strings or
  compiler IR objects in the schema.
- `dev.ets.compose.ComposeWidgetAdapter`: accepts official, resolved Kotlin IR,
  uses existing `Language`/`Scope`/`DiagnosticSink`, and returns
  `Children<EtsExpression, SourceSpan>`. It recognizes the resolved AndroidX
  symbols, reshapes arguments, and recursively retains semantic children slots.
  It cannot construct a native UI node and has no Harmony dependency.
- `dev.ets.compose.ComposeWidgetAdapterModule`: optional project/framework SPI.
  Its rule returns the same neutral Widget model and consumes shared structured
  content/modifier/value services. It does not use the deprecated `lowerUi`
  target-statement hook.
- `dev.ets.harmony.HarmonyWidgetBackend`: consumes the model plus typed language
  values and produces `EtsUiElement`s. It alone selects native controls,
  attributes, layout wrappers, and Button content presentation. It compiles and
  runs with only the model, existing target module, and Kotlin stdlib.

`MaterialTheme` becomes an explicit `Widget.ThemeProvider`: it carries a typed
context binding, the new theme value and structured children. It is not flattened
to a generic group and contains no ArkUI names. The Harmony backend alone chooses
the legal target binding representation. `Surface` and `ProvideTextStyle`
likewise update semantic context before their children are lowered.

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
| Material 2/3 String `Text` | `Widget.Text(WidgetValue(STRING, ...))` | native Text through the shared value consumer |
| `MaterialTheme` | `ThemeProvider(reference, theme, children)` | scoped target context binding; no native layout node |
| `Surface` / `ProvideTextStyle` | semantic background/text-style context plus children | Stack/background or context-only boundary |
| `Scaffold`, `TopAppBar`, `SnackbarHost` | explicit widget records and named slots | native layout composition owned by one backend |
| String literal / bound String | `Literal` / `Expression` provenance | typed String value |
| `stringResource(R.string.*)` | `Resource` provenance plus typed String expression | native string-resource lookup and emitted string artifact |
| `Color(...)` / bound Color | `Literal` / `Expression` provenance | typed ARGB value |
| Compose `Color.Red` and peers | `Resource` provenance | typed ARGB value |
| `18.sp` font size / bound `TextUnit` line height | `Literal` / `Expression` provenance | typed number attributes |
| `FontWeight.Bold` | `Resource` provenance and `FONT_WEIGHT` type | native numeric font weight |
| `FontFamily.Monospace` | `Resource` provenance and `FONT_FAMILY` type | native semantic family name |
| mapped source-owned typography property | individual `ThemeToken` value | one validated text attribute |
| whole `style = TextStyle(...)` | typed inherited/provided style expression | fields are merged once, then consumed as native Text attributes |
| mapped source-owned property | `ThemeToken` provenance | project-adapter result after target-type validation |
| unmapped source-owned property | source-linked rejection | project adapter mapping required |
| foundation `Image(painterResource(...))` | `Widget.Image(ImageSource.Resource(...))` | native Image with typed Resource |
| Coil `AsyncImage(String, ...)` | `Widget.Image(ImageSource.Url(...))` | native Image with typed String URL |
| Material 2/3 `Button` | enabled + callback + `content` slot | native Button with a Row content host |
| foundation `BasicTextField` | `Widget.TextField(value, onValueChange, enabled)` | native TextInput |
| Material 2/3 `TextField` / `OutlinedTextField` | the same `Widget.TextField` | the same native TextInput |
| layout `Row` / `Column` | ordered `children` slot | corresponding native layout |
| layout `Box` | children slot, including the content-free overload | native Stack |
| `Spacer` | explicit empty layout widget | native Blank plus ordered modifiers |
| `HorizontalPager` / remembered pager state | pager state, controller, indexed content and change event | Swiper plus reactive current-page state |
| `LazyColumn` / `LazyRow` | typed item slots, values/count sources and optional state | List/LazyForEach with target controller |
| source `if` / supported `when` | `Conditional` branches with original conditions | target `if` without preview branch selection |
| supported `repeat` | `ForEach(Count, item, children)` | target iteration with typed index binding |
| scalar Dp `size` | one ordered `Size(width, height)` element | one wrapper with width and height |
| `width`, `height` | distinct ordered elements | distinct size wrappers |
| scalar Dp `padding` overloads | start/top/end/bottom | padding wrapper, LTR mapping |
| `fillMaxWidth/Height/Size(fraction)` | one ordered `Fill(axes, fraction)` | percentage width/height wrapper |
| `RowScope.weight` / `ColumnScope.weight` | ordered `Weight(value, recorded parent)` | layoutWeight wrapper |
| `BoxScope.align` | ordered `Align(value, BOX)` | typed Alignment wrapper |
| solid-color `background` | `Background(WidgetValue(COLOR, ...))` | backgroundColor through the shared value consumer |
| `testTag(String)` | ordered `Tag` modifier | native `id` attribute with the same typed string |
| `clickable(enabled, onClick)` | typed `Click(onClick, enabled)` | enabled/onClick wrapper |
| `Modifier`, `then` | identity and ordered concatenation | no element erased or overwritten |

Button content is never reduced to a text label: nested Row/Box/Text content
remains a slot. Children after a slot stay siblings of the Button. Modifier
lists retain duplicates and order; `width → padding → width` and
`padding → width` have different target nesting.

Each children slot carries an explicit layout scope while adapting: Row and
Button content use `ROW`, Column uses `COLUMN`, and Box uses `BOX`. Weight must
match the resolved RowScope/ColumnScope API and its direct parent; align must be
a direct Box child. The neutral modifier records that parent, and the Harmony
backend validates it again against the actual neutral tree. Forwarding a scoped
modifier through an alias into another parent therefore fails at the original
modifier source instead of silently applying parent data to the wrong layout.
Harmony hoists validated Weight/Align wrappers to the direct-child boundary;
ordinary modifier order and the full neutral list remain unchanged.

Size, fill, background, click, and padding use the same model and backend operations
for every widget. Each ordinary operation becomes one wrapper around the result of the
next operation, so `size → background → click → padding` targets different
layers than `click → background → size`. Uniform and two-axis `size` overloads
both retain their width/height values. Background color, click callback, and
click enabled state remain typed expressions; the adapter contains no native
control or attribute choice.

`WidgetValue` carries an explicit semantic type, the already-lowered typed
target expression, its source span, and one of four origins: `Literal`,
`Resource(reference)`, `ThemeToken(reference)`, or `Expression(reference?)`.
The expected semantic type comes from the resolved API position (`Text.text`,
`Text.fontSize`, `Text.fontWeight`, `Text.fontFamily`, `Text.lineHeight`, or
`background.color`), never from a parameter or property name. The Harmony
backend has one `consume` function that checks semantic type and target type;
Text, Text nested in Button content, and every widget's Background modifier all
use that function.

`WidgetTextStyle` stores semantic fields separately and may also retain a typed
inherited `TextStyle`. Harmony maps color, size, weight, family, line height,
style, spacing, decoration, alignment, overflow and max-lines only after target
type validation. A source `TextStyle` object is merged once with inherited
Material typography before native Text consumes its fields; the object is never
passed blindly to ArkUI.

Source-owned property getters are project tokens. They cross this seam only
when a registered call rule maps them to the required typed target value. An
unknown token fails at the getter use with `Unmapped project widget token ...;
provide a project adapter mapping`; the adapter does not compile or guess the
getter body. Material theme and ColorScheme property reads retain
`ThemeToken` provenance when the existing language rules can lower them.

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

Values are lowered once at their original UI position through `Language` and may
contain ordinary calls or ordered language effects. Source locals become
`ValueScope` records so one-time evaluation and lexical scope survive target
lowering. Unsupported widgets/modifiers/arguments, dynamically selected slots,
arbitrary Painters, rich text, decoration slots, invalid literal URLs, and
nonterminal or nonlocal UI returns fail with `Unsupported` and source spans. The adapter never
substitutes an unknown call with empty children. Ordinary function bodies inside
supported events still belong to `Language`, not this adapter.

### Source argument evaluation

Kotlin evaluates a call receiver and explicit arguments once in source order.
ArkUI may consume a widget value later inside a child builder or print a native
attribute before another source argument. The neutral `Widget` contract therefore
has an optional `sourceEvaluations` sequence containing the already-lowered typed
expressions in original source order. It is generic widget metadata, not a Text or
Compose API exception.

`HarmonyWidgetBackend` wraps only non-reorderable values in typed
`EtsUiForEach(kind = SOURCE_EVALUATION)` bindings and replaces every corresponding
native call/attribute use with the binding symbol. In this form `ForEach` is the
ArkUI-compatible once-only binding carrier; it does not represent a source loop.
`target/UiEvaluationOrder.kt` owns the shared effect analysis and may remove a
binding only after proving the complete target expression stable. Language
lowering marks mutable local and top-level references as runtime reads. Ordinary
member reads also remain conservative; language/platform lowering explicitly
marks readonly stored properties and fixed target constants stable. Compose rules
and the Harmony backend must not infer purity from API or property names.

Explicit empty children are valid; ignored behavior is not. Local Modifier
aliases and the empty identity are accepted. Named source composable calls and
typed forwarded content slots use shared function lowering. Dynamically selected
lambdas, unsupported Material styling parameters, and arbitrary modifier
functions still require explicit semantics.

The modifier subset does not yet model arbitrary Brush backgrounds, all shape
families, click labels/roles, indication or interactionSource semantics,
combined/double/long click, general offsets, graphics transforms, pointer input,
or arbitrary semantics modifiers. Supported clipping is bounded to resolved
corner radii; supported scrolling is bounded to modeled remembered state.
Weight with `fill=false` remains outside this subset because ArkUI layoutWeight
cannot preserve that sizing contract. Explicit unsupported arguments fail with
their source span; they are not discarded.

## Reproduce

From the repository root:

```sh
node tools/kotlin-ets/tests/ui/widgets/run.mjs
bash tools/kotlin-ets/tests/target/run.sh
node tools/kotlin-ets/tests/ui/modifier-arguments/run.mjs
node tools/kotlin-ets/tests/ui/weight/run.mjs
node tools/kotlin-ets/tests/ui/material-button/run.mjs
node tools/kotlin-ets/tests/ui/fonts/run.mjs
node tools/kotlin-ets/tests/ui/typography/run.mjs
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

1. **Resolved-call structure.** `tests/ui/widgets/.work/run-HWLK7z` compiles
   against real AndroidX and Coil artifacts and asserts all seven widget kinds.
   Resource/URL source kinds, TextField value/event/enabled symbols, aliased Text,
   nested Button content, siblings, empty Box, Modifier identity/then, duplicate
   widths, and all size/background/click/padding values retain their structure.
   It also asserts String, Color, and text-style literals, resource references,
   mapped theme tokens, and bound expressions with their exact provenance and
   source. Direct Text and Text inside Button content share the same four
   individually typed style attributes. Dynamic and literal fill fractions,
   Row/Column weight (including Button's RowScope), Box alignment, recorded
   parents, and ordered modifier positions are asserted in the neutral model.
   The backend-only test rejects a forged parent mismatch.
   It proves different ordered chains on Text and Image through the same model
   and backend. `model.txt` records the result. The model compiles alone; the
   adapter compiles without Harmony; the backend compiles and runs without
   compiler or Compose classes.
2. **Harmony → typed ETS.** The same run validates the actual `EtsProgram`, emits
   distinct ordered modifier wrappers around native controls and copies
   `WidgetPage.ets.resources/base/media/widget_logo.svg`. The unchanged generated
   file, SHA-256
   `43aff84f9010e3f0f5bfce6f63dfa6ebdc059fda96576d2dfa6ee63fa583273e`,
   passes the installed DevEco SDK in
   `/private/tmp/kotlin-ets-basic-controls-sdk-59k8oS`. The SDK copy contains the
   media and string resources and produces ABC
   `45032ba2957fd503c0eb9589b46e1015612c920a50ea61a8a73365feeb9d68d8`
   plus `entry-default-unsigned.hap`. The generated string artifact SHA-256 is
   `29d4d2d7319fbf428c148f50e936869382ebd078eb187d476098ba8a5ae678a4`.
   No generated ETS was edited.
3. **Explicit rejection.** Thirty-one source-linked failures are recorded in
   `diagnostics.tsv`. The S2.2 cases remain, joined by Brush background, shaped
   background, click label/role semantics, dynamic click callback factory,
   negative size, effectful background factory, a whole custom TextStyle, and
   unmapped String/Color/text-style project tokens, wrong Weight/Align parents,
   weight `fill=false`, and an invalid fill fraction. Empty UI is never used as
   a recovery value.
4. **Existing regressions.** Target suite `kotlin-ets-target-tests.7RoQXe`,
   weight suite `kotlin-ets-layout-weight-XQS9ap`, modifier argument suite
   `kotlin-ets-modifier-arguments-A2qSZ2`, and Material Button suite
   `kotlin-ets-material-button-ezRpE5` pass. No legacy UI implementation changed.
5. **Branch scope.** Changes are confined to the three semantic pipeline modules,
   widget fixtures/harness, and this report. Language lowering, KLIB loading,
   project adapters, shared target/core contracts, and default CLI behavior are
   untouched.

The evidence proves the static semantic/compiler/SDK path. It does not establish
recomposition, Material visual parity, device interaction, or permission to
remove the existing default UI path.
