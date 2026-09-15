# Typed logical alignment values

Run `node tools/kotlin-ets/tests/ui/alignment/run.mjs`, compile its unmodified
Page.ets using `tests/ui/basic-controls-sdk.mjs`, then install the HAP and run
`native.mjs <dumpLayout.json> <pixels-per-vp>` in an LTR host.

One resolved-symbol CallRule maps Alignment, Horizontal and Vertical constants.
Source methods, arguments and conditions use the shared language pipeline; the
three layout controls consume those typed values. Native logical Start/End are
retained rather than replaced by Left/Right. The native test checks two cross-axis
positions and all nine Box positions, not just the emitted names. Host RTL and
mixed layout-direction overrides are not certified by the LTR test.

Custom/BiasAlignment and Arrangement algorithms are not guessed. This increment
does not add per-child alignment overrides or Box minimum-constraint propagation.

An unknown alignment call/read combined with an unstable modifier is diagnosed,
not silently reordered. Order.kt reproduces the width/alignment side effects for
all three controls and checks the supported once-bound source-val form.
