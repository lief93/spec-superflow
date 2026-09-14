# R2C Serialized Default Bodies

Status: tests-only GREEN through real producer/frontend/official inliner and
public CLI/JVM/host execution. No production, shared-interface or fixture changes
were needed during execution. SDK/native integration remains pending with main.

## Contract

An actual Kotlin 2.1.20 serialized top-level extension, bounded by nonnullable
`Any`, has a default `T` value computed by a generic extension helper in a second
JAR. The helper only invokes the supplied callback and returns its receiver.
The entry's callback parameter is `noinline`; the ordinary source closure remains
a real typed value. Producer sources are never inputs to the consumer frontend.

The finite tests cover omitted defaults, explicit replacement and named argument
order; Int and source Box values; receiver-once, callback factory/execution counts,
alias identity and mutations through returned references. Source code does not
need object `===`: the JVM-only oracle and host independently compare actual
object references. Both same-JAR cross-facade and second-JAR layouts are included.

Expected trace `RCDRVCNCD` records receiver, callback creation and default callback
execution for omitted calls, but receiver, explicit value and callback creation
without default execution for the named explicit call. The two objects start with
different values in the scenario; identity probes also use equal-valued distinct
objects to reject structural-equality substitutes.

## Official Existing Machinery

Pinned sources beneath
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/org/jetbrains/kotlin/`:

| File / Routine | Responsibility |
| --- | --- |
| `backend/common/serialization/IrDeclarationDeserializer.kt`, `deserializeIrValueParameter` / `deserializeExpressionBody` | Loads the actual serialized default expression into `IrExpressionBody`; this is not a JVM default-method signature or a manufactured expression. |
| `ir/inline/FunctionInlining.kt`, `visitFunctionAccess` | Transforms default expressions only for omitted actual arguments. |
| `ir/inline/FunctionInlining.kt`, `buildParameterToArgument` / `evaluateArguments` | Evaluates explicit arguments before defaults, preserves parameter order and substitutes actual receiver/value symbols. |
| `ir/inline/InlineFunctionBodyPreprocessor.kt` | Official generic type/symbol copying and substitution. |

Current `BinaryBodies.visit` checks the ordinary body and **every** parameter's
`defaultValue` before publishing availability, including DFS into inline helpers.
The original constant-default binary fixture already passed in earlier batches.
This batch targets default-only transitive reachability and effects, not a new
hand-written default expansion or a binary class/state implementation.

## Deferred Policy, Explicit Negative

The `ExplicitOnly.kt` consumer supplies every argument. The harness compiled and
ran it on JVM with only entry.jar for three inputs, then verified that the current
CLI still rejects a missing helper JAR or signature-only helper, even though that
default is not used by this call. This is the existing **conservative dependency
policy**, not missing default-body extraction and not claimed supported behavior.

`FunctionBodies.resolve(symbol)` is symbol-based, not call/omission-mask-based.
No new interface, unresolved-default skipping, per-call cache or relaxed linkage
is introduced. Call-sensitive dependency availability is deferred to a separately
approved contract. Member bodies, constructors, reified parameters and unsupported
binary formats retain their existing boundaries.

## Reproduction And Evidence

Run only after main grants the corresponding compiler slot:

```sh
node tests/binary-bodies/r2c/run.mjs
# After shared production freeze:
node tests/binary-bodies/r2c/replay.mjs tests/binary-bodies/r2c/.work/run-gDnObC
```

The runners reuse the frozen R2B command/log helper read-only and include its hash
in the producer manifest. It sets two active JVM processors and SerialGC. Focused
evidence checks real default `IrExpressionBody`, original entry/helper symbols,
binary payload/source provenance and the default helper's three needed expansions
versus five entry expansions. Public replay records the full current production
identity, six JVM/host scenarios, twelve exact-object checks and five closed
failures. These assertions passed in the recorded runs below.

| Evidence (Relative To `tests/binary-bodies/r2c/.work/`) | Result |
| --- | --- |
| `run-gDnObC` | Focused exit 0: two real producer layouts, six JVM scenarios, actual default expression/provenance, five entry and three needed helper expansions per layout, five closed boundaries, plus three explicit-only JVM cases with no helper JAR. `productionUnchanged=true`. |
| `run-gDnObC/public-pyPGQA` | Public replay exit 0: six same-input JVM/host pairs, twelve strict object-identity checks with mutation, five source-linked closed failures with no target output. `implementationUnchanged=true`. |

Both `combined.ets` and `second-jar.ets` have SHA-256
`c4b73512669cce0dd578203f4de01eb9c7e6104674a2b7c5a9128b1b2feaf68a`.
`identity.json`, `producers.json`, `runtime.json`, `complete.json` and per-command
JSON preserve production/input identities, commands, exits, stdout and stderr.
The first unchanged-production baseline was GREEN; no loader RED or production
fix is claimed for already supported behavior.

`second-jar-evidence/default.ir` retains the real default expression, offsets
127..146. `bodies.txt` records the original entry/helper symbols and actual class
SourceFile provenance with unknown debug lines. Serialized entry metadata is 735
bytes (SHA-256 `d1b5bfde3b069c33d49a19ba103b8db6db8c83cf49958cf054fc2920622f8646`);
helper metadata is 649 bytes (SHA-256
`9d12ea2c36a7d681c826f976bffbeed8ea0f7340c9b8a77071c37cfab0042b08`).
These are actual serialized payloads, not evidence inferred from JVM signatures.

Frozen, unchanged dependency production SHA-256:

```text
c397bd481d816e4c8882682e163f891289df4647020e84f0d039df74cca2782b  src/core/BinaryBodies.kt
7bb29b03e1f29047451060cd322011907a6171c37f5e7c30f51c4daeadcc9fc0  src/core/LibraryInlining.kt
```

No body/source provenance, debug lines or generated target bytes are fabricated.
Any newly exposed failure must be captured before a narrowly justified owned
internal fix; already working behavior stays tests-only. SDK/native acceptance
belongs to main and cannot be inferred from host execution.
