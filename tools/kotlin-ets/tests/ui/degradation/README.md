# Bounded UI degradation

Page generation defaults to `--unsupported-policy report`, including the
`--project` launcher. Use `--unsupported-policy error` for strict conversion.
Language mode remains strict and rejects report mode.

The generated target has a sibling `<output>.diagnosis.json`, also when a later
compiler failure blocks output. For `--out-dir`, the report is alongside that
directory, not mixed into generated source files. Existing reports are never
overwritten. Argument validation failures before an output is selected and
Gradle collection failures keep their existing CLI diagnostics/logs.

The report records source file, line/column and offsets, resolved capability,
omission action and impact. `generated_with_degradations` means usable candidate
output, not semantic or visual equivalence. `blocked` includes the blocking
failure and omissions recorded before it. Counts are diagnostic occurrences,
not a complete pre-scan of every unsupported dependency.

Recovery boundaries:

| Situation | Behavior |
| --- | --- |
| Explicit Text/BasicText `softWrap` or `minLines` | Omit the argument and its evaluation; use target defaults |
| Unknown resolved Modifier operation | Omit that operation and its arguments; retain other operations |
| Unclaimed external Unit call in UI position | Omit call, argument evaluation, callbacks and nested UI; retain siblings |
| Required value, unknown condition, source helper failure | Block; never fabricate values or choose branches |
| Claimed adapter rejects an argument, frontend error, invalid target | Block; no broad exception suppression |

This is deliberately not general Kotlin error recovery. In particular, skipping
`SideEffect` does not remove preceding local initializers such as `LocalView.current`.
`Build.VERSION.SDK_INT` used as a condition/value still requires a supported
translation or proven specialization. It is not replaced with an invented number.
Compiler temporaries used exclusively by omitted arguments are removed along with
their evaluation, including Kotlin's named-argument reordering temporaries.
Explicit source locals are retained even when a later UI argument is omitted,
except a private immutable Modifier whose consumers are all explicitly omitted:
its construction and argument evaluation are separately reported and discarded.
A Modifier shared with retained UI still propagates its original failure; it is
never substituted with an empty value.
The bounded [native project-theme projection](../theme-projection/README.md) is
an explicit exception: Android-version-dependent MaterialTheme color setup and
SideEffect-only guards in that projected function can discard their private
immutable local dependencies. Shared UI values and conditions still block.
An unsupported temporary type is kept as source IR until consumer analysis;
it is not replaced with a made-up ETS type. Any surviving consumer still fails.

Run the public CLI regression with a real Android/Compose classpath:

```sh
node tools/kotlin-ets/tests/ui/degradation/check.mjs /absolute/path/classpath.txt
node tools/kotlin-ets/tests/ui/degradation/named-arguments.mjs /absolute/path/classpath.txt
node tools/kotlin-ets/tests/ui/degradation/modifier-local.mjs /absolute/path/classpath.txt
```

It prints an evidence directory and generated `page.ets`. Compile that file
without editing it using `tests/ui/basic-controls-sdk.mjs`. Expected UI is two
labels, `Before` and `After`; the first retains width 160 and padding 8. The
progress indicator, blur and side effect are explicitly reported omissions.
The named-argument test executes generated builder calls with a Text observation
stub: omitted `wrapping()` leaves its counter at zero, while an explicit source
local still increments it. It also tests an omitted AnimatedVisibility argument
whose EnterTransition type is unsupported, and an explicit local that must still
fail. This host behavior check does not replace SDK testing.
