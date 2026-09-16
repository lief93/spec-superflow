# Native Host Context

Compile Page.kt with the Android/Compose classpath and entry `hostcontext.Page`.
Run `node check.mjs <output.ets>` and the existing basic-controls-sdk harness.
Entry `hostcontext.Unsupported` must fail on Context.getPackageName with a source
location and without output: mapping the host is not blanket Android API support.

LocalContext.current is read synchronously during composition using the SDK's
native `getContext()`. No synthetic Context or process-global cache is emitted.
The API is deprecated since API 18 in favor of component-bound
`UIContext.getHostContext`; this POC bridge depends on ArkUI's synchronous call
chain and is not an asynchronous context lookup. Captured Context values retain
their normal object identity. CompositionLocalProvider overrides are not claimed.
