# Verification: Reused Component Source Structure

Base: `2cae22e368c7d8b5ca0692fac79316c52974e4d4`.
Scope: ArkUI generation only. Reuse matching and source/contract extraction are
unchanged. Existing version JSON can be reused if it already has the correct
component-reuse record and slot child identities.

## Implemented Boundary

- Final imports use the target export name unless it collides with native uses,
  the root component, another import, or a generated/source binding.
- Reused component slots retain nested calls and source child order. Fixed text,
  resources, IDs and styles remain in local Builder bodies, not synthetic Props.
- Only referenced enclosing source parameters are forwarded into these methods.
  Ordinary source functions still use the existing source-file organization.
- Local slot Builders retain their page receiver. Exported source functions that
  call these methods need a typed rendering context; fixed dimensions do not.
- Ordinary non-reused source slots still use the existing BusinessSlot mechanism.
  This change does not claim to remove every rendered-fact Props or generated
  helper, translate arbitrary business callbacks, or guarantee visual parity.

## Automated Regression

From `skills/migrate-android-compose-to-harmony/scripts`:

```sh
python3 -B -m unittest test_reuse_source_structure test_component_reuse test_source_modules test_component_interfaces test_best_effort_reuse_page test_existing_target test_custom_target_paths test_page_commands test_component_discovery test_keyed_resources test_business_components test_component_ui_states
```

165/165 PASS, 184.332 seconds. Raw log:
`/tmp/reuse-source-structure-regressions.log`, SHA-256
`6d5af9097375e659bb9dd6a73adb3a08e9c95ded4c174c817fa6aa7c590b5813`.
Includes nested reuse, two named slots, actual parameter forwarding, separate
source files, mixed source/reused slots, native/root/duplicate import collisions,
and property/string spellings that must not be renamed.

## Actual SDK and Runtime

Public synthetic fixture: `/tmp/reuse-source-structure-r10`.

```sh
python3 -B /tmp/contact-full-regression-20260911/reuse_runtime.py /tmp/reuse-source-structure-r10
python3 -B /tmp/contact-full-regression-20260911/reuse_capture.py /tmp/reuse-source-structure-r10
```

These commands were run against a fresh directory. The harness writes source,
target-library and host fixtures, then uses the normal snapshot/contract/style/
page commands. It never patches generated ETS or version JSON. Generation took
1.982 seconds; the signed SDK build took 6.394 seconds. Generated Page.ets and
Outer.ets hashes remain unchanged through build and installation.

Seven reuse instances: nested Shell/Panel, Outer(title) from a separate Android
file, two repeated Shells, independent header/body slots, and a source Local
component inside a reused Shell. On Harmony device `127.0.0.1:5557`, all seven
expected texts were visible exactly once in source order. Foreground application
identity was checked, not inferred from a successful launch command.

- HAP SHA-256: `3e99b08dc9345b5a44b79a5866ce2de77eaed5c945f520d0295a74c095ea2b10`.
- Page.ets: `7640d4162716c2ec8f2bcd608da386685cdf0c895d2d07720f6172f142f471e4`.
- Outer.ets: `d951096d5c0a5ff84b114e9772fcfb5167faca924df94c1dc5b0799bc1da8fb0`.
- Screenshot: `93dbf3a4e4bdbb04634ba46655185a7e5158f40b0f524947c8a956b2bd8c73f9`.
- Evidence: commands.json, generator-hashes.json, build-identity.json,
  runtime-verdict.json, runtime.json and runtime.png in that run directory.

## Failed Candidates Kept as Evidence

The initial inline-arrow candidate compiled but crashed when raw component
construction ran in an ordinary callback (r3). Lifting slot methods to global
Builders also compiled but lost the rendering receiver (r5). Explicit standalone
this binding failed ArkTS validation (r6); direct void Builder calls as property
values failed type checking (r7). The final approach keeps local Builder methods.

r8 rendered all six initial texts, but its full-window host placed the first text
behind the system bar, so UITest omitted it. r9 corrected only the test-host
padding and passed six texts. r10 adds the cross-file and mixed-slot cases above.
No failed run is counted as runtime acceptance.

## Previously Adapted Full Page

The public Banking contact / loaded fixture was regenerated at
`/tmp/contact-full-regression-20260911-r10` using the normal full-page command and
existing-target output. Generation took 6.120 seconds and the signed SDK build
6.499 seconds. After cold-starting the same test emulator with its supported
SwiftShader renderer, Android instrumentation passed (`OK (1 test)`), and the
fresh Harmony HAP was installed, launched and captured successfully.

```sh
python3 -B /tmp/contact-full-regression-20260911/run.py /tmp/contact-full-regression-20260911-r10
python3 -B /tmp/contact-full-regression-20260911/capture.py /tmp/contact-full-regression-20260911-r10
/tmp/ssf-visual-fidelity-pillow/bin/python /tmp/contact-full-regression-20260911/compare.py /tmp/contact-full-regression-20260911-r10
```

- Build/install/capture process: PASS. All six visible text occurrences match.
- Generation quality: `partial_generation`, `generation_complete=false`, FAIL.
  Required-fact gate retains 2 failures (AsyncImage imageReq and ButtonDefaults
  colors); target consumption retains 5 failures, as in the previous baseline.
- Visual comparison: FAIL, SSIM `0.818164` against threshold `0.95`.
- Harmony content-area pixels are identical to r7 at `(0,140,1320,2786)`;
  both RGB pixel buffers hash to
  `b31ec41967079695e0396dd6a8819e91db3957e6030c8b7e59bcb4561f1fd14d`.
  The Android capture now uses software rendering, so tiny SSIM changes are not
  evidence of a target change. Locale/font-scale parity is not fully verified.
- Installed HAP SHA-256:
  `4fe20f68133b41c80bd28edc19d0e7949af8ba6a5c971d564069402cdf04a463`.
- Raw evidence: commands.json, capture-commands.json, generator-hashes.json,
  build-identity.json, capture-identity.json, paired-results.json,
  comparison-v2/comparison.json and comparison.html in the r10 directory.

r9 Android instrumentation passed its page/text assertions, then
UiAutomation.takeScreenshot returned null. The independent screencap command
also stalled. Only test emulator `emulator-5554` was rebooted; no real Android
device or other emulator was changed. The guest reboot timed out; a cold start
of that AVD with `-gpu swiftshader_indirect` restored screenshot capture. That
failed r9 capture is not a visual pass.

Full-page generation quality and visual comparison must remain separate from
build/install/capture success. The prior accepted baseline itself had
partial_generation and SSIM 0.818168; this task does not claim to fix those
existing resource/style differences.
