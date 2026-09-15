# Nonconstant top-level initialization

Status: accepted (bounded ordinary-language contract)
Blocked by: none (01 and 01b accepted)
Review: deferred by user

At the issue baseline, common object, list and function-call initializers were
rejected. The implementation below fills the owner-file initialization consumer,
not a new arithmetic or constructor parser.

Before claiming, specify initialization triggering, declaration order, cross-file
access, once-only execution, recursive access and failure behavior. Reuse existing
expression, class, collection and module output. The inspected Kotlin/JS
PropertyLazyInitLowering is the reference for per-file guarded initialization;
its JS-specific context is not directly installed by the ETS backend.

Do not remove the IrConst guard and silently emit eager ETS module expressions.
Reuse the round's common failure representation; do not introduce a separate
general try/catch/finally implementation as an incidental initialization task.
Acceptance must compare original JVM effects as well as returned values.

## Next implementation boundary

Official 2.1.20 PropertyLazyInitLowering was re-read from the local compiler source
archive. It gathers owner-file initializers and guards calls, but raises its
initialized flag before running the expressions. Copying that boolean alone
would falsely succeed after an initializer failure under this spec's JVM oracle.
Before file initialization is enabled, implement the minimal shared typed
exception/finalization support needed to record failure and prohibit retries;
this is a prerequisite slice of L6, not a second initialization-only try printer.
Common expression/constructor/collection bodies remain shared. Preserve ordinary
same-file initializer helper calls; do not mistake them for forbidden cycles.

## Implementation

- `language/FileInitialization.kt` gathers owner-file initializers in declaration
  order. Private inert storage plus a four-state guard preserves first use,
  initializer helper re-entry, successful once-only execution and sticky failure.
- Top-level function/getter/setter entry uses that guard. Reference storage keeps
  its public source type through typed accessors; default getter/setter source
  identities are distinguished even when their IR offsets are identical.
- Existing official `DefaultArgumentStubGenerator`/`DefaultParameterInjector`,
  body movement and type substitution now also process ordinary top-level default
  providers in initialized files. Omitted arguments run after initialization;
  expressions are not copied into a second evaluator.
- The shared target tree, walker, validator and printer gain `EtsTry`/`EtsCatch`.
  Typed Error construction supplies initialization failure categories. Kotlin
  `IrTry` consumption and a complete Throwable hierarchy remain L6 work.
- Both language and Compose module output call the same file initializer
  consumer. A Compose builder in the initialized owner file explicitly refuses
  until its lifecycle entry bridge is supported; no default layout is substituted.

## Scope boundaries

This increment accepts ordinary top-level non-inline, non-extension function
defaults plus ordinary property access and model/list initializers. It does not
claim all extension/inline combinations, pathological cyclic initialization,
custom Throwable hierarchies, source catch selection, reactive globals or native
UI behavior. SDK compilation is distinct from ArkVM runtime parity.

## Evidence

- Original missing-storage RED: initialization `.work/run-39c7M3`.
- Promoting the unchanged old `globals/Initialized.kt` exposed coincident default
  accessor identities: `.work/run-7UBSwn`. It is now a positive JVM/ETS case.
- Default-parameter order RED: `.work/run-k7Fcls`, ETS trace `EDACB` versus JVM
  `DACBE`. The official default dispatch extension fixes this at the actual
  public compiler CLI, not by editing output.
- Final language evidence `.work/run-Wneg2b`: **34 flat + 34 multi-file** JVM/ETS
  host results in six fresh-process scenarios. Objects/lists, dependent file
  initialization, own-helper re-entry, first method/read/write, default timing,
  repeated success/failure and nested failure agree. Strict host type checking,
  reversed-source determinism and input/output SHA-256 checks pass.
- Target contract suite `kotlin-ets-target-tests.XkINUa` passes, including five
  invalid catch/scope/return contracts and ordinary try/catch/finally traversal.
- Property regression `computed/.work/run-4xfIot`: 73 flat/module results.
- Globals regression `globals/.work/run-HTEe0N`: 26 flat/module results and
  relocated Compose callback replay, not native rendering.
- Default dispatch regression `inheritance/defaults/.work/run-ab6TZS`: 65 flat
  and 65 module results, three boundaries, official provider/origin/receiver
  checks and 29 IR calls.
- Earlier SDK proof `/private/tmp/kotlin-ets-initialization-sdk-PRgfGZ` compiled
  eight unchanged generated modules. Final frozen SDK run is recorded below.
- Final frozen SDK `/private/tmp/kotlin-ets-initialization-sdk-CblocL` passes:
  all eight generated modules appear in actual CompileArkTS input records;
  original/copy hashes agree, and ABC/HAP artifacts exist. Not device execution.

Self-check: inspected guard placement, getter/setter identities, declaration and
dependency order, default dispatch, target traversal/validation and unchanged SDK
inputs. Scoped diff passes `git diff --check`; no generated ETS was patched.

Independent review is deferred, not passed. All other L2-L8 acceptance remains
separate; this issue is not a completion claim for the entire approved spec.
