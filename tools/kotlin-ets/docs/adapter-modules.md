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

Each `AdapterTargetCall(id, name, signature)` declares a module-owned target
signature. `AdapterTargetApi.call` looks it up by ID and checks exact arity.
The shared target validator checks argument types and target bindings, including
ordinary inheritance. Never bypass validation with raw printed expressions or
invent source symbols. Use `language.expression`, `language.source`, resolved
arguments and existing typed constructors.

### Factory lifecycle

SPI instantiates providers once per compiler process. A registry calls
`create(target, null)` for ordinary value/effect/type rules. These delegates may
handle `lower`, `lowerStatement`, and `mapType`, but not UI dispatch.

Compose conversion separately calls `create(target, scopedUi)` for UI-only
delegates. These handle `lowerUi`; ordinary operations are not dispatched again.
Factories can be called more than once: keep scoped UI services in the returned
rule, not in global mutable state. Do not assume a single UI factory instance or
reuse one scope's services in another.

`ui.content(expression, scope)` delegates content conversion and
`ui.decorate(modifier, scope, element, boundaries)` delegates existing modifier
semantics. An explicit source call claim gets an opportunity before structural
business-component conversion and built-in controls. Returning `null` means the
rule did not handle the call; it is not an empty UI substitute.

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
module-local `Column`/`Text` signatures without editing central ArkUI APIs.
All three arguments must be explicit. In particular, an omitted `modifier`
rejects at the source call, even if the Kotlin declaration provides a default.
This finite example does not evaluate Kotlin default expressions and must not
silently replace a default such as `Modifier.width(120.dp)` with no modifier.

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

The CLI snapshot manifest contains hashes for all production sources, module
descriptors and fixtures, with live/snapshot equality checked. Main API/wiring
hashes in that proof begin `bf8611261237` (AdapterModules), `b89235b41246` (Main),
and `21b9ec74b872` (ComposeLowering).

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
