# Invocation-scoped Material colors

`node tools/kotlin-ets/tests/ui/material-theme/run.mjs` generates Page.kt through
the public compiler, compares the emitted content-color lookup against AndroidX
JVM (including matching precedence and fallback), and tests unsupported forms.
Compile its Page.ets unchanged with `tests/ui/basic-controls-sdk.mjs`, install the
HAP, then run `native.mjs <dumpLayout.json> [same-run.png]`. PNG checking covers
text nodes for which the native inspector omits FontColor; set
KOTLIN_ETS_NODE_MODULES to a directory containing pngjs outside Codex.

Theme contexts are immutable owned target values, passed through source builders
and WrappedBuilder slots. Slot invocation supplies the context; lexical capture
does not freeze the provider. MaterialTheme inherits an omitted color scheme;
Surface changes content color, using ordered AndroidX contentColorFor matching.
Unknown backgrounds inherit the parent's content color. No mutable global theme
stack, permanent preview substitution or generated-code patch is used.

This increment supports color lookup, Text and rectangular zero-elevation Surface.
Explicit typography/shapes, system palettes, value-returning composable helpers
and the receiver-based ColorScheme.contentColorFor extension (which can return
Unspecified instead of using the ambient fallback) remain unsupported. The
receiver-free composable contentColorFor call is tested through source dispatch.
Theme-dependent Button/Checkbox/Switch/default-divider colors also produce explicit
diagnostics. This does not certify a full Material theme implementation. Platform
control appearance, ripple and selection behavior need their own adapters.
