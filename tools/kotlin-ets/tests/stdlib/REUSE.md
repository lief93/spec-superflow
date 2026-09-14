# Official lowering reuse findings

Read-only sources are cached under
`artifacts/kotlin-js-official-prototype-20260913/official-backend/`. Their SHA-256
values match index.json's Kotlin v2.1.20 records:

- JsLoweringPhases.kt: `06a16a7c77cdccf0fbcdd91e2a0649d4990b4392570a0ae4cb0b7ae78a1602de`.
- lower/calls/NumberOperatorCallsTransformer.kt:
  `e61de2322f6a2a24716556b0b91c3da109ef1e114863745e117abcf3d844d763`.

## Arithmetic and target nodes

NumberOperatorCallsTransformer constructs Kotlin IR calls to JS intrinsic
symbols through JsIrBackendContext, its intrinsics, and JsIrBuilder. Its useful
semantic decisions include result-sensitive Int wrapping, Int multiplication via
jsImul, and eager Boolean and/or/xor via bit operations followed by Boolean
conversion. These inform typed node composition, but the transformer does not
produce EtsExpression nodes and is not a drop-in implementation of CallRule.
Its range and mixed-Long paths depend on additional runtime symbols and sometimes
mutate call arguments. They are not introduced by this migration.

Preserving this slice's existing JVM-tested divide-by-zero behavior requires its
pinned helpers. The cached numeric transformer routes division/remainder through
JS intrinsics and Int coercion; reading that source alone does not establish
equivalence to the verified helper's exception behavior.

## Scope functions and library bodies

JsLoweringPhases wires FunctionInlining to JsInlineFunctionResolver with a backend
context. Private/all-function inlining and validation precede later loop and call
lowering. This is evidence of a body-resolution and normalization pipeline, not
an API-name rewrite recipe. Reusing inline bodies for let/run/also/apply/with or
collection functions requires the integration owner to establish available
library bodies, dependency symbols, return-target handling, and phase ordering
for the actual input module. That availability has not been demonstrated here.

ForLoopsLowering is imported from backend.common, so common normalization passes
are candidates to investigate at the core boundary. In this JS phase list they
still run with a JsIrBackendContext and surrounding prerequisites; standalone
reuse on the current JVM-resolved module is not proven by this inspection.

No scope-function rewrites, guessed library-body expansion, or new map/filter/
repeat/let support was implemented. Existing bounded list map behavior is retained
through its typed runtime-helper call. Core owns any future official lowering
pipeline integration; this worker owns only stdlib rules and tests.
