# Bounded Int to Double conversion

## Integration gap and scope

The original binary overload fixture failed the public CLI at
`Application.kt:637..647` with `Unsupported external call: kotlin.Int.toDouble`.
The retained diagnostic is
`tests/binary-bodies/r2d/.work/run-Yyeyt3/public-jWy0iD/combined-cli.json`.
No binary fixture, producer JAR, or previous failure evidence was modified.

Only `src/stdlib/StandardLibraryRules.kt` changes production. Its new guard
accepts the actually resolved external, non-fake `kotlin.Int.toDouble(): Double`
member with nonnullable exact Int dispatch, exact Double declaration/call
results, no extension/super receiver, no parameters or type arguments, and the
observed `IR_EXTERNAL_DECLARATION_STUB` origin. All checks precede child lowering.

The adapter lowers the receiver once and retains its typed ETS `number` value.
Every signed 32-bit Int is exactly representable in a binary64 number. There is
no rounding operation, Float intermediate, bitwise narrowing, or new runtime
helper. Existing runtime source and fixed helper inventories are unchanged.

## Official reference and replacement

Inspected pinned local official source:
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/org/jetbrains/kotlin/ir/backend/js/lower/calls/NumberConversionCallsTransformer.kt`.
The Int registration at lines 40-46 maps `TO_DOUBLE` to `useDispatchReceiver`;
that implementation builds a typed reinterpret cast of the original receiver.

Reuse is semantic and architectural: official resolved symbols/types, the
existing shared `Language`/`CallRule`, and the same identity conversion for this
Int-only case. The Kotlin/JS transformer itself depends on `JsIrBackendContext`
and is not loaded as an ETS pass. ETS represents both Int and Double as `number`,
so no target cast/helper is necessary. No library body is fabricated, loaded
from an unavailable signature, or replaced through source-string parsing.

## Tests and evidence

New tests are isolated in `tests/stdlib/int-double/`:

- `IntDouble.kt`: original source for both JVM and public CLI, including a
  side-effectful receiver factory and an arithmetic failure before conversion.
- `Rejected.kt` and `Symbols.kt`: two actual accepted calls, actual Float/Long/
  Double/Number/source-lookalike calls declined, and 12 mutated declaration/call
  shapes rejected before child lowering. Typed validation also checks one
  receiver reference and empty conversion runtime closure.
- `Oracle.kt` and `host.mjs`: 14 same-input pairs covering MIN/MAX, adjacent
  extremes, integers around 2^24, negative/positive/zero values, receiver effects
  and failure prefixes. Java Double raw bits are compared with independent host
  DataView binary64 bits. Generated output is typechecked/executed unchanged.
- `run.mjs`: serialized, slot-gated symbols/public modes with exact frozen/live
  input hashes, retained command outputs and per-run result manifests.

Initial evidence relative to `tests/stdlib/int-double/.work/`:

- `symbols-ussRfS`: RED at the real external Int.toDouble call, missing adapter.
- `symbols-cu9c4B`: retained test setup failure after the accepted call and first
  11 rejects; official FIR lazy declarations prohibit name mutation. Replaced
  that attempted mutation with an executable nullable declared-result negative;
  actual differently owned conversion symbols remain separately covered.
- `symbols-VLNkH7`: GREEN, two accepted calls, five excluded conversion families,
  all 12 malformed shapes, one child, no conversion runtime, input hashes stable.
- `public-3xNSPu`: GREEN, all 14 JVM/public-CLI/host pairs matched exact binary64
  bits and receiver/error traces; unchanged output typechecked, exact helper
  inventory and frozen/live input hash guards passed.

Commands require main's explicit serialized slot:

```sh
KOTLIN_ETS_CONVERSION_SLOT=symbols node tools/kotlin-ets/tests/stdlib/int-double/run.mjs symbols
KOTLIN_ETS_CONVERSION_SLOT=public node tools/kotlin-ets/tests/stdlib/int-double/run.mjs public
```

These conversion proofs use StandardLibraryRules SHA-256
`c398838bb827664ee4fb45d9cf5416ff192665394f9f812cb2c936f1739de8d5`.
The original binary replay then advanced past conversion and exposed the next
separately approved gap: Double `greater` at `Application.kt:721..732`. That
failure is retained in `run-Yyeyt3/public-hIX9py/combined-cli.json`; see
[double-relations.md](double-relations.md). Later production changes invalidate
these as final combined-source proofs; main reruns acceptance on the final hash.
No SDK/native acceptance is claimed.

## Unsupported limits

No Float/Long/Number conversions, general numeric conversion family, nullable
receiver dispatch, source lookalikes, or new arithmetic behavior is added.
The representation assumes values obey the existing Kotlin Int lowering
contract; this adapter is not runtime validation of arbitrary external numbers.
