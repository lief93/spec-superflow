# UI source/CLI tests

Run `node tools/kotlin-ets/tests/ui/run.mjs` from the repository. The runner prints
a fresh temporary evidence directory containing argv, exit codes, diagnostics,
JVM outputs, and generated ETS. It uses the public CLI for each translation.

Prerequisites are the existing official Kotlin 2.1.20 compiler dependency manifest
and Compose classpath at `/tmp/kotlin-official-frontend-probe-06`, the actual
Compose 2.1.20 compiler plugin, and the installed Harmony SDK TypeScript library.
`KOTLIN_ETS_PROBE` and `JAVA_HOME` can select equivalent installed paths. The
classpath JSON is converted once to newline paths before invoking the CLI.
Pass `--typed-exit-only` to run just the public-CLI `--out` and `--out-dir`
typed-boundary traces without the broader UI semantic assertions.

The real fixture compiles with Compose on JVM. Its ordinary methods then run on
JVM and in generated target code with matching values for 0, 1, 2, 3, 2. Further
source cases cover renamed methods/state and changed defaults, modifier ordering,
single evaluation of both used and unused effectful local initializers, and
source-linked rejection without output for unsupported APIs/arguments.

`ComposableValues.kt` exercises a pure `@Composable` String-returning helper
through the public CLI and executes the emitted function. Only annotated Unit
functions become UI builders; unsupported runtime reads still fail closed.
`MaterialText.kt` checks body/label typography across named wrappers and slot
invocation, explicit font-size overrides, and restoration after Button content.
Custom providers and conflicting call-site text contexts are rejected.
`TouchTargets.kt` varies the actual source dimensions/count and tests emitted
nearest-target dispatch against independently probed center/overlap points.
Unbounded clickable topology is rejected, not silently assigned native hit rules.
ModifierOrder retains both ordered chains in isolated one-item groups separated
by 48dp so cross-group expanded target competition is outside that test.

Generated hierarchy assertions are supplementary. Real ArkUI compilation, native
slot rendering, pager/callback interaction, geometry, and touch bounds belong to
the verification owner. No device or host operation runs from this test suite.

`node tools/kotlin-ets/tests/ui/model-composition/run.mjs` is a separate focused
suite for ordinary models consumed by Compose. It checks the typed target tree,
public CLI output and actual lowered callback replay against a JVM oracle. This
host-only projection is not native rendering or reactive-state acceptance; see
`../../docs/model-composition.md` for scope and evidence.
