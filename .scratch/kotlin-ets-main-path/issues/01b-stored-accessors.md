# Top-level stored custom accessors

Status: completed
Blocked by: none (01-computed-properties accepted)
Review: deferred by user

Complete the remaining accessor portion of L1 for constant-initialized source
properties. Reuse resolved IrProperty/IrField/accessor symbols and the ordinary
function lowerer. Emit private owner-file backing storage; getter/setter calls
invoke accessor bodies, while explicit field reads/writes bypass them. Keep
default counterparts and private setter visibility. Initialization does not call
the setter. Nonconstant initialization stays issue 02.

Verify with the existing public computed-property CLI runner and independent JVM
oracle: cross-file class methods, repeated reads, compound updates, default
counterparts, initialization and private setters. Retain stored-global/member
regressions. Promote the old stored-accessor negative to supported coverage rather
than deleting its requirement. No SDK/native or full L1 claim.

## Acceptance (2026-09-15)

- RED `computed/.work/run-J27awx` rejects Stored.kt at the old default-accessor guard.
- GREEN `computed/.work/run-mclwVi`: 73 flat + 73 module JVM/host results,
  including unchanged former negative `globals/Accessor.kt`, four-file deterministic
  output, strict host types, backing-field/setter visibility and original parameters.
- Final regressions: `globals/.work/run-cviFMO` (26 flat/module results plus
  relocated callback replay), `language/.work/accessors-ZuHg8k` (18 results).
- Self-check passed: typed ordinary function/call/global nodes only; source field
  accesses bypass accessors; initialization does not invoke setters; no private
  backing exports. No independent review or SDK/native acceptance claimed.
