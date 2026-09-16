# Named Modifier Arguments

Kotlin IR represents reordered named arguments as temporaries in a block. Modifier
consumption accepts compiler-generated immutable temporaries containing stable
reads or mapped constants, including an existing Modifier chain with stable
arguments. The aliases are scoped to that consumption. Size, background color,
shape and trailing testTag remain intact.

The frontend still owns argument binding. This is not source-string parsing or
unrestricted inlining: effectful values, mutable reads and arbitrary block
statements remain explicit failures rather than changing evaluation order.

```sh
node tools/kotlin-ets/tests/ui/modifier-named/check.mjs /path/to/classpath.txt
node tools/kotlin-ets/tests/ui/basic-controls-sdk.mjs /fresh/Page.ets
```

The positive fixture uses `background(shape = CircleShape, color = circleColor)`
after `size(circleSize)`. The negative fixture passes a function that increments a
counter; it must fail with the evaluation-order diagnostic, not silently inline it.

Validated on 2026-09-16: both cases passed, and the unchanged positive output
compiled to ABC/HAP (`/private/tmp/kotlin-ets-basic-controls-sdk-HLLopm/result.json`).
The existing four-case `modifier-arguments/run.mjs` regression also passed,
including static forwarding and dynamic/effectful operand rejection.
