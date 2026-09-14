# R2B Bounded Binary Extensions

Status: bounded R2B accepted by main after focused/public/JVM/host checks, frozen
regressions, combined SDK RmCrqG (44 files), and native -05 (seven states, five
touch boundaries, Hypium and the unchanged 2px gate). The dependency lane remained
tests-only. BinaryBodies/LibraryInlining are unchanged; language-owned target
legality fixes were integrated by their owner, not bypassed in these fixtures.

## Existing Support Inventory

`BinaryBodies.types` already includes `extensionReceiverParameter.type` in the
resolved signature identity snapshot. R2A registered original FIR generic
parameter symbols and upper-bound classifiers using official signatures. The
top-level guard rejects dispatch receivers, not extension receivers. Transitive
lookup selects an actual FIR declaration by complete serialized signature.
`LibraryInlining.kt` invokes the same official common inliner unchanged.

Pinned Kotlin 2.1.20 sources in
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/org/jetbrains/kotlin/`:

| Official File / Routine | Relevant Existing Behavior |
| --- | --- |
| `backend/common/serialization/IrDeclarationDeserializer.kt`, `withDeserializedIrFunctionBase` | Decodes `proto.extensionReceiver` as an actual value parameter alongside generic types and the serialized body. |
| `backend/common/serialization/signature/IdSignatureComputers.kt`, `PublicIdSignatureComputer` | Real function/type-parameter signatures, not textual name substitution. |
| `ir/inline/FunctionInlining.kt`, `CallInlining.evaluateArguments` | Maps actual parameters and arguments; effectful receivers become temporaries outside the inline block. |
| `ir/inline/FunctionInlining.kt`, `createTemporaryVariable` | Marks extension-receiver temporaries with `IR_TEMPORARY_VARIABLE_FOR_INLINED_EXTENSION_RECEIVER`. |
| `ir/inline/InlineFunctionBodyPreprocessor.kt` | Reuses official generic classifier remapping, non-reified erasure and call-site substitution. |

The unchanged production baseline supports this extension slice. No loader RED
was invented and no already-supported receiver lowering was rewritten. The
separate source reference-equality boundary found by public CLI is retained below;
it is not evidence of a serialized-body loading failure.

## Finite Tests

`tests/binary-bodies/r2b/` contains real producer sources, consumer, JVM oracle,
official IR evidence, focused runner and a separately gated public replay.

- Generic top-level `Any`-bounded direct extension and one transitive generic
  helper extension, both same-JAR cross-facade and separate helper JAR layouts.
- Source-owned Box and Int receivers, different entry/helper type parameter
  names, multiple `this` reads, receiver evaluation once, receiver-before-argument
  evaluation, named value arguments, closure effects, Int overflow, shared object
  identity and mutations visible through the original caller's object. Direct and
  transitive identity bridges mutate the first receiver reference and return the
  second; JVM oracle and host use strict reference comparisons on those returns.
  The consumer also mutates after generic return and observes the original object.
- Expected trace `RADRAENAI`: two object receiver reads and one Int receiver read,
  exactly three ordinary argument effects, then each corresponding callback.
- Original binary function/body/receiver symbol linkage, parameter names, actual
  serialized-payload hashes and class SourceFile provenance with unknown lines.
- Ordinary signature-only JAR; missing transitive body/JAR/SourceFile; reified,
  member, constructor and multifile-format boundaries. No fabricated body or
  producer source supplied to the consumer frontend.

Run only in the main task's corresponding exclusive compiler slot:

```sh
node tests/binary-bodies/r2b/run.mjs
# After all shared production writers freeze:
node tests/binary-bodies/r2b/replay.mjs tests/binary-bodies/r2b/.work/run-UUuwgl
```

Both runners pin `JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=2 -XX:+UseSerialGC`.
The focused run records unchanged production and producer hashes. Public replay
checks those producer/test hashes before reuse, records the whole current
production revision, and compares the normal public CLI output against the
actual same-input JVM. Host execution is not SDK/native acceptance.

## Evidence And Preserved Failures

Directories below are relative to `tests/binary-bodies/r2b/.work/`.

| Run | Result |
| --- | --- |
| `run-0NRCSq` | Extension positives passed; constructor-negative assertion failed because an unused construction inside an Int-returning body first hit unlinked `kotlin.Unit`. No loader change: the negative fixture was made Unit-returning so its actual signature supplies Unit and the constructor boundary is tested without that masking error. |
| `run-cqWNjG` | Original fixture focused GREEN: both layouts, five official extension inline blocks per layout, JVM oracle and eight body boundaries. Constructor now rejects the actual `extensionbinary/Artifact.<init>` symbol. |
| `run-cqWNjG/public-y8AG8v` | Genuine public CLI failure on original fixture: `Unsupported external call: kotlin.internal.ir.EQEQEQ`, Application.kt offsets 854..861, exit 2. This is the separately owned equality boundary, not a loader failure. |
| `run-UUuwgl` | Final focused GREEN on unchanged production: both layouts, eight official inline blocks and eight receiver temporaries per layout, six JVM scenarios including strict identity checks and return-after-mutation assertions, eight body boundaries. |
| `run-UUuwgl/public-2r2zwH` | Public CLI reached target validation after equality was isolated, then rejected `Reserved target identifier: this` with consumer offsets -1..-1. Actual IR contains eight `IR_TEMPORARY_VARIABLE_FOR_INLINED_EXTENSION_RECEIVER` variables named `this`. Reported to main/language owner; no fixture rename, validator bypass or dependency-lane production patch. |
| `run-UUuwgl/public-k7DNH6` | Final main-owned replay GREEN after language legality fixes: six JVM/host pairs, twelve exact-object checks, nine closed failures, `implementationUnchanged=true`. `identity.json`, `runtime.json`, `complete.json` and per-command JSON preserve the tested revision. |

Both final outputs have SHA-256
`6caac7f995681684665dcf16af3fa21679d054c11d2601c83a04c719ba8ee98c`.
Main subsequently accepted the unchanged combined SDK/native evidence above;
this acceptance is not inferred from Node transpilation alone. It covers the
finite R2B case list, not general binary classes or general source equality.

The failed original Application.kt is preserved byte-for-byte as
`ReferenceEqualityApplication.kt`, SHA-256
`f2a096c4ef3272046869594652d332138521e89257550c16b469464b3a3e7c3e`,
matching the original `run-cqWNjG/producers.json` entry. Public replay retains it
as a ninth explicit negative. Removing `===` from positive emitted source does
not remove the identity requirement: the independent JVM oracle uses `===`/`!==`
and host uses `assert.strictEqual`/`assert.notStrictEqual` on actual objects, plus
mutation through the returned reference. No equality rule was added to stdlib.

Final focused `bodies.txt` records actual serialized payloads: extDirect 903
bytes, extEntry 932 bytes, extHelper 1009 bytes, each with its payload hash and
actual JAR/class SourceFile identity. Direct/helper bodies read their own bound
receiver symbol twice; the entry reads it once to call the transitive helper.
The consumer does not import helper or provide producer source to the frontend.
Line data remains explicitly unknown rather than fabricated.

Unchanged production SHA-256:

```text
c397bd481d816e4c8882682e163f891289df4647020e84f0d039df74cca2782b  src/core/BinaryBodies.kt
7bb29b03e1f29047451060cd322011907a6171c37f5e7c30f51c4daeadcc9fc0  src/core/LibraryInlining.kt
```

## Explicit Boundaries

No nullable receiver expansion, multiple bounds, reified inline, binary members,
binary constructors, KLIB/multifile loading or general binary class support is
included. No target, language, frontend, CLI or shared-contract edits are planned.
If resulting IR exposes a shared issue, report it to the main task rather than
adding a second receiver/type-substitution implementation here.
