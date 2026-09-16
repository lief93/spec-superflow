# Fixed Main-Axis Spacing

The single-space `Arrangement.spacedBy` factory produces a typed spacing value.
Source helpers, parameters and local values preserve that value until native
Row/Column constructor consumption. No custom layout engine is generated.
The spacing expression is evaluated once. Alignment overloads, custom arrangement
implementations and distributed arrangements are not covered by this change.

```sh
node tools/kotlin-ets/tests/ui/arrangement/check.mjs /path/to/classpath.txt
node tools/kotlin-ets/tests/ui/basic-controls-sdk.mjs /fresh/Page.ets
node tools/kotlin-ets/tests/ui/arrangement/native.mjs /tmp/arrangement-layout.json
```

The CLI checks generation and an unsupported alignment overload. Compile and
install the unchanged generated page before the native check: it observes 8vp
horizontal gaps computed from source parameters `6 + 2`, 12vp vertical gaps and
retained sibling labels. A generated-text assertion alone is not a layout test.

Validated on 2026-09-16: public CLI positive/negative cases passed; the unchanged
ETS compiled to ABC/HAP and was installed. Device bounds confirmed both Row gaps
at 8vp and the Column gap at 12vp. Evidence: `/private/tmp/kotlin-ets-basic-controls-sdk-rNbdXp/result.json`
and `/private/tmp/arrangement-layout.json`. Banking replay r38 passed the original
spacedBy failure and next reported an unsupported Modifier receiver at
`ProgressBar.kt:182`; this is not a claim of whole-page generation success.
