# R2E serialized member inline bodies

## Supported loading boundary

`BinaryBodies` now admits actual Kotlin 2.1.20 serialized IR on a top-level,
non-generic, stateless final class. A selected non-reified inline
member may call another supported inline member. Default arguments and caller
receiver/argument evaluation stay in the official inliner's responsibility.

R2.2 extends this same route to method type parameters. The existing shared
registration seeds each parameter using its official parent signature/index;
the official deserializer and common inliner perform loading, erasure and
call-site substitution. There is no ETS-specific generic substitution algorithm.
Checks now also require the original parameter parent and index after decoding.
Tests compose a generic member, generic helper, a default referencing an earlier
generic parameter, Int/String/nullable-String instantiations and callback effects.

The implementation reuses `JvmIrDeserializerImpl`, the official symbol table,
public signature computer and common function inliner. It seeds original FIR
receiver/class/function symbols and validates their identity after decoding.
Provenance comes from the binary's real `SourceFile` record and serialized body
offsets; unavailable line tables are not invented.

The shared source-owner query excludes official deserialized class/facade
sources, including their members. Their IR provenance file exists for inlining
and diagnostics; it does not make the binary an input-source class. Without an
explicit receiver mapping, the ETS backend reports the unsupported source type
and caller span instead of trying to name/emit a fabricated class.

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

### R2.2 generic member increment

- `run-2DADsf`: genuine RED; producer/JVM oracle succeeded but production rejected
  `FinalMember.choose` at the old generic-member guard.
- `run-OxFwNr`: 14 official inline blocks passed. `replay-PWQ67z` matched the
  three JVM/host results, then failed the unmapped-receiver negative with an
  internal uninitialized-module error. It is not a passing replay.
- Root cause: `sourceFile` treated a deserialized owner's provenance file as a
  source input, so ETS class naming accessed an absent source module. Fixed the
  common owner query, not by inventing a source module or relaxing rejection.
- `run-NXPH8l`: frozen body/receiver/type-parameter identity, source-ownership
  checks, signature-only and seven existing unsupported cases pass. Producer
  source copies are removed before consumers run.
- `run-NXPH8l/replay-WWI5My`: unchanged full backend, explicit receiver adapter,
  strict host typecheck and three same-input JVM/host results pass. The public
  unmapped CLI returns `UNSUPPORTED` with the exact source file/parameter span
  and creates no output. `replay-TsTO3P` is the preceding passing host replay
  without the newly added strict host typecheck.
- `../.work/policy-fIaIGJ`: existing top-level binary body/default/callback path
  still passes actual loading, missing-body/source checks and two public-CLI
  JVM/host pairs after the shared source-owner correction.
- `tests/language/.work/typed-5CBsdl`: source declarations and shared adapter
  value/statement/UI contract regression passes.
- No SDK/native result or generic binary-class support is claimed. KLIB loading,
  additional bounds/receiver shapes and general dependency linking remain R2.2
  work; this is not completion of that row.

```sh
node tests/binary-bodies/r2e/run.mjs
node tests/binary-bodies/r2e/replay.mjs tests/binary-bodies/r2e/.work/run-REPLACE
```

The focused test builds real producer JARs and removes the producer source copy
before consuming them. It now checks fourteen official inline blocks, canonical receiver
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
