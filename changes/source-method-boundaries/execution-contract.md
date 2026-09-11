# Source Method Boundaries

The user approved implementation on 2026-09-11 with "modify it", following the
request to keep source-extracted methods extracted and source-inline UI inline.

## Scope

Preserve source method ownership rather than merely renaming generated helpers.
Remove the synthetic page snapshot method by placing its UI in build. Use native
trailing content for reused components only when the target declaration proves
one no-argument BuilderParam; preserve source-inline nesting there. Multiple or
unknown target slots retain the verified receiver-bound Builder lowering and
report the reason. Keep actual source methods and calls, names and parameter
bindings. Do not infer missing domain types or business computations from the
selected rendered result. Record remaining source-structure gaps explicitly.

No edits to generated ETS/version JSON, no Android source reopening in the
backend, no changes to defaulting or adapter matching. Target signature facts
must enter through the same page JSON. No general Kotlin transpiler or invented
business logic. Preserve native scrolling and current selected-state semantics.

## Verification

1. RED/GREEN tests for inline nesting, source function forwarding, target-slot
   ambiguity, stale JSON, and absent synthetic snapshot method.
2. Inspect native SDK build/runtime for the new inline path, including nested
   reused components, cross-file source method calls, and multiple slots.
3. Fresh full Contact page generation, build, installation, capture and comparison;
   distinguish process, completeness and visual verdicts.
4. Freeze the scoped candidate for the fixed independent reviewer. Commit and
   push after review under the user's standing instruction. Unimplemented
   reconstruction of source loops/domain computations is not a completed claim.
