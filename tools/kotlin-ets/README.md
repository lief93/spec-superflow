# Kotlin to native ETS

An independent, bounded platform-transcription implementation. It uses the
official Kotlin 2.1.20 frontend and resolved IR in memory; it does not consume
generated JavaScript or the older migration skill's page/version JSON.

This first slice is not a general Kotlin compiler or an Android compatibility
runtime. See the tests and verification reports before claiming a feature works
on a device. In particular, host-language execution is not ArkTS SDK validation.

Image/Icon and bounded URL AsyncImage support: [usage and limits](docs/compose-images.md).
Local image assets use the [materializer](docs/image-resources.md), which reuses
the old vector converter without consuming old page JSON.

## Architecture

```text
Kotlin sources + real dependency classpath
  -> K2 resolution / FIR2IR, before Compose runtime lowering
  -> selected official common passes and source-function inlining
  -> resolved declarations, types, symbols and expression bodies
  -> language lowering + standard-library call rules
  -> typed ETS target program and contract validation
  -> per-file symbol imports + ETS printer + required runtime support
  -> module behavior and SDK validation
```

| Module | Responsibility |
| --- | --- |
| `src/core/Frontend.kt` | Own official compiler lifetime and reject frontend errors |
| `src/core/Contract.kt` | Lexical symbol bindings, source diagnostics, language and call-rule interfaces |
| `src/language/` | Source methods, classes, expressions, control flow and closures |
| `src/stdlib/` | Resolved standard-library operations and necessary target helper functions |
| `src/core/Backend.kt` | Source validation and typed language-backend assembly |
| `src/target/` | Compiler-independent target tree, validation and syntax-only printer |
| `src/output/` | Source-file ownership, typed dependencies and flat module output |
| `src/ui/` | Compose controls, remembered UI state, content slots and ordered modifiers |
| `src/ui/controls/` | One file per control family, all implementing the shared call-rule contract |
| `src/core/Main.kt` | CLI, output assembly and failure handling |
| `verification/` | Separate native hosts, generation identity, builds, installation and comparisons |

Compiler IR is the source-program representation. Language lowering produces a
typed `EtsProgram`, independent of the compiler and printer. The existing Compose
adapter also produces this target tree, including controls, attributes, callbacks,
state and slots; it no longer emits a separate `UiTextModule`. The full module boundary
and outstanding work are documented in [docs/architecture.md](docs/architecture.md).
The four development lanes share [these fixed interfaces](docs/shared-contracts.md).
Diagnostics may be serialized to JSON, but serialized JSON is not a compiler
input. The old Python implementation remains independent and unchanged by this
module. Its adapters are not automatically loaded here.

See [Compose basic controls](docs/compose-basic-controls.md) for current control
coverage, supported parameters, explicit limitations and focused test commands.

## Run

For an existing Android/Gradle project, use the project input entry instead of
listing source files and dependency JARs manually:

```sh
bash tools/kotlin-ets/kotlin-ets --project /absolute/path/to/android \
  --module :app --variant debug --entry sample.Page \
  --out /absolute/path/to/new/Page.ets
```

It collects the real Kotlin compile task inputs via the project's wrapper, then
invokes this same backend. `--collect-only` checks input discovery without ETS
generation. See [Gradle project inputs](docs/gradle-project-inputs.md) for offline
use, prerequisite tasks, retained logs and scope limitations. This entry requires
Node.js 18+ in addition to the compiler prerequisites below.

Page mode defaults to reporting explicitly approved animation/system projections.
Unknown UI calls, modifiers, business calls and display arguments still require
adaptation; report mode does not permit deleting them. It writes
`<output>.diagnosis.json` with omissions and any blocking failure. A
`generated_with_degradations` result is not equivalence success. Required values,
unknown conditions and claimed-adapter failures remain blocking. Use
`--unsupported-policy error` for strict page generation; language mode is always
strict. See [recovery boundaries and tests](tests/ui/degradation/README.md).
An explicit exception replaces Android-version-dependent MaterialTheme color
configuration with the current native project palette, without removing its
content. Configure the consumed `kotlin_ets_material_*` resources before running
the generated app; this is a reported theme replacement, not equivalent Android
version emulation. See [theme projection](tests/ui/theme-projection/README.md).
For the animation-excluded POC, Float Animatable values can use their explicit
initial value while animation-only effects are reported and skipped. This does
not disable ordinary page state or interactions. See [static animation projection](tests/ui/static-animation/README.md).

From the repository root, with a fresh output path:

```sh
bash tools/kotlin-ets/kotlin-ets --mode language \
  --out /tmp/LanguageSlice.ets tools/kotlin-ets/tests/language/LanguageSlice.kt

bash tools/kotlin-ets/kotlin-ets --mode language \
  --out-dir /tmp/new-ets-modules \
  tools/kotlin-ets/tests/modules/Model.kt \
  tools/kotlin-ets/tests/modules/Numbers.kt \
  tools/kotlin-ets/tests/modules/Entry.kt

bash tools/kotlin-ets/kotlin-ets --mode page --entry sample.Page \
  --classpath-file /absolute/path/compose-classpath.txt \
  --out /tmp/Page.ets tools/kotlin-ets/fixtures/Page.kt
```

`--classpath-file` contains one existing JAR or class directory per line. It must
describe the source project's actual dependencies, not replacement Compose stubs.
`--classpath` accepts the platform-separated equivalent. Additional positional
arguments supply additional Kotlin source files.

Language mode accepts either `--out` or `--out-dir`, never both. The latter keeps
source basenames in a flat directory and adds symbol-based relative imports.
Existing destinations and colliding basenames are rejected, not overwritten or
silently renamed. See [docs/module-output.md](docs/module-output.md).

The launcher uses the existing Gradle cache under `GRADLE_USER_HOME` or
`~/.gradle`. It requires Kotlin compiler-embeddable, stdlib, script-runtime and
daemon-embeddable 2.1.20; kotlin-reflect 1.6.10; trove4j 1.0.20200330;
kotlinx-coroutines-core-jvm 1.8.0; and annotations 13.0. It does not download them.
`JAVA_HOME` overrides the default Android Studio bundled JDK. The validated JDK
is 21, and the frontend uses JVM target 17 for dependency analysis. Compiler
internal interfaces are version-sensitive; changing the version requires replay.

Each invocation compiles the small tool into a private temporary directory,
emits the requested target, then removes that temporary tool build. Existing
output paths are rejected. Exit 1 reports frontend/configuration failure; exit 2
reports an unsupported source operation or invalid target with file and offsets.
Its `source` also includes `line`, `column`, `endLine` and `endColumn` (1-based;
the end is exclusive). Columns use UTF-16 units, like Kotlin PSI offsets, after
BOM removal and LF/CRLF/CR normalization. Invalid ranges or unreadable source
files keep the original offsets and return `null` coordinates. Neither case
publishes a new target file.

## First-slice boundaries

- Ordinary methods and model classes retain meaningful source names and calls.
  Target helpers are reserved under `__ets`; source collisions are rejected.
- Conditions and arithmetic remain expressions. A preview's initial page does
  not remove other pages or state updates.
- The UI slice supports the fixture's Column/Row/Box/Spacer/Text/Button/Pager,
  root remembered scalar state, pager events and zero-argument UI content slots.
- Ordinary dp values map to vp and text sp to the target text-size convention.
  Custom density, pixel measurement and unsupported modifier forms are rejected,
  not flattened into guessed numbers.
- The coroutine mapping is deliberately limited to the recognized remembered
  UI scope and pager scroll operation; it is not general coroutine translation.
- Unknown library calls, external effects and unsupported parameters fail with
  source-linked diagnostics. No automatic blank UI or invented default values.

Detailed supported and rejected language/library cases are documented beside
their tests. This slice does not establish compatibility for arbitrary business
libraries, inherited classes, network calls, services or all Compose APIs.
Common Float/Double arithmetic and conversions share the typed language path;
see [docs/numeric-lowering.md](docs/numeric-lowering.md) for JVM precision rules,
focused tests and explicit limits.
The previous backend increment added bounded generics, explicit-source library
inlining and multi-file output; see
[docs/modules-generics-inline-batch.md](docs/modules-generics-inline-batch.md).
Named local functions now use official declaration lifting and shared-variable
analysis with typed ETS cells. The ownership, tests and remaining boundaries are
in [docs/local-declarations.md](docs/local-declarations.md).
The first parallel increment added bounded official Int for-loop lowering,
typed collection filtering and stricter multi-file linking; its historical results
are in [docs/parallel-batch-20260914.md](docs/parallel-batch-20260914.md).
Checked serialized JVM inline bodies now have a bounded production path; see
[docs/binary-bodies.md](docs/binary-bodies.md). The target-tree continuation and
current integration evidence are tracked in [docs/typed-ui-integration.md](docs/typed-ui-integration.md).

## Verify

```sh
python3 -B tools/kotlin-ets/tests/integration/test_cli.py
bash tools/kotlin-ets/tests/target/run.sh
node tools/kotlin-ets/tests/language/run.mjs
bash tools/kotlin-ets/tests/stdlib/check-symbols.sh
bash tools/kotlin-ets/tests/stdlib/check-public-cli.sh
node tools/kotlin-ets/tests/ui/run.mjs
```

Some test harnesses use locally installed SDK/compiler paths; their own READMEs
state those prerequisites. Native page commands and fixed comparison tolerances
are in [verification/README.md](verification/README.md). The fixture includes
four pages, a last-page button, state callbacks, computed spacing and nested
content slots. Generated ETS is copied to the native host without hand edits.

Independent acceptance and remaining gates are recorded under
`artifacts/ui-program-transcription-manager-20260913/native-ets-acceptance.md`.
Until those gates pass, successful generation or installation alone is not
whole-page acceptance.
