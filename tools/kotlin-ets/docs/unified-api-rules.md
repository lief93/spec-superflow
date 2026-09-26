# Unified API rule dispatch

> Historical record. The production page path no longer consumes
> `CallRule.lowerUi` or `ComposeLowering`. New Compose controls belong in the
> neutral widget adapter/model and the Harmony widget backend. `CallRule.lower`
> remains the shared typed value/platform API mechanism.

The current production contracts are documented in
[`widget-semantic-pipeline.md`](widget-semantic-pipeline.md) and
[`shared-contracts.md`](shared-contracts.md). `CallRule.lower` and
`lowerStatement` remain the value/effect hooks used by the language backend.
`lowerUi` is retained only for old adapter binaries; page mode never consults it.

```text
resolved Kotlin IR
    -> shared language lowering for declarations, values and effects
    -> ComposeWidgetAdapter / project ComposeWidgetRule
    -> neutral Widget tree
    -> HarmonyWidgetBackend
    -> typed EtsProgram, validator and printer
```

## Ownership

- `language/LanguageLowering.kt`: Kotlin names, parameters, defaults, visibility,
  generics, ordinary values and effects.
- `ui/compose/ComposeSourceFunctionLowering.kt`: requests shared function
  lowering and supplies only Builder, slot and neutral UI-body semantics.
- `ui/compose/ComposeWidgetAdapter.kt`: resolved Compose calls to neutral widgets.
- `ui/compose/ComposeWidgetRule.kt`: project/framework extension SPI targeting
  neutral widgets, never ArkUI statements or source text.
- `ui/harmony/HarmonyWidgetBackend.kt`: the only control/modifier target mapper.

Do not add an external control through `CallRule.lowerUi`. Add source-framework
recognition to the Widget adapter, a neutral Widget/Modifier node when needed,
and target rendering to the Harmony backend. Ordinary values and effects still
use `CallRule.lower` and `lowerStatement`.

Ordered Modifier application and remembered-state declarations retain specialized
framework structure handling. This increment does not claim that all UI-specific
algorithms have disappeared or that every responsibility is already extracted
from the coordinator. The follow-up [basic controls](compose-basic-controls.md)
increment adds controls without changing source naming policy.

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
