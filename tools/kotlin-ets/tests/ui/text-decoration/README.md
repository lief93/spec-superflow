# Native text decoration

Compile Page.kt with entry decoration.Page, then run `check.mjs <Page.ets>`.
The check executes the generated ordinary style adapter against a recording
TextAttribute and verifies inherited Underline, explicit None/LineThrough and
resolved font-color precedence. Pass the same generated file to
`tests/ui/basic-controls-sdk.mjs` to validate the real ArkUI decoration contract.

Entry decoration.Combined must fail without output: combined decorations are
not silently replaced by one line. Rendering is native, not custom drawing.
