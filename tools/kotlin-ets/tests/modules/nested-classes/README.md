# Nested class module contract

Run from the repository root only with main's exclusive compiler grant and all
production writers frozen:

```sh
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/modules/nested-classes/run.mjs
```

The runner freezes every production Kotlin source, fixtures, and compiler script;
guards their hashes before and after each child; and uses two JVM processors and
SerialGC. It builds an independent original-source JVM oracle before the target
probe, then checks fifteen outcomes in both flat and multi-file host execution.
The SDK's TypeScript parser/transpiler is used for host execution, not an SDK build.
Generated ETS is not edited. Reverse source input order must preserve module bytes.

The fixture contains eleven classes/interfaces and five required fresh names:
lexical Node/Cell collisions, a top-level Node, two noncapturing Local declarations,
an independently bound generic Local, and an existing top-level interface whose
emitted binding collides after class flattening. Node_0 and Local_0 remain unchanged
source functions. Properties, methods, constructor calls, generic arguments and
instanceof class values retain canonical source identities. Local classes must
not be exported; member and parameter names must not change.

Bindings.kt adds eleven malformed typed-target cases with exact diagnostic spans,
plus positive output ownership independent of source provenance and a renamed
interface's type/member import. Core owns proof of original lexical provenance,
capture rejection and effective visibility before lifting. This lane checks IR
names/offsets/binders immediately before versus after language lowering.

Optional RED replay accepts a compatible preserved backend root containing src/:

```sh
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/modules/nested-classes/run.mjs \
  --baseline-root /absolute/path/to/pre-lifting-backend
```

That snapshot must include the agreed class sourceName API but predate class
lifting. The original JVM must succeed and the target must reject nested/local
classes before publishing output. No RED or GREEN execution is claimed by test
preparation alone. No inner/capturing classes, anonymous objects, new inheritance
semantics, SDK/native acceptance or whole-R2 closure is claimed.

## Focused evidence

`.work/green-bM9IEq/result.json` passed against frozen core/target inputs: eleven
source classes/interfaces, five fresh names, original IR names/offsets/binders,
fifteen JVM outcomes in each output mode, deterministic module bytes, and eleven
typed negatives with exact diagnostic spans. All source/input/snapshot hash guards
passed. The preceding `.work/green-bVy9Zd` is retained: it reached the positive
ownership check after the language checks and all negatives, then exposed two
incorrect single-quote expectations in this new test. Only those test expectations
changed to match the printer's existing double quotes before the successful run.
No pre-lifting RED replay, SDK or native run was performed by this lane.

## Review fix: lexical class values

ClassNaming now checks actual class-value uses against their emitted lexical
scopes. Parameters and local bindings keep their names; only an unsafe class
spelling receives an official NameTable fresh name. For equal class names, an
unshadowed declaration can retain the original spelling instead of renaming the
whole group. Transparent statement composites and block-wide const/let shadowing
are included. Unrelated functions, sibling blocks and type-only uses do not force
renames. Core declaration ordering is not changed by this lane.

The separate shadow fixture covers parameter/local/initializer/later-declaration
shadowing, nested blocks, closures, constructor property initialization and
instanceof, plus preservation controls. It requires 55 independent JVM outcomes
to match both flat and module execution. The old GREEN backend is retained for
an executable RED: original JVM result(7) is 7, while both old output modes must
throw the specific Node constructor TypeError. Generated files are never edited.

Only after main grants the compiler slot:

```sh
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/modules/nested-classes/shadow.mjs \
  --baseline-jar tools/kotlin-ets/tests/modules/nested-classes/.work/green-bM9IEq/backend.jar
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/modules/nested-classes/shadow.mjs
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/modules/nested-classes/run.mjs
```

Focused verification passed with frozen production inputs:

- `shadow-red-NrNISv`: the minimal reviewer constructor case returns 7 on the
  original JVM and throws `Node is not a constructor` in both unchanged baseline
  output modes. The pre-fix `green-bM9IEq/backend.jar` and its evidence are unchanged.
- `shadow-green-Ableh3`: all 55 JVM outcomes match each output mode, with one
  required fresh class name, unchanged parameters/locals, canonical identities,
  and deterministic cross-file imports under reversed source input order.
- `green-wl8Wgl`: the original 15 JVM outcomes match each output mode, all eleven
  typed negatives retain exact source checks, and module bytes remain deterministic.

All source/input/snapshot hash guards passed. The initial RED attempt
`shadow-red-PqSDMs` is retained: the broader instanceof fixture hit the old
validator's existing `Unbound target symbol: Node` rejection before emission.
RED runtime replay therefore uses the reviewer's minimal constructor case;
the broader cases remain mandatory GREEN coverage. No production code changed
during these three checks. No SDK/native tests, review or commit were run.
