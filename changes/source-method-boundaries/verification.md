# Source Method Boundaries Verification

## Scope and Result

This is a bounded improvement, not a complete source-preserving Kotlin-to-ArkTS
translator. Page UI is emitted in build without renderAndroidPageSnapshot.
Reused components with one verified no-argument BuilderParam retain inline UI
through ArkUI trailing content. Existing source methods and argument forwarding
remain separate at those boundaries. Literal visual facts inside this inline
content are not promoted into extra Props fields. Collision-free style imports
use their exported names. Multiple or unproven slots retain receiver-bound local
Builders; generation-manifest source_modules.slot_lowerings records why.

Already-expanded loops, arbitrary source computations/domain types, and the
original full BannerPageItem signature are NOT reconstructed by this change.
The wider request for complete source method/parameter equivalence remains open.

## Tests

Focused RED cases reproduced synthetic page methods, unnecessary slot extraction,
lost import names, and incorrect single-slot inference with a private second
BuilderParam. The final cases cover nested slots, cross-file source forwarding,
multiple/private/parameterized/uninspected slots, serialized JSON consumption,
and the no-auto-reuse explicit-adapter CLI with ETS-root output.

Final command, from skills/migrate-android-compose-to-harmony/scripts:

```sh
python3 -B -m unittest test_source_method_boundaries test_reuse_source_structure test_component_reuse test_source_modules test_component_interfaces test_best_effort_reuse_page test_existing_target test_custom_target_paths test_page_commands test_component_discovery test_keyed_resources test_business_components test_component_ui_states test_generate_arkui_lanhu_input
```

Final result: 215/215 tests PASS. Log:
`/tmp/source-method-boundaries-tests-final.log`.
An earlier in-flight run loaded a pre-correction macOS /var versus /private/var
test expectation; that run failed and is not counted as passing evidence.
One separately attempted legacy test_tools snapshot test cannot reach generation
because its old harness omits the required --page-json argument. That unrelated
harness was left unchanged; the whole repository suite is not claimed to pass.

## Native Runtime

`/tmp/source-boundaries-runtime-r3` contains generated sources, build identities,
SDK logs, capture commands, runtime.png and runtime-verdict.json. Fresh generation
took 6.244 seconds; signed SDK build took 11.255 seconds. Installation, launch and
UI capture passed. Exactly seven expected texts rendered once in source order:
Nested body, Forwarded title, First item, Second item, Header slot, Body slot,
Mixed source slot. Screenshot was visually inspected.

HAP SHA256: `c3186abb57d4c16067617cc9f06cc3767989a81aa437a1cb4cd55af3d1552c01`.
This covers nested reused single-slot components, separate source methods,
list instances, multiple-slot fallback, and a reused/local-source mixture.
No generated ETS or page JSON was manually patched.

## Full Contact Page

Fresh public Banking-App-Mock-Compose ScannedContactScreen_Ui loaded-state run:
`/tmp/contact-full-regression-20260911-r12/comparison.html`.
Generation took 12.345 seconds; signed build took 11.212 seconds. Generation
process, SDK build, installation, launch, original Android instrumentation and
both platform captures passed. Generated-file and installed-HAP hashes were
checked. HAP SHA256:
`f87eb2fb3a7248925296aa5b932944434c46f81bd85e9b7d7dd9a1899156051c`.

Completeness remains partial_generation, generation quality FAIL, visual
comparison FAIL, SSIM 0.818164. All six expected text occurrences match counts.
Content pixels are identical to the previous r10 baseline after RGB cropping
to (0,140,1320,2786), SHA256:
`b31ec41967079695e0396dd6a8819e91db3957e6030c8b7e59bcb4561f1fd14d`.
This proves no visible regression for this baseline, NOT improved fidelity or
full locale/font-scale equivalence. Existing resource/style gaps remain.

Each runtime directory includes generator-hashes.json for the tested script
tree; the base revision alone does not identify these uncommitted changes.
Inputs are public or synthetic. No company source was transferred.

## Regeneration

Regenerate source-page/Lanhu version JSON so target_content_slot facts can flow
from the target signature inventory into the backend. Existing snapshots and
contracts can be reused if unchanged. Old JSON remains valid but unproven slots
use the existing Builder fallback. No extra adapter registration flag is needed.
