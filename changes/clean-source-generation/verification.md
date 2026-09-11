# Clean Source Generation Verification

## Implemented

- Provenance source evidence accepts multiline text (10,000-character bound),
  preserving values rather than removing newlines from generated JSON. Empty,
  non-string and invalid control-character values still fail.
- Final source modules emit fixed numeric lengths directly. `16.dp` becomes
  `.width(16)`, not a runtime `layoutPx` call. Unused pixel helpers are removed;
  context remains for actual state and measurement/font-metric dependencies.
- A single-use source facade with inert arguments can contain its rendering body
  directly. Source names and parameters remain; effectful arguments, unsafe scope
  substitutions, shared helpers and multi-state dispatch are not flattened.
- A single fallback body uses its source name instead of a `preview` prefix.
  Target identifier normalization still handles reserved words and invalid source
  identifier characters; both cases have a regression test.
  Unsupported source parameter types can still require generated props. This
  change does not promise arbitrary domain-model or business behavior migration.

## Full Page Run

145 focused regression tests passed in 149.061s; the log is
`/tmp/clean-source-r7-regressions.log`. Coverage includes source
modules, declared component interfaces, UI-state selection, complete CLI commands,
Lanhu consumption, provenance, diagnostics and partial-page generation.

Exact command, from `skills/migrate-android-compose-to-harmony/scripts`:

```sh
python3 -B -m unittest test_source_modules test_source_provenance test_business_components test_component_interfaces test_component_ui_states test_page_commands test_generate_arkui_lanhu_input test_generation_diagnostics test_partial_page_generation test_composed_modifier
```

Fresh candidate run: `/tmp/contact-full-regression-20260911-r7`.
Base revision is `80ec340`; `generator-hashes.json` records the actual modified
generator identity (the revision alone does not identify this candidate).
`commands.json`, `migration/result.json`, `build-identity.json`,
`generated-hashes.json`, `capture-commands.json` and `capture-identity.json`
record commands, durations and source/APK/HAP/generated-file/capture hashes.

Banking `ScannedContactScreen_Ui`, loaded Contact mock state:

| Stage | Result |
| --- | --- |
| Fresh snapshot / contract / styles | Passed |
| Fresh source-page / Lanhu / theme / fonts / ArkUI processes | All child commands exit 0 |
| Overall generation quality | Failed: partial_generation, generation_complete=false, verdict=fail |
| Required-fact / target-consumption gates | Failed: 2 / 5 recorded failures |
| Signed SDK build | Passed |
| Original Android APK install and instrumentation | Passed, 1 test |
| New Harmony HAP install / launch / UI tree / screenshot | Passed |
| Expected text occurrences | All six matched |
| Screenshot comparison against Android | Failed, SSIM 0.818168 < 0.95 |

Contract extraction took 13.671s, the full migration command 6.676s and signed
build 7.009s. Source UI file hashes and state fixture hashes match the original
Android test build. Generated ETS hashes were unchanged through compilation.
No generated JSON or ETS was manually patched. Only the host imports the emitted
root component. Android display overrides/font scale were restored after capture.
This final candidate was installed and launched after the control experiment.

## Controlled Visual Regression

Control: `/tmp/contact-full-regression-20260911-control`, using detached revision
`80ec340` plus only the provenance validator repair. Its full fresh generation,
build, installation and comparison also ran. It retains old pixel rounding and
render wrappers. Both runs used the same source, fixture and viewport.

The 1320x2646 content crops at (0,140) are byte-identical as RGB pixels, SHA-256
`b31ec41967079695e0396dd6a8819e91db3957e6030c8b7e59bcb4561f1fd14d`.
`controlled-comparison.json` records equality and an empty difference bounding box.
Both obtain SSIM 0.818168 against fresh Android captures. No additional visual
change was observed on this page from fixed-length emission and fallback naming.
The real page manifest has an empty `inlined_methods` map: this device regression
does not exercise facade collapse. That path has focused generated-output tests
and independent AST/scope probes, not device-runtime evidence.

## Remaining Limits

This is not full visual acceptance: the threshold fails, complete page.v2 runtime
visual facts were not supplied, Harmony system locale differs, and the attempted
runtime font-scale query was unavailable. The compared content is the same English
loaded-state fixture; this does not establish all environment gates. Historical
0.942641 is not the current run's score and its difference has not been bisected.
Current content geometry differences remain, including approximately 2.86dp for
name/card/description vertical positions and 5.14dp for the main button label.
The title's accessibility bounds include different padding; a -16dp bound offset
is not by itself proof that its visible glyphs moved.

The partial-generation quality failure is also present in the controlled baseline;
it has not been accepted as complete migration. Required facts still lack the
`AsyncImage` resource for `imageReq` and a complete mapping of
`ButtonDefaults.buttonColors(...)`. Target consumption records five failures
(image resource/content scale, button text and colors). These remain outside the
current provenance/naming/context repair and are not suppressed or declared fixed.
The independently executed SDK build/install evidence does not change the
generator's own quality verdict or its built-in `build_verified=false` field.

Readable local comparison: `/tmp/contact-full-regression-20260911-r7/comparison.html`.
Raw results: `paired-results.json` and `comparison-v2/comparison.json` in the same run.
No company intranet files were used and no intranet validation is claimed.
