# Default-Only Same-Name Component Reuse

## Approved Requirement

Prefer the unique same-name Harmony component without requiring identical source
parameter names or types. Explicit component adapters retain priority and their
existing strict contract. Latest user decision: do not map any Android arguments
for automatic reuse; use target defaults and omit whatever can be omitted.

## Binding Policy

- Do not evaluate, convert or forward source arguments, even for matching names/types.
- Omit all target properties with defaults or optional declarations.
- Use explicit placeholders for missing required strings, finite numbers,
  booleans, nullable values and no-argument void callbacks/slots.
- Report every dropped source argument and placeholder. Record normal target-only
  omissions in binding decisions. Reuse can succeed while completeness remains false.
- Never construct arbitrary required objects, pick ambiguous declarations, ignore
  unsupported target declaration syntax, or shift positional builder arguments.
- Keep the source-page -> page JSON -> ArkUI boundary. No generated ETS edits.

## Verification

Public projection tests must cover no-argument success, differing names/types,
missing/unresolved values, defaults, callbacks/slots, explicit adapters, ambiguous
names, complex required objects, no source evaluation and positional gaps. Diagnostics must survive to
the unified report. Run adjacent regressions and an SDK compilation of synthetic
default-only component calls. Review a frozen candidate before commit/push.
