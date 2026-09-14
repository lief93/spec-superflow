# Backend Contract Results

Pending final freeze: the source-call binding assertion was added after the
GREEN run below. It matches actual resolved source calls to their target call
spans and requires external=false plus equality with EtsFunction.symbol. Prior
lexical identity/capture checks are unchanged. This addition has NOT been run;
waiting for worker/integration stability confirmation, with no SDK/device work.

Command: `bash tools/kotlin-ets/tests/backend/run.sh`

GREEN evidence directory:
`/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-backend-tests.c4vwhP`

- Both real official-IR fixtures pass the typed AST/source/default/control/object
  and lexical symbol/capture checks. No IR mock or Compose input is used.
- Lowering compiles and executes without any Printer class on its classpath.
- Injected CallRule matches the actual resolved function symbol, returns a wrong
  STRING type for an Int call, and is rejected by lower at the exact source call
  without returning an EtsProgram. Both original and renamed fixtures pass.
- Separately compiled Printer prints the same AST deterministically across ten
  repetitions with reused and fresh instances, without AST mutation.
- JVM and printed-target host execution match all ten values: original
  `346,751,2266`; renamed/changed inputs `369,774,2289`; explicit/default ordinary
  calls `247,281,469,423`.
- Input SHA256 stability check passes, including production, test and cached
  compiler dependencies. Input manifest SHA256:
  `a07f186020febb3731782758a8ac294e982a68a0efbda50812d1278c3ff6b430`.
- Runtime: cached official Kotlin2.1.20, OpenJDK21.0.7, Node22.19.0. Exact commands,
  exits, output streams, generated target and input hashes remain in evidence.

RED history is retained: Arbpfi exposed the in-progress lowering type migration;
iWxgt7 passed lowering but exposed Printer.kt cross-module smart-cast illegality.
The integration owner fixed the latter with a local condition value. This test
owner did not edit production or merge modules to bypass the failing boundary.
kJyXzQ also records a corrected test assumption: external Math symbol references
carry per-use source spans, so identity/source equality applies to lexical
symbols, not globally to all external references.

Scope is module architecture and ordinary host execution only. No SDK build,
device mutation, page work, screenshot, commit, push or cache synchronization.
This does not claim full Kotlin/ETS compatibility or native SDK acceptance.
