# Compose File Initialization

Compile State.kt, Page.kt, Other.kt and Failure.kt with entry `uiinit.Page` and the Compose
classpath, then run `node check.mjs <output.ets>` and the existing
`tests/ui/basic-controls-sdk.mjs <output.ets>` harness.

The checker executes the generated ordinary declarations and builder method
bodies with a native Text recorder. It verifies lazy initialization without a
property read, declaration order, repeat rendering, initialization before
default argument evaluation, and first/subsequent initialization failures.
SDK compilation separately validates the unchanged generated ArkUI conditions.
The bridge delegates to the language layer's existing JVM file guard; it does
not eagerly initialize every file in a component lifecycle callback.

Compile State.kt and Remember.kt with entry `uiinit.RememberPage`, then run
`node remember-check.mjs <output.ets>` and the SDK harness. This executes the
generated component field initializers and verifies file initialization before
remembered-state side effects, including failure before the state is initialized.
