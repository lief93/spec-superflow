# Local Class Value Captures

This is the finite R2G language consumer proof, paired with main's core guard
proof. It does not establish completion of R2 or SDK/native acceptance.

## Contract

`Models.kt`, `Cases.kt`, and `Consumer.kt` exercise six named local classes:
immutable capture and property initialization; shared mutable state across two
instances, a lambda, and independently created closures; source object mutation;
replacement of a captured object through its shared cell; named/default argument
and initializer effect order; generated field/parameter collisions with source
`$seed` and `$seed_0` bindings. `Oracle.kt` executes all six scenarios for zero,
negative, ordinary positive, and both signed Int boundaries.

`Probe.kt` consumes actual lowered Kotlin IR and checks seven official capture
fields against typed ETS field/member identities, constructor parameter symbols,
exact source spans, source names, private module ownership, and canonical shared
cell/object types. Its eight mutated-IR negatives preserve exact diagnostic source
checks: same-text unofficial field origin, nonlocal owner, static storage, mutable
capture storage, late capture prefix, unofficial prefix, a source parameter in
place of the bound capture parameter, and an incorrect receiver. Each mutation is
restored; emitted artifacts come from the original unmodified target program.

The runner snapshots and hashes all production Kotlin sources, test inputs, and
the compiler launcher. It guards live and frozen bytes before and after every
child. Only the preserved language file is replaced in baseline mode: current
core lowering still produces real official captured fields. Generated ETS is
parsed/transpiled directly by the installed SDK TypeScript implementation for
Node execution, without editing its bytes. This is host parity, not an ArkTS
typecheck or actual SDK build.

## Commands

Run from `tools/kotlin-ets` only after main grants the exclusive compiler slot:

```sh
KOTLIN_ETS_BUILD_SLOT=1 node tests/local-classes/captures/run.mjs --baseline-language tests/modules/nested-classes/.work/green-wl8Wgl/frozen/src/language/LanguageLowering.kt
KOTLIN_ETS_BUILD_SLOT=1 node tests/local-classes/captures/run.mjs
```

Every JVM uses `-XX:ActiveProcessorCount=2 -XX:+UseSerialGC`.

## Evidence

- `.work/red-sNZMI1`: retained probe compilation failure because an initial test
  attempted to subclass final `IrDeclarationOriginImpl`; not semantic RED.
- `.work/red-9bnwut`: original JVM produced 30 outcomes; preserved R2F language
  rejected the actual captured field at `Cases.kt` offsets 67..188 before output.
- `.work/green-fEhNxA`: six local classes/seven capture fields, eight source-linked
  negative cases, three modules with resolved exports/imports, and all 30 JVM
  outcomes matched independently in flat and multi-file execution. Source
  `$seed` and `$seed_0` were preserved; only colliding generated capture field and
  constructor parameter became `$seed_1` using official symbol-keyed NameTable.
- `tests/modules/nested-classes/.work/green-rHTaeq`: affected noncapturing
  constructor/declaration regression, 15 JVM outcomes matching flat/modules,
  11 typed negatives, and byte-identical modules after reversed source inputs.

The GREEN production `LanguageLowering.kt` SHA-256 is
`1d5974b1dcc05de16cf22e47f4c9be8f9d4c5bcf4e8aeec31ead14c1d288afe7`.
Each result manifest records the complete production hash set and commands.

Captured outer type parameters, inner/anonymous classes,
and captured classes with a non-Any supertype remain excluded. Unique-root
secondary construction is covered separately in `../../../docs/constructor-captures.md`.
Core owns those eligibility rejections. No shared target API, arbitrary raw field acceptance,
source-string rewrite, SDK/native run, or round-completion claim is introduced.

## R2G Review Fix: Emitted Binding Shadows

`shadow/Global.kt` and `shadow/Overload.kt` are byte-identical to the fixed
reviewer's repros. The former catches a retained generated parameter shadowing
the source `$seed()` function. The latter catches a fresh parameter shadowing
the officially emitted overload binding `$seed_0`. `shadow/imported` splits the
second shape across two source files to check the actual named import. All three
original JVM cases return 17 for seed 7; five signed Int inputs are compared in
both flat and module execution.

`ShadowProbe.kt` checks generated parameter names, canonical helper-call symbols,
original function/source parameter names, and exact call source on baseline
rejection. `shadow.mjs` snapshots and guards inputs using the same low-CPU policy
as the original runner. It performs no generated-source rewriting or SDK build.

```sh
KOTLIN_ETS_BUILD_SLOT=1 node tests/local-classes/captures/shadow.mjs --baseline-language tests/local-classes/captures/.work/green-fEhNxA/frozen/src/language/LanguageLowering.kt
KOTLIN_ETS_BUILD_SLOT=1 node tests/local-classes/captures/shadow.mjs
KOTLIN_ETS_BUILD_SLOT=1 node tests/local-classes/captures/run.mjs
```

- `.work/shadow-red-h3o8XO`: all three JVM cases execute; the frozen R2G language
  consumer rejects the canonical helper reference at its exact source before
  either flat or module emission. Previous evidence is retained unchanged.
- `.work/shadow-green-xtyLVs`: all 15 JVM outcomes match flat/modules; exact
  source names and canonical helper symbols remain unchanged. Global capture
  uses `$seed_0`; overloaded and imported cases use `$seed_1`, reserving the
  actual emitted `$seed_0` helper binding.
- `.work/green-I5AG8s`: original capture suite rerun with the corrected allocator;
  all 30 JVM outcomes match flat/modules and all eight source-linked negatives
  remain GREEN, including shared mutation, defaults/effects, and source collisions.

The correction adds official root function/class names to both stable-name
collision checks and fresh-name reservations. It does not rename source IR or
change overload allocation. Corrected `LanguageLowering.kt` SHA-256:
`811609674c8517ac016969e03674e548b377f99c6c1ac8390e687dd4dbb1d4ba`.
