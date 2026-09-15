# Typed Color values

Run `node tools/kotlin-ets/tests/ui/color-values/run.mjs` from the repository.
The test uses the installed official Kotlin compiler and the existing Compose
classpath probe (`KOTLIN_ETS_PROBE` can select another probe directory).

The same resolved `CallRule` maps Color types and value-producing calls in both
language and page modes. Native attributes consume those values through the
shared language lowering; they do not parse a second expression language.

Covered: source methods/parameters, object properties, multi-branch `when`,
signed Int ARGB construction, Long IR literals (including values beyond exact
JavaScript integer precision), named sRGB constants and signed `toArgb()`.
The oracle executes the actual Compose Color implementation on JVM, rather than
reimplementing its result in the test. The generated page is also suitable for
`tests/ui/basic-controls-sdk.mjs`; host parity alone is not an SDK/device test.

The effectful named-argument fixture executes generated builder methods with a
recording Text sink (excluding only the native entry layout). It asserts the
color function runs before the later text argument, and runs once. Unchanged
generated ETS is checked separately by the SDK; the sink is not a layout oracle.

Unsupported: general Long expressions (including unary `-1L` in pre-lowering IR),
wide-gamut Color construction/conversion, and Unspecified/default inheritance.
These produce failure without a plausible ETS output. This test does not claim
all boxed Color operations or all Compose color APIs are supported.

Reference: AndroidX `ui-graphics` Color.kt uses ARGB in the high 32 bits of an
sRGB Color's packed value; `Color(Long)` shifts the supplied low 32 bits and
`toArgb()` returns an Int. The target stores unsigned ARGB directly:
https://github.com/androidx/androidx/blob/androidx-main/compose/ui/ui-graphics/src/commonMain/kotlin/androidx/compose/ui/graphics/Color.kt
