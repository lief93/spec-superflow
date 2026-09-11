# Source Value Method Verification

## Scope and Evidence

- Initial three pipeline tests failed before implementation: no emitted record,
  no function consumer, no unsupported-dependency diagnostic.
- Eighteen focused tests cover two Kotlin/JVM versus transpiled-target
  differential executions over multiple inputs, Int overflow, constructor
  defaults/nested records, ambiguity, external calls, adapter precedence, and
  generation without an adapter or fixture.
- The first broad run passed 223 tests; intermediate runs passed 226 and 228.
  The 232-test run passed (exit 0, 218.635 seconds). The final 233-test run
  adds the Number/Alignment/FontWeight layout collision regression and passed
  with exit 0 in 223.658 seconds.
- Review regressions first reproduced intrinsic/import/normalized-field name
  collisions and local declarations leaking into top-level resolution. They now
  pass with fail-closed name checks, reserved import/Builder names, explicit PSI
  top-level facts and caller-scoped resolution. Local methods are not exported.
- The r2 review found Number missing from target reserved names. Its Button
  measurement combination and SDK enum-name variants first failed (three
  subcases), then passed with the native emitters' conversion/import/enum names
  reserved as well. This remains an explicit bounded set of emitted SDK globals,
  not discovery of arbitrary third-party runtime globals.
- One reusable Label called with two different arguments retains its parameter
  inside the value-method call, rather than embedding its first preview input.

## Installed Value-Method Fixture

`/tmp/source-value-runtime-r5` records fresh snapshot, contract, source-page,
Lanhu/version JSON, ArkUI output, signed SDK build, installation and capture.
`runtime-verdict.json` proves seven visible Text values in source order:
`Ada!?`, `Inactive`, `Next`, `Explore`, `....`, `First!`, `Second!`.

`Labels.ets` contains the original Person class and caption/title/button/dots
method boundaries. `Page.ets` imports and calls them. The SDK-built files were
hash-checked against the generator outputs; no generated code was hand-patched.
The real command initially exposed a skipped projection path without adapters;
that entry path now has a dedicated regression test.

## Full Contact Regression

`/tmp/contact-full-regression-20260911-r17` records a fresh complete public Contact
page run, SDK build, installation, Android instrumentation and paired captures.
Process verification passed. Source files, fixture and built artifact hashes
were checked. `comparison.html` and `paired-results.json` report SSIM 0.818164,
unchanged from r12. Visual/completeness verdict remains fail/partial_generation,
not a new claim of visual parity. The page still has the previously documented
root UI state/callback/Modifier interface limitations.

## Remaining Boundary

Only bounded pure value methods are covered. No arbitrary business services,
coroutines, navigation, member methods, whole-page state machine or callback
reconstruction is claimed. Unsupported source operations keep explicit
diagnostics and existing marked preview output. Source-stage diagnostics and
target method-consumption evidence are distinct; emitted declarations alone do
not prove whole-page behavior or visual fidelity.

## Reproduction

Run from `skills/migrate-android-compose-to-harmony/scripts` in the repository,
with local Kotlin compiler artifacts and the installed DevEco SDK available:
local runner `/opt/homebrew/bin/python3`, Python 3.14.5 on macOS.

```sh
python3 -B -m unittest \
  test_source_value_methods test_source_method_boundaries \
  test_reuse_source_structure test_component_reuse test_source_modules \
  test_component_interfaces test_best_effort_reuse_page test_existing_target \
  test_custom_target_paths test_page_commands test_component_discovery \
  test_keyed_resources test_business_components test_component_ui_states \
  test_generate_arkui_lanhu_input
```

This is the exact module set for the recorded 232-test run and the final
233-test run; the extra test is in `test_source_value_methods`. The focused
command is `python3 -B -m unittest test_source_value_methods`.
The 55-test related run used `test_source_value_methods
test_source_method_boundaries test_business_components test_component_interfaces`
before the final additional test.

Runtime artifact directories contain `commands.json`, build/capture identities,
per-command exit codes and durations.

## Independent Review

The persistent read-only reviewer approved r3, with no remaining findings.
Frozen candidate identity:
`e3c147ab176ea0b19ed7ef7df730108d9e048c23f6c68a882d7d830b412a1755`.
The reviewer independently verified 378/378 candidate files, ran 18 focused tests
and the exact 233-test broad command (exit 0, 207.555 seconds), and checked r5/r17
generator, generated-file, HAP and capture hashes. Explicitly bounded reserved
names and the Contact visual/completeness failures remain documented risks.
This review record is the only post-freeze change; executable files are unchanged.
