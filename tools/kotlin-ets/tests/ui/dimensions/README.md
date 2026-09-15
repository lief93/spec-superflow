# Shared dimension values

`node tools/kotlin-ets/tests/ui/dimensions/run.mjs` checks the typed source-value
path and JVM parity using the actual Compose unit library. It includes values
which distinguish Float32 from JavaScript Number. Compile emitted Page.ets with
`tests/ui/basic-controls-sdk.mjs` without patching it.

Dp and sp TextUnit scalars retain source parameter and method names. Native layout
numbers are vp; Text.fontSize numbers are fp. There is no px conversion or invented
density context. Source immutable value bridges preserve single evaluation;
modifier sequencing restrictions still apply. Em, Unspecified, density operations
and other not-yet-adapted unit operations are not claimed as supported.

Symmetric padding evaluates dynamic horizontal/vertical arguments once through a
typed ordinary helper, not twice for opposite edges. The test executes emitted
builder methods with a stub only for the empty native Stack node; the actual SDK
test validates the unchanged DSL separately. Source-val padding is a control case.

Reference: AndroidX ui-unit 1.7.6 source Dp.kt/TextUnit.kt getters use toFloat for
Int/Double receivers. The target uses Math.fround, matching the existing numeric
backend convention rather than a second runtime number implementation.
