# Material3 Typography

`node tools/kotlin-ets/tests/ui/typography/run.mjs` exercises the public compiler,
compares all 15 default role metrics with AndroidX 1.3.2 on Kotlin/JVM, checks a
custom constructor and source parameter/getter, and compiles nested MaterialTheme,
Surface, Button and source content slots. It also evaluates the generated typed
Text consumer to verify explicit override precedence and inherited metrics/color.

Pass the generated Page.ets to `tests/ui/basic-controls-sdk.mjs` for native SDK
validation. Platform font rasterization/default family differences are not claimed
to be identical. Typography copy, custom Shapes and arbitrary LocalTextStyle
providers remain outside this requirement.
