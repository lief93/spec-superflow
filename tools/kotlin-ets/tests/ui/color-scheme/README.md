# Material3 ColorScheme values

Run `node tools/kotlin-ets/tests/ui/color-scheme/run.mjs`. It compares the
light/dark semantic baseline, explicit overrides and named, positional and mixed
calls with the actual AndroidX JVM dependency. It also generates a native Text
consumer and a separate file that only receives the ColorScheme type.

Run `node tools/kotlin-ets/tests/ui/color-scheme/modern.mjs <classpath.txt>` with
the pinned Now in Android classpath to compare all twelve fixed-color roles added
by the 48-role Material3 factory, explicit fixed-role overrides, dependent
`surfaceTint` and source-order effects. `signature.mjs` builds external test
dependencies and verifies that an unknown role or a non-`Color` role type fails
with a source location.

The shared CallRule maps resolved `lightColorScheme` / `darkColorScheme` symbols
and `ColorScheme` property getters. It binds each resolved source parameter by its
declared name and `Color` type into one 48-role target contract; it does not select
an adapter by argument count or source spelling. The 29-, 36- and 48-role AndroidX
overloads therefore share one path. Unknown roles and incompatible parameter
types fail closed. Source conditions, functions, parameters and argument
evaluation order remain in the language pipeline. Each explicit value is lowered
once. Default `surfaceTint` uses the already-evaluated `primary` value.

Omitted source roles come from the target's Material semantic baseline, pinned to
AndroidX `ColorLightTokens` / `ColorDarkTokens` and `PaletteTokens` v0_210. Static
factories never substitute project resources. The explicit dynamic/project-theme
replacement policy remains the only path that reads `kotlin_ets_material_*`.
Reference source archive:
https://dl.google.com/dl/android/maven2/androidx/compose/material3/material3-android/1.5.0-alpha03/material3-android-1.5.0-alpha03-sources.jar
SHA256: e7983f3907c0b7e13143751562bdfae3a5263f2e513bdd8531f32ebe12dd89f1

Compile the generated Page.ets with `tests/ui/basic-controls-sdk.mjs` to check
unmodified output with the actual Harmony SDK. JVM/target parity and native SDK
compilation are different gates. Theme providers, current-theme lookup,
contentColorFor fallback, dynamic system palettes and ColorScheme.copy are not
implemented by this value rule. Real Banking is not yet accepted.

Run `node tools/kotlin-ets/tests/ui/color-scheme/sdk.mjs <generated-modules-dir>`
to compile the unchanged factory and type-only consumer together. The SDK test
passes a factory result across that file boundary and verifies input hashes.
