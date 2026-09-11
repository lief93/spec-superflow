# Flat Generated Source Layout

## Approved Request

Generate page and source-backed component ETS files directly in the configured
output directory. Do not recreate Android package directories or expose an
`_migration` helper directory. Preserve separate source-file groups, function
names, parameters, calls, and existing output ownership protection.

## Implementation Scope

- Flatten source-derived filenames to their basenames. Reject ambiguous filename
  collisions rather than overwrite an unrelated component.
- Colocate generated anonymous builders and structural support declarations with
  the page/component files that consume them; retain typed runtime context.
- Relocate previously owned nested output during regeneration, preserving the
  entry basename and validating every old hash before retiring obsolete files.
- Update source-module tests and output-layout documentation.

## Verification

1. Focused tests prove flat paths, nested calls, slot/runtime behavior, collision
   rejection, import paths, and protected legacy regeneration.
2. Public CLI full-page fixtures plus a real Harmony SDK build verify generated
   modules without editing their ETS output.
3. Run related regressions, freeze the candidate, obtain the persistent independent
   review, then commit and push under the user's standing instruction.

## Non-Goals

No business semantic changes, no manual generated ETS fixes, no removal of
ownership metadata, no overwriting user-edited output, and no package version bump.
