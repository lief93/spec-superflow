# Empty pointer input

Run `node tools/kotlin-ets/tests/ui/pointer-input/run.mjs` against the public CLI.
The generated `Page.ets` must compile unchanged using `tests/ui/basic-controls-sdk.mjs`.
After installing and launching that HAP, run `native.mjs <evidence-directory>`.

The native assertions check both sides of the contract: an empty input overlay
blocks a lower sibling, but does not disable an interactive child. Nonempty
handlers and effectful keys are diagnosed rather than silently discarded.

Reference: Compose `PointerInputModifierNode.sharePointerInputWithSiblings` and
the ArkUI SDK `HitTestMode.Default` contract. This is not a general gesture adapter.
