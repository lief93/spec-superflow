# Top-level properties

## Contract

Ordinary source `val` and `var` declarations with default accessors and an
official IR constant initializer lower to `EtsGlobal`. This includes primitive,
string and nullable constant values supported by the existing type lowerer.
Names and source identities are retained. Functions read the shared storage;
local variables and class fields keep their existing lowering.

Private storage is not exported. A visible mutable property with a visible
setter gets a source-linked `__etsSet_<property>` bridge. Writes use this bridge,
including writes originally in the owner source file: UI slot methods can later
move to the entry component's target file, where imported bindings cannot be
assigned. Reads still use the original variable name. Private setters use direct
owner-file writes and do not get exported bridges. Moving a private-storage
access across target files remains a diagnosed visibility/ownership limitation.
A bridge name collision is
diagnosed by the existing target declaration validator, not silently renamed.

For example, source `var currentPage: Int = 0` produces owner-file storage and
a setter bridge; a different file's `currentPage = next` calls that bridge.
The target validator also rejects malformed trees that write imported storage
directly or assign immutable storage.

Computed top-level properties without backing storage emit source-linked ordinary
functions `__etsGet_<property>` and `__etsSet_<property>`. Their original accessor
bodies, setter parameter names and calls pass through the existing language
lowerer. Every read invokes the getter; no backing field or cache is invented.
Private accessors are not exported. These functions are necessary because ETS
has no standalone top-level getter/setter declaration syntax; class accessors
retain their original property syntax.

Stored custom accessors use the same accessor functions plus private owner-file
`__etsField_<property>` storage. Explicit IR field accesses bypass the functions;
property calls invoke them, including default counterparts. A constant initializer
writes the storage directly without running the setter. Private setters stay
private even when the getter is visible. Computed, stored-custom and default
stored properties all use the same resolved IR and expression/body lowering.

Nonconstant source initializers (ordinary function calls, objects and lists) use
one owner-file initialization function. The first top-level function, getter or
setter invocation runs that file's non-const initializers in declaration order.
Imports publish only inert default storage; they do not run source effects.
Accessing another file goes through its accessor/function and initializes that
dependency on demand. Helpers called during their own file's initialization may
re-enter and read fields already assigned, without starting initialization again.
Ordinary class construction alone does not initialize the surrounding file.

Initialized storage is private and gets getter/setter functions even for default
accessors. Reference storage starts nullable and is exposed with its original
declared type after the guard. User method and parameter names are retained.
Top-level default arguments in this family reuse the official common default
stub generator/injector: initialize the owner before evaluating omitted arguments.
Explicit arguments still evaluate in the caller first. Getter and setter symbol
identities remain distinct even when the official IR gives them equal offsets.

An initialization failure marks the file failed before propagating an
`ExceptionInInitializerError`; a subsequent entry raises `NoClassDefFoundError`
without retrying source effects. Dependency initialization failures are propagated
without wrapping them again. These supported categories use the shared typed
target Error construction, not a separate raw-text exception emitter. Full Kotlin
exception inheritance, source try/catch/finally lowering and general cyclic
initialization are not implemented by this slice.

Delegates, `lateinit` and external storage remain unsupported. Compose builders
in a nonconstant-initialized file explicitly require a future lifecycle-entry
bridge; ordinary language dependency files use the same guards in Compose mode.
Plain globals do not become reactive Compose state.

## Official reference and reuse

The official common `PropertiesLowering` separates properties into backing
fields and accessors. The JS `PropertyLazyInitLowering` separately handles
initialization timing. These clarify why declaration storage and initialization
effects are different responsibilities.

Our frontend supplies the resolved `IrProperty`, `IrField` and accessor symbols.
The ETS backend maps these into its typed tree and owner-file access rules.
Neither referenced property pass is installed by this increment: removing all properties
would disrupt current class-property consumers, while JS lazy initialization
depends on its own backend context and runtime. No source-string matching or
page-specific expression path is introduced. The existing common default argument
pass is extended to ordinary top-level providers needing initialization timing;
its function bodies, mask dispatch and IR substitution are reused. Compose module
declarations use the same property lowerer as ordinary language mode.

## Verification

Run from the repository root:

```sh
node tools/kotlin-ets/tests/language/globals/run.mjs
node tools/kotlin-ets/tests/language/computed/run.mjs
node tools/kotlin-ets/tests/language/initialization/run.mjs
# Pass the successful initialization evidence directory to the SDK runner:
node tools/kotlin-ets/tests/language/initialization/sdk.mjs <evidence-directory>
bash tools/kotlin-ets/tests/target/run.sh
bash tools/kotlin-ets/tests/backend/run.sh
```

The global-state runner compares 26 JVM results against flat and multi-file
output, checks deterministic reversed-source imports and original names, and
retains constant-global behavior. The former custom-accessor boundary is promoted
to the property runner's supported coverage; the original Initialized.kt refusal
is now executed by the initialization runner. Fixtures
include private storage/setters, nullable storage, repeated resets, default
arguments and a global named `value` to catch generated-parameter shadowing.
An additional two-file Compose fixture validates a relocated slot callback and
replays its actual lowered body to verify updates reach the owner-file storage.
Inputs, outputs and process logs are recorded under the runner's `.work` folder.

Target tests exercise the shared declaration, traversal, printer and validator.
These are host semantic/type checks, not Harmony SDK, device or UI acceptance.

Computed-property evidence: `tests/language/computed/.work/run-ZZulpa` compares
54 flat and 54 multi-file results with Kotlin/JVM, with deterministic reversed
input order, strict host type checking, original setter names and no invented
storage. Delegated and extension properties remain source-linked refusals.
RED `run-Wcc1qn` reproduced the old storage guard before the change.

The expanded runner `tests/language/computed/.work/run-mclwVi` passes 73 flat
and 73 multi-file JVM/host results across four source files. It also compiles and
executes the original `globals/Accessor.kt` refusal as a supported input. Checks
cover private backing storage/setters, default counterparts, class-method access,
initialization without setter invocation and original setter parameters. Stored
custom-accessor RED evidence is `computed/.work/run-J27awx`.
Final stored-global regression `globals/.work/run-cviFMO` retains 26 flat/module
results, deterministic imports and relocated Compose callback replay.

File-initialization evidence: `initialization/.work/run-Wneg2b` passes 34 flat
and 34 module JVM/host results across eight source files, strict host types and
reversed-source determinism. Default-order RED `run-k7Fcls` records `EDACB` versus
JVM `DACBE` before the official default-dispatch fix. Final SDK proof
`/private/tmp/kotlin-ets-initialization-sdk-CblocL` compiles all eight unchanged
modules as actual ETS inputs and produces ABC/HAP. No native execution claimed.
Regression evidence: `computed/.work/run-4xfIot` (73), `globals/.work/run-HTEe0N`
(26 plus callback replay), and `inheritance/defaults/.work/run-ab6TZS` (65 plus
official default-dispatch IR assertions). Full source exceptions remain pending.
