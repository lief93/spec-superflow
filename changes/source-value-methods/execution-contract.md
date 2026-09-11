# Source Value Methods

Approved by the user's "implement it" on 2026-09-11 after requesting preservation
of ordinary business objects and basic-type methods, not only UI snapshots.

## Scope

Add bounded, source-grounded value-method preservation to the existing page JSON
pipeline. Collect reached plain records and non-UI functions with PSI bodies and
lexically resolved calls. Preserve names, parameters, property access, local
variables, calls, branches and collection loops where their semantics are
supported. Emit ordinary ArkTS declarations in the original flattened source
modules and wire their results into native UI properties. Existing successful
resource adapters take precedence. Unsupported operations retain the selected
preview and a specific diagnostic; they are not silently converted to stubs.

This increment does not claim full Kotlin compilation, automatic service,
coroutine or navigation translation, reconstruction of all root UI state, or
preservation of arbitrary Modifier parameters. Keep these gaps explicit. Neither
generated ETS nor version JSON may be manually patched. The backend reads only
the page JSON, never Android source or executable project adapters.

## Verification

1. RED/GREEN pipeline test: a record passed through ordinary methods with a
   branch and loop produces a real function call consumed by Text.
2. Differential execution on multiple inputs; test unsupported dependencies,
   ambiguous names, numeric semantics, adapter precedence and module ownership.
3. Fresh full Contact generation, SDK build, installation and comparison, plus
   SDK verification of the new value-method fixture. Report preview and visual
   limitations separately from process success.
4. Freeze the scoped candidate for the persistent independent reviewer, then
   commit and push under the user's standing instruction.
