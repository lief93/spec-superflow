# Readable Target Output

2026-09-13: reduce unnecessary expression parentheses and discarded-value IIFEs.
This is a language-lowering/printer change, not source-text rewriting or a new
page-specific adapter.

## Rules

- Printer emits grouping from typed expression precedence. Right operands retain
  equal-precedence grouping; no arithmetic reassociation is performed.
- Nullish/logical mixing, asserted types, numeric member receivers and invoked
  lambdas retain required parentheses.
- In statement position, implicit Unit coercion lowers its operand as statements.
  A zero-argument, zero-parameter void wrapper with exactly one expression
  statement can discard that result directly, without an immediately invoked
  arrow function. Other call/return/scope boundaries remain intact.
- Value-position blocks, named-argument evaluation temporaries and Int32 arithmetic
  are unchanged. No dead-code elimination, increment reconstruction or helper
  runtime removal is included.

The unchanged LanguageSlice fixture has 7 IIFEs before and 2 after; void IIFEs
drop from 4 to 0. Generated program-body parenthesis characters drop from 162 to
46 and lines from 56 to 48. These counts exclude the identical runtime preamble;
parenthesis counts include required declaration/call/type syntax.

## Verification

RED: target/run.sh failed the new `return base + extra;` expectation before the
printer edit (target-tests.c4OW1m). LanguageSlice then failed its no-void-IIFE
assertion before the lowering edit (language/.work/run-wUsGza).

GREEN commands and local evidence:

| Command under tools/kotlin-ets | Result | Evidence |
| --- | --- | --- |
| bash tests/target/run.sh | Precedence, deterministic printing and invalid-target checks pass | /var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-target-tests.D6phji |
| node tests/language/run.mjs | 5 positive and 7 unsupported fixtures pass | tests/language/.work/run-b1yPN9 |
| node tests/language/typed.mjs | Typed adapter/value/effect contracts pass | tests/language/.work/typed-e9u0vl |
| bash tests/backend/run.sh | Lowering independent of printer; JVM/target 10-value differential passes | /var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-backend-tests.YFTeYW |
| bash tests/stdlib/check-public-cli.sh | 66 JVM/target cases and unsupported-call rejection pass | tests/stdlib/.build/cli.iOGqzl |
| node tests/ui/run.mjs | UI generation, helper oracle, renamed inputs and negative contracts pass | /var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-ui-tests-WSBOkE |
| python3 -B tests/integration/test_cli.py | 3 tests pass | 33.515 seconds |
| node tests/language/sdk.mjs | All 5 generated modules compile as ETS into HAP | /private/tmp/kotlin-ets-language-sdk-W8GmMk/manifest.json |
| node tests/stdlib/check-sdk.mjs | Both generated stdlib modules compile as ETS into HAP | /tmp/kotlin-ets-stdlib-sdk-MrHroa/result.json |

Actual SDK input bytes are unchanged from the freshly generated originals. The
comparison at /tmp/kotlin-ets-readable-output-20260913/comparison.md checks the
old/new source and generated-file hashes against both SDK manifests; inputs.json
records identities. The code excerpts are not manually cleaned up.

No device installation, page interaction or visual acceptance was performed for
this language-level change. The fixed independent reviewer again completed with
an empty response (turn 01a09a77-00e8-7c12-854d-cac6a0a6e456); review is not approved.
No commit or push. Read-only review candidate:
/tmp/kotlin-ets-readable-review.fzj32F/kotlin-ets.
