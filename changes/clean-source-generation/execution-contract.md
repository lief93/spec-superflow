# Clean Source Generation

User approved implementation on 2026-09-11: repair the failed full-page regression
and remove unnecessary preview/render naming and context indirection for fixed dp.

1. Accept bounded multiline source provenance without discarding its evidence;
   continue rejecting empty, oversized and invalid control-character metadata.
2. Emit fixed source dp as logical ArkUI lengths, not runtime pixel rounding.
   Retain context only for actual runtime state or measurement dependencies.
3. Preserve source method names and parameters. Collapse redundant single-variant
   rendering facades where semantics and binding safety can be proven; retain
   necessary state specializations rather than changing state selection.
4. Verify focused regressions, then fresh Banking Contact loaded generation,
   SDK build, installation and same-state capture/comparison. Never patch generated
   ETS or JSON. Record visual failures separately from build/install success.
5. Independent read-only review of a frozen scoped candidate, then commit/push
   tested changes according to the user's standing instruction. Exclude unrelated
   worktree edits. Unexpected unrelated generation failures require diagnosis.
