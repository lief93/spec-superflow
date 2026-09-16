# Explicit projections, not unknown UI omission

Page generation defaults to `--unsupported-policy report`, including the
`--project` launcher. Use `--unsupported-policy error` for strict conversion.
Language mode remains strict and rejects report mode.

The generated target has a sibling `<output>.diagnosis.json`, also when a later
compiler failure blocks output. For `--out-dir`, the report is alongside that
directory, not mixed into generated source files. Existing reports are never
overwritten. Argument validation failures before an output is selected and
Gradle collection failures keep their existing CLI diagnostics/logs.

The report records source file, line/column and offsets, resolved capability,
omission action and impact. `generated_with_degradations` means usable candidate
output, not semantic or visual equivalence. `blocked` includes the blocking
failure and omissions recorded before it. Counts are diagnostic occurrences,
not a complete pre-scan of every unsupported dependency.

Recovery boundaries:

| Situation | Behavior |
| --- | --- |
| Unsupported Text/BasicText argument | Block until the argument has a target mapping |
| Unknown resolved Modifier operation | Block until layout, drawing or input behavior is adapted |
| Unclaimed external Unit call in UI position | Block; never discard callbacks or nested UI to produce output |
| Explicit static animation projection | Retain the initial value and UI; report omitted animation-only effects |
| Required value, unknown condition, source helper failure | Block; never fabricate values or choose branches |
| Claimed adapter rejects an argument, frontend error, invalid target | Block; no broad exception suppression |

This is deliberately not general Kotlin error recovery. Being outside Compose
does not itself make an API safe to skip. Business and third-party calls remain
required. Android platform-only effects need an explicit projection; UI-critical
resources, density, measurement and Insets still need target implementations.
`Build.VERSION.SDK_INT` used as a condition/value still requires a supported
translation or proven specialization. It is not replaced with an invented number.
Compiler temporaries used exclusively by approved projections can be removed
along with their evaluation. This does not authorize skipping unknown arguments.
Explicit source locals are retained, except a private immutable Modifier whose
consumers are all explicitly projected away:
its construction and argument evaluation are separately reported and discarded.
A Modifier shared with retained UI still propagates its original failure; it is
never substituted with an empty value.
The bounded [native project-theme projection](../theme-projection/README.md) is
an explicit exception: Android-version-dependent MaterialTheme color setup and
SideEffect-only guards in that projected function can discard their private
immutable local dependencies. Shared UI values and conditions still block.
An unsupported temporary type is kept as source IR until consumer analysis;
it is not replaced with a made-up ETS type. Any surviving consumer still fails.

Run the public CLI regression with a real Android/Compose classpath:

```sh
node tools/kotlin-ets/tests/ui/degradation/check.mjs /absolute/path/classpath.txt
node tools/kotlin-ets/tests/ui/degradation/named-arguments.mjs /absolute/path/classpath.txt
node tools/kotlin-ets/tests/ui/degradation/modifier-local.mjs /absolute/path/classpath.txt
```

These tests require unsupported controls, modifiers and arguments to report a
blocking source diagnostic and emit no ETS. In particular, AnimatedVisibility
must not lose its content just because animation effects are excluded.
The clean page remains a positive generation case. Static animation and native
theme projections have separate positive tests in their own fixture directories.
No diagnostic-only test establishes native rendering equivalence.

## Required-UI policy verification (2026-09-16)

- Public rejection/clean-output/report-ownership cases: `kotlin-ets-degradation-XnWTnm`.
- Named arguments and unsupported content: `kotlin-ets-degradation-named-Porqal`.
- Private/shared conditional modifiers: `kotlin-ets-modifier-local-4zcCvV`.
- Animation-only effects, business-effect protection and unrelated static layers:
  `kotlin-ets-static-animation-NTHi46`.
- Native theme projection and mixed business-effect protection:
  `kotlin-ets-theme-projection-JvO15v`.
- Referenced overloads, virtual dispatch and implicit Map key methods:
  `kotlin-ets-data-members-f8JacK`; existing flat/module JVM equivalence and
  initialization tests: `kotlin-ets-source-selection-Uaa7Xb/result.json`.

These evidence directories are under the host temporary directory. The unchanged
Banking replays r47/r48 now correctly block on `ErrorFullScreen.kt:53`,
`androidx.compose.foundation.layout.BoxWithConstraints`, instead of deleting its
content. The page is not yet generated or visually validated under this policy.
