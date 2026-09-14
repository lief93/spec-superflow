# R2I named inner chains: fixed contract

Cost sample 2, main implements, tests and self-checks without subagents. The
initial delegated fixture preparation is separately accounted for.
This extends R2H only to named nongeneric immediate inner owners, for example
`Outer.Inner.Deep`. Every inner link has one primary constructor and Any-only
heritage. The chain ends at a named nongeneric top-level source class. Static
nested barriers, generic enclosing/inner binders, secondary constructors, derived
inner classes, anonymous owners and local/capture combinations remain diagnostics.
The existing ordinary top-level class gates are unchanged.

Reuse the existing official common declaration, member-body and constructor-call
passes, in the pinned JS phase order, before flattening. The official member-body
pass already walks `innerClass.parentAsClass` and produces one exact outer-field
read per link; constructor calls move their resolved receiver to the first regular
argument. Do not reconstruct chains or arguments from names/source strings.

Keep `SourceInnerClassBinding` unchanged: its `outer` is the immediate original
IrClass, not the ultimate root. Each owner must have its own identity-registered
binding. Language validation follows these bindings to the root, rejecting missing,
malformed or cyclic chains. Existing exact field/parameter origins, types, owning
constructor prefix, source fallback and nontransferable registration checks remain.
No target node, validator exemption, printer change or new lowering pipeline.

Preserve actual outer objects, not copies: a Deep stores its Inner, whose own link
stores its Outer. Source mutations through parent/grandparent reads and writes must
remain shared. Official default expressions, receiver single evaluation, named
argument order, names, source spans and source-file ownership must survive.

After flattening, descendants can read an ancestor's synthetic link from a distinct
target class. Such intermediate link fields must be non-private; identify them only
through registered child-owner identities, matching the official JVM support's
package-visible synthetic field. Leaf links retain R2H private storage. This does
not change source field visibility or authorize raw synthetic fields. Verify emitted
ordinary declarations with a real TypeScript semantic checker as well as runtime
parity; transpilation alone would miss illegal private accesses.

Focused proof: original JVM versus flat and multi-file target for shared and
distinct outer/inner objects, parent/grandparent mutation, receiver evaluation,
defaults/named argument order, lexical name collisions and cross-file references.
Check canonical field/class IDs, source ownership, exact negative spans, unchanged
IR source names, deterministic reversed file order, and retained R2H malformed IR
negatives. Update the old inner-chain negative to a still-unsupported static nested
owner; preserve the positive chain as a new owning fixture. No SDK/native gate is
needed because this slice uses existing ordinary class/field/constructor syntax.

## Accepted evidence (2026-09-14)

Main completed implementation, tests and self-check without further subagents.
Pinned common `InnerClassesMemberBodyLowering` already walks the immediate
`parentAsClass` chain; existing three official phases remain unchanged.

- `tests/inner-classes/chains/.work/red-8095mq`: original JVM executes, prior
  backend rejects with a valid source span.
- `green-ipRKeg`: five registered links, immediate owner identities, ancestor
  malformed type rejection, eight excluded structures; 20 JVM outcomes equal
  flat and multi-file output, reversed file-order determinism. Actual TypeScript
  semantic checks (not only transpilation) pass for both output forms. All 64
  frozen input hashes match accepted files. Full commands/stdout/stderr retained.
- R2H regression `.work/green-oQQeaz`: 20 outcomes and 14 malformed bindings pass.
- Core regression `core/.work/run-4zZ7IX`: official identity/constructor prefix
  proof and generic/derived/secondary/static-owner exclusions pass. The former
  chain negative is now a static-owner negative; supported chains have their own
  positive proof above.

Self-check confirms only identity-registered intermediate links become accessible
to flattened descendants; leaf links stay private and all stored links stay
immutable. No source field access is widened. No SDK, device or visual result is
claimed, and generic/derived/local/anonymous combinations are not newly supported.
