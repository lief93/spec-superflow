# Android Theme Projection

Report-mode page generation replaces an external MaterialTheme `colorScheme`
argument whose expression (including immutable local aliases) reads the resolved
Android `Build.VERSION.SDK_INT` field. The source function name is irrelevant.
The adapter participates in the common CallRule source-preparation hook before
dependency selection and official lowerings. It does not parse source strings or
invent an Android version number. An IR attribute carries the replacement through
lowering into the existing typed MaterialTheme consumer.

Content, typography and ordinary UI conditions remain. In a projected function,
standalone SideEffect trees containing only recognized Android system-bar setters
and their supporting reads, including guards, are omitted and reported. Business
calls inside a SideEffect prevent that omission. Private immutable locals used exclusively by discarded configuration
are removed transitively; shared values, mutable locals, unused source declarations
and file-initialization semantics are not silently discarded. A still-required
SDK value remains blocking. Strict mode does not project anything. This is a
bounded source shape, not automatic adaptation of every Android theme/helper.

The native palette reads `kotlin_ets_material_<role>` through the current host
ResourceManager, reusing the lazy project ColorScheme implementation. Configure
consumed colors in `base/element/color.json` and `dark/element/color.json`. No
automatic resource emission, hardcoded fallback palette, Android wallpaper
simulation or independent configuration-change subscription is provided here.
The report records skipped source evaluation and the visual replacement;
`generated_with_degradations` is not equivalence success.

```sh
node tools/kotlin-ets/tests/ui/theme-projection/check.mjs /path/to/classpath.txt
node tools/kotlin-ets/tests/ui/theme-projection/runtime.mjs /fresh/page.ets
node tools/kotlin-ets/tests/ui/project-theme/sdk.mjs /fresh/page.ets tools/kotlin-ets/tests/ui/theme-projection/resources
node tools/kotlin-ets/tests/ui/theme-projection/native.mjs /tmp/before.json /tmp/after.json /tmp/after.jpeg
```

The CLI test uses real Compose/Android dependencies. It verifies named content,
state/event/branch preservation, strict mode, shared SDK values, required UI
conditions, unused helper exclusion and a clean page without projection.
The SDK harness compiles unmodified output. The native check requires actual
installation and tapping Advance between layout captures.

## Verification (2026-09-16)

- Public CLI: Page, strict Page, SharedValue, RequiredCondition and Clean passed.
- Current-host palette runtime and existing explicit light/dark palette tests passed.
- Prior omitted/named argument regression: six cases passed.
- Unmodified generated ETS SHA-256:
  `2c4d5328ccf09c5c86a447c69594968ec25fadbc776be9d673737cde519aa7ec`.
  Actual SDK evidence: `/private/tmp/kotlin-ets-basic-controls-sdk-I1S8Kq/result.json`.
- Installed native page: First changed to Next after clicking Advance. Preserved
  content used 975 matching primary-color glyph pixels. Evidence:
  `/private/tmp/theme-projection-before.json`,
  `/private/tmp/theme-projection-after.json`, `/private/tmp/theme-projection.jpeg`.
- Unchanged Banking project replay r36 passed the Theme.kt SDK_INT dependency.
  Its diagnosis records two theme degradations and a new blocker at
  `ProgressBar.kt:142`, `remember { Animatable(0f) }`. Full page generation is
  still blocked; this verification does not claim Banking equivalence.
- Fixed independent reviewer: requirements PASS, quality PASS. No Android source
  or generated ETS was patched for this requirement.
