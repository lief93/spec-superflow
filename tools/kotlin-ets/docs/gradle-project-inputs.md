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
  Android variant runs also record the namespace, ordered module resource roots
  and the declared runtime symbol artifact.
- `compiler-environment.json`: forwarded arguments and every intentional exclusion
  when conversion is requested; `frontend-arguments.txt` is its internal launcher input.
- `sources.txt`, `classpath.txt`: the exact lists passed to the backend.
- `gradle.command.json`, `gradle.stdout.log`, `gradle.stderr.log`.
- `compiler.command.json`, `compiler.stdout.log`, `compiler.stderr.log` when run.

These files remain local and can contain company paths, dependency names and
compiler diagnostics. Treat them as internal data; nothing is uploaded.
The manifest is a build-input inventory, not a serialized source-program IR or
replacement for `version_json.json`.

When an Android variant supplies resource inputs and no explicit
`--image-resources` override is present, project mode materializes its drawable
and mipmap images into the run directory before invoking the frontend. The same
backend publishes only used media and keeps the overlay/source provenance. See
[image resource materialization](image-resources.md). Unsupported or missing
selected image definitions remain source-linked failures and never emit ETS.

## Collection semantics and limits

The bundled Gradle init script registers an input-collection task without changing
project build scripts. It obtains sources and libraries from the selected real
Kotlin JVM compile task. Gradle resolves transitive dependencies, project outputs
and Android transformed classpath artifacts; the tool does not glob the global
cache or guess dependency versions. Android boot classpath is also included.

A completed prerequisite may legitimately emit no classes. An absent classpath
entry is omitted only when its exact path is a declared output of a completed
producer (including UP-TO-DATE/NO-SOURCE), not a disabled or failed task.
`inputs.json.omittedClasspath` records the path, producer and reason. Missing
unowned dependencies and unreadable existing inputs still fail. This rule uses
Gradle output identity, not plugin names or inferred directory layouts.

Collection runs the selected task's prerequisites so generated sources and
dependent module outputs exist, but does not execute the selected Kotlin compile
task itself. Therefore it may run generators and compile dependency modules; it
is not a read-only operation or guaranteed to be instantaneous. Configuration
cache is disabled for the init-script task. Existing project Gradle logic still
executes with normal project permissions.

This entry targets JVM/Android `KotlinCompile` tasks, not arbitrary KMP/Native/JS
compilations. All source inputs of the selected task are passed to the frontend;
after successful FIR/FIR2IR resolution, `--entry` selects the source declarations
needed by that top-level function, before ETS lowerings. No additional switch is
needed for page mode. Language mode can also use `--entry`; without it, language
mode still translates the whole supplied source module.

Selection follows resolved symbols, types, defaults, closures and all branches,
not preview values or text matching. Referenced classes retain all members. Calls
and property accesses also retain the activated file's stored non-const top-level
properties and initializer dependencies. This is conservative top-level selection,
not member-level DCE: an unsupported member of a retained class can still block
translation. An unrelated source file must still pass Kotlin resolution, and
required compiler plugins/classpath cannot be skipped before that resolution.

The compiler's stderr includes a JSON `source-selection` event with retained and
excluded declarations, source locations and first retention reasons. Project mode
keeps this in its compiler log, including when a later backend stage fails.
Dependencies on classpath are available for resolution, not automatically copied
or fully rewritten into ETS. Source ownership, binary-body coverage and framework
support remain the backend's existing bounded contracts.

### Fixed frontend compatibility and compiler plugins

Project mode captures `serializedCompilerArguments` from the real task. Compatible
plugins and options are forwarded through the official configuration/FIR/FIR2IR
phases; the exact 2.1.20 serialization plugin is one verified case. There is no
custom plugin execution engine. Ordinary language/API version, opt-ins, JVM
target/module name, JDK home and the supported semantic flags are forwarded by
`compiler-environment.mjs`. No extra command option or manually supplied plugin
JAR is required in project mode.

The backend uses the pinned Kotlin 2.1.20 frontend. Project input is compatible
when its compiler is a stable numeric version on the same `2.1` language line
and its patch is no newer than 20. Thus 2.1.20 is exact and 2.1.0 enters the same
formal frontend/lowering path; 2.0.x, 2.2.x, patches newer than 2.1.20,
prereleases and a missing project compiler version fail before compilation.
`compiler-environment.json` and every successful Core Profile report record
`projectCompilerVersion`, `frontendCompilerVersion` and
`compatibilityDecision`. Direct source input records a null project version and
`direct_source_input`.

This source/compiler decision does not bypass binary metadata validation. The
real K2 frontend reads every dependency header. Incompatible metadata emits the
official dependency diagnostic plus source resolution errors and produces no
preflight report or ETS. `-Xallow-unstable-dependencies` is excluded and recorded;
metadata compatibility-skip options are unsupported and fail closed. The
compatibility boundary downloads no compiler and rewrites no project version.

Unknown compiler arguments still fail explicitly at `compiler-environment`.
Plugin classpaths and options are forwarded to Kotlin's official loader: a
classpath can contain both plugin implementations and helper JARs, so artifact
filenames are not an implementation whitelist. Kotlin validates registration,
option ownership and compatibility. Invalid plugins/options fail in official
configuration/frontend phases, with compiler logs retained.

Gradle destination/classpath settings are replaced by the ETS entry's own paths.
Known scripting registrar JARs are excluded because collection accepts only
`.kt`/`.java`, not scripts; ordinary helper dependencies remain on the plugin
classpath. Compose JVM plugins/options are recorded as target-owned exclusions
at every compatible patch because the existing ArkUI adapter owns UI lowering.
For an older compatible patch, its serialization plugin and options are also
excluded because compiler plugins are version-coupled and the 2.1.0 plugin cannot
run in the 2.1.20 frontend. Serializer references must already resolve from source
or dependencies; otherwise normal K2 analysis fails. Other version-coupled
project compiler plugins from an older patch are rejected. Exact 2.1.20 plugin
behavior remains forwarded. All exclusions are visible in the environment report.

This reuses plugin loading, not arbitrary JVM backend execution. Plugin-generated
declarations may still hit a source-linked backend limitation.
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
  generation and function host execution still pass.
- `node --test tools/kotlin-ets/tests/project-inputs/compiler-environment.test.mjs`:
  six compatibility, plugin and fail-closed policy tests pass.
- `node --test tools/kotlin-ets/tests/project-inputs/launcher.test.mjs`: 17 tests
  pass, including incompatible compiler and same-priority image-overlay rejection
  with no report or ETS.

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

## Explicit Dependency Sources

When a dependency's implementation is needed and its binary has no usable IR body,
provide the matching upstream Kotlin/Java source using
`--dependency-sources-file /absolute/path/sources.txt`. Each nonempty line is an
absolute source-file path. This is an offline, explicit input, not an automatic
download or a replacement for classpath collection. Use the dependency's exact
version and retain its license/provenance.

The launcher preserves `inputs.json` as Gradle collected it, records the explicit
list in `dependency-sources.json`, and passes the deduplicated union in `sources.txt`
to the same official frontend and ETS backend. It does not edit the Android
project or stub missing implementations. Unsupported dependency code remains a
diagnostic; source availability alone does not guarantee successful translation.
