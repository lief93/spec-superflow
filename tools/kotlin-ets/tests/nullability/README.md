# Nullable Flow Test Boundary

Prepared tests only. No compiler, public CLI, probe or SDK has been run for this
suite by the test lane. Production flow refinement belongs solely to main.

After main grants the heavy execution slot, run from the repository root:

```sh
node tools/kotlin-ets/tests/nullability/run.mjs
```

The runner executes serially with two active JVM processors and SerialGC.
It retains original-input and production hashes, commands, exit statuses,
stdout/stderr, oracle results and the untouched output in `.work/run-*`.

The same original `Nullability.kt` is used by Kotlin/JVM and public CLI:

- Six nullable Int inputs across `!= null && > 0`, Elvis, explicit null-check
  false-branch return, guarded non-null `val` assignment, guarded nullable
  source-class method receiver, effectful Elvis and guarded argument use.
- Three nullable String inputs across nullable `?.length`, safe length with
  fallback, `safeString`, a guarded member read, and an effectful safe call.
- Trace strings verify exactly one receiver evaluation, fallback only on null,
  and no short-circuit RHS evaluation without a non-null value.

This gives 57 independent JVM/host comparisons. Expected behavior is produced
by the JVM oracle, not recomputed by the test runner. The host also checks
method/parameter names with the TypeScript AST. Host transpilation/execution
does not certify ArkTS legality or ArkVM behavior.

The three `Invalid*.kt` inputs intentionally have no valid non-null proof:
direct nullable comparison, direct nullable member access, and a proof used
outside its guarded block. Both actual JVM compiler and public CLI must reject
them, identify the input file, and publish no output. These are frontend
rejection tests, not runtime or target-flow mutation tests. Explicit `!!` is
not used as a substitute for flow evidence. Main owns any forged-IR/target
negative needed to prove the backend itself cannot invent a non-null binding.
