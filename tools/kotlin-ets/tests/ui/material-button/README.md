# Material3 buttons

`node tools/kotlin-ets/tests/ui/material-button/run.mjs` exercises the public
compiler, Kotlin/JVM oracle and generated typed values. SDK/native evidence uses
the generated Page.ets unchanged.

Supported: Material3 Button and TextButton, ButtonColors constructors/factories,
source parameter forwarding, enabled/disabled colors and callbacks, uniform Dp
rounded shapes, LTR PaddingValues factories, default 58x40 minimum size, content
color inheritance and native interaction feedback. Default values follow
AndroidX Material3 1.3.2 Button.kt and FilledButtonTokens/TextButtonTokens.

Padding and color factory arguments retain their evaluation count/order.
Custom elevation, interaction sources and non-uniform shapes are diagnosed;
native ripple/hover feedback is not a pixel-identical Material animation port.
Dynamic layout direction and custom theme typography are not added by this test.
Source UI methods use the existing callback lowering for no-argument Unit
callbacks, so remembered-state access is not lost at business method boundaries.
The fixture uses explicit `.value` reads/writes, not delegated local state or
compound state assignments. The parent input gate avoids ArkUI's extra disabled
opacity; the inner Button's accessibility enabled flag still differs, so this
POC does not claim accessibility-state equivalence. The callback additionally
checks enabled even if invoked without normal pointer dispatch.
