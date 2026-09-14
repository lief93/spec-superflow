# R2E serialized member inline bodies

## Supported loading boundary

`BinaryBodies` now admits actual Kotlin 2.1.20 serialized IR on a top-level,
non-generic, stateless final class. A selected non-reified/non-generic inline
member may call another supported inline member. Default arguments and caller
receiver/argument evaluation stay in the official inliner's responsibility.

The implementation reuses `JvmIrDeserializerImpl`, the official symbol table,
public signature computer and common function inliner. It seeds original FIR
receiver/class/function symbols and validates their identity after decoding.
Provenance comes from the binary's real `SourceFile` record and serialized body
offsets; unavailable line tables are not invented.

Ordinary class members are removed from the loader's canonical intrinsic set for
these admitted owners. An inline body calling an ordinary method must reject,
not silently assume that its body is already linked. Class state, inheritance,
inner/generic/value/data classes, member extension/context receivers, reified
bodies and binary constructor calls remain outside this finite increment.

## Loading is not class replacement

No external class is emitted as a guessed empty source class. A consumer retaining
the binary receiver type still needs a supported target implementation/type
mapping. `Replay.kt` uses the existing public `CallRule.mapType` boundary with
explicit test-host stateless receiver types in `Receivers.ets`. The adapter does
not provide any inline method's computation; those computations come from the
serialized bodies. This proves the embedding API composition, not a new command
line project-adapter loader. Unmapped command-line generation must still reject.

## Tests and evidence

```sh
node tests/binary-bodies/r2e/run.mjs
node tests/binary-bodies/r2e/replay.mjs tests/binary-bodies/r2e/.work/run-REPLACE
```

The focused test builds real producer JARs and removes the producer source copy
before consuming them. It now checks eight official inline blocks, canonical receiver
identities, signature-only refusal, six unsupported member cases and a missing
`SourceFile` diagnostic. A separate JVM oracle records argument/callback order.
The target replay compares the same inputs and effect trace using generated ETS
through the full typed tree/validator/printer plus explicit receiver replacement.

Initial `run-TnLR6Q` failed compiling the test harness because its frozen inputs
omitted the shared target validator. `run-CZBNJh` includes that dependency and
passed the focused loading checks. This is not host/SDK/device evidence.
The immutable pre-edit source run `run-qHTGSH` reproduced the old explicit
top-level-only rejection. The first target replay, `run-CZBNJh/replay-szE9s7`,
then exposed an official inliner local named `this`. The language binder now
recognizes that exact inlined-parameter origin and renames only the generated
receiver binding; the target validator was not relaxed.

`run-CZBNJh/replay-lgYLzV/result.json` passes three JVM/host pairs after that fix,
including receiver and named-argument effects, defaults, callbacks and Int
overflow. Original method/parameter names are retained. The replay also proves
that the ordinary CLI refuses the unmapped external receiver rather than
publishing a guessed class. Implementation hashes are unchanged during replay.
Final refreshed focused evidence is `run-NKWEt6/complete.json`; it uses the
corrected harness, real rebuilt producers and a frozen core/target snapshot.
`run-NKWEt6/replay-hn4M5d/result.json` again passes all three JVM/host pairs with
the frozen full backend, explicit receiver mapping and unmapped-CLI rejection.
No SDK/device or arbitrary binary-class translation is claimed. The historical
top-level binary overload replay is a separate affected-module regression.

Independent review requested a default expression that uses the receiver and an
earlier parameter, not only `right = 2`. The existing literal-default case stays;
`dependent(left, right = finish(left), action)` adds omitted and explicit paths
with effectful receiver/arguments/callbacks. Fresh `run-8BBxfT/complete.json`
passes the real binary loading checks (five direct, three transitive expansions),
canonical symbols, original JVM effect traces and all seven boundary checks.
`run-8BBxfT/replay-BFfK4x/result.json` passes all three full-backend JVM/host
pairs, including the default expression, trace, overflow and explicit-path
override. The unmapped CLI still rejects; no SDK/native claim is added.
After the source-accessor default-slot correction, refreshed final-backend
`run-8BBxfT/replay-pv2Q7C/result.json` again passes those three pairs and the
unmapped-CLI guard, with immutable production hashes.
Final accessor-name allocation is covered by `run-8BBxfT/replay-lQQe6j/result.json`,
again passing the same three JVM/host pairs and unmapped-CLI rejection.
