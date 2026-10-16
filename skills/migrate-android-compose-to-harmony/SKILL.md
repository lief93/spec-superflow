---
name: migrate-android-compose-to-harmony
description: Migrate Android Compose or Views/XML pages and their business behavior to HarmonyOS with AI source-first semantic transcription, a lightweight UI/business dossier, native builds and runtime comparison. Preserve source ownership and image-byte isolation; optional analysis tools support rather than gate the AI procedure.
---

# Source-first Android to Harmony migration

The default path is **safe source → AI UI/business dossier → source-first implementation →
build and behavior comparison**. AI reads and transcribes the source; a parser does not decide
which source APIs may be migrated. PSI, a full migration Contract, an effective-page closure and
per-syntax-region mappings are optional aids, not prerequisites for this path.

Keep the requested production page/flow as the scope. A captured state is a test case, not the
entire implementation. Include the page's reachable behavior and preserve its source conditions.

## When business pseudocode is the requested deliverable

When the user explicitly requests runnable high-fidelity UI with business semantic transcription
rather than a fully working application, keep UI implementation/build/capture acceptance real and
allow detailed pseudocode for business bodies and platform boundaries. Use synthetic state to
exercise the source UI states and interactions, identifying that fixture separately from live data.
Preserve existing working business code; additional service/storage/device integration is not a
prerequisite for accepting this explicitly selected deliverable.

Keep the same source collection and source-to-target reconciliation. Link each scoped chain to
existing target code or its pseudocode in the existing dossier. Follow original method/module
ownership, conditions/defaults, payloads, data relationships, state writes, effect order, and
error/lifetime behavior. A prose feature summary or an opaque “save data” step is insufficient
when the source contains application rules inside that operation. Platform interfaces may remain
abstract with their inputs, results, errors and caller behavior explicit.

For this deliverable, the execution and business-runtime checks below apply to the runnable
portions, not as a demand to implement every pseudocode body. Accept business transcription by
reconciling all scoped source chains and branches against code/pseudocode and resolving omissions;
record this separately from executed behavior. UI acceptance is unchanged. Preserve historical
failed/unrun checks as runtime evidence, not failures of a pseudocode-only deliverable. Existing CLI
implementation/runtime gates retain their meanings; pseudocode does not satisfy them. The result
is UI plus business transcription, not a runtime-verified application. Without this explicit user
choice, follow the complete executable migration procedure below.

## Prepare source and runtime facts

Keep the original Android repository read-only and the Harmony target separate. Read
[privacy-boundary.md](references/privacy-boundary.md) before source intake. Reuse an approved
safe snapshot, or prepare and validate one with the existing helpers:

```bash
python3 "$SKILL_ROOT/scripts/prepare_safe_snapshot.py" --source "$SOURCE" --snapshot "$SNAPSHOT"
python3 "$SKILL_ROOT/scripts/validate_ai_safe_tree.py" --require-safe-manifest "$SNAPSHOT"
```

These helpers protect source access; they do not require Kotlin PSI. Once the snapshot exists,
inspect source only there. Treat images/fonts/vector artwork as opaque resources; reuse the
manifest-based copy/conversion helpers without exposing pixels or artwork to the model.

Find the production page, its actual caller and state owner in source. Trace the selected callsite's
arguments/callbacks, then follow the handlers, repositories, models and platform effects it uses.
A navigation host or shared DI container is reading context; importing it does not mean migrating
every sibling route or service. If a dependency cannot be resolved, record the concrete missing
behavior and source location rather than replacing it with a guessed implementation.

Observe representative source states on an authorized emulator using synthetic data. Reuse
matching runtime theme, system-inset and UI-tree facts when available. Source provides the
component tree, ordered modifiers and behavior; runtime facts resolve defaults and measured
platform boundaries. Distinguish measured values from source-derived values and unknowns.

## Keep one lightweight dossier

Read [semantic-transcription.md](references/semantic-transcription.md) for the business-chain loop.
Use the existing page spec/dossier if present; otherwise keep UI and business sections in one
page dossier. Markdown is sufficient. A populated behavior JSON may be reused as an index, but
do not require a new JSON schema, whole-repository census, or an entry per syntax node.

Keep just the facts that guide implementation and let missing work be seen:

- **UI:** source-owned component hierarchy/order, displayed strings, conditional states, ordered
  layout/style expressions, theme/resources, control properties and safe-area policy, with
  source locations. Resolve the reached custom components and their active theme/library defaults,
  not just the page's explicit arguments. Record the values needed to implement the same appearance
  in the existing UI section; reference shared source definitions instead of copying them. Use
  [dossier style reconciliation](references/compose-arkui-mapping.md#dossier-style-reconciliation)
  to distinguish missing source facts from target-platform defaults.
- **Business chains:** trigger/initial state → source handlers/state owner → conditions, state
  writes and data/platform effects → observable result. Include initial load, host callbacks,
  relevant failures and lifetime behavior found in the actual source. Keep the fields written or
  passed across each boundary and their source expressions visible, not just the action name.
- **Implementation and checks:** for each chain, link source definitions, target symbols and
  source-derived checks in the same entry. Track implementation separately from executed checks
  and environment-blocked checks; a working captured state does not close the other chains.

For example, a save chain points to the source validation, conversions, repository write, error
path and navigation outcome. It does not expand into a ledger of every expression. Reopen those
definitions while implementing; the dossier is a reading/verification index, not replacement code.
Unknown material behavior calls for source investigation or a necessary user question, not an
assumed success path.

Use the [direct dossier checks](references/semantic-transcription.md#executable-dossier-checks)
at the existing implementation boundaries: source coverage and a saved baseline before transcription, target
entry/implementation/binding/consumer references after wiring, and executed source-derived tests
before reporting checked behavior. Both existing CLI entrances share these checks. Keep their
anchors and test identifiers in this same dossier, not a second inventory or Contract.
Trace the source page through its actual state/data/platform consumers before fixing that baseline.
Later checks reconcile against it; an omitted chain or rule is repaired and retested, not removed
from the denominator. Completion requires closing every source-backed chain and required check.

## Transcribe and run

Implement each complete chain through UI, state and data/platform boundaries. Preserve source
class/method/state identities and module responsibilities where the target allows it. Translate
the reached definitions and their calls, not a new algorithm inferred from the feature or a
captured result. Keep source-owned conditions, data relationships and effect order in their
corresponding target owners; replace only the platform mechanism beneath those rules. Follow
[semantic-transcription.md](references/semantic-transcription.md#implement-from-source-keep-the-dossier-as-an-index)
while writing the target, including application logic located in data-access code.

Use the existing Harmony project when supplied. For a new independent target the existing
initializer works without an analysis Contract:

```bash
python3 "$SKILL_ROOT/scripts/init_harmony_project.py" \
  --output "$TARGET" --project-name "$PROJECT_NAME" \
  --bundle-name "$BUNDLE_NAME" --sdk-version "$SDK_VERSION"
```

This creates a scaffold only. Set an installed SDK version (for example `6.1.1(24)`).
Read [compose-arkui-mapping.md](references/compose-arkui-mapping.md) for native UI mappings and
[platform-capabilities.md](references/platform-capabilities.md) for the actual platform
boundaries encountered. Preserve source styling, assets and inset policy alongside business code.
Choose target primitives for that source appearance and interaction, rather than their native
default look. Transcribe each source-owned UI component's layout, styling and business callbacks
together; a functional placeholder is an intermediate result, not the completed UI slice.

Work through the page's chain inventory, including the state/data result behind each UI action.
Establish one built, working production chain before expanding the page. Its acceptance test uses
the same composed application entry as the UI and observes the resulting state/data/effect;
controller tests with replacement application callbacks supplement, rather than replace, it.
Before treating a chain as implemented, trace its target entry through the concrete dependency
bindings to the result consumer using the source-to-target reconciliation below. Finish missing
code and wiring before scheduling device verification; execution is not needed to identify an
unused handler, an unbound interface or an unconsumed effect request.
When an external dependency blocks execution, retain the source behavior and record that check
as blocked, then continue the next incomplete chain. Prioritize missing main behavior over
polishing one example or investigating peripheral platform anomalies.

Build with the real Harmony SDK, install on the authorized emulator and exercise the same source
and target scenarios. Use source tests as oracles where possible; compare state, persisted data,
errors and effects as well as visible output. Related cases can share one test run.
Record source/target/build/runtime/visual timings separately, including retries.

Capture matching Android/Harmony route, data, theme and viewport states for local screenshot
comparison. Use direct device capture when an analyzer-backed capture wrapper is inapplicable;
do not invent source mappings to satisfy it. Reuse `compare_local_screenshots.py` for local
diagnostics without reading image pixels. A raw-image score without compatible page/viewport
evidence is diagnostic only, not a visual gate pass.
When the user explicitly authorizes screenshot inspection, follow the scoped
[visual-access exception](references/privacy-boundary.md#explicitly-authorized-screenshot-inspection)
and inspect the paired captures directly as part of acceptance.

Report implemented business chains, executed scenarios and remaining gaps separately from build
and visual results. Missing behavior, stubbed effects or unrun scenarios remain incomplete.
A dossier, a successful build or a screenshot alone cannot establish whole-page business parity.
During implementation, reconcile from the original page triggers into the target and from target
effects back to their source rules, as described in
[semantic-transcription.md](references/semantic-transcription.md#reconcile-coverage-and-meaning).
This is part of implementation, not a dependency on an independent Reviewer. Reuse the existing
trace comparator when tests emit comparable observations; it checks results, not semantic coverage.
Run the dossier target check on the current implementation; it executes one selected test suite
and requires every declared case to pass. A failed or missing case leaves its business check open.
Its reference/test pass is separate from native runtime, visual results and whole-page completeness.

## Acceptance and readiness for batch testing

Keep separate **UI**, **business** and **batch readiness** conclusions in the existing dossier.
Agree the page/flow scope and observable checks from source before implementing; extend them when
an omission is discovered. Passing counts use that scope, not whatever the target happens to do.

**UI passes** when the same source/target route, data and UI states have matching visible content,
component order, layout, styles and interaction feedback. Check the whole page, including scroll
content and reached overlays; inspect relevant selected, focused or expanded states as applicable.
Use actual production theme/defaults and runtime bounds alongside authorized screenshot inspection.
Missing controls/assets/text, clipping, wrong state styling, material layout differences or native
default styling in place of source styling require correction. Small font-rasterization/shadow
differences and harmless system-chrome differences may be recorded as non-blocking; safe areas must
still leave content and actions usable. Preserve full captures when aligning content crops. Record
each remaining difference and its consequence; neither a high SSIM nor a mostly blank screen is
sufficient for acceptance. Without authorized image access, retain human visual acceptance as pending.

**Business passes** when every scoped source-backed chain has its real target implementation,
production bindings and result consumer, and its source-derived acceptance cases pass. Reconcile
conditions, validation, defaults, data relationships/fields, effect order, persistence and relevant
lifetime behavior through UI → state/domain → data/platform → UI. Preserve source-owned method and
module responsibilities instead of replacing them with a feature-level reimplementation. A linked
symbol, stub, fake success or screenshot is not proof of the actual behavior. Exercise each feature's
representative feasible path on the emulator, including production storage/platform connections;
external-condition branches may use controlled inputs beneath application rules. This does not
require reproducing every network/device branch. Keep untested platform effects explicitly pending,
and distinguish approved platform adaptations from equivalent behavior. Missing business rules or
unapproved changed outcomes block acceptance, regardless of the UI result. Reuse the existing dossier
checks and source-derived tests; no independent Reviewer is needed to execute this acceptance.
The acceptance target is complete source-business semantics within the requested page/flow, not
only its primary path: different syntax and platform APIs are acceptable, omitted logic is not.
An exception requires a demonstrated platform limitation with the affected behavior and accepted
adaptation recorded; implementation difficulty, missing code or an unavailable test environment
is not such an exception. Prefer an equivalent target mechanism before accepting a difference.

**Batch readiness is not final delivery acceptance.** Start the batch when a representative pilot
demonstrates source collection, semantic implementation, a working build/install, faithful main UI
structure/style, no known omitted business logic within its scope, and passing source-derived
business checks through production bindings. Missing main controls, invented business behavior,
disconnected persistence or a broken primary path block readiness.
Document small visual differences and untested peripheral/external platform cases without stalling
the whole batch; retain their real status for final acceptance. The implementer makes and records
this decision instead of asking the user to approve every detail. A repaired pilot proves attainable
quality, not first-pass repeatability; evaluate that distinction within the batch rather than adding
another mandatory pilot. Record first output and correction rounds separately, and source collection,
UI/business implementation, build/runtime, acceptance and environment/retry wall time. A failed page
returns to its owning implementation or source fact, not a smaller scope or a changed delivery
threshold. These decisions reuse the dossier, not new workflow states or extra handoff documents.

## Optional tool-backed auditing

When structured CLI audit outputs are specifically required, use
[scripted-migration.md](references/scripted-migration.md) and its relevant references.
Existing source/target validators keep their prerequisites and pass/fail meanings. A direct
dossier run does not set their `source_complete`, `runtime_complete` or `business_verified` flags.
If the surrounding workflow requires such a gate, report its actual pending/failed result rather
than silently substituting dossier completion. This Skill does not change workflow states.

For tool maintenance, read [tooling-architecture.md](references/tooling-architecture.md).
