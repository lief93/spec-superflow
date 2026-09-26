# Source builder ownership

R1B moves reachable, page-independent source `@Composable` Unit functions to
top-level `@Builder` functions in their original `EtsFile`. Source names,
parameter names/types/defaults and declaration identities remain unchanged.
Public/internal source builders are exported; private builders remain local to
their original output file. Direct pipeline use keeps a stateless entry as a
top-level Builder. Production `page` mode packages the entry as a same-named
component method called by `build`, while stateful direct entries are components.

## Binding and ownership

`ComposeSourceFunctionLowering` delegates each reachable source
`IrSimpleFunction` to `IrFunctionToEts` with `FunctionTargetSemantics`. The
shared language lowering therefore owns the original name, parameters, defaults,
generic binders, visibility and symbol identity; Compose supplies only builder
effect, UI body lowering and typed slot representation. `ComposeWidgetPipeline`
places the resulting typed builders in their source-owned `EtsFile`; source
builder calls bind exact target symbols rather than looking declarations up by
printed name.

Composable function parameters use `WrappedBuilder<[T...]>`, derived from the
resolved Kotlin function type rather than a parameter name. Zero- and
parameterized slots share declaration, forwarding, invocation and capture
lifting. Synthetic helper names are limited to anonymous source lambdas; named
business composables retain their source method names.

Named source composables remain top-level builders. State and ordinary local
values captured by an anonymous UI lambda become explicit parameters of its
generated slot builder. The reactive-builder pass changes state-dependent
parameters to ArkUI `Binding<T>` only after target structure is complete. A
page-capturing callback stays in the page caller; it does not force the called
business builder or its transitive callers into the component class.

Receiver occurrences are counted per structural edge, not deduplicated by object
identity. Sharing an immutable `EtsReference` between a source-call receiver and
a field read/default/callback therefore cannot conceal the actual page access.

The typed rewrite changes only eligible source-member references into declared,
nonexternal `EtsReference` nodes. It preserves all arguments, source spans,
callback bodies and captured symbols, including references inside page-owned
generated bridges. The printer does no ownership inference or text replacement.
Module assembly continues to check symbol ownership, visibility and collisions.

## Boundary

Generated slot bridges are top-level builders with explicit captured parameters;
they never retain a free page `this`. No receiver/context parameters are
introduced into named source functions. Source composable receivers and slot
defaults remain outside the profile; this increment does not claim arbitrary
Compose support.
Recursive source UI traversal is still rejected by the existing material text
context analysis. Cycles below are tested only at the typed ownership seam,
not claimed as newly supported source recursion.

## Focused verification

Run serially from `tools/kotlin-ets`, with the shared compiler slot:

```sh
node tests/ui/ownership/graph.mjs
node tests/ui/ownership/probe.mjs
```

Both runners pin low-CPU SerialGC JVM options and retain command/stdout/stderr,
input SHA-256 hashes and outcomes under `tests/ui/ownership/.work/`. The source
probe uses actual Kotlin 2.1.20 IR from `Widgets.kt`, `Screen.kt`, `Services.kt`;
it checks all reachable named source builders, generated anonymous slot builders,
exact symbols/parameters/private visibility, explicit callback captures and the
absence of free `this` in global builders. Ordinary Kotlin behavior is covered
by the language/lowering suites rather than duplicated in this ownership test.

The probe emits the complete untouched `OwnershipPage.ets` and `modules/*.ets`,
with output hashes in `result.json`. The integration owner runs public CLI,
actual SDK and native regression separately. A focused typed/host pass alone
does not establish SDK or native acceptance.

## Evidence

Baseline snapshot before producer edits:
`/tmp/kotlin-ets-builder-baseline-tkneML/src`. Replay with
`KOTLIN_ETS_SOURCE_ROOT=/tmp/kotlin-ets-builder-baseline-tkneML/src` on the source
probe. Baseline RED `probe-Oj1Ami` reaches actual IR/target creation, then rejects
the root's unbound class type: the old producer assembled the root using the
last visited declaration's file. Source file ordering is deliberately mixed.

Graph RED `graph-5qrNEO` rejects the old identity-set classification when one
receiver object is shared by a source call and an actual page field read.
Each GREEN source probe records actual IR, detached validation, three module
outputs and the full production input hash guard under
`tests/ui/ownership/.work/`.
Graph GREEN `tests/ui/ownership/.work/graph-fpLw9q/result.json` covers shared
receiver occurrences, defaults/callbacks, bridge/transitive page dependence,
pure and anchored typed graph cycles, and exact-symbol rewriting.

The frozen `ComposeLowering.kt` hash from the original experiment is historical
evidence only. That page assembler was removed when page mode switched to the
Widget pipeline and must not be restored as an alternate producer.

These focused runs did not execute public CLI, SDK or devices. The integration
owner separately reported the prerequisite five-module target-only global
builder SDK test (`p4AJqu`) passed; actual source fixture SDK/native regression
remains integration-owned and pending at this source freeze.
