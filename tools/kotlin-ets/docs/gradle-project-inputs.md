# Gradle project input

The project entry collects the selected Kotlin compile task's real source and
dependency inputs, then invokes the same Kotlin/ETS compiler. It does not use the
legacy Python migration pipeline, page JSON or legacy project adapters.

## Generate a page

Run from the tool repository, with the Android project available locally:

```sh
bash tools/kotlin-ets/kotlin-ets \
  --project /absolute/path/to/android-project \
  --module :app \
  --variant debug \
  --entry sample.OnBoardingScreen \
  --out /absolute/path/to/new/OnBoardingScreen.ets \
  --work-dir /absolute/path/to/new/run
```

Use the real module and variant, including flavor names such as `demoDebug`.
`--variant demoDebug` selects `compileDemoDebugKotlin` in that module. A missing
task fails; it does not silently select another variant. Use
`--compile-task compileKotlin` instead of `--variant` for an exact JVM task or a
nonstandard task name. `--mode language` selects ordinary code translation.
`--out-dir` may replace `--out` for separate ETS source modules.

Node.js 18+, the project's Gradle wrapper/JDK/Android SDK, and the compiler
dependencies described in the main README must already be available. Gradle uses
the project's configured repositories and caches. Add `--offline` when all
necessary artifacts are cached; it cannot supply absent dependencies. The Gradle
wrapper distribution must also be available locally for fully offline use.

## Collect and diagnose first

```sh
bash tools/kotlin-ets/kotlin-ets \
  --project /absolute/path/to/android-project \
  --module :app --variant debug \
  --collect-only --offline \
  --work-dir /absolute/path/to/new/input-check
```

This does not run the ETS compiler. Successful collection proves input discovery,
not Kotlin/ETS feature support. Every run requires a fresh work directory. If
omitted, a fresh temporary directory is created and printed; it is retained for
diagnosis. Output ETS must not already exist, including user-owned files.

The run directory contains:

- `inputs.json`: source/classpath paths, compiler version and the selected task's
  serialized compiler arguments (including plugin paths/options), with provenance.
- `compiler-environment.json`: forwarded arguments and every intentional exclusion
  when conversion is requested; `frontend-arguments.txt` is its internal launcher input.
- `sources.txt`, `classpath.txt`: the exact lists passed to the backend.
- `gradle.command.json`, `gradle.stdout.log`, `gradle.stderr.log`.
- `compiler.command.json`, `compiler.stdout.log`, `compiler.stderr.log` when run.

These files remain local and can contain company paths, dependency names and
compiler diagnostics. Treat them as internal data; nothing is uploaded.
The manifest is a build-input inventory, not a serialized source-program IR or
replacement for `version_json.json`.

## Collection semantics and limits

The bundled Gradle init script registers an input-collection task without changing
project build scripts. It obtains sources and libraries from the selected real
Kotlin JVM compile task. Gradle resolves transitive dependencies, project outputs
and Android transformed classpath artifacts; the tool does not glob the global
cache or guess dependency versions. Android boot classpath is also included.

Collection runs the selected task's prerequisites so generated sources and
dependent module outputs exist, but does not execute the selected Kotlin compile
task itself. Therefore it may run generators and compile dependency modules; it
is not a read-only operation or guaranteed to be instantaneous. Configuration
cache is disabled for the init-script task. Existing project Gradle logic still
executes with normal project permissions.

This entry targets JVM/Android `KotlinCompile` tasks, not arbitrary KMP/Native/JS
compilations. All source inputs of the selected task are passed to the frontend;
`--entry` selects a page entry, not a new source-reachability pruning pass.
Other declarations in that module may still expose unsupported backend features.
Dependencies on classpath are available for resolution, not automatically copied
or fully rewritten into ETS. Source ownership, binary-body coverage and framework
support remain the backend's existing bounded contracts.

### Compiler plugins (bounded to Kotlin 2.1.20)

Project mode now captures `serializedCompilerArguments` from the real task. It
loads the captured serialization compiler plugin and forwards its `-P` options
through the official configuration/FIR/FIR2IR phases. There is no custom plugin
execution engine. Ordinary language/API version, opt-ins, JVM target/module name,
JDK home and the supported semantic flags are forwarded by `compiler-environment.mjs`.
No extra command option or manually supplied plugin JAR is required in project mode.

The backend still uses its pinned compiler version; a different collected compiler
version fails before compilation. Unknown plugin artifacts or compiler arguments
also fail explicitly at `compiler-environment`, rather than silently dropping
potentially necessary semantics. The initial artifact boundary admits the official
serialization 2.1.20 embeddable JAR; it is not arbitrary third-party plugin support.

Gradle destination/classpath settings are replaced by the ETS entry's own paths.
Scripting support is excluded because collection accepts only `.kt`/`.java`, not
scripts. The known Compose JVM plugin/options are recorded as target-owned
exclusions: Compose is handled by the existing ArkUI adapter, not rewritten into
JVM Composer calls before that adapter. This does not claim every Compose compiler
option has an ArkUI equivalent. All exclusions are visible in the environment report.

Plugin-generated declarations may still hit a source-linked backend limitation.
In particular, accepting serialization in the frontend does not implement
`KSerializer`, descriptors, encoders/decoders or generated serializers in ETS.
Plugins which mutate inputs only inside the selected task's execution actions are
not replayed: that task is deliberately not executed during collection.

## Failure handling

Configuration/collection failures return `PROJECT_INPUTS_FAILED` with a stage,
message and work directory. Inspect the Gradle logs for missing modules/tasks,
SDK setup, unresolved transitive dependencies or prerequisite task errors.
`stage: compiler-environment` identifies unsupported plugin/version/argument inputs;
the unfiltered task arguments remain available in `inputs.json`.
Compiler exit codes and JSON diagnostics are preserved in the compiler logs and
stdout. `UNSUPPORTED` identifies a backend capability gap; a Kotlin resolution
error may instead require project/compiler configuration support.
Do not report collection or generation as successful application installation.

## Plugin verification (2026-09-15)

- `tests/project-inputs/serialization/.work/run-CQjFG5/result.json`: real Gradle
  serialization compilation, missing-plugin negative and generated descriptor IR
  passed. Public conversion progresses to a source-linked external KSerializer
  heritage rejection, not a Kotlin resolution error; no ETS output is emitted.
- `tests/project-inputs/collector/.work/run-Xdv3HN/complete.json`: real JVM/Android
  inputs and compiler-environment classification passed with six rejection cases.
- `tests/project-inputs/.work/public-Pr1fhR/result.json`: plugin-free project
  generation and function host execution still pass. Policy/launcher tests: 12 passed.

## Earlier verification (2026-09-14)

- `node --test tools/kotlin-ets/tests/project-inputs/launcher.test.mjs`: seven
  parameter/path/manifest/log/no-overwrite checks passed. The Gradle failure-log
  case uses an explicit failing wrapper fixture; it is not a dependency test.
- `tests/project-inputs/collector/.work/run-bbfiNO/complete.json`: real Gradle
  collection passed with Kotlin/Java/generated sources, two transitive project
  dependencies, six rejection cases, and an Android host with 47 classpath
  entries. Selected Kotlin compile tasks did not execute; host source hashes
  remained unchanged. Tested Gradle 8.11.1, Kotlin plugin 2.1.20, AGP 8.9.3.
- `tests/project-inputs/.work/public-mpmAFk/result.json`: public `--project`
  command collected inputs and generated ETS; host execution returned
  Next/Next/Next/Explore and spacing 24 with source method/parameter names intact.
  This tests source-list ingestion, including paths with spaces, not native UI.
- `$TMPDIR/kotlin-ets-project-VNxU9B/inputs.json`: public Android `--collect-only`
  succeeded with two sources and 47 classpath entries. The initial run
  `kotlin-ets-project-vI8jSL` retained a missing-SDK configuration error; setting
  the host's actual `ANDROID_HOME` fixed that configuration, without source edits.

These focused checks do not claim that a private Onboarding page is supported.
No installation, screenshot comparison, review, commit or push was performed.
