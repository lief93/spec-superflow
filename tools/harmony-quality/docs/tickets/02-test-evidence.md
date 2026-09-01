# 02 - Normalize test and coverage evidence

**What to build:** A developer can run a quality check and receive traceable unit, acceptance, UI, and changed-code coverage evidence, with missing or broken infrastructure distinguished from failed behavior.

**Blocked by:** 01 - Discover and configure a Harmony project.

**Status:** complete

- [x] Normalize configured command results, native Hypium case results, and test counts.
- [x] Verify acceptance-criterion-to-test mappings.
- [x] Treat native Hypium assertion failures as failed behavior even when Hvigor exits zero.
- [x] Parse LCOV or native DevEco `coverageReport.json` and identify uncovered changed lines.
- [x] Emit deterministic JSON evidence.
