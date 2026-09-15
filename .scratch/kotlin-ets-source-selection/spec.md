# Entry-based source selection

Scope: page-level migration, after official FIR/FIR2IR resolution and before ETS
lowerings. `--entry` roots one uniquely resolved top-level function; language mode
without an entry continues to translate all input declarations.

Keep reachable top-level functions, properties and whole classes using resolved
IR symbols, including types, defaults, closures, references, both branches and
overrides. Preserve stored non-const properties in activated files, in source
order, so unread initializers cannot silently lose effects. Do not activate an
unrelated file just because its source was supplied. Do not strip sources before
Kotlin type checking or suppress an unsupported reachable dependency.

Reference: Kotlin/JS `UsefulDeclarationProcessor` uses a declaration-symbol work
queue. Reuse official IR traversal; do not import JS-specific DCE context or
prototype/lowered-JS assumptions. This is conservative top-level selection, not
member-level DCE or automatic whole-application migration.

Acceptance:
1. Same JVM/ETS results for defaults, references, branches, models and ordered
   file initialization; irrelevant unsupported hosts/overloads are excluded.
2. Necessary unsupported dependencies and invalid Kotlin still fail explicitly.
3. Emit a source-linked selection report, including on later backend failure.
4. Re-run the previous Android controls project without manually selecting files;
   compile its unedited generated ETS with the Harmony SDK.

Out of scope: Android lifecycle conversion, external serialization runtime and
member-level minimization. The existing read-only reviewer checks the frozen
increment after implementation; no new developer or reviewer is created.
