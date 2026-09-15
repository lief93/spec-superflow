# Material3 Surface foundation

`node tools/kotlin-ets/tests/ui/surface/run.mjs` exercises the public compiler.
It verifies the emitted measurement callbacks and rejects unsupported theme
defaults, elevations, interactive overloads and direct effectful color calls.
Supported colors are stable sRGB values (including parameters and source val
bindings). Shape, border, elevation and theme-dependent defaults are not guessed.

The CallRule emits typed ArkUI nodes. A scoped `WithTheme` supplies Material Text's
content color; BasicText retains its independent default black. The fixed layout
uses top-aligned text content, and BasicText's default font size is 14sp as defined
by AndroidX SpanStyle. Neither is inferred from the test page's labels. The layout
runtime propagates parent minima, and tracks axes fixed by source modifiers
because ArkUI supplies explicit component sizes as maxima to custom measurement.
Source modifiers retain their layers; no generated output is patched.

Compile generated Page.ets with `tests/ui/basic-controls-sdk.mjs`, install its HAP,
then capture `hdc shell uitest dumpLayout -a -b com.joker.kit`. Verify the downloaded
JSON with `native.mjs <layout.json> <device-pixels-per-vp>`. If font attributes are
absent immediately after launch, capture again after the first rendered frame.
Native compilation, node assertions and screenshot comparison are separate gates.

Compile and install the generated TouchPage.ets, then run
`node tools/kotlin-ets/tests/ui/surface/touch-native.mjs <evidence-directory>`.
It taps the child button and the blank Surface area over a second button,
verifying the child updates and the underlying button does not. Merely checking
the hit-test enum is not interaction evidence. Mutable global color reads are
negative cases, while immutable source snapshots may pass through builder parameters.

References:
- AndroidX Material3 1.3.2 `Surface.kt`: non-interactive Surface uses a Box with
  `propagateMinConstraints = true`, background, clipping and pointer input.
- OpenHarmony `ts-custom-component-layout.md`: measurement callbacks and vp sizes.
- OpenHarmony `arkts-builderparam.md`: builder initialization and the restriction
  on fluent attributes after custom-component trailing content closures.
- OpenHarmony `ts-container-with-theme.md`: scoped native theme propagation.

This increment does not complete real Banking migration: its omitted contentColor
requires MaterialTheme/contentColorFor, followed by other source dependencies.
