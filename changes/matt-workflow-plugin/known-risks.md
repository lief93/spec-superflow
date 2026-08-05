# Known Risks

## Runtime Compatibility

- Only explicit `ask-matt` and automatic `diagnosing-bugs` were promoted to
  `PASS` through real VS Code 1.123 Chat evidence.
- The other 20 Matt Skills remain `PENDING`; their source and package structure
  are verified, but their host-specific semantics were not executed.
- Both Plugin roots preserve an unprefixed `grill-me`. VS Code duplicate-name
  resolution remains `PENDING`; this Change intentionally adds no prefix or
  resolver.

## Maintenance Boundary

- Ordinary build and installation are offline and deterministic. The explicit
  `sync-matt-plugin.mjs` maintainer command is the only path allowed to contact
  the pinned upstream source and must be reviewed before apply.
