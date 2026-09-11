# Latest Full Page Regression

Date: 2026-09-11. Tested generator revision: `80ec340`.
Page: public Banking `ScannedContactScreen_Ui`, `loaded` mock state.
Verdict: **FAILED during generation; build, install and visual comparison NOT RUN.**
This report is not runtime or visual acceptance of the latest version.

## Execution Evidence

Fresh run: `/tmp/contact-full-regression-20260911-r3`.
Commands and timing: `commands.json` and `migration/result.json` in that run.
Harness: `/tmp/contact-full-regression-20260911/run.py`.
Reproducer: `/tmp/contact-full-regression-20260911/reproduce.py`.
Run the reproducer with `python3 -B`; it reads the actual emitted artifacts,
invokes the provenance validator, and asserts no generated page ETS exists.
Its output is recorded in the run's `reproduction.json`.

| Stage | Result | Seconds |
| --- | --- | ---: |
| Fresh snapshot | Passed | 0.32 |
| Fresh contract | Passed | 13.16 |
| Project style definitions | Passed | 0.11 |
| Fresh target setup | Passed | 0.26 |
| source-page | Passed | 3.45 |
| Lanhu | Passed | 1.02 |
| Theme | Passed | 0.21 |
| Fonts (three copies) | Passed | 0.62 |
| ArkUI | Failed | 0.21 |
| Build / install / capture / compare | Not run | - |

Earlier harness attempts are preserved separately: r1 used an obsolete snapshot
without its required safe manifest; r2 copied old theme resources without their
ownership records. Both are setup failures, not generator regressions. r3 uses
fresh intake and a fresh target, with only the old local signing configuration.
No generated ETS or source UI was manually edited. No new HAP was installed.

## P0: Provenance Format Blocks Page Generation

- Last inspected artifact without this malformed provenance: `migration/source-page.json`.
- First inspected artifact containing it: `migration/lanhu/version_json.json`.
- Component: `source-9f9459d31f11b8c971bc`, the native Button in `Buttons.kt:54`.
- Fields: `migration.provenance[2].source` and `[3].source`, covering
  `style.surface.background` and `style.typography.color`.
- Actual value begins `Material3 baseline: ButtonDefaults.buttonColors(` and
  retains three line breaks. Its length is 186, so this is not a length overflow.
- Producer: `frontend/material_controls.py`, `MaterialControlDefaults.assign`.
- Rejecting consumer: `page_snapshot.py`, `normalize_provenance` calls the
  single-line `bounded_string` validator.
- Evidence: `reproduction.json`, `migration/06-arkui.stderr.log`, and the failed
  stage in `migration/result.json`. Both malformed entries reproduce rejection.
- Cause established: producer/consumer disagree about multiline source provenance.
  This is not an unresolved color, adapter miss, or output-directory problem.
- Introduction commit has not been bisected; do not attribute this specifically
  to the latest flat-output change.
- Repair boundary: agree a provenance text contract in the generator and its
  validator, retaining source evidence. Do not patch emitted JSON or ETS.
- Required repair verification: multiline and long provenance regression tests,
  then rerun this page from fresh generation through signed build, installation,
  capture and same-state comparison. Those steps remain outstanding.

## Comparison Limit

The historical loaded Contact comparison is under
`/tmp/ui-stability-contact-20260907-dev019e`. It was below the 0.95 threshold
(reported strict score 0.942641), not an accepted pixel-perfect baseline. No new
screenshot or similarity score exists for this run. Historical scores must not
be presented as results for revision `80ec340`.
