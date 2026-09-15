# Compiler plugin input acceptance

Status: the bounded serialization frontend integration passed tests and self-check.
Independent review remains deferred. Private project execution was not performed.

## Change

The Gradle collector uses KotlinCompile.serializedCompilerArguments and records
the compiler version. Project mode preserves supported semantic arguments and
serialization plugin options, then hands them to the existing official Kotlin
configuration/FIR/FIR2IR pipeline. No custom plugin loader or generated ETS patch.
Every intentional exclusion is recorded; unhandled plugin/version/argument inputs
fail in the compiler-environment stage with the original inputs retained.

Official implementation references inspected locally:
- KGP 2.1.20 AbstractKotlinCompileTool.getSerializedCompilerArguments.
- Kotlin AbstractConfigurationPhase.loadCompilerPlugins and PluginCliParser.
- Kotlin JvmFir2IrPipelinePhase and CommonCompilerArguments.pluginOptions.

## Verification

| Check | Result and local evidence |
| --- | --- |
| Parameter policy and existing launcher | 12 tests passed: `node --test tools/kotlin-ets/tests/project-inputs/compiler-environment.test.mjs tools/kotlin-ets/tests/project-inputs/launcher.test.mjs` |
| Real serialization project | `tests/project-inputs/serialization/.work/run-CQjFG5/result.json`; original Gradle compilation succeeds, no-plugin analysis reproduces missing descriptor, captured plugin generates descriptor getter IR |
| Public project entry with serializer | Same run: passes resolution, reaches a source-linked backend UNSUPPORTED at Model.kt:8 for external KSerializer heritage; no target file emitted |
| Real Gradle JVM/Android collection | `tests/project-inputs/collector/.work/run-Xdv3HN/complete.json`; generated sources, transitive modules, compiler settings, Android boot/transformed classpath, six closed boundaries; selected compile action absent |
| Plugin-free public generation | `tests/project-inputs/.work/public-Pr1fhR/result.json`; real project collection, ETS output and host execution of original-name buttonLabel/pageSpacing functions passed |

Evidence paths above are relative to `tools/kotlin-ets`. Serialization acceptance
records 77 compiler/configuration/source hashes and verifies them unchanged across
the run. All run directories are generated local evidence, not committed outputs.

Reproduction:

```sh
node tools/kotlin-ets/tests/project-inputs/serialization/run.mjs
node tools/kotlin-ets/tests/project-inputs/collector/run.mjs
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/project-inputs/project-run.mjs
```

These fixture runners use the existing local Gradle wrapper host and cached
dependencies; COLLECTOR_ANDROID_HOST overrides the wrapper/Android fixture host.

## Boundaries and operator action

- Re-run the original `--project` command after updating the tool. Use a fresh
  work/output path as before. No manual plugin JAR or extra enabling flag needed.
- Kotlin 2.1.20 serialization is the admitted semantic plugin, not all compiler
  plugins. The known Compose JVM plugin is excluded because ArkUI lowering owns
  that framework conversion; this is recorded, not a claim of JVM Compose parity.
- Serialization-generated IR is not yet a supported ETS serialization runtime.
  The current fixture reaches the explicit external-interface heritage boundary.
  An exploratory @Serializable model also reached the existing nested generated
  declaration limitation (`serialization/.work/run-Dcxjfg/with-plugin.stderr`).
  Neither diagnostic is repaired by dropping classes or inserting default values.
- Source arguments mutated only in the selected task's execution actions cannot
  be replayed by an input-only collector. Unknown flags fail explicitly.
- No native device/SDK/visual result is claimed for this frontend integration.
