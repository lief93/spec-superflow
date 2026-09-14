# Independent Kotlin/ETS First Slice

Core is official Kotlin 2.1.20 compiler objects on the JVM, before Compose runtime
lowering. No JavaScript intermediary or legacy JSON input. Diagnostic JSON is an
optional output only. Existing Skill and accepted prototype trees are read-only.

Integration owner: shared interfaces, CLI and whole-module integration.
Frontend worker: core/Frontend.kt, official passes and dependency body loading.
Language worker: src/language/, tests/language/.
Stdlib worker: src/stdlib/, tests/stdlib/.
Target/output worker: src/target/, src/output/ and typed UI target integration.
Verification worker: verification/ only, including host/build/device harness.
No worker edits another owner's files. Shared Contract.kt changes go through the
integration owner. Kotlin package is dev.ets across source directories.
See docs/shared-contracts.md for the minimum agreed API and explicit remaining
work. Framework adaptation must use those APIs, not a second language backend.

Public seams: source-to-ETS CLI, generated language execution, real ArkUI SDK
compile, and actual paired fixture state/interaction. Source text snapshots do
not replace runtime assertions. Unsupported constructs fail closed with offsets.

Shared interface: Language handles typed IrExpression/IrBody/declarations. CallRule
handles exact resolved library symbols. Scope is lexical symbol binding/aliasing,
not string source parsing. UI maps typed calls, lambda slots and ordered modifier
receivers. Root generator produces a single generated page plus helpers preserving
source method/parameter names. Transient compiler-generated names may be normalized
only by declaration identity/origin, never by fixture-name specialization.

Required devices: adb emulator-5560; hdc 127.0.0.1:15557. Do not operate any other
device. Never use AI screenshot/image inspection. No commit/push/cache sync.
