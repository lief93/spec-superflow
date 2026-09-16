# Long model values

Run `node tools/kotlin-ets/tests/language/long-values/run.mjs` for JVM versus
generated ETS host execution. It covers values beyond 2^53, both signed 64-bit
limits, field/parameter/return transport, interpolation and negation overflow.

`Page.kt` is the native SDK consumer: generate it with `Values.kt` and a real
Compose classpath, then pass its unedited ETS to `tests/ui/basic-controls-sdk.mjs`.

The ETS representation is native `bigint`, not floating point. Negation uses
`BigInt.asIntN(64, ...)` to retain Kotlin overflow. This follows the official JS
backend's separation of Long from ordinary number operators; it does not reuse
the JS Long runtime. General Long arithmetic, hashing and conversions remain
unsupported instead of silently applying number semantics.
