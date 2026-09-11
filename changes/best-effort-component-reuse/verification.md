# Default-Only Component Reuse Verification

## Candidate

- Base: `d692323d9f0625651f7a4bcc399fb092b6b4449c`.
- Frozen candidate: `/tmp/best-effort-reuse-20260911/candidate-v6`.
- Identity: `6ea886e1a08362798a0757493b50e344186b30f038162c6d613af3eb1b4e48e7`.
- All 369 frozen file hashes matched the live task sources before delivery.
- Final verification notes are not part of that pre-review code identity.

## Behavior

Automatic reuse selects a unique same-name target without source signature matching.
It never evaluates or forwards Android arguments. Optional/default target parameters
are omitted; supported required values use typed placeholders. Positional middle
holes retain `undefined`, trailing defaults are omitted, and required slots get empty
content. Unsupported required object-only types and ambiguous declarations retain
the existing incomplete-reuse fallback. Explicit component adapters retain strict
argument mapping and caller-owned slots.

Source omissions and placeholders remain defaulted diagnosis items. They do not
stop supported code generation or become claims of equivalent UI/business behavior.

## Tests

- Final targeted candidate: 70 tests passed in 16.327 seconds across discovery,
  explicit reuse, full-page commands and unified diagnosis.
- Previous candidate v5: 241 tests passed in 208.377 seconds. The final candidate
  additionally supports union member defaults and verifies them through public
  projection and the SDK fixture.
- Final candidate broad regression: 242 tests passed in 203.143 seconds:
  `test_component_discovery test_component_reuse test_best_effort_reuse_page
  test_generation_diagnosis test_ui_migration_architecture test_composable_values
  test_page_roots test_resource_arguments test_keyed_resources test_property_resources
  test_component_interfaces test_component_ui_states test_business_components
  test_source_modules test_existing_target test_custom_target_paths test_page_commands
  test_visual_triage` via `env PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest`.

## Full Page And SDK

- Synthetic source page calls three existing target components with mismatched
  names/types, source modifiers, required callbacks/slots and a required union.
- Public pipeline: snapshot, contract, style definitions, initialized target,
  `migrate_compose_page.py`, generated JSON and ArkUI output.
- Every generation stage completed; result is honestly `partial_generation`,
  with 10 defaulted groups and no current pending groups.
- SDK `hvigorw assembleHap --mode module -p module=entry@default -p product=default
  --no-daemon`: exit 0, 7.162 seconds including process overhead.
- Fixed evidence: `/tmp/best-effort-reuse-20260911/evidence-v6.json` and
  `/tmp/best-effort-reuse-20260911/build-v6.log`.
- Target: `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/page commands vwin_rxz/harmony`.
- Generated `Page.ets` SHA-256:
  `8e1827f47bac3e600135eac19365bb14c01b8bd41249b17d8ea39f8c1311ffd2`.
- Generated ETS and existing target-component hashes were unchanged by the build.
  Only a fixture entry host and cached dependencies were supplied for compilation.
- No device installation, screenshot comparison or business behavior equivalence
  is claimed. Signing was skipped because this synthetic project has no signing
  profile; SDK dependency/entryability warnings did not fail compilation.

## Earlier Failures

- Two prior CLI tests expected automatic `Hello` forwarding. Assertions now enforce
  the approved omission policy and retained degradation diagnostics instead.
- Initial SDK fixture name `Badge` collided with ArkUI's built-in component; renamed
  the synthetic source and target declaration to `StatusLabel`, without patching
  generated ETS.
- Review found that required string-like unions did not receive a default. The
  final candidate chooses a valid supported union member (null preferred) and
  still refuses object-only unions. Public projection and SDK compilation cover it.

## Scope Limits

No company source files were used. Defaults can intentionally produce empty labels
or slots and inactive callbacks. Use an explicit component adapter when actual
source values/content must be preserved. Re-run Lanhu/version JSON and downstream
generation for this policy; an unchanged source snapshot/contract may be reused.
This is focused migration coverage, not a claim that every repository test passes.

## Independent Review And Acceptance

- Persistent read-only review task `019f9f14-8207-7d60-9745-d8a2e28d7be8`:
  approved v6, no open findings (turn `01a08dfd-0ea3-72d1-b648-2dbb0519d7b8`).
- Reviewer independently ran 103 related tests: PASS in 132.752 seconds.
- Separate public-pipeline positive and negative probes confirmed a string/resource
  union default and refusal to construct an object-only union.
- Reviewer independently copied the generated target and ran SDK `assembleHap`:
  BUILD SUCCESSFUL in 6.268 seconds; candidate and saved ETS hashes still matched.
- Task-level functionality, tests and evidence accepted against the latest
  default-only requirement. Commit/push follows the user's standing instruction.
