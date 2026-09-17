# Local font descriptors

Run `node tools/kotlin-ets/tests/ui/fonts/run.mjs` and
`python3 tools/kotlin-ets/tests/resources/fonts_test.py`.

The public launcher uses real AndroidX classes and a non-final R fixture, as in
modern Android library resource classes. Compare descriptor weights and call
counts with JVM; verify only referenced font bytes are emitted. The optional
`KOTLIN_ETS_TEST_FONT` supplies a real TTF; default is macOS Arial. Both fixture
weights intentionally use the same bytes: this verifies resource transport,
not glyph/weight rendering. Registration and TextStyle application are separate.

Create resource inputs with `font-resources.py --res-dir RES --namespace PACKAGE
--out FRESH_DIR`, then pass `--font-resources FRESH_DIR/fonts.properties`.
Output goes into `OUTPUT.resources/rawfile`, alongside existing string resources.
Local TTF/OTF descriptors, constant weights, normal/italic style and nonempty
explicit vararg families are supported. Missing resources, already-folded
numeric IDs, qualified resource directories, remote/variable font settings,
list/spread families and unsupported font APIs remain diagnosed.

`Default.kt` checks `FontFamily.Default` returned through an ordinary method and
consumed by a Material TextStyle. It maps to the target's existing default family
(`HarmonyOS Sans`) without registering a local font. `default-check.mjs` executes
the emitted ordinary selection code; native compilation remains a separate check.

Reference: AndroidX ui-text `Font.kt`, `FontFamily.kt`, `FontWeight.kt` and
`FontStyle.kt`; resolved IR calls/constructors use the shared typed contract.
