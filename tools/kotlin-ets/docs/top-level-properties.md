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

Delegates, `lateinit`, external storage and nonconstant
initializers remain unsupported with source-linked diagnostics. In particular,
`val page = loadPage()` must not become eager module initialization without
preserving Kotlin initialization timing. This increment does not implement
general file initialization or make plain globals reactive Compose state.

## Official reference and reuse

The official common `PropertiesLowering` separates properties into backing
fields and accessors. The JS `PropertyLazyInitLowering` separately handles
initialization timing. These clarify why declaration storage and initialization
effects are different responsibilities.

Our frontend supplies the resolved `IrProperty`, `IrField` and accessor symbols.
The ETS backend maps these into its typed tree and owner-file access rules.
Neither referenced pass is installed by this increment: removing all properties
would disrupt current class-property consumers, while JS lazy initialization
depends on its own backend context and runtime. No source-string matching or
page-specific expression path is introduced. Compose module declarations use
the same property lowerer as ordinary language mode.

## Verification

Run from the repository root:

```sh
node tools/kotlin-ets/tests/language/globals/run.mjs
node tools/kotlin-ets/tests/language/computed/run.mjs
bash tools/kotlin-ets/tests/target/run.sh
bash tools/kotlin-ets/tests/backend/run.sh
```

The global-state runner compares 26 JVM results against flat and multi-file
output, checks deterministic reversed-source imports and original names, and
verifies call initializers fail without publishing ETS. The former custom-accessor
boundary is promoted to the property runner's supported coverage. Fixtures
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
