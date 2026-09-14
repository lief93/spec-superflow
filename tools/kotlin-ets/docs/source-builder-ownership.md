# Source builder ownership

R1B moves reachable, page-independent source `@Composable` Unit functions to
top-level `@Builder` functions in their original `EtsFile`. Source names,
parameter names/types/defaults and declaration identities remain unchanged.
Public/internal source builders are exported; private builders remain local to
their original output file. The entry function stays a component method.

## Binding and ownership

`ComposeLowering` binds each actual `IrSimpleFunction` to the same
`etsFunctionSymbol` used by its target declaration. Source builder calls and
generated bridge calls initially use `EtsMember.symbolId`, not a lookup by name.
Generated calls bind the exact newly created `EtsFunction.symbol`.

`BuilderOwnership` walks the immutable typed functions, including parameter
defaults, lambdas, nested bodies and UI arguments. References to source builders
form dependency edges. The root, real page receiver/state accesses and calls to
generated slot/local-evaluation bridges anchor page ownership; this dependence
propagates to source callers until stable. Callback parameters alone do not
anchor their declaring builder. A page-capturing callback passed by the root
still captures the page in the caller, without inventing a context parameter.

Receiver occurrences are counted per structural edge, not deduplicated by object
identity. Sharing an immutable `EtsReference` between a source-call receiver and
a field read/default/callback therefore cannot conceal the actual page access.

The typed rewrite changes only eligible source-member references into declared,
nonexternal `EtsReference` nodes. It preserves all arguments, source spans,
callback bodies and captured symbols, including references inside page-owned
generated bridges. The printer does no ownership inference or text replacement.
Module assembly continues to check symbol ownership, visibility and collisions.

## Boundary

Generated slot and evaluate-once bridges remain page methods, even when further
capture conversion might theoretically make them global. A source builder
depending on such a bridge remains page-owned transitively. No receiver/context
parameters are introduced. Existing source-receiver/generic/slot limitations
remain in force; this increment does not claim arbitrary Compose support.
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
it checks five original-file globals, root and transitive page ownership, exact
symbols/parameters/private visibility and live page callback captures. Ordinary
source helper closures run on the JVM and the generated host code for five
identical seeds, including signed overflow endpoints. The host helper projection
comes from typed declarations, not a simulation of UI composition.

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
Source GREEN `tests/ui/ownership/.work/probe-VzNazW/result.json` records actual
IR, detached validation, three module outputs and five same-input JVM/host
results (`2`, `-4`, `16`, `2`, `0`), with the full production input hash guard.
Graph GREEN `tests/ui/ownership/.work/graph-fpLw9q/result.json` covers shared
receiver occurrences, defaults/callbacks, bridge/transitive page dependence,
pure and anchored typed graph cycles, and exact-symbol rewriting.

Frozen production SHA-256:

```text
b144cc502b76749a8d95fc8574900ace6847e68934b59fd5b83090d287975bc6  src/ui/ComposeLowering.kt
87e41cb362bbbab976f5b556085c6b326a91c05f9e57e2aa30c1f7e09fc944c4  src/ui/BuilderOwnership.kt
```

These focused runs did not execute public CLI, SDK or devices. The integration
owner separately reported the prerequisite five-module target-only global
builder SDK test (`p4AJqu`) passed; actual source fixture SDK/native regression
remains integration-owned and pending at this source freeze.
