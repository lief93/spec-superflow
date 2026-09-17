# Parent constraints

Run `node tools/kotlin-ets/tests/ui/constraints/run.mjs` from the repository root.
Compile its emitted `Page.ets` unchanged with `tests/ui/basic-controls-sdk.mjs`.
After installing and launching that HAP, run `tests/ui/constraints/native.mjs`
with an evidence directory argument.

The native assertions check a 120-to-240 vp parent resize, the child width,
conditional content, and captured text changes without a resize. Native
FrameNode measurement supplies constraints and BuilderNode updates the existing
content; measurement does not mutate a component's @State.

The generated builder and its typed capture class are paired by the compiler.
Only the native component boundary erases the capture class to Object because
ArkUI structs do not support type parameters. The builder restores that exact
class with an explicit cast. UI source expressions remain in the typed target
tree, not in the fixed native runtime template.

`propagateMinConstraints=true` and direct page-owned state in constraint content
remain explicit diagnostics. They are not silently dropped or approximated.
