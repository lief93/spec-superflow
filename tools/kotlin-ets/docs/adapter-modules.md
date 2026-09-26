# Independent adapter modules

An adapter maps resolved Kotlin IR APIs to typed ETS nodes. Add a module's own
Kotlin sources and standard Java SPI descriptor; do not edit a central rule list,
`ArkUiCalls`, or the target printer. The launcher rebuilds the tool on each run.
This is not a hot-loader or a dependency downloader. Adapter sources execute as
trusted compiler code; install only modules you trust.

## Layout and discovery

```text
my-adapters/
  frame/
    src/ExampleFrameModule.kt
    META-INF/services/dev.ets.AdapterModule
```

The service file contains the provider's fully qualified JVM class name:

```text
# Comments and duplicate provider lines follow ordinary SPI conventions.
dev.ets.examples.ExampleFrameModule
```

Providers implement `dev.ets.AdapterModule` and have a public no-argument
constructor. Use a class, not a Kotlin singleton `object`. Discovery does not
parse Kotlin source to guess provider classes: Java `ServiceLoader` validates the
compiled providers.

The launcher always discovers `tools/kotlin-ets/adapters/` when present. Additional
roots are supplied through `KOTLIN_ETS_ADAPTER_DIRS`, separated by the platform path
separator (`:` on macOS/Linux). Each root may contain immediate module directories
or be a module itself. Quote paths containing spaces. Relative roots resolve from
the invoking working directory. Empty path segments reject.

Every module needs its descriptor and at least one `.kt` source. Nonhidden Kotlin
files are gathered recursively; keep application fixtures and tests outside the
module directory. Canonical paths deduplicate repeated/symlinked roots. Cyclic
source directories reject. Roots, source paths, and merged provider entries are
sorted deterministically. Module registration is then sorted by module ID.

The build compiles these sources alongside the compiler sources and puts the
merged descriptor in `tool.jar`. Missing roots/descriptors/sources and malformed
provider names fail during discovery. Missing provider classes, incorrect
interfaces, or unusable constructors fail when loading SPI, before generation.

## Module API

Implement `AdapterModule` with a stable `id`, explicit `sourceCalls` and/or
`sourceTypes`, optional `targetCalls` and `imports`, and `create(target, ui)`.
Claims are resolved fully qualified IR names, not source spelling. An adapter
must still check the supported overload, receiver, parameters and return type.
Sharing a name does not make every overload supported.

`rootDefaultCalls` is a narrow contract for a direct default expression on the
selected root `@Composable`. The call must also be in `sourceCalls`, and its
resolved result type must exactly match the parameter type. The compiler turns
that parameter into a required target component prop and does not execute the
platform-owned default. The same call in a function body, nested default, or
ordinary value position still reaches the adapter and must reject unless the
module defines separate target semantics. The built-in AndroidX Hilt adapter
uses this contract for `hiltViewModel`; it does not construct or fake a ViewModel.

Each `AdapterTargetCall(id, name, signature)` declares a module-owned target
signature. `AdapterTargetApi.call` looks it up by ID and checks exact arity.
The shared target validator checks argument types and target bindings, including
ordinary inheritance. Never bypass validation with raw printed expressions or
invent source symbols. Use `language.expression`, `language.source`, resolved
arguments and existing typed constructors.

Use `lower` only for a typed value. The shared consumer checks that value against
the expected target type at its call position, even when the value is discarded.
Use `lowerStatement` for a pure effect; Unit expression bodies also consume this
path without inventing a return value. Returning a `void` expression from `lower`
cannot satisfy a value position. Wrong types, void-as-value and empty unrecorded
effects fail with the source call span before target emission.

For ordinary value and effect calls, an available source body takes precedence
over an `AdapterModule` claim. Serialized inline bodies are reused by the common
inliner before adapter dispatch; source-owned ordinary functions stay in the
normal declaration and linking path. A binary signature without a reusable body
may reach a declared adapter. If no adapter accepts it, generation fails with the
source call span and names both missing options; JVM bytecode is not decompiled
and no default value is fabricated.

`replacesSourceBodies` is an explicit exception for a host bridge that owns the
target implementation of every call listed in that module's `sourceCalls`.
Source selection then treats only those calls, and only the types in the same
module's `sourceTypes`, as externally supplied. This keeps Android repositories,
coroutine bodies, and other implementation dependencies out of target lowering
when the host contract replaces them. Keep this flag off for ordinary adapters;
it is module-wide and never inferred from a matching name.

### Factory lifecycle

SPI instantiates providers once per compiler process. A registry calls
`create(target, null)` for ordinary value/effect/type rules. These delegates may
handle `lower`, `lowerStatement`, and `mapType`.

The former page assembler also called `create(target, scopedUi)` and dispatched
`lowerUi`. That lifecycle is historical and has no production caller. New UI
extensions must map source calls into the neutral Widget model and let the
Harmony backend own ArkUI control selection; do not revive scoped UI factories.

For UI structure, implement `ComposeWidgetAdapterModule` on the same SPI
provider and return one `ComposeWidgetRule`. The rule may use
`ComposeWidgetServices.content`, `modifiers`, and `value`; those services retain
source slots, modifier order, semantic value type and source spans. The result
must be a neutral `Widget`, so project adapters cannot bypass the shared Harmony
backend or target validator with prebuilt ArkUI statements.

### Initialization and imports

Registry initialization rejects duplicate module IDs, overlapping source call or
type claims, duplicate target IDs, and conflicting import bindings. These are
configuration failures even when the current application would not use the
conflicting adapter. Module IDs and target signatures cannot be blank; target
generic signatures are outside this finite API.

Identical imports can be shared. Imports are emitted only for modules that
successfully handled a call or type; merely discovering a module does not inject
its imports. Build errors and failed translation must not leave plausible output.
Ordinary unsupported calls should throw a source-linked `Unsupported` diagnostic.

## Examples

`adapters/example-math` is a built-in independent provider. Its local signatures
map the non-generic, non-suspending top-level `demo.adapters.absolute(Double): Double` to `Math.abs` and
`demo.adapters.record(String): Unit` to `console.log`. It deliberately rejects
other overloads and receiver-bearing calls. The source library's behavior must match this mapping.

`examples/adapters/frame` is an external provider. It maps the finite
`demo.adapters.Frame(label, modifier, content)` wrapper to a `Column` with a
`Text` heading, then delegates its real Compose content and modifiers. It uses
the neutral Widget SPI without editing central Compose or ArkUI rule lists.
All three arguments must be explicit. In particular, an omitted `modifier`
rejects at the source call, even if the Kotlin declaration provides a default.
This finite example does not evaluate Kotlin default expressions and must not
silently replace a default such as `Modifier.width(120.dp)` with no modifier.

The built-in `accompanist-swipe-refresh` provider maps the finite
`rememberSwipeRefreshState(Boolean)` and `SwipeRefresh` contract to ArkUI
`Refresh`. It preserves the refresh callback, modifier, and content, and rejects
explicit Accompanist parameters outside that contract.

The built-in `architecture-samples-statistics` provider is a project bridge for
the pinned public Statistics screen. It exports typed `StatisticsUiState` and
`StatisticsViewModelBridge` host contracts for `uiState` and `refresh()` and sets
`replacesSourceBodies` so the Android Hilt repository implementation is not
lowered. It does not construct the ViewModel or perform repository work.

Android `dimen` resources are materialized from finite base `dp` values. Android
qualifiers have no direct target equivalent: report mode uses the base value and
records `dimension_qualifier_fallback`; strict mode rejects the same source use.

From the repository root:

```bash
KOTLIN_ETS_ADAPTER_DIRS="$PWD/tools/kotlin-ets/examples/adapters" \
  tools/kotlin-ets/kotlin-ets --mode page --entry demo.adapters.AdapterPage \
  --classpath-file /path/to/real-compose-classpath.txt \
  --out /tmp/AdapterPage.ets \
  tools/kotlin-ets/tests/adapter-modules/fixtures/Page.kt
```

Compiler-adapter sources and application dependencies are separate. Supply the
actual source library JAR/Compose dependencies via `--classpath` or
`--classpath-file`; putting an adapter in a discovery root does not fabricate
the Kotlin APIs it claims. Additional adapter-side JAR dependency management is
not provided by this source-module build contract.

## Verification

```bash
node tools/kotlin-ets/tests/adapter-modules/discovery.mjs
JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' \
  node tools/kotlin-ets/tests/adapter-modules/run.mjs
```

The Node discovery suite covers deterministic roots/providers, spaces, comments,
deduplication, malformed/missing inputs, and symlink cycles without a JVM.
The CLI suite snapshots compiler/module/fixture inputs, saves every child log,
and checks original JVM versus generated value/effect execution, exact no-use
output bytes with/without providers, source-linked overload/receiver rejection, missing
SPI provider rejection, and a real Compose source wrapper using the external
module. An omitted nontrivial modifier default rejects with an exact source-call
span, while the explicit-modifier positive retains its width and content.
The suite does not rewrite generated ETS.

After a test-only assertion correction, `run.mjs --resume EVIDENCE_DIRECTORY`
can reuse saved command results when the live and snapshotted inputs still match
and command arguments are identical. The result marks reused commands explicitly;
this is not a fresh compiler run. Production changes require a fresh snapshot.

`tests/adapter-contract/run.sh` owns API dispatch, signature and registration
negative checks. A focused SDK check consumes the CLI suite's unchanged
`page.ets` using `tests/ui/basic-controls-sdk.mjs`. This is separate evidence,
not implied by host execution. No native install/interaction/visual loop is
part of this bounded adapter-module change.

## Initial frozen evidence (2026-09-14)

- Discovery: `tests/adapter-modules/.work/discovery-d4LBYY/result.json`, 15 checks.
- CLI: `tests/adapter-modules/.work/cli-B82uId/result.json`, seven launcher cases,
  original JVM value/effect oracle, real Compose dependencies. Completed commands
  were reused after correcting only the expected official IR call span.
- Actual SDK: `/private/tmp/kotlin-ets-basic-controls-sdk-y6JWrf/result.json`,
  `BUILD SUCCESSFUL`, ABC and signed/unsigned HAPs. Input/copied page SHA-256:
  `ef1a2e402f740a86b2dc3cbb89d401f2a12469be27e62136575c95e78fd42aaa`.
- Main's API proof: `kotlin-ets-adapter-contract.j2bsQO`; main's existing-control
  regression: `kotlin-ets-basic-controls.9Gmaso` (reported by main, not rerun here).
- Failure evidence retained: `cli-W7jRre` (snapshot path check, before JVM),
  `cli-Nih5XA/language.json` (fixture requested unsupported Double concatenation),
  `cli-ijW53E/no-extension.json` (UI example missing abstract null `lower`).
  `cli-B82uId/unknown-receiver.json` retains the exact IR diagnostic that corrected
  the test's receiver-inclusive span assumption.

Frozen build-side SHA-256:

```text
9bf9deb91e325248c21fd5a503962ac46b248988684ef7e689351bdb91c334ee  kotlin-ets
24f8e3a1e15982be523a41dd6f4a63a2c927299c363762950d0c9f5580879c82  adapter-modules.mjs
874c481527feae994ba62f81ba8e85eeb42a517f1ea9c9ba3f22a0f6aa1a88a3  adapters/example-math/src/ExampleMathModule.kt
0c8d0f1feec61971d83158de4745a12df5c35f79f3a49662c07db1a6f9359694  examples/adapters/frame/src/ExampleFrameModule.kt
```

The CLI snapshot manifest and hashes below record the historical adapter-module
experiment. Its `ComposeLowering` hash is not an active production dependency;
the file has been removed.

Cost observation for this lane: the explicit clock window was 08:09:31 through
08:26:32 UTC (17m01s); initial inspection preceded the first clock capture.
The build slot arrived while test preparation was still underway, so no idle
slot-wait duration was measured. Child logs total 158.237 seconds across three
CLI attempts: 11 launcher compilations (seven final cases and four earlier
attempts), six small JVM fixture compilations and their oracles/path probes.
The separate SDK reports a 6.659-second hvigor build; that is not its full setup
time. Four harness/fixture/example corrections are listed above. No timing-only
baseline was repeated. Cached/uncached token counters are not exposed in this
lane, so no token savings or serial speedup is claimed. All children finished
before slot release; no native, review, commit or push was run by this lane.

## Review fix: explicit modifier (2026-09-14)

The Frame example now rejects an omitted modifier before converting content.
No generic default evaluation was added. Changes are limited to
`examples/adapters/frame/src/ExampleFrameModule.kt`,
`tests/adapter-modules/run.mjs`, the new `fixtures/OmittedModifier.kt` in that
test directory, and this guide. The existing explicit-modifier fixture is unchanged.

- RED: `tests/adapter-modules/.work/modifier-red-86gD0Q/result.json` and
  `command.json`. The prior frozen backend accepted `Frame("Title") {}` but
  omitted the declared `Modifier.width(120.dp)` from generated ETS.
- Fresh GREEN: `tests/adapter-modules/.work/cli-W0vMlh/result.json`, eight CLI
  cases, `resumed: false`. The new negative returns source-linked `UNSUPPORTED`
  at offsets 521-538, exactly `Frame("Title") {}`, and leaves no target file.
- Fresh actual SDK: `/private/tmp/kotlin-ets-basic-controls-sdk-6pUyF4/result.json`,
  unchanged positive page bytes, ABC and HAP output. Its input hash remains
  `ef1a2e402f740a86b2dc3cbb89d401f2a12469be27e62136575c95e78fd42aaa`.
- Frozen Frame SHA-256:
  `a0b28dcdca29f79218b3d81061f8d7de96903fb7cb1e45152127d6ef5f1c119c`.
  Full production and fixture hashes remain in the fresh snapshot manifest.

This correction's explicit clock window was 08:31:19-08:35:02 UTC (3m43s).
The fresh CLI/JVM command logs total 115.976 seconds, in addition to the one
targeted RED compilation and focused SDK. Unchanged discovery and main API/control
proofs were not rerun here. No second implementation correction was needed.
All children finished and the heavy slot was released before this evidence update.
# External constructors

`CallRule.lowerConstructor(IrConstructorCall, Language, Scope)` handles object
construction through the same typed value checker as `lower(IrCall, ...)`.
Return `null` to decline. Declare the resolved constructor symbol in
`sourceCalls`, for example `example.Amount.<init>`, and its mapped class in
`sourceTypes`. Inspect parameter types to distinguish overloads; do not match
source text. Constructors cannot use the statement/UI hooks to bypass the
return-type check, including when the caller discards the result.

Use `language.expression(argument(call, "value")!!, scope)` for an explicitly
required argument and return a typed target expression. Handle defaults and
argument evaluation order in the adapter contract; do not evaluate a source
argument twice or assume a library constructor has no effects. Ordinary source
constructors keep the existing `EtsNew` path when no adapter claims them.

The executable example and rejection tests are in
`tests/adapter-constructors/module/ConstructorModule.kt` and
`tests/adapter-constructors/run.mjs`. This follows the official IR distinction
between `IrCall` and `IrConstructorCall`; Kotlin/JS also redirects constructor
symbols in `SecondaryCtorLowering`, while our adapter provides ETS semantics.

## External field values

Claim resolved field identities in `sourceFields`, for example
`setOf("example.NativeConstants.size")`, and implement
`lowerField(value: IrGetField, language: Language, scope: Scope)`.
Return a typed expression, or `null` to decline. Fields use the same shared
result checker as calls/constructors; `void` cannot stand in for an `Int` or
object value. Field-only modules may declare empty `sourceCalls`/`sourceTypes`.
Duplicate field claims are rejected. An instance-field implementation must
preserve receiver evaluation. Unclaimed fields and external field writes remain
explicit diagnostics; ordinary source field reads/writes are unchanged.

## External singleton values

`CallRule.lowerObject(IrGetObjectValue, Language, Scope)` adapts a resolved
external singleton reference. Claim its fully qualified type in `sourceTypes`
and return its mapped typed value, or `null` to decline. The same result checker
rejects wrong/void values. An object reference is not a constructor or UI call;
preserve singleton identity and do not introduce repeated initialization effects.
The constructor test module also exercises singleton success and rejection.

The built-in `EtsEmptyModifier` represents only Compose's empty identity value.
It may cross source helper/builder parameters and act as the base of a supported
inline modifier chain. It is not a representation of arbitrary nonempty chains;
passing those as values still diagnoses unsupported conversion rather than
silently dropping their layout or drawing behavior.
