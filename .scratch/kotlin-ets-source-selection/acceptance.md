# Entry selection acceptance

Base: `ce71a64`, branch `andorid-to-hormony`.

## Result

Implemented entry-based source selection after successful official FIR/FIR2IR,
before target lowerings. Public page/project commands use their existing `--entry`;
language mode can opt in with the same option. No-entry language mode is unchanged.
Selection reports include source locations, excluded declarations and retention
reasons in compiler stderr. No Android source or generated ETS was patched.

## Evidence

- RED: the old compiler JAR attempted the unreferenced `unsupported` method and
  failed on `java.lang.System.getProperty` despite `--entry selection.observations`.
  `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-source-selection-6X5Rkw/red.stdout`
- Final focused suite: `node tools/kotlin-ets/tests/source-selection/run.mjs`.
  `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-source-selection-vFlnW0/result.json`
  All 78 input hashes unchanged, output hashes recorded. JVM and flat/multi-file
  ETS host outputs agree: `label:4`, `item:4`, `positive`, `123`. Repeated calls
  preserve once-only initialization. Strict host type checks pass. Both branches,
  defaults, closure dependencies, interfaces and properties survive selection;
  unused hosts/overloads and a type-only file's unrelated initializer are excluded.
  Reachable unsupported calls/references, invalid Kotlin, missing/ambiguous entry
  and unscoped whole-module failures remain explicit and emit no target.
- Public real-project replay:
  `/private/tmp/kotlin-ets-project-replay-20260915-04/run/`.
  Original controls Android module, all 4 source files and 53 classpath entries;
  `basiccontrols.BasicControls` retained, 9 unrelated top-level declarations
  excluded, including `MainActivity`. Previous replay `...-03` failed on that host.
  Uses `--project`, `--module :app`, `--variant debug`,
  `--entry basiccontrols.BasicControls`, `--offline`; restores the original
  Android SDK/AndroidX environment, without editing project source/build files.
- Actual Harmony SDK:
  `node tools/kotlin-ets/tests/ui/basic-controls-sdk.mjs /private/tmp/kotlin-ets-project-replay-20260915-04/BasicControls.ets`.
  `/private/tmp/kotlin-ets-basic-controls-sdk-x9Ib8a/result.json` records successful
  CompileArkTS, ABC and signed/unsigned HAP production. Generated/copied ETS SHA256
  both `ab102acdde4d4f2395c27b58a6f558f63e4ab354416c2778904b5a207123e22a`.
- Existing independent read-only reviewer Aristotle: requirements PASS, code
  quality PASS, no actionable findings; verified frozen input/output hashes and
  project/SDK identity. No reviewer edits or builds.
- Scoped `git diff --check`: passed.

## Boundaries

This proves source-scoped page generation and SDK compilation, not whole-project
conversion. Classes are retained whole; unsupported used dependencies still fail.
Official resolution still needs all compile-task source inputs, classpath and
necessary plugins. Plain function-reference output remains unsupported (the test
checks retention plus explicit rejection, not successful translation).

No Harmony device was connected (`hdc list targets`: empty); this increment did
not install or visually compare the page. Prior native visual results are not
claimed as current verification. ETS language equivalence runs use the typed host,
not ArkVM. No timing or whole-project completeness claim is made.
