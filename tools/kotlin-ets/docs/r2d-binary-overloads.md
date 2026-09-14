# R2D Binary Inline Overload Selection

Status: finite tests-only preparation. No R2D JVM/compiler/CLI execution yet.
No production or shared-contract edits; wait for the main task's compiler slot.

## Existing Contract And Official Reuse

`BinaryBodies.index` decodes the real serialized signature table using Kotlin
2.1.20 `IdSignatureDeserializer`. The package/name enumerate actual FIR candidates;
the complete `PublicIdSignatureComputer(JvmIrMangler)` signature selects one.
`register` rejects conflicting actual owners for an already registered signature;
post-deserialization checks retain resolved parameter/return type identity.
`LibraryInlining` consumes the actual selected function symbol through the common
official inliner. R1 already verified an Int helper with a String overload sibling.

Official cached sources beneath
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/org/jetbrains/kotlin/`:

- `backend/common/serialization/IdSignatureDeserializer.kt`: package/declaration,
  member identifier and flags decoded from the real signature table.
- `backend/common/serialization/signature/IdSignatureComputers.kt`:
  `PublicIdSignatureComputer.visitSimpleFunction`.
- `ir/backend/jvm/serialization/JvmMangler.kt` and
  `backend/common/serialization/mangle/ir/IrMangleComputer.kt`: actual Kotlin
  parameter/receiver types and JVM return type participate in signature mangling.
- `ir/util/SymbolTableSlice.kt`: registered symbol ownership and no rebinding.
- `ir/inline/FunctionInlining.kt`: resolved callee, actual argument slots and
  default evaluation, not overload selection from target types or textual names.

The optional target `EtsFunction.sourceName` contract applies to surviving source
declarations. These binary calls are fully inlined, so no source allocator or
emitted overload name is used to select a binary body.

## Finite Cases

Two top-level serialized `select`/`helper` overload pairs take Int or Double,
both mapped to target `number`, but produce deliberately different Int markers.
The callback also observes values and records effects; results avoid floating
string-formatting differences. The consumer covers omitted Int and Double defaults,
explicit bias and named arguments supplied in non-declaration order, positive,
negative and Int-overflow inputs.

Three layouts use identical source inputs: one combined JAR; Int and Double
overloads in separate JARs; those same two JARs in reversed classpath order.
Focused evidence requires four distinct complete official signatures and eight
actual selected inline blocks, with each body linked to its original declaration,
parameter names, concrete Kotlin type, payload hash and class SourceFile record.
Public replay compares nine same-input JVM/host cases on the current frozen target.

Three closed negatives keep the Int sibling available while the selected Double
root is signature-only, its transitive Double helper is signature-only, or that
helper is absent. Rejection must name the selected dependency/signature and caller
source span; no same-name Int fallback, fabricated ordinary body or target output.

## Boundaries

This is not a global duplicate-binary policy. Public signatures do not uniquely
encode every artifact location; the official frontend can apply classpath
shadowing, and `index` skips signatures already registered. Existing owner-conflict
guards are not proof of exhaustive duplicate-JAR detection or real hash-collision
coverage. No duplicate-artifact policy or fake signature-collision tests are added.

The conservative all-default-dependencies policy accepted in R2C is unchanged.
Binary members, constructors, reified bodies and unsupported formats are not
widened. No new body is fabricated from a JVM signature or source-text substitute.

## Commands

Run only after the corresponding explicit slot grant:

```sh
node tests/binary-bodies/r2d/run.mjs
# After shared source freeze:
node tests/binary-bodies/r2d/replay.mjs tests/binary-bodies/r2d/.work/run-REPLACE
```

The frozen R2B command helper is reused read-only, included in the input hash
manifest, and caps JVM work at two processors with SerialGC. Producer/JVM and
focused evidence precede the separately gated public CLI/host run. Both record
commands, diagnostics and source/payload/output identity. Assertions are prepared,
not claimed GREEN before execution. SDK/native integration remains main-owned.
