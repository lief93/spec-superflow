# Verification contract

## Required layers per demand

Every demand-related migration slice has three evidence layers:

1. Unit tests for new or changed pure behavior.
2. Demand-related UITest for user-observable interactions and state rendering.
3. Demand-related device testing on an emulator or physical device.

Historical unit/UITest suites may be run for regression. A complete historical UI smoke suite is
not a substitute for demand-related evidence, and it is not automatically required for every
slice.

## Unit tests

Test state machines without network or device dependencies. Cover applicable cases:

- initial state and initial request;
- loading visible while a deferred request is pending;
- success, empty, and error transitions;
- retry of the same operation;
- stale response/cancellation behavior;
- duplicate click or concurrent request suppression;
- pagination order, next key, exhaustion, and partial-data error;
- validation and serialization contracts.

An exit code of zero plus the generated test report is execution evidence. Compilation alone is
not.

## UITest

Use `@ohos/hypium` as the suite framework and TestKit/ArkTS UITest selectors for device UI
interaction. Prefer stable IDs or resource-derived text. Reset the Ability/app state before each
test or provide an explicit deterministic entry route.

Use fakes/deferred promises for transient states that real services cannot hold reliably. Verify
both sides of the transition: loading before resolution, then success/error after controlled
completion.

Separate these statuses:

- `compiled`: `entry@ohosTest` HAP assembled;
- `installed`: signed application and test HAP installed;
- `executed`: test runner completed on a named device;
- `passed`: runner reported zero failed cases.

Never report `compiled` as `executed`.

## Device testing

An emulator counts as a device. Test only demand-related scenarios unless the user requests broader
smoke/regression coverage. Record:

- device/emulator name and OS/API version;
- signed package version and source revision;
- scenario steps and expected result;
- actual result and evidence owner;
- timestamp and pass/fail/blocked.

The implementer may supply automated build/test logs. A named human developer or QA provider must
supply manual device evidence. Codex must not execute the provider's `record` command on their
behalf or invent a role.

## Build gates

Minimum commands for a single `entry` module:

```bash
ohpm install
hvigorw test --mode module -p module=entry@default -p product=default -p buildMode=debug --no-daemon
hvigorw assembleHap --mode module -p module=entry@default -p product=default -p buildMode=debug --no-daemon
hvigorw assembleHap --mode module -p module=entry@ohosTest -p product=default -p buildMode=debug --no-daemon
```

Adapt module/product names from `build-profile.json5`. Configure signing before installation or
`onDeviceTest`. An unsigned HAP is build evidence only.

## Evidence record

Do not write evidence JSON by hand. Run `scripts/evidence_runner.py`. In `run` mode it resolves an
executable outside the target/run trees, executes argv after `--` with `shell=False`, captures
stdout/stderr, and requires the command to freshly generate its declared HAP or test report. It
copies parsed reports into runner-owned artifacts. Every mode derives the current source/target
revisions and HMAC-signs the complete record with the target's external ownership secret. Store
each run as a direct `.json` child under `.migration/evidence/`.

Passed UITest evidence must use a direct trusted `hdc -t <device> shell aa test ...` invocation
with `--test-report-from-stdout --test-report-format hypium-text`,
`--ui-main-hap <main.hap>`, and `--ui-test-hap <ohosTest.hap>`. The device ID must match the
evidence identity. In the same controlled run, the runner installs those exact non-empty HAPs in
main-then-test order, records their hashes and installation output, and stops before `aa test` if
either installation fails. It then accepts exactly one complete, internally consistent
`OHOS_REPORT_*` transcript from that subprocess's stdout, rejects HDC failure markers and
incomplete/conflicting results, and writes and parses its own canonical Hypium report. The
consumer reconstructs the command log from the signed invocation, installation, and result
fields, then re-parses that report and requires it to equal the stdout-derived report. File-based
JUnit/xdevice reports cannot satisfy the UITest gate. This is execution evidence from the named
runner; it is not a substitute for a human device scenario or visual review.

```json
{
  "schema": "android-to-harmony.evidence.v2",
  "gate": "unit_tests",
  "scope": "slices:home-loading",
  "slice_ids": ["home-loading"],
  "demand_ids": ["home-loading"],
  "runner_type": "harmony_unit_runner",
  "runner_mode": "run",
  "argv": ["/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw", "test"],
  "requested_argv": ["/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw", "test"],
  "executable": {
    "requested": "/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw",
    "resolved_path": "/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw",
    "sha256": "<sha256>",
    "size": 1672
  },
  "tool_origin": {
    "schema": "android-to-harmony.tool-origin.v1",
    "source_environment": "DEVECO_HOME",
    "root": "/Applications/DevEco-Studio.app",
    "relative_path": "Contents/tools/hvigor/bin/hvigorw"
  },
  "command": "/Applications/.../hvigorw test ...",
  "started_at": "2026-07-24T12:00:00+00:00",
  "duration_seconds": 4.2,
  "exit_code": 0,
  "artifact": ".migration/evidence/artifacts/unit-tests.log",
  "artifact_sha256": "<sha256>",
  "artifact_size": 1200,
  "tests": { "passed": 12, "failed": 0, "skipped": 0 },
  "test_report": {
    "status": "captured",
    "format": "hypium-text",
    "path": ".migration/evidence/artifacts/unit-tests.hypium.txt",
    "sha256": "<sha256>",
    "size": 900,
    "source": "entry/.test/default/intermediates/test/coverage_data/test_result.txt"
  },
  "device": "not_applicable",
  "source_revision": "snapshot-sha256:<safe-manifest-sha256>",
  "target_revision": "sha256:<target-source-manifest-hash>",
  "status": "passed",
  "attestation": {
    "schema": "android-to-harmony.evidence-attestation.v1",
    "runner": "android-to-harmony-evidence-runner-v1",
    "signature": "<hmac-sha256>"
  }
}
```

`gate` is one of `build`, `unit_tests`, `ui_tests`, `device_test`, or `visual_review`. `artifact`
must be an existing target-relative regular file whose size and digest match the record.
`slice_ids` and `demand_ids` must both be non-empty. `started_at` must include a timezone. A passed
UnitTest must obtain at least one pass and zero failures from a freshly generated, runner-parsed
JUnit XML or Hypium text report. UITest must obtain the same result from the controlled HDC
stdout path and its runner-owned canonical Hypium report. A passed build must similarly hash at least one
freshly generated HAP/APP in `output_artifacts`.

For `ui_tests`, use a concrete device object with `kind`, `id`, `os_version`, and `api_version`,
plus `"execution_status": "executed"`. `compiled` is not accepted as a UI execution result.

For passed/failed `device_test`, the named human provider uses `record` only after actually running
the listed scenario on the concrete device. Include `provider_kind: human`, `scenario_steps`,
`expected`, `actual`, and `provider`. This is intentionally separate from UITest execution and
cannot reuse an `onDeviceTest` command as both gates.

For `visual_review`, use `record` only after the named human completed local comparison. Include
`actual`, `notes`, and `evidence_owner`; do not put image bytes in the record or model context.
Every slice with `human_visual_check_required: true` must be covered before the project is complete.

For an unavailable device, use `probe` for `ui_tests` or `device_test`. The classified preflight
command must fail; the runner records the real `probe_exit_code`, sets `exit_code` to `null`, and
requires non-empty `blocker` and `next_action`. Because HDC can print a standard
`[Fail][E######]` device error while returning zero, that exact marker is accepted and recorded as
`probe_failure: hdc_failure_marker` without changing the real exit code. Any other successful
probe is rejected instead of being recorded as blocked.

The orchestrator rejects missing/invalid HMAC attestations, changed artifacts, category mismatches,
and evidence whose scope does not contain the verified slice. A `verified` ledger must name all
four `required_gates`; each gate must reference current passed evidence covering the ledger's
slice and every declared demand. Use `implemented` while any gate remains unfinished.

The orchestrator selects the latest record per gate by `started_at` and file path. The latest
record must match the current source and target revisions; it never falls back to an older pass.
Historical stale records may remain for audit.

The runner rejects command tools outside configured DevEco/SDK roots and records the accepted root,
relative executable path, executable hash, and artifact hashes. Together with the HMAC, this makes
ordinary same-name substitution, stale reports, target-to-target copying, and accidental category
confusion detectable. It is not an OS-backed identity proof: a malicious process running as the
same local user can create a fake installation tree, change environment variables, or read local
secrets. Human provider names are assertions, not cryptographic identity. Use
organization-controlled signing or external approval when adversarial provenance must be proven.

Do not hide a blocked signing/device gate behind an overall success label.
