# Unified API rule dispatch

The language backend and Compose now use the same resolved-call interface and
dispatcher, rather than one library rule pipeline plus a separate UI API switch.

```text
Resolved Kotlin IrCall + lexical Scope + CallContext
    -> adaptCall
       scoped override -> scoped rules -> backend rules
    -> Value | Statements | Ui
    -> existing typed target tree and validator
    -> existing printer and module output
```

`CallRule.lower`, `lowerStatement` and `lowerUi` are typed hooks for different
uses, not independent pipelines. `null` declines; an empty statement/UI list is
explicitly handled. Value result types are checked even if discarded. UI hooks
must handle Unit-returning calls; ordinary void/effect results are not inferred
to mean UI content. Each applicable rule is consumed once; scoped forks retain
the ordered registrations. Unknown Compose values can reach backend rules rather
than being rejected solely by their framework package prefix.

## Ownership

- `core/Contract.kt`: contexts, results, rule interface, priority and consumption.
- `language/LanguageLowering.kt`: ordinary language lowering and source fallback;
  calls the shared dispatcher, without its former private adapter type checker.
- `ui/ComposeControlRules.kt`: independent layout, text and button rules. Each
  receives the specific content/value/modifier operations it needs, not the
  entire mutable ComposeLowering object.
- `ui/ArkUiCalls.kt`: typed target API signatures/construction, no output strings.
- `ui/ComposeLowering.kt`: source method/state/slot orchestration; registers UI
  rules and requests UI adaptation through the shared dispatcher. Pager/repeat
  and source slot invocation use that same registration path.

To add an external control, implement a `CallRule.lowerUi` rule using resolved
symbols and typed nodes, then register it with the backend. Implement value or
effect hooks on the same rule where the API family needs them. The test
`tests/ui/UnifiedApi.kt` + `TypedBoundaryProbe.kt` shows one backend registration
handling actual Compose HorizontalDivider and currentCompositeKeyHash calls.
That probe is not a production Divider mapping or a plugin-loader feature.
Built-in scoped rules have priority over backend rules; unsupported arguments of
an already claimed API still reject rather than bypassing its checks.

Ordered Modifier application and remembered-state declarations retain specialized
framework structure handling. This increment does not claim that all UI-specific
algorithms have disappeared or that every responsibility is already extracted
from the coordinator. No new control coverage or source naming policy is claimed.

## Focused verification

- `tests/language/.work/typed-fbv88f`: actual official IR tests for rule ordering,
  context isolation, value checking, handled-empty results and source diagnostics;
  existing binding/default/body-lifetime checks passed. The earlier compile RED
  `typed-jYYVrB` also exposed a missing Traversal.kt test compile-list entry; that
  harness dependency was repaired, not a target semantic failure.
- `$TMPDIR/kotlin-ets-typed-ui.WuXijI`: existing state/slot/Pager/touch/runtime tests,
  detached target validation, and an actual Compose value/UI shared registration
  test all passed with Printer.kt/Main.kt/output code absent.
- `/tmp/kotlin-ets-unified-api.wC45Yk/Page.ets`: current public CLI generation
  is byte-identical to the accepted native-06 generated Page.ets. Both SHA-256:
  `4ec023d7a5fcf3e9a7ff4b6c4669a7633e35008fe38d043f443b38930d0cef89`.

The last check proves unchanged generated code for that fixture, not a fresh
native run or broad framework equivalence. No SDK/install/visual regression,
private Onboarding validation, review, commit or push was performed.
