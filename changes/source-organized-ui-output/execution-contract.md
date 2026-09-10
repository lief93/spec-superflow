# Source-organized UI output

The user approved preserving Android UI file boundaries, source names, parameters,
and component calls instead of emitting every component into one page file.

## Scope

- Generate source-relative ETS modules from the existing single page JSON.
- Preserve existing source-named builders and typed parameter facades. Do not
  invent domain types, callback implementations, or runtime business conditions.
- Use the SDK syntax parser to relocate generated declarations and references;
  do not rewrite user strings or parse Kotlin in the backend.
- Reuse existing Harmony components without copying them. Preserve existing page
  entry paths on regeneration. Validate every output and remove only unchanged,
  previously owned obsolete outputs in the same transactional write.
- Keep fixed-state specialization explicit. Different pages cannot overwrite a
  shared source module with different contents; cross-page merging is not inferred.

## Verification

Cover source-relative paths, nested/repeated components, unchanged names and
arguments, slots, external imports, state/helper access, name/path collisions,
unowned/edited outputs, and regeneration. Generate a complete multi-file page
and compile the emitted files with the native SDK. Compilation is not visual or
business parity. Preserve unrelated worktree changes.
