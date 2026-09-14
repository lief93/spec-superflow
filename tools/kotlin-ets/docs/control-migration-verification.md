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
