# R2H ordinary inner classes

## Shared contract

Support named nongeneric inner classes directly inside a nongeneric top-level
source class, with one primary constructor and Any-only heritage. Preserve the
outer object's identity; multiple inners share its mutations, not copied values.
Generic inner/enclosing binders, secondary constructors, derived inner classes,
anonymous objects and local-capture combinations remain diagnostics. R2I extends
named nongeneric inner chains under the contract in `inner-chains.md`.

Core provides `sourceInnerClassBinding(IrClass): SourceInnerClassBinding?`.
The binding records `outer: IrClass`, `field: IrField`,
`constructor: IrConstructor`, `parameter: IrValueParameter`, and
`source: SourceSpan`. Registration is by the original class identity before file
placement, not by generated spelling. Do not transfer authorization to IR copies.

Reuse common `InnerClassesLowering`, `InnerClassesMemberBodyLowering`, and
`InnerClassConstructorCallsLowering` in that order after local popup and before
ETS lexical class flattening. The existing JVM-backed context owns its official
InnerClassesSupport. Verify exact `FIELD_FOR_OUTER_THIS` field origin and
`JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS` parameter origin. Common
lowering owns receiver rewriting, constructor replacement and call arguments.
Official JS applies these phases in the same order; its JS-specific support
implementation is a reference, not a second expression conversion path.

Language consumes the registered field as private typed EtsField and references
it with the same symbol ID. It accepts only one registered parameter-to-field
assignment on the owning this receiver immediately before Any delegation.
Missing/duplicate/late/wrong writes, spoofed origin or unregistered ownership are
errors. Official outer writes have no dedicated statement origin: exact registered
identities and constructor shape are required, not a broad raw-field exception.
Retain valid source offsets; use binding.source only for synthetic absent offsets.
Use official NameTable for generated field/parameter collision avoidance, including
emitted root bindings. Do not rename source methods or parameters unnecessarily.

No new target node, raw output, validator exemption or argument reconstruction.
Existing target types, validation, module dependencies and printer must suffice.

## Ownership and evidence

- Main: core contract, phase ordering, eligibility and official IR probe.
- Parfit: language consumer and JVM/flat/modules behavior and malformed IR tests.
- Aristotle: fixed read-only review after freeze and focused regressions.
- Heavy compiler slot is serial; main owns the initial core RED/GREEN.

Required cases: multiple outer/inner instances; outer mutation; explicit outer
access; initializer/default/named argument order; receiver evaluated once;
cross-file constructors/imports; generated name conflicts; source-linked malformed
bindings and unsupported structures. This batch is not a native/SDK acceptance.

## Core results

RED `tests/inner-classes/core/.work/run-5Kfhij` retains the previous blanket
rejection after valid Kotlin compilation. GREEN `run-QEdvBO` verifies registered
identities, exact official origins, constructor prefix, regular outer argument,
source provenance and generic/derived/secondary/inner-chain diagnostics. The
existing local-class core regression `tests/local-classes/.work/run-bizWa3` passes.
Production snapshots/hashes and command logs are retained in each evidence folder.
Language `green-THZBKn` passes 20 JVM outcomes in flat/modules, fourteen negative
cases and deterministic modules; R2G regressions also pass. Aristotle's resumed
review reports requirements PASS and code quality PASS with no findings. Main
accepts this finite R2H subset; SDK/native and whole-R2 acceptance remain open.
