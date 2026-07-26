# Local Demo Rehearsal Evidence

- Date: 2026-07-26
- Scope: Offline installation/upgrade and ordinary Android requirement
- Network dependency: None for the offline path

| Step | Actual result | Elapsed | Evidence |
|---|---|---:|---|
| Verify Plugin-only bundle, local CLI install, upgrade, READY, and idempotency | PASS | 4.44 s | `validation/evidence/offline-install-upgrade.md` |
| Validate ordinary requirement artifacts | PASS | 0.05 s | All five planning/contract artifacts valid |
| Check workflow state consistency | PASS | 0.03 s | State `closing`; stored and current hash match |
| Run full affected unit suite | PASS | 4.08 s | `app/build/test-results/testDebugUnitTest/` |
| Run exact Compose UI class on device | PASS, 3/3 | 15.70 s | Medium_Phone AVD, `emulator-5580`, API 29 XML report |

The complete live verification segment takes approximately 25 seconds after the
Android project and emulator are warm. The first Gradle build is intentionally
excluded from the live demo and retained as evidence because it took more than
one minute on this machine.

Overall: **PASS**
