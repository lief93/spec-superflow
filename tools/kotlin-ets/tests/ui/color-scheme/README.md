# Material3 ColorScheme values

Run `node tools/kotlin-ets/tests/ui/color-scheme/run.mjs`.
It compares 36 light and 36 dark roles plus six override/evaluation-order results
with the actual AndroidX JVM dependency. It also generates a native Text consumer
and a separate file that only receives the ColorScheme type.

The shared CallRule maps resolved `lightColorScheme` / `darkColorScheme` symbols
and ColorScheme property getters. Source conditions, functions, parameters and
named-argument evaluation order remain in the language pipeline. One owned typed
target class represents the immutable role fields. The shared adapter declaration
link runs before validation; module output imports that class instead of declaring
a different nominal type in each file. Default surfaceTint is computed
from the already-evaluated primary argument, not a duplicated expression.

Defaults are pinned to AndroidX Material3 1.3.2, ColorLightTokens/ColorDarkTokens
and PaletteTokens v0_210. A different factory signature is rejected. This does
not certify the defaults of every Material3 version with the same signature.
Reference source archive:
https://dl.google.com/dl/android/maven2/androidx/compose/material3/material3-android/1.3.2/material3-android-1.3.2-sources.jar
SHA256: e58d105a4fcf1f65a6b2838ca8a6fe40b5784b5dba9ddcf27aabcdfc92b3e4e2

Compile the generated Page.ets with `tests/ui/basic-controls-sdk.mjs` to check
unmodified output with the actual Harmony SDK. JVM/target parity and native SDK
compilation are different gates. Theme providers, current-theme lookup,
contentColorFor fallback, dynamic system palettes and ColorScheme.copy are not
implemented by this value rule. Real Banking is not yet accepted.

Run `node tools/kotlin-ets/tests/ui/color-scheme/sdk.mjs <generated-modules-dir>`
to compile the unchanged factory and type-only consumer together. The SDK test
passes a factory result across that file boundary and verifies input hashes.
