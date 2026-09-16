# Historical projects through the current backend

Approved scope: fix common design defects exposed by historical project replays,
not project-name exceptions, invented values or edits to generated ETS. Preserve
source code and use the real Gradle task's sources, dependencies and environment.

First requirement: distinguish absent outputs of completed classpath producers
from missing external or unbuilt dependencies. Use Gradle task/output identity,
not path names, directory suffixes or plugin-specific rules. Keep classpath order
and record omissions with their producer and outcome. An upstream failure or
disabled producer must not be treated as a successful empty output.

Acceptance: real Gradle fixture tests for empty/present producer output, unknown
missing dependency, disabled/failed producer, and existing transitive dependency
and Android collection coverage. Rerun historical Banking, Finance, Architecture
and Ekspensify entry points, retaining first-failure evidence at each stage.
Continue fixing common backend defects; do not claim success before unchanged
generated ETS compiles with the Harmony SDK. Device/visual acceptance is separate.

Environment limits must remain explicit: do not invent private credentials or
silently upgrade an original project's Kotlin/compiler plugins. Freeze each
requirement before the existing independent review; no new reviewer is created.

Second requirement: a compiler plugin classpath is a classloader input, not a
list of independent plugin implementations. Forward intact retained plugin
classpath entries and plugin options to the official compiler loader. Let that
loader validate registrations, option ownership and compatibility; do not keep
a growing filename whitelist of every transitive plugin dependency. Continue
explicitly excluding the existing target-owned Compose JVM lowering and unused
scripting support. Preserve absent-path/version failures and report official
configuration/frontend failures without creating an output.

Acceptance: mixed plugin/dependency classpath with original order, arbitrary
plugin options, existing serialization-generated FIR/IR test, explicit missing
artifact and unsupported-option failure, real Banking frontend replay. This does
not promise arbitrary JVM backend plugin passes work in the ETS backend.

Third requirement: named nested object/companion declarations must use the
existing object runtime and resolved-symbol class placement, not be rejected by
an earlier CLASS-only gate. Preserve independent singleton identity for equal
names in different owners, method parameters and once-only initialization.
Anonymous objects remain outside this increment. Companion initializers with
effects are explicitly rejected: JVM initializes them with the enclosing class,
which is not the existing lazy object runtime contract. Do not silently compile
that difference. Ordinary nested objects retain lazy first-use initialization.
Validate JVM/ETS parity in
flat and cross-file output and replay Banking to the next real failure.

Fourth requirement: diagnostic file identity must follow declaration ownership;
recursive UI context analysis must restore its caller's source file. Validate
both a root parameter error and a root default-expression error after visiting a
builder in a different file. Check source text and line numbers, not just errors.
An entry without source defaults still fails; do not invent input state.

Fifth requirement: preserve the already-supported multiple source-parameter
forwarding, and follow resolved composable arguments at external call boundaries
just as direct lambda arguments are visited. Validate an external UI adapter with
a forwarded slot, retaining contents and inherited typography. Do not replace
unresolved external theme/provider semantics with defaults to make a page pass.

Sixth requirement: framework Color values must use the shared CallRule type and
value contracts, including source methods, parameters, properties and control
flow. Native color attributes consume the same typed expression, not a second
UI-only expression parser. Support sRGB ARGB Int and constant Long constructors,
named sRGB constants and toArgb; preserve the low 32 bits and signed Int result.
Other color spaces and Unspecified remain rejected rather than guessed. Verify
JVM parity, multi-branch values and actual SDK compilation of parameterized UI.
Effectful Color temporaries must follow the existing one-evaluation bridge,
including named argument reordering; they are not unconditional textual aliases.

Seventh requirement: add a separately owned Material3 Surface CallRule for the
non-interactive rectangular, zero-elevation/no-border form with explicit sRGB
background and content colors. Preserve source modifiers, clipping, input
blocking and propagation of incoming minimum constraints to content roots.
Use the typed target tree and a fixed target layout runtime, not page templates.
Default theme/contentColorFor, explicit shapes/elevations/borders and interactive
overloads remain diagnosed until their real semantics are implemented. Verify
the measurement algorithm, actual SDK output and native layout/color behavior
before claiming this form supported. Real Banking remains incomplete until its
theme-dependent form and subsequent dependencies also work.
Use native scoped theme colors instead of relying on foreground inheritance
across custom layout boundaries. Foundation BasicText keeps its independent
default black color. Until ordered argument binding is generalized for scoped
UI adapters, Surface accepts stable color values and diagnoses direct effectful
calls/mutable reads; source val bindings use the existing once-only bridge.

Eighth requirement: represent Material3 ColorScheme values through the shared
CallRule type/value contract. Preserve light/dark factory defaults, explicit
overrides, property reads, source parameters/returns and evaluation order.
Take defaults from the pinned AndroidX implementation and compare all supported
roles against the actual JVM library; surfaceTint defaults to the supplied
primary and must not reevaluate it. Do not identify project theme names or infer
colors from property spelling. Factory dispatch uses resolved library symbols.
This is a prerequisite to composition-scoped MaterialTheme/contentColorFor,
not a claim that a theme provider or the Banking page already works.
The value class has one target-program owner. Multi-file factories and consumers
must import that same declaration; independently printed structural copies are
not acceptable in ArkTS. Verify actual SDK compilation across the file boundary.

Ninth requirement: preserve invocation-scoped Material3 color schemes and content
colors across source builders and forwarded UI slots. MaterialTheme color-only
providers inherit omitted schemes; Surface defaults use the scheme and ordered
contentColorFor role matching, falling back to the surrounding content color.
Theme context is passed only when the page needs it; it is not a global mutable
stack or a fixed preview value. Nested providers must restore the outer context.
Keep unsupported typography/shapes, system dynamic palettes and out-of-context
value helpers explicit, not silently skipped. Validate nested and forwarded slots
with native SDK output, then replay the historical page to its next failure.

Tenth requirement: map resolved Compose Alignment, Alignment.Horizontal and
Alignment.Vertical values through the shared typed CallRule contract. Preserve
function/parameter/conditional flow; consume the same values in Box content
alignment, Column horizontal alignment and Row vertical alignment. Use native
logical Start/End, not physical Left/Right. Bias/custom alignment and arrangement
algorithms remain explicit unsupported calls. Verify generated SDK output and
native child positions, then replay Banking without editing source or output.
Until UI argument sequencing is generalized, reject combinations of an unknown
alignment read/call and unstable modifier expressions. Do not reorder their
effects silently; immutable source bindings and constant modifiers remain valid.

Eleventh requirement: adapt resolved Compose stringResource calls as string-valued
expressions, not UI builders or integer resource IDs. A separate resource input
materializer reads XML from an explicitly selected resource directory/namespace;
the compiler emits only referenced strings as a fresh sibling resource bundle.
Preserve default and supported language variants for native resource lookup.
Plain text is the initial supported form; formatting, styled/escaped text and
unsupported qualifiers must diagnose the referenced resource, not become blank.
Verify unchanged generated ETS plus emitted resources with the SDK/native host,
then replay Banking with its compiled module resource inputs. This increment
does not infer Gradle overlays by scanning arbitrary source directories.

Twelfth requirement: ordinary Dp and sp TextUnit construction/value reads use the
shared CallRule contract, including source methods, immutable locals and parameters.
UI dimension consumers use that same typed lowering instead of recognizing only
inline getter syntax. Match AndroidX Float precision for Int/Double constructors,
preserve argument evaluation through existing value bridges, and emit native
numeric vp/fp values without invented density contexts. Em, Unspecified, special
density operations and unsupported unit arithmetic remain explicit. Verify scalar
behavior and SDK output, then replay the unchanged historical page.

Thirteenth requirement: external object construction participates in the same
typed adapter contract as ordinary calls. Add a constructor entry point to
CallRule and route it through shared result validation and independent SPI
modules. A constructor must produce the mapped source value type, never void
or an unrelated value. Preserve normal source constructors and exception
construction; do not execute library JVM constructor bodies in the target.
Validate a separately compiled library, once-only argument effects, rejected
wrong/void results, and unclaimed constructors. This is a shared prerequisite
for FontFamily/TextStyle model adaptation, not a claim that those types or the
historical page are already supported.

Fourteenth requirement: preserve blocking local Font/FontFamily descriptors as
owned typed target values, including source parameters, return values, weights
and styles. Materialize explicitly supplied module font resources, carrying only
referenced TTF/OTF bytes into the generated resource bundle. Resolve R.font by
symbol, never integer value or project names. Reject missing/unsupported fonts,
empty families, async/variation settings and unimplemented weight operations;
do not register fonts as a side effect of constructing a source descriptor.
Native registration/selection and TextStyle consumption are the next dependent
requirement. Validate JVM descriptor parity and SDK value ownership, then replay
Banking to locate the next failure without changing its Kotlin source.

Fifteenth requirement: consume shared TextStyle values in native Text, retaining
explicit argument precedence and the distinction between omitted Material style
and an explicit partial TextStyle. Support the common color/size/weight/style/
family/tracking/line-height/logical-alignment fields; diagnose other explicit
fields. Select blocking local font faces using the official weight/style matching
order and register the selected native font only during Text consumption. Keep
source method/parameter flow and once-only style evaluation. Target declarations,
their transitive owned dependencies and imports use the shared typed linker.
Validate value parity, selection and override behavior, unchanged SDK output and
native text/font attributes; rerun Banking. MaterialTheme typography providers,
advanced paragraph attributes and complete font synthesis are separate gaps.

Sixteenth requirement: preserve external singleton values through the shared
typed adapter contract. Initially represent only the empty Compose Modifier
identity across ordinary helpers and source builder parameters/defaults. Keep
one target identity and preserve argument effects. A bound empty identity is a
no-op base for an otherwise supported inline modifier chain. Nonempty modifier
values crossing methods remain explicit unsupported cases, never silently empty.
Use a minimal source-component fixture and SDK output, then replay Banking.
Correct default-argument source ownership when evaluating another declaration's
default; no offsets from a callee may be attributed to the caller's file.

Seventeenth requirement: map resolved RowScope/ColumnScope weight as parent
layout data, not an attribute trapped inside generated padding layers. Support
positive weight constants and immutable scalar parameters with fill=true;
validate dynamic positivity and Float infinity coercion. Reject unsupported
fill=false, repeated weights or unstable ordering rather than guessing sizes.
Preserve the actual parent Row/Column axis, pass allocated constraints through
generated modifier layers, and verify fixed-plus-weighted native bounds before
replaying the unchanged Banking page.

Eighteenth requirement: preserve Coil 2 ImageRequest construction through the
shared typed value adapter, with owned builder/request/decoder declarations.
Support direct LocalContext.current as the native image consumer's context,
string/null data, default SvgDecoder.Factory, Boolean/Int crossfade and build.
Preserve receiver/argument evaluation, builder identity, mutation and immutable
build snapshots across ordinary methods. Do not infer arbitrary Context values,
drop unknown request options, or claim that a request descriptor alone implements
loading. AsyncImage consumption is the next explicit requirement. Validate
generated values against the official Coil contract, SDK output, and replay.

Nineteenth requirement: support typed external field reads through the shared
adapter/SPI contract, without accepting void or changing ordinary source fields.
For image resources, preserve actual Android Int IDs from the selected build's
R.txt across ordinary parameters and resolve painterResource through a typed
target lookup. Never derive IDs from spelling or hashes. Extend the existing
asset tool with explicit symbol metadata and optional resource selection, emit
referenced media beside ETS, and reject missing/ambiguous mappings. Validate
field adapter types, helper-parameter resource flow, artifact bytes and SDK
output, then replay Banking; resource writes remain unsupported.

Twentieth requirement: represent owned ArkUI component invocations, input props
and property-change observers in the shared typed target tree. Validate bindings,
input names/types and observer method signatures before printing; preserve
cross-file dependency discovery and builder argument substitution. This supplies
the lifecycle/state contract needed by asynchronous image consumption, without
adding raw ETS templates or claiming that image loading is implemented. Verify
positive and rejected target contracts and compile the unmodified generated
parent/child fixture with the real SDK.

Twenty-first requirement: consume supported Coil ImageRequest values in a typed
owned ArkUI component, preserving placeholder, success/error, request changes
and crossfade duration. Use native Image for IO and SVG decoding, not a new
network runtime. Require bounded size while intrinsic-size negotiation remains
unsupported; continue rejecting unimplemented loader options and callbacks.
Native applications resolve LocalInspectionMode.current to false without
deleting source branches. Verify loading state, stale callback isolation,
placeholder/fade transitions, SDK compilation and native loading; then replay
the unchanged historical page. Do not claim identical Coil caching policy.
Native replay exposed frozen by-value builder argument chains. Preserve
state-dependent single-consumer forwarding through the SDK Binding/makeBinding
contract; reject repeated or deferred consumers until shared composition
evaluation is represented. Ordinary language methods and constant-only builder
signatures must stay unchanged. Verify this independently of image loading.
Review correction for requirement 21: a Binding getter can execute zero or many
times even with one syntactic consumer. Limit this pass to repeatable values;
reject source calls, allocations and mutable ordinary reads in affected argument
lists rather than changing side effects/order. Add conditional non-consumption
and reversed-consumer negative tests. Full effectful composition boundaries
remain explicitly unsupported, not claimed complete by the image fixture.

Twenty-second requirement: preserve resolved rectangular/circular clip shapes
through the ordinary typed value adapter and ordered modifier lowering. Keep
background-before-clip outside the clipping layer, and preserve padding order.
Reject other shape implementations rather than erase them. Verify square and
non-square clipping, source shape parameters, ordering, SDK output and native
pixels, then replay the unchanged Banking entry to the next real failure.

Twenty-third requirement: preserve closed, statically known Modifier chains
across source UI method boundaries by compile-time specialization, not erasure
to the identity modifier or expansion into the caller. Retain ordinary parameters
and source method/file ownership; deduplicate equal modifier programs. Distinct
modifier programs may require named variants. Reject captured dynamic modifier
operands until a first-class target layout program can preserve them. Handle
Modifier.then as ordered composition, not a renderable operation. Validate
forwarding, repeated reuse, two distinct programs and rejected dynamic operands.

Twenty-fourth requirement: support the Material3 filled/text button value and
consumer contract through typed CallRules. Preserve ButtonDefaults identity,
ButtonColors across source parameters, explicit/default enabled and disabled
colors, uniform Dp rounded shapes, and PaddingValues. Consume those values in
native Button with content-color inheritance, source callbacks, minimum size
and content padding. Use AndroidX 1.3.2 defaults and native interaction feedback;
do not claim pixel-identical hover elevation/ripple. Reject custom elevation,
interaction sources, unsupported shapes and brushes rather than drop them.
Test value evaluation and native enabled/disabled rendering, SDK compilation,
then replay the unchanged historical entry. Typography and unconstrained wrap
measurement remain separately diagnosed if encountered.
Native disabled color verification requires gating input on a plain parent,
because Button multiplies disabled opacity. Preserve pointer/focus suppression
and guard callback execution. Record the remaining inner accessibility enabled
flag difference as a POC limitation, not full accessibility equivalence.

Twenty-fifth requirement: carry Material3 Typography as a typed value with its
15 TextStyle roles, constructor overrides and AndroidX 1.3.2 defaults. Preserve
the typography field through MaterialTheme, Surface, Button and source content
slots. Text consumes the selected style, with explicit properties taking
precedence. Validate default role values against Kotlin/JVM and custom/nested
theme propagation through SDK compilation; replay the unchanged Banking entry.
Do not infer typography from token names or substitute page-specific styles.

Twenty-sixth requirement: lower bounded wrapContentWidth/Height/Size using native
Stack sizing/alignment, preserving modifier order and the untouched axis. Clear
only the wrapped axis's propagated minimum/fill constraint. Verify inner and
outer geometry and alignment under explicit outer sizes on the native SDK/device.
Reject unbounded=true until unconstrained child measurement is supported.

Twenty-seventh requirement: map TextDecoration None/Underline/LineThrough to
native Text.decoration through the shared typed TextStyle consumer. Preserve
explicit Text property precedence over style and use the resolved text color.
Do not draw custom lines; reject unsupported combined decorations.
