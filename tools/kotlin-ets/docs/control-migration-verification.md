# Control migration verification, 2026-09-14

User requested fresh migration tests for the new controls and a commit if they
passed. All checks below were rerun on the candidate after the image increment.
No production changes were needed in this verification turn.

## Fresh checks

| Check | Result | Evidence |
| --- | --- | --- |
| Resource materialization | Passed: bitmap copy/independent decode, vector conversion, stable names, namespace isolation, 15 negative cases | `tests/resources/.work/run-buYyJ0/complete.json` |
| Gradle launcher | 8/8 passed, including image-registry option, failure handling and no overwrite | `node --test tools/kotlin-ets/tests/project-inputs/launcher.test.mjs` |
| Basic controls | Passed: real Compose IR, typed text/dividers/selection, seven negative cases, emitted Boolean callbacks executed | `$TMPDIR/kotlin-ets-basic-controls.rGzqC0` |
| Images | Passed: resource conditions, Painter arguments, method names, wrong-type rejection, registry validation, twelve negatives, executed tint arithmetic | `$TMPDIR/kotlin-ets-images.nONOdR` |
| Shared typed UI | Passed: state, slots, Pager, symbol/source identity, target after frontend disposal and shared API registration | `$TMPDIR/kotlin-ets-typed-ui.z8MCqS` |
| Basic-control SDK | Passed: unchanged generated ETS, ABC and signed/unsigned HAP | `/private/tmp/kotlin-ets-basic-controls-sdk-EPpLSL/result.json` |
| Public image migration + SDK | Passed: actual materializer, public compiler, unchanged ETS and generated media, ABC and signed/unsigned HAP | `$TMPDIR/kotlin-ets-images-cli-PetNTU`; `/private/tmp/kotlin-ets-basic-controls-sdk-YvcZpa/result.json` |

Commands use the existing scripts documented in
[basic controls](compose-basic-controls.md) and [images](compose-images.md).
The SDK image command used the fresh resource fixture at
`tests/resources/.work/run-buYyJ0/res`, not a previously materialized package.
Resource conversion and compilation never downloaded the AsyncImage fixture URL.

## Acceptance boundary

Passed within the explicitly supported subset. This is not full Compose/Material
equivalence. There was no fresh device installation, UI gesture execution,
network image load or Android/Harmony screenshot comparison. In particular,
native default appearance, inherited Icon tint, arbitrary Painter/ImageVector,
resource qualifiers/intrinsic sizing and Coil request objects remain subject to
the documented limits. No independent review was run in this turn.

The user authorized a commit after these checks. Only the related
`tools/kotlin-ets` changes belong to that commit; unrelated workspace changes
and ignored generated test artifacts are excluded.

## Follow-up: installed Android/Harmony comparison

The later user-requested native run is separate from the compile-only checks
above. Evidence root: `/private/tmp/kotlin-ets-controls-native-20260914-01`.
Open `comparison.html`; `comparison.json`, `inputs.json`, and the four
`*-final` directories retain assertions, package/source identities, environment
logs, device command logs, accessibility trees and screenshots.

- Android builds the unchanged `BasicControls.kt` and `ImageControls.kt` in an
  isolated host using real Compose and Coil dependencies; the installed APK
  SHA-256 matches the local package.
- Harmony builds and installs the previously generated ETS without changing
  its hash. Only the test EntryAbility normalizes the host environment and
  logs the generated identity; it does not implement or patch the controls.
- Both captures use 1320x2856, density 3.5, application font scale 1, light mode
  and hidden system bars. Harmony app language is en-US, but its resource
  configuration still reports zh_Hans; localized resources are not tested.
- Native clicks pass on both: false -> Checkbox click -> true -> Switch click
  -> false. Both controls and the dependent text are checked in all three states.
- Local image bounds are 280x280 pixels (80 logical units); opaque red icon
  bounds are 84x84 (24 logical units). Half-opacity bitmap interior maximum
  channel difference is 1/255; opaque red icon interior difference is zero.
- Visual parity is NOT passed: default text bounds are 276x57 on Android vs
  324x66 on Harmony, and native checkbox/switch appearance and occupied space
  differ. Accessibility touch bounds must not be confused with painted bounds.

The invalid AsyncImage URL does not prove successful network loading. The
single-color bitmap does not prove complex crop behavior. The alternate vector
branch and partial-alpha icon tint were not exercised on devices in this run.
The final evidence supersedes early attempts that had an unmatched host inset
policy or a test locator assuming Android Switch had a Switch class name.
