# Reused Component Source Structure

User approved these changes on 2026-09-11 with "modify these problems".

1. Preserve reused component export names in final ETS unless actual generated
   bindings require disambiguation. Keep collision handling for native controls,
   root types, multiple imports and generated declarations.
2. Preserve mapped no-argument UI slot ownership, nested component calls and
   source child order without lifting internal UI attributes into synthetic Props.
   SDK-required Builder helpers may carry only referenced enclosing source
   parameters. Keep existing diagnostics/defaults.
3. Do not synthesize business behavior, change adapter matching, or remove valid
   runtime measurement. No manual edits to generated ETS or version JSON.
4. Test nesting, two named slots, forwarded parameters, repeated instances and
   import conflicts. Run a fresh previously adapted full page through generation,
   SDK build, installation and capture/comparison; also build and run a nested
   reuse fixture so the changed path has actual SDK/runtime coverage.
5. Record process success separately from partial generation and visual failure.
   Freeze a scoped candidate for the existing independent reviewer, then commit
   and push only reviewed changes under the user's standing authorization.

Runtime refinement: the first inline-arrow candidate compiled, but failed on the
device with "class constructor cannot called without 'new'" inside its content
arrow. Use actual Builder helpers; do not infer a target trailing-slot name from
only one mapped source slot (the target may declare other BuilderParams).

Keep slot Builders as page-local methods: global calls inside arrows lose their
rendering receiver on the device. Explicit standalone-this binding and direct
void Builder calls as property values fail SDK checking. Source functions remain
separate; only callers of local slot methods need a typed rendering context.
