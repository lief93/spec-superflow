# Source Modifier arguments

Run `node tools/kotlin-ets/tests/ui/modifier-arguments/run.mjs` with the local
Compose compiler classpath fixture available.

Closed Modifier chains are compile-time UI programs. Their source builders get
deduplicated `_ModifierN` specializations, with only those Modifier parameters
removed; ordinary parameters and source method/file ownership remain intact.
Plain identity Modifier calls keep the existing signature and helper effects.
This is not first-class support for dynamic or effectful Modifier factories.
Those inputs must fail without publishing an output, rather than becoming empty
modifiers. `then` preserves the ordered chain across nested source calls.

The fixture covers forwarding, equal-chain reuse, different-chain variants,
mixed identity/static calls, and dynamic/effectful rejection. The existing
`empty-modifier` fixture separately checks identity and helper evaluation counts.
