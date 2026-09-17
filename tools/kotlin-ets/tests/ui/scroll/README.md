# Native scrolling

Run `node tools/kotlin-ets/tests/ui/scroll/run.mjs` from the repository root.
The fixture goes through the public Kotlin frontend and typed ETS backend.
Compile its emitted `Page.ets` unchanged with `tests/ui/basic-controls-sdk.mjs`.

The supported slice keeps zero-initialized, modifier-only scroll offsets inside
native Scroll. It preserves Modifier ordering, vertical/horizontal axes,
conditional scroll containers and enabled=false. State reads/commands, nonzero
initial values, reverse scrolling and custom fling behavior are not silently
approximated. They remain diagnostics.
