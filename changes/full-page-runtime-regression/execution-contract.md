# Full Page Runtime Regression

User requires every migration-tool change to regress a previously adapted page
through generation, build, installation, capture and comparison. Verify current
HEAD `80ec340` using Banking ScannedContactScreen_Ui, loaded ContactUi.mock data.
Reuse the original public source snapshot and Android instrumentation fixture;
generate fresh source/version/ETS and install the freshly built Harmony artifact.
Keep source files and generated ETS unchanged. Match viewport, density, font scale,
theme, locale and fixed state; report unsupported comparison gates honestly.

Store repeatable commands, stage timings, artifact hashes, captures, comparison,
and the last-good/first-bad stage for any regression in a fresh evidence directory.
Add the required regression gate to the migration workflow documentation. No
generator fixes are pre-authorized by this verification-only contract; diagnose
failures before proposing a scoped implementation contract.
