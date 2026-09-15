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
