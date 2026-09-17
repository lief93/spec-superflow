# Smart-cast subject

Run `node tools/kotlin-ets/tests/language/smart-cast/run.mjs`.

A promoted subject must keep one evaluation and one target binding. Kotlin's
frontend introduces a temporary for the `when` subject and uses it in the branch
conditions, while the branch bodies still reference the original receiver or
parameter through an implicit cast. The lowering must not leave that implicit cast
as a direct assertion between two named types: ArkTS rejects it (10505001,
"neither type sufficiently overlaps"), so the assertion is bridged through
`Object`, matching the checked-cast path. Assertions are erased at run time, so no
evaluation is added, dropped or reordered.

The fixture covers a promoted receiver (`when (this)`) and a promoted parameter
(`when (text)`), each with a data-class-like branch reading a property and a
second branch reading an `Int` and concatenating. The JVM oracle and the generated
ETS must agree on all four results, and the generated code must contain no
unbridged assertion.

Reference: Kotlin IR `IrTypeOperatorCall(IMPLICIT_CAST)` over the subject
temporary; ArkTS error 10505001.
