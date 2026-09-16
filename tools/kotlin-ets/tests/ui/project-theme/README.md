# Project theme colors (API 12+)

By explicit migration policy, `dynamicLightColorScheme(context)` and
`dynamicDarkColorScheme(context)` use the Harmony project's configured colors.
This is not Android wallpaper-color reproduction. Static `lightColorScheme` and
`darkColorScheme` continue to use their explicit values and Material defaults.

Put colors in the module's official resource directories:

```
src/main/resources/base/element/color.json
src/main/resources/dark/element/color.json
```

Both use the same resource names. The adapter convention is
`kotlin_ets_material_<snake_case_role>`, for example `kotlin_ets_material_primary`
and `kotlin_ets_material_on_surface`. These names are not Harmony's official
theme-role names. Alias them to existing project colors with `$color:brand_primary`,
as shown in this fixture. Do not replace a project's existing resource files.

The generated value implements the same typed ColorScheme contract as static
palettes. A getter reads only the requested color using native
`ResourceManager.getColorByNameSync`. Unused roles need no resources; this fixture
renders with only `primary` configured. A consumed missing color reports its
resource name rather than returning a fabricated default. Native resource
qualifier fallback (for example dark to base) remains in effect.

The factory copies the native configuration, sets explicit LIGHT or DARK and
creates `getOverrideResourceManager(configuration)`. It does not change the host
or application color mode, and preserves locale/density. There is no value cache.
The returned palette's selected mode is fixed: this adapter does not add system
theme listeners or guarantee automatic recomposition on resource changes.
`LocalContext.current` retains the synchronous composition restriction documented
in `../local-context/README.md`.

## Checks

Generate `Page.kt` through the public CLI with a real Compose classpath and
`--entry projecttheme.Page`. Then run:

```
node tools/kotlin-ets/tests/ui/project-theme/check.mjs /absolute/generated.ets
node tools/kotlin-ets/tests/ui/project-theme/sdk.mjs /absolute/generated.ets
```

The first executes the generated ordinary Kotlin helper `palette` and verifies
lazy reads, both explicit modes, unchanged host configuration, refresh on later
reads and named failures. The SDK check merges fixture resources into an isolated
seed project, compiling the byte-identical generated ETS to ABC/HAP. Install that
HAP and verify `Project light` is #1256AB and `Project dark` is #DA3478 on the same
screen. This checks actual native override resource selection, not only a mock.
`native.mjs <dumpLayout.json> <screenshot.jpeg>` checks the visible labels and
their glyph colors using same-run device artifacts.

Official references:
- https://github.com/openharmony/docs/blob/master/en/application-dev/ui/ui-dark-light-color-adaptation.md
- https://github.com/openharmony/docs/blob/master/en/application-dev/reference/apis-localization-kit/js-apis-resource-manager.md
