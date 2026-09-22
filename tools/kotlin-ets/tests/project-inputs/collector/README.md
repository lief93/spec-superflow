# Real Gradle Collector Verification

Run from `tools/kotlin-ets` with an exclusive Gradle/JVM slot:

```sh
node tests/project-inputs/collector/run.mjs
```

`COLLECTOR_ANDROID_HOST` can select another existing host with a Gradle wrapper.
The default is `/private/tmp/kotlin-ets-native-20260914-06/android`.
The runner caps Java at two processors with SerialGC, uses offline Gradle 8.11.1,
and retains every command, exit status, manifest and selected task graph.

## Verified Contract

The production init script uses the actual KGP `KotlinCompile` class hierarchy,
`getSources()`, `getJavaSources()` and `getLibraries()`. These signatures were
checked in the cached official `kotlin-gradle-plugin-2.1.20-gradle85.jar` with
`javap`, then exercised with real KGP 2.1.20 JVM and Android tasks. Android uses
AGP 8.9.3. No second plugin classloader, inferred configuration name, cache scan,
or raw source payload is used.

The root collector depends on the selected compile task's real prerequisites
and the source/library file collections' build dependencies, not the selected
compile action. File resolution occurs after those dependencies. Project
dependency compilers and Android resource/manifest prerequisites may run; this
is not a configuration-only operation. No APK packaging/install/device tests
are involved.

Sources are the actual filtered Kotlin/Java file collections, sorted and
deduplicated. Gradle's normal absence of optional source directories is not an
error. Every enumerated path must exist and be readable; classpath order is
preserved. Android application/library `bootClasspath` entries are appended
only if absent. The selected task's serialized compiler arguments are retained.
This does not collect Kotlin/Native/JS or metadata compilation inputs.

Manifest: `schemaVersion: 2`, absolute root `project`, selected Gradle `module`
and full `task` path, absolute `sources` and `classpath` arrays. Android variant
runs also include namespace, ordered module resource roots and the declared
runtime symbol file. Output must be absolute and fresh; creation uses
`CREATE_NEW` rather than overwriting.

## Evidence

Final GREEN: `.work/run-bbfiNO/complete.json`, script SHA-256
`d546111698e2a18115d60c7f70b4126db48ae5d2875badda3a77062144969561`.

- JVM: three source files (Kotlin, Java, Gradle Sync-generated Kotlin), excluded
  source absent, four classpath entries including actual `dep -> leaf` project
  class directories and Kotlin stdlib. The application deliberately contains an
  unresolved call; an independent task-graph observer rejects selected compile
  execution. Both dependency Java compilation tasks and the generator run.
- Android: two unchanged source files, 47 classpath entries including transformed
  dependency JARs and the platform `android.jar`; `compileDebugKotlin` is absent
  from the graph. The host requires `-Pandroid.useAndroidX=true`, also present in
  its earlier native verification commands. This is a caller project option,
  never silently supplied by production collection.
- Six failures: missing library, wrong task type, missing task, missing module,
  relative output and existing output. No new manifest is produced on failure.

Preserved earlier evidence: `run-dFuDwP` is only the missing-script setup failure,
not a semantic RED. `run-oIDMZP` passed JVM and all six negatives but the Android
host rejected its missing AndroidX option. No production fix was needed for that
host invocation failure.

The final `.work/run-bbfiNO/fixture` remains available for wrapper verification.
For backend generation, replace only its intentionally unresolved `App.kt` with
a supported application fixture; keep the generated source and real transitive
dependency graph. Wrapper/backend generation belongs to the main lane and is
not claimed passed by this collector test.
