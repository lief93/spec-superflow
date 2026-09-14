# Typed Backend Checkpoint

Historical checkpoint for the preceding batch. For subsequent implementation
and current open architectural work, see [Parallel Backend Batch](parallel-backend-batch.md).

2026-09-13. Implementation and module verification are complete for this bounded
architecture batch. Independent review is pending; this is not a release gate
approval, full Kotlin support claim, or page acceptance.

## Implemented

- Official K2 IR remains the source input. `EtsBackend.lower` returns typed,
  compiler-independent target nodes rather than generated text.
- Language and library adapters share expression types, source locations and
  symbol identities. Statement-only effects cannot stand in for returned values.
- Target validation and printing are separate from lowering. Source function
  calls bind to their target declarations, including across source files.
- Compose uses the same typed language interface; its `UiTextModule` control
  envelope remains transitional and is not yet a fully typed UI target tree.

## Verification

- Twelve language CLI fixtures and typed symbol/effect tests passed.
- Standard library: 71 supported-call checks, 66 JVM/target runtime comparisons,
  six unsupported API checks and 106 malformed-return checks passed.
- UI interface regression: 15 successful and 13 expected rejected commands.
- Independent backend tests, target-only tests and three public CLI tests passed.
- Actual ArkTS SDK compilation passed for five language and two library modules.
  Generated source bytes were not manually patched; no device installation ran.

Exact final commands, input hashes and artifacts are recorded in
[FINAL-RESULTS.md](../tests/backend/FINAL-RESULTS.md). The source candidate submitted
for review is frozen under `/tmp/kotlin-ets-typed-review.ifgFmB`; its manifest
contains 178 files with SHA256
`b44f868f147b2ff18431b0a76d225bed56a4a1dc650da88e4f7cf8d8803c8a3c`.
Result/checkpoint documents added afterward are not part of that source snapshot.

## Subsequent Reuse Work

The previously proposed `FlattenStringConcatenationLowering` experiment has since
been implemented and integrated into the production frontend. Its source/body
identity checks, effectful `toString` comparisons and exact reuse boundaries are
recorded in [Official Common Lowering](official-lowering.md). This does not imply
that general inlining, library-body loading or the rest of the common pipeline
has been implemented. Independent review is currently paused at user request.
