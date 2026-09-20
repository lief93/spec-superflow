# Native Focus Manager

Compile Page.kt with the Android/Compose classpath and entry `focusmanager.Page`.
Run `node run.mjs` against the public CLI, then `node check.mjs <output.ets>`
and the existing basic-controls-sdk harness.

Entry `focusmanager.Unsupported` must fail on FocusManager.moveFocus with a
source location and without output: mapping the host is not blanket focus API
support. Entry `focusmanager.SoftClear` must fail on `clearFocus(false)`; only
the default `force=true` argument is claimed.

`LocalFocusManager.current` is an opaque composition value. `clearFocus()`
delegates to the native `UIContext` captured in `aboutToAppear`, then
`FocusController.clearFocus()`. CompositionLocalProvider overrides and
FocusRequester/moveFocus are not claimed.
