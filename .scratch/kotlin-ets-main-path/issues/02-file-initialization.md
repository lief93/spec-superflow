# Nonconstant top-level initialization

Status: needs-triage
Blocked by: none (01 and 01b accepted)
Review: deferred by user

Common object, list and function-call initializers are currently rejected.
This is a real missing capability, not a missing arithmetic or constructor parser.

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
