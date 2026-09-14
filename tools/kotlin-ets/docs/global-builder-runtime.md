# Global builder runtime dependency contract

## Scope

R1B adds standalone typed-target fixtures in `tests/stdlib/builder-modules/`.
These construct global `EtsFunction(kind = FUNCTION, builder = true)` declarations
and pass them to the existing `emitEtsModules` and `StandardLibraryRuntime`.
No production source, source parser, UI-specific runtime resolver, or alternate
declaration/reference traversal is added. Source calls reference the exact
fixture declaration symbols. Reference checks reuse `walkEts`.

This is a target/module/runtime dependency test, not evidence of Kotlin
frontend lowering, public CLI compilation, JVM/host behavioral equivalence,
actual ArkTS SDK acceptance, or device execution.

## Module contract

| Output | Exact source imports | Selected runtime functions |
| --- | --- | --- |
| `RuntimeActions.ets` | None | `__etsIntRem` |
| `RuntimeCaptions.ets` | None | `__etsSubstring` |
| `RuntimeSummary.ets` | `onRuntimeMetric` from `./RuntimeActions`; `captionForRuntime` from `./RuntimeCaptions` | `__etsIntDiv`, `__etsListFilter`, `__etsSubstring`, `__etsSubstringFrom`, `__etsArrayIterator`, `__etsListCount` |
| `RuntimeQuiet.ets` | None | None |
| `RuntimeBuilderPage.ets` | `renderRuntimeQuiet` from `./RuntimeQuiet`; `renderRuntimeSummary` from `./RuntimeSummary` | None |

Only `RuntimeSummary.ets` needs the runtime class `__etsIterator`. Its class,
array iterator factory, and count consumer must appear in dependency order.
The summary builder contains a conditional, text property expressions, numeric
attributes, a typed record/object attribute, an ordinary event callback, and
`EtsUiForEach`. Count is referenced only inside the callback. The action source
import is also callback-only, but the action module's remainder helper must not
leak into the builder's runtime closure. Repeated division/filter references
select one helper declaration each.

The quiet builder contains helper-looking string literals, including an unknown
helper name, but needs no runtime. The consuming component needs neither the
builders' runtime nor the ordinary source functions' runtime.

## Assertions

- Exactly one existing runtime provider invocation per emitted module, retaining
  its original typed file and exact assembled source imports.
- Exact helper function sets, declaration counts, class counts, and order; no
  unused quantifier or progression helpers.
- The same expression and callback nodes in an ordinary function select the
  identical runtime closure. Reversing source file order preserves output.
- Unknown owned runtime IDs and mismatched runtime ID/name pairs inside the
  callback fail closed through the existing provider.
- UI DSL inside an ordinary callback fails target validation before any runtime
  provider invocation.
- The test writes all five emitted modules unchanged only after assertions pass.

## Running and evidence

Run only after main grants the exclusive isolated target build slot:

```sh
KOTLIN_ETS_BUILDER_SLOT=1 node tools/kotlin-ets/tests/stdlib/builder-modules/run.mjs
```

The runner snapshots the required target, module emitter, runtime provider, and
fixture sources; compiles serially using installed Kotlin 2.1.20 with
`JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`; records command
outputs and SHA-256 hashes; and checks both snapshot and live inputs remain
unchanged. Unique evidence directories are under
`tests/stdlib/builder-modules/.work/run-*`. `result.json` records the test level,
inputs, commands, pass status, output directory, and module hashes.

Focused execution passed in `.work/run-lfhqvL` with all three assertion groups
GREEN and every snapshot/live-input SHA guard unchanged. Compile, classpath,
and contract commands exited 0. `result.json` records `passed: true`; exact
outputs are in `.work/run-lfhqvL/modules/`. SDK and public CLI execution remain
main-owned and were not run by this lane. No production fix was required.

| Unchanged emitted output | SHA-256 |
| --- | --- |
| `RuntimeActions.ets` | `4ecbfc32436b39863066a7bd498d7cb5cb2dd38072a63f7a1c1f064611552414` |
| `RuntimeBuilderPage.ets` | `68858f5548d133f931621c2802a6b3a6d54a2228b993bb82bae3333298f55f49` |
| `RuntimeCaptions.ets` | `2db96f7169f10c31c4e4a7834940b69cf3854f0d3b9cfb552d69b680d35528e9` |
| `RuntimeQuiet.ets` | `b5e4d5fb2e542ae3451bd3292f7bd73e0e4bd6629db46a7c74d0a50fdcf9e997` |
| `RuntimeSummary.ets` | `d88b50abb0ef679a1ce7fcaac496c1ba32beeec080271bb4b23bafe822286236` |

The exported builder signature is
`renderRuntimeSummary(label: string, values: Array<number>, expanded: boolean)`;
the second builder is `renderRuntimeQuiet()`. Both return `void` in the typed
target. `RuntimeBuilderPage.ets` is the unchanged typed consumer fixture. These
are not claims that an arbitrary Kotlin source builder, iterator implementation,
or unsupported collection representation is accepted.
