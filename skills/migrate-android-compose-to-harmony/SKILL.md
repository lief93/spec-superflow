---
name: migrate-android-compose-to-harmony
description: Migrate local Android Jetpack Compose or Android Views/XML applications into buildable HarmonyOS Stage projects using ArkTS and ArkUI, with code-only UI reconstruction, image-byte isolation, behavior contracts, platform capability mapping, unit tests, UITest, and device verification evidence. Use when converting, assessing, planning, or validating an Android-to-HarmonyOS migration, especially when source images must not be exposed to an AI model.
---

# Migrate Android UI to HarmonyOS

Build an auditable migration in vertical slices. Preserve the Android source as read-only, expose
only an audited text snapshot to the model, copy approved assets through local hash-checked tools,
and call a slice complete only after its behavior and build gates pass.

## Establish the boundary

Set four separate paths:

- `SOURCE`: original Android repository; never modify it.
- `SNAPSHOT`: generated model-visible UTF-8 tree.
- `CONTRACT`: generated migration inventory JSON.
- `TARGET`: independent HarmonyOS project.

Do not place `SNAPSHOT` or `TARGET` inside `SOURCE`. Do not inspect source image contents with image
viewers, OCR, base64, hex dumps, browser data URLs, or file-reading tools. After preparing the
snapshot, perform all model-visible source inspection against `SNAPSHOT`, not `SOURCE`.

Read [privacy-boundary.md](references/privacy-boundary.md) before touching a private repository or
when image isolation is required.

If the supplied input already contains `.android-to-harmony-safe.json`, treat it as `SNAPSHOT`.
Skip snapshot preparation and run validation plus analysis directly. The preparer intentionally
refuses to snapshot an existing safe snapshot.

## Start or resume an agent run

When invoked from `spec-superflow`, require the active Change state to contain
`capability: android-to-harmony`. Use the repository-local
`skills/migrate-android-compose-to-harmony` tree as `SKILL_ROOT` when it exists;
do not silently fall back to a personal cache path unless the workflow has no
repo-local skill bundle. Bind the exact skill tree digest into the Change's
evidence before running public regression or benchmark migration commands. These
checks are scoped to Android-to-Harmony Changes only and must not be applied to
ordinary spec-superflow projects.

For a new migration, prefer the resumable orchestrator. `RUN_ROOT`, `SOURCE`, and `TARGET` must be
separate directories that do not contain one another:

```bash
python3 "$SKILL_ROOT/scripts/migration_agent.py" start \
  --source "$SOURCE" \
  --run-root "$RUN_ROOT" \
  --target "$TARGET" \
  --project-name "$PROJECT_NAME" \
  --bundle-name "$BUNDLE_NAME" \
  --sdk-version "$SDK_VERSION"
```

`start` runs snapshot preparation, independent snapshot validation, contract analysis, and target
initialization. It writes `RUN_ROOT/agent-state.json` only after every intake step succeeds. The
resulting target is a scaffold, not migrated business code.

After `start`, Codex must inspect only the safe snapshot and contract, reconcile the candidate
inventory, implement one complete vertical slice at a time in `TARGET`, run the applicable
verification gates, and update a ledger under `TARGET/.migration/slices/`. The CLI does not
translate screens, business logic, or resources. Use `implemented` after source coverage is
finished but any gate is pending or blocked. Use `verified` only after all four required gates
have current, passed evidence explicitly scoped to this slice:

```json
{
  "schema": "android-to-harmony.slice-ledger.v1",
  "id": "home-loading",
  "batch_id": "features",
  "status": "verified",
  "source_files": ["app/src/main/java/example/HomeScreen.kt"],
  "demand_ids": ["home-loading"],
  "required_gates": ["build", "unit_tests", "ui_tests", "device_test"],
  "evidence": [
    ".migration/evidence/build.json",
    ".migration/evidence/unit_tests.json",
    ".migration/evidence/ui_tests.json",
    ".migration/evidence/device_test.json"
  ]
}
```

`source_files` must be a subset of the named contract batch. `implemented` counts as reviewed
source coverage for inventory reconciliation, but it does not count as verified and cannot make
the run complete. A batch remains pending until implemented/verified or explicitly dispositioned
slice ledgers cover all of its candidate source files. Use `intentionally_excluded` with a
non-empty `rationale`, or `unsupported` with both `rationale` and `decision_owner`, for reviewed
source that is not migrated. Do not overlap the same source file across ledgers.

Create evidence only with `scripts/evidence_runner.py`; do not hand-write evidence JSON. The runner
executes an argv after `--` directly without a shell, captures its log, derives JUnit counts when
applicable, hashes the artifact, and signs the full record using the target's external ownership
secret. Keep records under `TARGET/.migration/evidence/` using
[verification-contract.md](references/verification-contract.md). Evidence referenced by a
verified slice must match the current target-source manifest and include that slice ID and a
matching demand ID in scope.

After every safe-snapshot text file has exactly one final disposition, write
`TARGET/.migration/inventory-reconciliation.json`:

```json
{
  "schema": "android-to-harmony.inventory-reconciliation.v1",
  "status": "authoritative",
  "all_snapshot_files_reviewed": true,
  "snapshot_manifest_sha256": "<from agent-state.json>",
  "contract_sha256": "<from agent-state.json>",
  "reviewer": "<actual reviewer or automation>",
  "reviewed_at": "<RFC3339 with timezone>"
}
```

The orchestrator derives authoritative inventory and gate status from these records. Editing the
legacy `verification` values in target state is not evidence.

Resume after an interruption or inspect progress without changing files:

```bash
python3 "$SKILL_ROOT/scripts/migration_agent.py" resume \
  --run-root "$RUN_ROOT"

python3 "$SKILL_ROOT/scripts/migration_agent.py" status \
  --run-root "$RUN_ROOT"
```

`resume` revalidates the immutable snapshot, contract owner record, and target ownership before
reporting the next phase and pending batches. It never regenerates or replaces migrated target
code. `status` is read-only and emits machine-readable JSON containing the candidate/non-
current target revision, and whether the target is still only the generated scaffold. It rejects
stale evidence, symlinked target metadata, and unproved `verified` ledgers. Do not edit
`agent-state.json`; start a new run if its immutable intake artifacts must change.

For a validated target created by an older version that reports `target_ownership` pending, upgrade
it without hand-writing a secret:

```bash
python3 "$SKILL_ROOT/scripts/migration_agent.py" claim-target-ownership \
  --run-root "$RUN_ROOT"
```

## Run the deterministic intake

Resolve the skill directory as `SKILL_ROOT`, then run:

```bash
python3 "$SKILL_ROOT/scripts/prepare_safe_snapshot.py" \
  --source "$SOURCE" \
  --snapshot "$SNAPSHOT"

python3 "$SKILL_ROOT/scripts/validate_ai_safe_tree.py" \
  --require-safe-manifest "$SNAPSHOT"

python3 "$SKILL_ROOT/scripts/analyze_compose_project.py" \
  --snapshot "$SNAPSHOT" \
  --output "$CONTRACT"
```

Use `--force` only to replace an output already owned by the corresponding script. Never forge an
ownership marker to bypass a refusal. Contract analysis refuses existing unowned files and refuses
an output inside either the source or snapshot tree.

After the contract exists, generate a dispatch backlog before splitting work across multiple
agents:

```bash
python3 "$SKILL_ROOT/scripts/generate_migration_backlog.py" \
  --contract "$CONTRACT" \
  --output "$RUN_ROOT/migration-backlog.json"
```

The backlog is a candidate planning artifact, not completion proof. Every backlog item remains
`candidate=true` and `status=pending` until a real migration implementation updates target-owned
slice ledgers and the run reaches authoritative inventory reconciliation. Use the backlog to
assign vertical slices such as routes, screens, composables, viewmodels, repositories, data
adapters, platform capabilities, resources, and tests. Do not upgrade backlog status to
`verified` or `completed`, and do not treat backlog coverage as a substitute for reviewed slice
ledgers or unsupported/intentionally-excluded dispositions.

The workflow and `migration_agent.py` are the only normal user entry points.
Through `start`, `resume`, and `status`, they must automatically generate,
validate, and return the current immutable execution plan together with the
current mutable task state, plus the internal capability graph, fact packs,
gate-evidence bundle, and gate report under `RUN_ROOT`. Do not teach ordinary
users a second CLI workflow for these artifacts. The bundled
`build_capability_graph.py`, `aggregate_gate_evidence.py`, and
`build_execution_plan.py` remain internal maintainer/debug helpers for tests,
reproducibility, and workflow implementation only; they are not a second
normal-user planning seam.

These outputs remain migration-scoped and fail closed. The capability graph and
fact packs are candidate evidence only; they do not become authoritative merely
because they were generated. A parent `page` or `project` must not verify while
an applicable child is still `candidate` or `implemented`, and build or
`ohosTest` compile must never substitute for device, visual, or manual gates.
See [capability-graph-and-gates.md](references/capability-graph-and-gates.md)
for schemas, profile semantics, stale-evidence rules, and the internal artifact
contract.

Stop before source inspection if validation fails. Report blocked sensitive files and symbolic
links without reading their contents. Files containing recognized credential literals are blocked
as a whole. Android values XML keeps obvious UI labels such as
`<string name="password">Password</string>`, but still blocks credential-looking values under
sensitive keys. Local-only image and font assets are expected: use their manifest paths, sizes, and
hashes as opaque identifiers.

## Define executable slices

Inspect `CONTRACT` and relevant text files in `SNAPSHOT`. Build a route-to-data dependency chain for
each feature:

```text
entry route → screen → actions → state holder → use case/repository → model/platform API
```

For each slice, write a machine-readable ledger under `TARGET/.migration/slices/` containing:

- included source modules, routes, files, states, and actions;
- observable behavior to preserve;
- tests to port or add;
- intentional security/platform changes;
- exclusions and unsupported capabilities.

Keep source behavior and proposed improvements separate. Preserve behavior by default; record a
source bug or security exception instead of silently changing it.

When backlog generation emits `unassigned_source_files`, keep them visible and reconcile them
before closure. A file is complete only when exactly one final slice ledger or supported
disposition covers it and `inventory-reconciliation.json` is current.

Treat the generated contract as a candidate inventory. Reconcile every ignored path and the actual
Gradle module/build graph before using it as a completeness ledger. In particular,
`dependency_inventory.candidate_count` is an approximate static-call count, not the resolved Gradle
dependency graph. Comments and quoted literals are excluded, and conventional variant plus
explicitly declared custom configurations are recognized, but plugin-created or dynamic
configurations can still be missed.

`platform_capabilities` is also candidate-only. It scans supported source, Gradle/TOML, and XML
files while excluding documentation, baseline profiles, code comments, and quoted code literals.
Ordinary manifest-only permissions such as `INTERNET` are not classified as runtime-permission
flows. Reconcile dynamic API use, reflection, generated code, and dependencies whose behavior is
hidden outside the safe snapshot.

`ui.custom_image_component_inventory` is also non-authoritative. A custom `*Image` call is retained
only when the safe text associates it with an explicit import or an `@Composable` definition. That
reduces suffix-only false positives but cannot eliminate alias/shadowing errors, and image-rendering
components with other names can still be missed. These candidates describe code structure only;
they never establish image contents or visual fidelity.

`ui.semantic_translation_candidates` preserves candidate UI call hierarchy, named layout and
typography/content/visual arguments, non-Modifier positional arguments, ordered Modifier calls from named or direct positional
`Modifier` arguments, dimension references/units, and recognized custom-image state slots. Only
top-level Modifier calls belong to the ordered chain; calls nested inside Modifier arguments are
not separate modifiers. Parenthesized and trailing-lambda modifiers are retained. The UI
inventory also retains Compose component calls that omit parentheses and use only a trailing
content lambda, such as `Column { ... }`, so their children remain attached to the right parent.
The route
inventory recognizes direct and custom composable wrappers, resolvable constant/string-template
expressions, enum-backed `route` properties, and sealed destination objects whose `route` getter
returns `this::class.java.simpleName`. Use these inventories as semantic transcription
aids, not complete Kotlin ASTs. Reconcile aliases, helper-returned Modifier variables, generated
DSL calls, dynamic route expressions, runtime branches, and library-hidden behavior before calling
a slice covered. Preserve separate parent/child padding and source-defined state branches; do not
flatten the contract into a screen description and reimplement it from memory.
Kotlin comments are masked before top-level named UI/theme arguments are normalized, so commented
default values do not become active role or component expressions.

The analyzer attaches `primitive_mapping_id` only to recognized non-project Compose primitives.
The referenced candidate definitions appear in `ui.primitive_component_mapping_catalog` and come
from the machine-readable global baseline under `assets/compose-arkui-primitive-mappings.json`.
Use each definition as a review checklist for source semantics, states, geometry, and possible
ArkUI components, not as generated target code or parity proof. Resolve the actual Compose import,
Material dependency version, and theme before implementation. The analyzer records explicit
Compose imports as stronger candidate evidence and rejects an explicit non-Compose import with the
same simple name; calls reached only through wildcard imports or implicit scope remain unresolved
simple-name candidates. A resolved project-defined composable never receives a global primitive
mapping; expand its call graph and reuse the mapped primitives inside it instead.

The catalog includes candidate checklists for common animation, flow layout, pager, navigation,
form, menu, picker, staggered-grid, canvas, card, tab, chip, and clickable-text families exercised
against fixed revisions of unrelated public Compose projects. This broadens primitive recognition;
it does not turn a mapping into generated parity or authorize promoting project-private wrappers.

`ui.compose_theme_token_inventory` extracts candidate code-defined color and font-family tokens,
literal `dp`/`sp` dimension tokens, Material 2/3 light and dark color schemes, typography roles and
their `TextStyle` properties, shape roles, and `MaterialTheme` applications. Conditional bindings
such as a runtime dark-theme selection are retained when they directly feed the theme call. Use
this inventory to create project-local Harmony color, float, font, typography, and shape resources
before translating screens; do not substitute a public sample project's tokens. Aliases,
delegated/helper-returned values, `CompositionLocal` overrides, runtime palette generation, and
Material defaults still require source and dependency-version reconciliation.
The resource generator currently fills only the Material3 `lightColorScheme` default
`onPrimary` color when the source omits that role; treat it as a candidate library default, not a
complete generated Material default color table.

After reconciling the selected theme declarations, generate candidate Harmony resources into an
initialized target:

```bash
python3 "$SKILL_ROOT/scripts/generate_harmony_theme_resources.py" \
  --contract "$CONTRACT" --target "$TARGET" --module entry
```

The generator merges owned names into base/dark `color.json` and, when non-empty, base
`float.json`, records typography/shape contracts and a font opaque-copy plan under `.migration`,
and binds every output with SHA-256. It omits empty resource-category files because Harmony rejects
empty resource arrays. When distinct declarations normalize to one resource name with different
values, it omits the ambiguous resource, records `resource_name_collision`, and leaves
`resource_skeleton_complete=false`. That completeness flag covers only statically resolved
resource generation; it is not migration completion. Use `--force` only when all prior generated
outputs are unchanged.

After theme resources exist, generate one exact Compose component closure as a conservative ArkUI
page candidate:

```bash
python3 "$SKILL_ROOT/scripts/generate_arkui_page.py" \
  --contract "$CONTRACT" --target "$TARGET" --module entry \
  --root-source "app/src/main/java/example/HomeScreen.kt" \
  --root-composable "HomeScreen" \
  --android-page-json "$ANDROID_PAGE_JSON"
```

The root identity is the source-relative path plus composable name; a name alone is deliberately
insufficient. Generate `ANDROID_PAGE_JSON` from the exact Android route/state capture before
high-fidelity page generation. The generator accepts only a v2 Android page snapshot, binds its
hash, page/state, viewport, screenshot identity, and applied property paths into the generation
manifest, and maps runtime components to exact source `call_id` values through the embedded source
attribute inventory. Proven Android geometry, content, typography, spacing, surface, and transform
facts override static visual defaults where a compile-safe ArkUI emitter exists. Missing or
ambiguous call mappings, unresolved Android visual facts, unproved values, and proven properties
without a safe emitter remain explicit generation blockers rather than being guessed.

Without `--android-page-json`, the command retains its legacy code-only candidate behavior for
diagnostic and compatibility runs; do not use that legacy mode as pixel-fidelity evidence. The
generator also consumes `transitive_closures`, reached definitions, semantic calls,
invocation arguments, parent call IDs, and ordered Modifier chains. It emits a separate ArkUI
builder for every reached project component, uses generated theme resource names only when their
hash-checked theme manifest is current, and writes a hash-bound manifest under
`.migration/arkui-pages/`. It emits no generic UI fallback for an unresolved call. Instead, the
manifest records the exact call/parameter/modifier/asset issue and sets `generation_complete` to
`false`; a buildable incomplete page is not fidelity evidence. Repeat execution is refused, and
`--force` is accepted only when every previously generated output is unchanged.

This generator intentionally covers only compile-safe static semantics. Runtime branches,
collection DSLs, state holders, callbacks, Material-version defaults, asset resolution, and
platform-specific components remain explicit implementation work unless their manifest contains
no unresolved record. Compile the generated source, then continue the vertical-slice migration;
never treat generation or compilation alone as a completed screen.

`ui.custom_composable_call_graph` resolves project `@Composable` calls reached through explicit
imports, same-package visibility, or same-file definitions. Before implementing a screen, traverse
its graph transitively and review every reached component plus the recorded invocation arguments.
Use `transitive_closures` to select an exact source/composable root and inspect its reached
definitions, project-component calls, mapped primitive coverage, unmapped components, and cycles.
Composable parameter defaults are retained for static UI values, and the page generator may use
compile-safe defaults such as literal `Dp` and `Color` values when an invocation omits them.
Default Android `<string>` resources from `res/values` are copied into Harmony app-level string
resources during target initialization, and static `stringResource(...)`,
`UiText.StringResource(...)`, `UiText.DynamicString(...)`, and `.asString()` calls may be emitted
as `ResourceStr` when the referenced key exists in the target. A default-locale
`stringResource(...).uppercase()` may be emitted as static text from the copied default string
value; locale-sensitive case mapping remains explicit reconciliation work.
`BasicTextField`/`TextField`/`OutlinedTextField` may be emitted as a conservative ArkUI `TextInput`
only when the source `value` and `onValueChange` are compile-safe string parameters or literals;
Material decoration, keyboard behavior, transformation, and validation semantics remain explicit
unresolved records unless separately reconciled.
Static analyzer output filters unresolved lowercase Modifier/helper calls out of the UI component
list while retaining resolved lowercase project composables. Container-like primitives such as
`BoxWithConstraints` and `CenterAlignedTopAppBar` may be emitted as structural ArkUI containers
with a `component_semantics` record for defaults/slot behavior that still needs reconciliation.
`BasicText` may use the same conservative text emission path as `Text`, and `ClickableText` may
emit static display text while retaining annotation, span, and click-offset work as
`component_semantics`. `LazyRow`, `Canvas`, and `DatePickerDialog` may be emitted only as
structural containers to preserve hierarchy and keep the generated page buildable; item
virtualization, drawing commands, picker state, dismissal, and sheet/dialog behavior remain
explicit reconciliation work.
Static `painterResource(R.drawable.name)` calls may emit an ArkUI `Image` only after a matching
`base/media/name.*` asset has been copied or converted locally through the manifest-approved asset
tools. The generator may apply literal/static tint, but dynamic painter expressions and missing
media remain asset gaps.
`Modifier.then(Modifier...)` is expanded into the nested modifier chain when the nested expression
is static, so supported inner padding/size/background/fill modifiers can still be emitted.
Compile-safe no-op/default-layout modifiers such as no-argument `wrapContentWidth`,
`wrapContentHeight`, and `wrapContentSize` may be omitted, and `matchParentSize`, literal
`heightIn`, literal `alpha`, and direct callback-parameter `clickable(onClick = ...)` may be
emitted as ArkUI width/height, constraint, opacity, and click handlers. Non-literal constraints,
custom gestures, interaction sources, indications, semantics, and parent-scope modifier behavior
remain explicit unresolved records.
Project composable parameters of type `Modifier` are classified as UI-boundary forwarding rather
than unknown Kotlin data types; unsupported call-site forwarding is still recorded separately.
Do not replace a source component closure with a newly designed screen that merely serves the same
purpose. Wildcard imports, generated functions, overload resolution, function-valued variables,
and runtime branches remain candidate-only and require source reconciliation.

Keep mappings for project-defined components local to the current migration. Reuse a reconciled
custom-component mapping across that target's pages, but do not promote the sample project's
composition, branding, or styling into the global Skill by default. Global mapping rules should
prefer versioned Compose/Material primitives and ArkUI platform semantics. A project-local pattern
may become a shared rule only after its project-specific theme tokens and business behavior are
removed and independent projects prove the remaining semantic pattern is actually common.

For Android Views or hybrid Fragment/Compose projects, use the candidate
`ui.android_view_layout_inventory`, `ui.android_navigation_inventory`,
`ui.android_activity_inventory`, `ui.android_binding_adapter_inventory`, and
`ui.android_value_resource_inventory` together. Preserve XML parent/child hierarchy, qualifiers,
IDs, namespaced attributes, data-binding expressions, included layouts, Navigation XML graph
starts/destinations/actions/arguments/deep links, Activity launch modes, explicit navigation
extras, styles, dimensions, colors, and locale resources. A BindingAdapter is
behavior, not decoration: inspect its source body and translate pagination, visibility, event,
loading, dynamic-color, and adapter semantics into the target state/controller contract. These
inventories are static candidates; reconcile style/theme inheritance, resource overlays,
generated Safe Args and binding code, runtime BindingAdapters/navigation, included or nested graph
back-stack composition, and library behavior before
calling a slice covered.

Use [compose-arkui-mapping.md](references/compose-arkui-mapping.md) for UI, state, navigation, and
resource translation. Read [platform-capabilities.md](references/platform-capabilities.md) when the
contract reports Android-specific APIs.

## Initialize the target

For a new target, run:

```bash
python3 "$SKILL_ROOT/scripts/init_harmony_project.py" \
  --output "$TARGET" \
  --project-name "$PROJECT_NAME" \
  --bundle-name "$BUNDLE_NAME" \
  --sdk-version "$SDK_VERSION" \
  --contract "$CONTRACT"
```

Set `SDK_VERSION` to an installed HarmonyOS SDK release such as `6.1.1(24)`. The default remains
`6.0.1(21)` for compatibility with existing runs; use the option when the installed SDK differs.
The initializer writes that value only to project-level `app.products[]` as `targetSdkVersion` and
`compatibleSdkVersion`. Current DevEco/Hvigor schemas do not permit these fields in the module
`build-profile.json5`. `compileSdkVersion` is not rendered by this Skill and therefore follows the
HarmonyOS schema default: the SDK bundled with DevEco Studio.

The bundle name must satisfy the HarmonyOS three-segment schema. The initializer refuses arbitrary
non-empty directories, Git repositories, symlink destinations, malformed contracts, targets inside
the source/snapshot, and forced replacement after any generated file or extra file changes.

When a validated contract is regenerated after target creation, attach its sanitized copy without
exporting local paths:

```bash
python3 "$SKILL_ROOT/scripts/attach_contract_to_target.py" \
  --contract "$CONTRACT" \
  --target "$TARGET" \
  --force
```

The command replaces only the unchanged contract already recorded by the target state.

Run dependency installation before tests:

```bash
export DEVECO_HOME=/Applications/DevEco-Studio.app
export PATH="$DEVECO_HOME/Contents/tools/ohpm/bin:$DEVECO_HOME/Contents/tools/hvigor/bin:$PATH"
ohpm install
```

On non-macOS hosts, locate the equivalent DevEco Studio `ohpm` and `hvigor` directories and prepend
them to the existing `PATH`; never replace the existing `PATH`.

If the registry is unavailable, retain the lockfile and use an approved local package cache. Do not
vendor dependencies from an unrelated project into source control.

## Implement page-fact-driven visual parity

Migrate one complete dependency chain at a time:

1. Use Android source to enumerate the route's deterministic visible states and business transitions.
2. Capture one Android page JSON and screenshot for every applicable route/state.
3. Generate the initial ArkUI hierarchy and visual properties from proven page JSON facts.
4. Use Android source to implement callbacks, state, navigation, scrolling, lifecycle, and responsive intent.
5. Copy referenced opaque assets locally only after matching resource keys to manifest paths.
6. Generate the matching Harmony page JSON and compare the structured page facts.
7. Compare the paired screenshots for the final pixel-fidelity verdict.
8. Add unit, demand-related UITest, and device scenarios for the slice.

For visual implementation, Android page JSON is the primary rendered-state contract: component
hierarchy, geometry, padding/margin, typography, surfaces, assets, transforms, and visible state.
Android source remains authoritative for behavior and layout intent that a single rendered frame
cannot express. The screenshot is the final pixel-level acceptance input, not a substitute for
either the structured page facts or the source behavior contract.

Copy an approved image or font asset without exposing its bytes:

```bash
python3 "$SKILL_ROOT/scripts/copy_local_asset.py" \
  --manifest "$SNAPSHOT/.android-to-harmony-safe.json" \
  --asset-path "app/src/main/res/drawable/example.png" \
  --target "$TARGET" \
  --destination "$TARGET/entry/src/main/resources/base/media/example.png"
```

The source path must exactly match a manifest entry, and the pre-copy/post-copy size and SHA-256
must match. `--force` may replace only a destination whose bytes already match that same approved
asset. Android drawable/mipmap XML is deliberately rejected by the copier because it requires
explicit HarmonyOS resource conversion rather than an opaque byte-for-byte copy.

Copy manifest-approved `.ttf` and `.otf` fonts byte-for-byte into a target
`resources/rawfile` subtree and keep the original extension. The copier never parses or prints
font contents. Image assets remain restricted to HarmonyOS `resources/**/media` directories.

Convert a supported manifest-approved Android VectorDrawable locally without exposing its XML or
path data:

```bash
python3 "$SKILL_ROOT/scripts/convert_android_vector.py" \
  --manifest "$SNAPSHOT/.android-to-harmony-safe.json" \
  --asset-path "app/src/main/res/drawable/example.xml" \
  --target "$TARGET" \
  --destination "$TARGET/entry/src/main/resources/base/media/example.svg"
```

The converter currently supports literal `width`, `height`, `viewportWidth`, `viewportHeight`,
`autoMirrored`, root `tint`, and path `pathData`, `fillColor`, `fillAlpha`, `fillType`, basic
`strokeColor`/`strokeAlpha`/`strokeWidth`, and stroke cap/join/miter fields. An omitted path fill is
preserved as Android's transparent default. A conversion reporting
`requires_auto_mirroring: true` must be used through an ArkUI `Image` with
`matchTextDirection(true)`. A same-module `@color` may resolve only through
hash-verified default `values/*.xml`. The fixed Android platform colors `black`, `white`, and
`transparent` are translated to their documented literals and recorded by token. One dynamic theme
attribute is preserved as `currentColor`;
when `requires_target_tint` is true, translate its `dynamic_color_tokens` entry to the equivalent
Harmony color and apply it at the ArkUI image boundary. The converter rejects other vector
semantics rather than silently approximating them. Its stdout and
`.migration/vector-conversions.json` contain hashes and converted field names, never XML, path
data, or SVG bytes. Do not open the source or generated SVG with model-visible tools.

To materialize static drawable/mipmap resources in one local-only step, use the batch wrapper:

```bash
python3 "$SKILL_ROOT/scripts/materialize_static_drawables.py" \
  --manifest "$SNAPSHOT/.android-to-harmony-safe.json" \
  --target "$TARGET" \
  --module entry
```

Repeat `--name drawable_name` to restrict the batch to known referenced resources. The wrapper
delegates PNG/SVG copies to `copy_local_asset.py` and VectorDrawable XML conversion to
`convert_android_vector.py`, preserving the same no-image-inspection boundary.

Prefer native ArkUI and HarmonyOS kits. Do not add a third-party UI framework unless the source
contract requires it and the user approves it. Do not copy trust-all TLS, secret logging, embedded
credentials, or Android-only permission assumptions.

When the contract reports `app-widget-glance`, migrate it as a Harmony Form, not as an ordinary
page. Add the `FormExtensionAbility`, form metadata/config, card source, size/dimension mapping,
provider data, per-instance cleanup, empty/content branches, and card actions. Compile the real
Form card because Form supports fewer ArkUI components than a normal page; on the API 24 SDK,
`Grid`/`GridItem` must be replaced by a semantics-preserving supported layout such as paired items
inside `List` rows. Verify launcher placement and action routing on a device before marking the
slice verified.

Before implementation, derive the state-capture matrix from source branches and interactions:
default, loading, empty, error, selected, disabled, dialog/sheet, keyboard-open, and meaningful
scrolled states when they exist. Do not invent captures for states the source cannot reach, and do
not let one default-state page JSON stand in for a visually different branch.

Use each state's Android page JSON to drive the ArkUI visual boundary, then reconcile source
semantics that a rendered frame cannot prove: parent/child ownership, ordered modifiers, dynamic
conditions, layout constraints, callbacks, navigation, and semantic roles. Translate `dp` to `vp`
and `sp` to `fp`; a Web/RichText physical-pixel boundary must use an explicit scale conversion and
must not map `16.sp` to `16px`. Keep nested padding layers additive. Do not add spinner, fallback
icon, button, animation, or decoration absent from the captured state and corresponding source
branch. Keep project-private component mappings local to the target until at least two unrelated
public projects prove the remaining rule is general.

## Diagnose screenshot differences locally

After page-JSON-driven implementation and structured Android/Harmony page comparison, compare the
authorized screenshots with the local-only diagnostic tool:

```bash
python3 "$SKILL_ROOT/scripts/compare_local_screenshots.py" \
  --left "$ANDROID_SCREENSHOT" \
  --right "$HARMONY_SCREENSHOT" \
  --left-label android \
  --right-label harmony \
  --left-components "$ANDROID_COMPONENT_BOUNDS" \
  --right-components "$HARMONY_COMPONENT_BOUNDS" \
  --source-attributes "$SOURCE_ATTRIBUTE_INVENTORY" \
  --left-crop x,y,width,height \
  --right-crop x,y,width,height \
  --target-size widthxheight \
  --output-dir "$NEW_COMPARISON_DIRECTORY"
```

The command uses only the local Pillow package; install it with
`python3 -m pip install 'Pillow>=9.1'`. It starts no external image process. It refuses
symbolic-link inputs and existing output directories, removes partial output after processing
errors, and does not record absolute input paths. It emits a candidate JSON report, normalized
inputs, amplified and annotated difference images, and a side-by-side image. The report binds the
comparator, input, and image-artifact hashes and records the Pillow version; stdout includes the
report SHA-256 so the caller can retain an external binding.

Align route, state, scroll position, viewport, font scale, locale, theme, and dynamic data before
interpreting `ssim_color`, `ssim_luma`, or `ssim_edges`. With v2 page snapshots, each side is
automatically cropped to its recorded content bounds and component geometry is rebased to that
content origin; explicit crop arguments override the automatic values. These metrics locate
regressions; `difference_analysis.regions` groups connected changed tiles, while
`difference_analysis.hotspots` ranks the most severe individual tiles and maps their normalized
bounds back to both input screenshots. These are location candidates, not source-code fix
instructions. Optional component-bound inventories add per-hotspot Android/Harmony component
candidates; a shared sanitized `semantic_key` adds a cross-platform pair candidate. The aggregated
`difference_analysis.component_impact_summary` exposes that key as `source_component`, ranking the
runtime/source components to inspect first and listing their hotspot IDs. The inventory schema
rejects display text, unknown fields, stale screenshot dimensions, and non-identifier tokens.
Component pairing and the impact summary remain candidate-only.

Create `SOURCE_ATTRIBUTE_INVENTORY` from the same exact Compose closure before comparison:

```bash
python3 "$SKILL_ROOT/scripts/generate_source_attribute_inventory.py" \
  --contract "$CONTRACT" \
  --root-source "app/src/main/java/example/HomeScreen.kt" \
  --root-composable "HomeScreen" \
  --output "$NEW_SOURCE_ATTRIBUTE_INVENTORY"
```

The inventory is deliberately display-content-free: it retains only safe source-relative
locations, call lines, component/attribute names, Modifier indices, units, and resource keys. It
also expands uniquely invoked project composables into a source-semantic parent/preorder graph and
retains only allowlisted compile-time numeric layout sizes, offsets, scales, and rotations. Page
snapshots use that graph before runtime containment, compressing uncaptured wrapper calls to the
nearest captured source ancestor; repeated or ambiguous invocation sites stay on the runtime
fallback instead of being guessed.
Each deterministic `semantic_key` identifies one exact semantic `call_id`, not a composable-wide
group, so page JSON can drive one ArkUI call without ambiguous source ownership. When that key
matches the component-bound inventories, the comparator adds exact source attribute candidates and
a metric-weighted attribute-group inspection order to the component impact summary. This narrows
where to inspect; it is not a proven diagnosis, a suggested fix, or permission to change the
highest-ranked property without source reconciliation.

For HarmonyOS, copy
`assets/ohos-uitest-component-bounds/ComponentBounds.ets` into the target's `src/ohosTest`, add
stable ArkUI IDs at source component boundaries, and log the returned inventory with the exact
`OHOS_COMPONENT_BOUNDS:` marker. Clear Hilog before the one export test, require the Hypium test to
pass, then pipe that Hilog into `scripts/extract_ohos_component_bounds.py --output <new.json>`.
The exporter never reads display content; the extractor requires one record and binds the output
with SHA-256. Capture the same stable page immediately after the test and reject stale or
dimension-mismatched pairs. See the reference for the exact sequence and the consecutive-versus-
atomic capture boundary.

For Android Compose, copy
`assets/android-compose-uitest-component-bounds/ComponentBounds.kt` into an independent Android
build copy's `src/androidTest`. Add stable test tags at source component boundaries, expose them
from the screen root with `testTagsAsResourceId`, and capture through an `ActivityScenario` test.
Pipe its unique `ANDROID_COMPONENT_BOUNDS:` status record through
`scripts/extract_android_component_bounds.py`. This UiAutomation path does not wait for permanent
Compose animations to become idle and does not read node display content. See the reference for
the exact privacy and screenshot-pairing contract. If the project's Compose version does not
provide `testTagsAsResourceId`, use the adjacent `ComposeSemanticsComponentBounds.kt` compatibility
asset with a frozen Compose test clock, a bounded readiness loop, and the real Compose-view screen
offset. Keep the accessibility path as the default for supported versions.

Generate one canonical page JSON for each captured Android and HarmonyOS page state. Both commands
emit `android-to-harmony.page-snapshot.v2`, bind the component inventory to the exact screenshot
dimensions and SHA-256, convert runtime bounds to px and logical units, record safe-area/content
bounds, infer parent/child order, and attach matching source attributes plus resolved visual facts
through `semantic_key`. Read [page-snapshot.md](references/page-snapshot.md) for the complete visual
fact schema, provenance rules, and cross-device viewport requirements. Physical screenshot sizes
may differ; whole-screen pixel metrics require equivalent logical content aspect, orientation,
system-bar crop, font scale, locale, theme, state, and scroll position.

For a component with a proven non-identity rotation or scale, platform runtime APIs may expose
different clipped/transformed AABBs. In that case the strict comparator uses the proven
pre-transform layout size plus translation/scale/rotation contract and retains both runtime AABBs
as diagnostics. This mode is unavailable unless both sides carry the complete transform
provenance and at least one proven pre-transform layout dimension; an unproved transform continues
to use ordinary runtime geometry and can fail the 1dp gate.

Use the v2 component-bound capture assets so runtime system-bar, navigation-area, and cutout Insets
travel with the exact screenshot. The page generator consumes those Insets automatically. Supply
`--insets-px` only as an explicit override for a deliberately different content crop; never use a
fixed device-independent status-bar height.

Collect visual facts in the same deterministic state and emit exactly one
`ANDROID_VISUAL_FACTS:` or `HARMONY_VISUAL_FACTS:` marker. Convert it with
`extract_android_visual_facts.py` or `extract_harmony_visual_facts.py`; do not hand-copy JSON.
Runtime-inspectable values use `origin=runtime`; values resolved from exact XML/Compose/ArkTS or
resource declarations use `origin=source_resolved`; retain state-dependent expressions under
`unresolved`. Never label an unexposed property as runtime-measured.

```bash
python3 "$SKILL_ROOT/scripts/generate_android_page_json.py" \
  --page-id home --state-id default \
  --screenshot "$ANDROID_SCREENSHOT" \
  --components "$ANDROID_COMPONENT_BOUNDS" \
  --visual-facts "$ANDROID_VISUAL_FACTS" \
  --source-attributes "$SOURCE_ATTRIBUTE_INVENTORY" \
  --density "$ANDROID_DENSITY" --font-scale "$ANDROID_FONT_SCALE" \
  --orientation portrait \
  --device-id "$ANDROID_DEVICE_ID" \
  --device-model "$ANDROID_DEVICE_MODEL" \
  --os-version "$ANDROID_OS_VERSION" \
  --output "$NEW_ANDROID_PAGE_JSON"

python3 "$SKILL_ROOT/scripts/generate_harmony_page_json.py" \
  --page-id home --state-id default \
  --screenshot "$HARMONY_SCREENSHOT" \
  --components "$HARMONY_COMPONENT_BOUNDS" \
  --visual-facts "$HARMONY_VISUAL_FACTS" \
  --source-attributes "$SOURCE_ATTRIBUTE_INVENTORY" \
  --density "$HARMONY_DENSITY" --font-scale "$HARMONY_FONT_SCALE" \
  --orientation portrait \
  --device-id "$HARMONY_DEVICE_ID" \
  --device-model "$HARMONY_DEVICE_MODEL" \
  --os-version "$HARMONY_OS_VERSION" \
  --output "$NEW_HARMONY_PAGE_JSON"
```

Pass these files to `compare_local_screenshots.py` through `--left-components` and
`--right-components`. The comparator verifies that each page JSON names the exact screenshot bytes,
then rejects mismatched page/state pairs and reports explicit missing components, hierarchy and
sibling-order changes, logical geometry deltas, property-level spacing/surface/typography/asset/
transform/state/content deltas, unresolved facts, viewport compatibility, and pixel hotspots.
Generate one pair per route and deterministic UI state; never reuse a default-state JSON for a
dialog, loading, empty, error, selected, or scrolled screenshot.

The report and command stdout include a final `pass` or `fail`. A pass requires complete v2 page
snapshots, equivalent component presence and hierarchy, geometry within 1dp, no unresolved or
one-sided proven style facts, compatible logical viewport/orientation/font scale, and all three
SSIM metrics at or above `--min-ssim` (default `0.95`). Process exit code zero means comparison
completed; read `verdict` for the UI result. The color-channel tolerance remains 8. Raw asset pixel
dimensions are retained as metadata, while cross-density size comparison uses normalized logical
units. This automated verdict does not replace authorized product acceptance. Treat every generated
PNG as protected image data. For private screenshots, neither the
model nor a model-visible image tool may open the inputs or outputs. See
[local-image-comparison.md](references/local-image-comparison.md) for the workflow and metric
limits.

## Verify every slice

Read [verification-contract.md](references/verification-contract.md), then run the applicable gates:

```bash
export DEVECO_HOME=/Applications/DevEco-Studio.app
export PATH="$DEVECO_HOME/Contents/tools/ohpm/bin:$DEVECO_HOME/Contents/tools/hvigor/bin:$PATH"
export DEVECO_SDK_HOME="$DEVECO_HOME/Contents/sdk"

hvigorw test --mode module \
  -p module=entry@default \
  -p product=default \
  -p buildMode=debug \
  --no-daemon

hvigorw assembleHap --mode module \
  -p module=entry@default \
  -p product=default \
  -p buildMode=debug \
  --no-daemon

hvigorw assembleHap --mode module \
  -p module=entry@ohosTest \
  -p product=default \
  -p buildMode=debug \
  --no-daemon
```

After the final source/test/config change, bind evidence to a deterministic target manifest:

```bash
python3 "$SKILL_ROOT/scripts/hash_target_source.py" \
  --target "$TARGET" \
  --output "$TARGET/.migration/target-source-manifest.json"
```

The evidence runner derives this revision itself; do not copy it into hand-authored JSON.
The revision hashes each slice's definition but excludes its lifecycle-only `status`, `evidence`,
and `blocker` fields. This permits the normal `implemented → run gates → verified` transition
without invalidating the evidence while still detecting scope changes.

Run demand-related UITest on an emulator or device. Treat `ohosTest` compilation as compile
evidence only, never as proof that UITest executed. Passed UITest evidence must use direct
`hdc shell aa test` with `--test-report-from-stdout --test-report-format hypium-text`,
`--ui-main-hap <main.hap>`, and `--ui-test-hap <ohosTest.hap>` instead of a report path. The
runner installs those exact non-empty HAPs, in main-then-test order, through the same trusted HDC
and explicit `-t` value matching `--device-id`; it records their hashes and installation output,
then strictly converts only that subprocess's complete `OHOS_REPORT_*` stdout into its owned
report. The consumer reconstructs the command log from the signed fields, re-parses the owned
Hypium report, and requires both views to agree. An installation failure prevents `aa test` from
running.

For generated or migrated ArkTS UITest code, never cache a component across an interaction that can
recompose the page. Re-query the next component immediately before acting on it, especially after
`TextInput.onChange`, navigation, dialog, list mutation, or validation-state updates. For text
entry, prefer a small project-local helper that clicks the field, dismisses known one-time system
IME/permission prompts on the test device, uses `inputText(value, { paste: true })` when the SDK
supports it, hides the keyboard, and waits for UI idle before locating the next control. Device
first-run IME setup screens are environment state, not source-app behavior; handle them in the
test harness or device preflight so they do not masquerade as app migration failures. Keep the
accepted prompt labels local to the test/device profile and do not treat them as app assertions.

Run each gate through the controlled runner. For example:

```bash
python3 "$SKILL_ROOT/scripts/evidence_runner.py" run \
  --target "$TARGET" --run-root "$RUN_ROOT" \
  --gate unit_tests --name unit-tests \
  --slice-id home-loading --demand-id home-loading \
  --test-report entry/.test/default/intermediates/test/coverage_data/test_result.txt \
  --test-report-format hypium-text \
  -- "$DEVECO_HOME/Contents/tools/hvigor/bin/hvigorw" \
  test --mode module -p module=entry@default --no-incremental --no-daemon
```

Use `probe` with non-empty `--blocker` and `--next-action` to record a failed signing/device
preflight. A successful probe is rejected rather than mislabeled blocked. HDC is known to return
exit code zero for some device failures, so the runner also recognizes its standard
`[Fail][E######]` line and records both the marker and the real zero exit code. The runner accepts only
gate-appropriate Harmony command categories: build assembly cannot attest UITest execution, and a
passed UITest must use the controlled HDC stdout path, install both declared HAPs successfully,
and produce a complete Hypium result containing at least one pass.

Command evidence is accepted only when the resolved executable is under a configured Harmony
toolchain root. Set both `DEVECO_HOME` and `DEVECO_SDK_HOME` for a DevEco Studio installation;
`OHOS_SDK_HOME` or `HOS_SDK_HOME` may identify a standalone HDC SDK. A same-named script elsewhere
is rejected. The evidence records the configured root and executable-relative path as well as the
executable hash.

Use `record` for a demand-related device scenario only after the named human actually completed
the steps. Codex must not execute a human `device_test` or `visual_review` record on that person's
behalf: present the command to the provider and wait for their result. Use `visual_review` only
after a named human reviewed the code-defined UI against an authorized local reference. Do not
invent either provider. A visual-review record contains text findings only; never attach or inspect
protected image bytes.

```bash
python3 "$SKILL_ROOT/scripts/evidence_runner.py" record \
  --target "$TARGET" --run-root "$RUN_ROOT" \
  --gate device_test --name device-scenario --record-status passed \
  --slice-id home --demand-id home \
  --device-kind emulator --device-id emulator-1 \
  --os-version HarmonyOS --api-version 24 \
  --provider-kind human --provider "actual human provider" \
  --scenario-step "Launch the demand" \
  --expected "Expected behavior" --actual "Observed behavior"

python3 "$SKILL_ROOT/scripts/evidence_runner.py" record \
  --target "$TARGET" --run-root "$RUN_ROOT" \
  --gate visual_review --name visual-review --record-status passed \
  --slice-id home --demand-id home \
  --evidence-owner "actual human name" \
  --actual "Observed comparison result" \
  --notes "Local review notes; no image bytes"
```

The runner records the trusted toolchain root, resolved executable path/hash, command log, current
source revision, and newly generated HAP or test-report hash. Its tool-root check and external HMAC
detect common same-name substitution, accidental edits, and copying between targets; they are not
OS-backed signatures and cannot prove tool or human identity against a malicious process running
as the same local user.

## Completion rule

Do not describe the application as fully migrated until:

- every source route/module is `verified`, `intentionally excluded`, or `unsupported`;
- the HarmonyOS application builds;
- pure behavior contracts pass;
- demand-related UITest flows execute on a device;
- demand-related manual device scenarios pass;
- resource keys resolve and opaque asset hashes match local copies;
- platform/security differences are documented;
- a current `visual_review` record from the actual human covers every slice marked
  `human_visual_check_required`.

Report progress as verified slices and remaining inventory. Never convert file count into a
percentage of functional completeness.
