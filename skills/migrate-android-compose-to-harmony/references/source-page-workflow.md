# Source to Lanhu JSON to ArkUI

This is the implementation-stage recipe used inside the migration workflow. It is not a
second planning entry point: normal runs still start/resume through `migration_agent.py`.
The page-level commands below wrap the existing parser, state projection and ArkUI
generator. They do not add another translation implementation.

## One command for one page

With an existing snapshot, analysis contract and project style configuration:

```bash
python3 "$SKILL_ROOT/scripts/migrate_compose_page.py" \
  --snapshot "/path/to/run/snapshot" \
  --contract "/path/to/run/migration-contract.json" \
  --style-definitions "/path/to/run/project-style-definitions.json" \
  --root-source "app/src/main/java/example/HomeScreen.kt" \
  --root-composable HomeScreen --page-id home --state-id loaded \
  --state-fixture "/path/to/home-loaded.json" \
  --viewport-width-dp 360 --viewport-height-dp 760 \
  --output-dir "/path/to/new-home-attempt" \
  --target "/path/to/harmony-project"
```

Replace `--snapshot ... --contract ...` with `--source /path/to/android-project`
to create a fresh snapshot and analysis under the new output directory. The
explicit style file must already exist in either mode; use
`generate_project_style_definitions.py` to prepare it once. Missing styles never
silently fall back to re-extraction. Add `--project-name`, `--bundle-name` and
`--sdk-version` when creating a new target; an existing target must satisfy the
normal project/asset ownership checks. New targets use module `entry`; existing
targets may select `--module`.

`--root-source` and `--root-composable` are required. There is no automatic entry
selection. `--state-fixture` is optional only when source values suffice; omitted
state does not invent loaded data. `--api-adapters /absolute/manifest.json` passes
explicit project API adapters to state projection. PSI still uses the documented
`JAVA_HOME` / `KOTLIN_PSI_CLASSPATH` environment, not a guessed project JDK.

The command emits `source-page.json`, `lanhu/version_json.json`, per-stage command,
stdout/stderr and elapsed-time records, plus `result.json` containing the emitted
ArkUI path and manifest. It prepares theme resources, selected manifest-backed
drawables and unambiguous local font files using the existing verified tools.
External images, Material icon source archives and company Harmony token libraries
are not downloaded or invented; prepare unsupported/external target dependencies
through their documented adapters/resource tools. Resource integrity errors stop
the run with their failed stage and logs.

This ends at **generated page code**, not build/install/visual acceptance and not
automatic production navigation registration. Import the exported root type from
the generated manifest into the desired host/route. Existing project files are
not replaced. `--force` only permits the existing owned-page regeneration checks;
it never overwrites the run directory or reinitializes an existing target.
Theme resources use the existing regeneration guard, which checks that previously
generated files are unchanged before writing; user-edited theme files cause a
stage error rather than being overwritten.

Exit 0 means output was produced. `status=partial_generation`, `verdict=fail` and
`generation_complete=false` retain unresolved facts and are not acceptance.
Fatal errors exit 1, set `failed_stage`, and preserve intermediate artifacts/logs.
The final stdout/result JSON also contains `diagnosis`: grouped generation problems,
affected components and source lines, property paths, failed expressions, available
parameter bindings, original reasons and suggested repairs. `diagnosis_report`
points to the Chinese `diagnosis.md` with the same details, so start there instead
of manually joining stage logs. It distinguishes command interruption from partial
code generation and preserves the original verdict. Preflight errors before a new
run directory exists return diagnosis on stdout only; previous runs are untouched.
Diagnosis uses current-run worklist/manifest evidence, not AI or screenshot analysis.
`root_cause_confirmed=false` means the failing step is identified but the complete
upstream cause is not proven. Unknown errors remain explicit, and evidence-read
errors appear in `collection_errors`; neither is treated as success. Group ordering
does not prove which issue caused a blank rendered page. This report does not replace
build or visual verification.
Use a new `--output-dir` for each attempt. Paths containing spaces are supported;
quote each argument normally, without embedding Python or setting `PYTHONPATH`.

## Live progress and slow-run diagnosis

Commands are unchanged. `migrate_compose_page.py`, `analyze_compose_project.py` and
`generate_source_page.py` now emit flushed `[progress]` JSON records on **stderr**.
Stdout remains one final machine-readable JSON result. A wrapper must forward or
tail stderr while the child is running, not wait for `communicate()` to finish.

The page command writes these files under its new `--output-dir`:

- `progress.jsonl`: parent stage start/end/failure, reuse decision, child PID and
  elapsed time (`elapsed_s`). Events are emitted on actual work, not on a timer.
- `result.json`: atomic current status, `current_stage`, stage `status=running`, PID
  and log paths, recorded before waiting for the child. Stage exit code/time follow
  when it finishes; `seconds` here is a checkpoint value, not a live ticking timer.
- `NN-analysis.stderr.log`: live analyzer detail, including PSI file, function
  dependencies, cross-file symbol matching and call closures. Other stages have
  their corresponding stdout/stderr files; files are not delayed until process exit.

For example, while an intake is running:

```sh
tail -f "/new-page-run/progress.jsonl" "/new-page-run/01-analysis.stderr.log"
```

The stage number depends on whether intake was reused; use the paths in `result.json`.
For a standalone analyzer or source-JSON command, persist stderr explicitly:

```sh
python3 "$SKILL_ROOT/scripts/analyze_compose_project.py" \
  --snapshot "$SNAPSHOT" --output "$CONTRACT" \
  2> "/work/analysis.progress.log"
```

Records contain timestamp, process ID, phase, elapsed time, current file/function
(`unit`) and real `completed`/`total` counts where available. Counts describe that
specific loop, not overall migration percent. There is no periodic heartbeat or
background logging thread. When work takes a long time, inspect the last unfinished
stage and its latest file/function checkpoint to identify where to profile next.
Silence alone does not prove a deadlock; this change adds diagnostics,
not a performance fix or automatic timeout. Filenames and symbol names are logged,
not complete source bodies. Apply company log-handling policy to these files.

For source-page generation, `function-dependencies` reports `indexed_functions`
(all declarations), `analyzed_functions` (dependencies processed so far), and
`pending_functions` (queued candidates, potentially including duplicates). It follows
the selected page's transitive dependencies, including defaults and property
initializers; it no longer constructs edges for every unrelated function first.
PSI parsing still covers the snapshot for cross-file resolution. Whole-project
`analyze_compose_project.py` still analyzes all functions, so reuse its snapshot and
contract when generating additional pages from unchanged sources. No new CLI option
or periodic heartbeat is introduced.

`analysis` / `symbol-resolution` is a different phase: it builds the contract's
cross-file name associations, before page JSON or ArkUI generation. The analyzer
now uses a name index instead of scanning every declaration for each query. It still
visits every snapshot file, including test files present in that snapshot; its local
symbol counter is not the overall migration percentage. `elapsed_s` measures the
operation since start, not the current symbol alone. Existing commands are unchanged.

### Reuse snapshot and contract across pages

`snapshot` is a directory of approved Android text sources, not a screenshot or a
page JSON. Keep it paired with the contract produced from that exact directory.
After the first `--source` run, subsequent pages can use:

```sh
--snapshot "/first-run/snapshot" \
--contract "/first-run/migration-contract.json"
```

Replace the `--source` argument with this pair; keep the project styles and target,
change `--root-source`, `--root-composable`, `--page-id` (and state as needed), and
choose a new `--output-dir`. No copying of the snapshot is needed. The progress log
then contains `reuse-analysis` and the stage list contains no `analysis` stage.
This reuses project analysis, not the prior page JSON. Do not move the snapshot
without rebuilding its paired contract, or reuse stale analysis after source changes.
Passing `--source` again intentionally performs fresh whole-project analysis;
selecting a smaller page does not reduce that intake scan.

## Inputs and outputs

```text
read-only Android project
  -> validated safe snapshot
  -> analyze_compose_project.py -> migration-contract.json
  -> generate_source_page.py -> source-page.json
  -> one explicit state fixture
  -> generate_lanhu_source_page.py -> version_json.json
  -> generate_arkui_page.py -> generated ArkUI + generation manifest

running Android/Harmony pages -> screenshots + runtime page.json -> comparison
```

| File | Producer / purpose | Implementation input? |
| --- | --- | --- |
| `migration-contract.json` | Source analyzer; source calls, definitions, resources and candidate business inventory | Only upstream of the page JSON |
| `source-page.json` | `generate_source_page.py` calls `build_source_page_spec`; expanded source component tree and expressions | Input to the Lanhu generator |
| `state-fixture.json` | Author supplies one source-reachable state's values | Input to state projection, not a second ArkUI input |
| `version_json.json` | Lanhu generator; hierarchy, layout/style facts, migration metadata and unresolved facts | **The only page-fact input to ArkUI** |
| `component-manifest.json`, `page-state-manifest.json` | Lanhu generator; component/geometry/state diagnostics | No sidecar required by ArkUI |
| runtime `page.json` and screenshot | Real-page capture scripts; measured validation evidence | Comparison only in this source-only recipe |

This `version_json.json` is source-generated, Lanhu-compatible data with migration extensions.
It is not downloaded from Lanhu and not reconstructed from a screenshot. An arbitrary raw Lanhu
export without the required source metadata is not accepted by the current ArkUI entry point.
The recipe currently selects an exact **Compose** root; the broader XML/View inventory does not
imply that the same automatic page generator supports all Views/XML screens.

## 1. Prepare the source inventory

Use the `SNAPSHOT`, `CONTRACT` and `TARGET` returned by an existing migration run when available.
For an isolated maintainer run, set absolute paths; `RUN_ROOT` and `TARGET` must be outside
`SOURCE` and outside one another. Replace the example project/root/package identities below.
Use a new page directory for each attempt rather than overwriting acceptance evidence.

```bash
export SKILL_ROOT="/path/to/repository/skills/migrate-android-compose-to-harmony"
export SOURCE="/path/to/android-project"
export RUN_ROOT="/path/to/new-migration-run"
export TARGET="/path/to/new-harmony-project"
export SNAPSHOT="$RUN_ROOT/snapshot"
export CONTRACT="$RUN_ROOT/migration-contract.json"
export ROOT_SOURCE="app/src/main/java/example/HomeScreen.kt"
export ROOT_COMPOSABLE="HomeScreen"
export PAGE_ID="home"
export STATE_ID="default"
export PAGE_RUN="$RUN_ROOT/pages/home-default-attempt-1"
export SOURCE_PAGE="$PAGE_RUN/source-page.json"
export STATE_FIXTURE="$PAGE_RUN/state-fixture.json"
export LANHU_PAGE_DIR="$PAGE_RUN/lanhu"
export WIDTH_DP="360"
export HEIGHT_DP="760"
export SLICE_SCALE="2"
export PROJECT_NAME="MigrationPreview"
export BUNDLE_NAME="com.example.migrationpreview"
export SDK_VERSION="6.1.1(24)"
```

Choose `SDK_VERSION` from the installed SDK and target environment, not from this example.
`WIDTH_DP`/`HEIGHT_DP` describe the intended logical **application layout viewport**, not an
unexamined physical screenshot size. Use the source window's edge-to-edge/inset policy. The
numbers above are illustrative; do not apply them to every phone. `sliceScale` is the JSON
coordinate scale (`frame / sliceScale` gives dp), not a target-screen resize instruction.

For a new source only, run the intake below. If `SOURCE` is already a validated snapshot,
set `SNAPSHOT` to it and skip preparation. If the run already owns a current `CONTRACT`, reuse
it; do not regenerate the orchestrator's immutable intake files in place.

```bash
python3 "$SKILL_ROOT/scripts/prepare_safe_snapshot.py" \
  --source "$SOURCE" --snapshot "$SNAPSHOT"
python3 "$SKILL_ROOT/scripts/validate_ai_safe_tree.py" \
  --require-safe-manifest "$SNAPSHOT"
python3 "$SKILL_ROOT/scripts/analyze_compose_project.py" \
  --snapshot "$SNAPSHOT" --output "$CONTRACT"
```

Stop on a nonzero command exit. Inspect only approved snapshot text. Do not view source images,
run OCR, or copy blocked files into the snapshot. Confirm the exact `ROOT_SOURCE` and
`ROOT_COMPOSABLE` pair occurs in `ui.custom_composable_call_graph.transitive_closures`.

## 2. Generate source-page.json without a device

### Reuse project-wide styles

After the initial contract analysis, extract one style file per project:

```bash
export PROJECT_STYLES="$RUN_ROOT/project-style-definitions.json"
python3 "$SKILL_ROOT/scripts/generate_project_style_definitions.py" \
  --contract "$CONTRACT" --output "$PROJECT_STYLES"
```

An existing file is reused without reading the contract or re-extracting styles. There is no
hash, timestamp, or automatic invalidation. After intentionally changing the project theme,
reanalyze the snapshot, then run the same command with `--refresh`. Do not reuse another
project's style file. Malformed files fail explicitly rather than silently rebuilding.

The file holds resolved theme colors/text styles and their source providers, including fonts,
shapes and extended color sets. The currently supported global selection is the light theme;
this cache does not add dark/dynamic-theme selection or resolve ambiguous providers. Missing
facts remain unresolved. Existing component-specific defaults use the cached theme; explicit
local values, transparent paint and selected-state overrides still take precedence. A plain
Box with no background stays unpainted, not filled with a global surface color.

This reuses global style extraction, not the entire page analysis: page trees and fixed-state
expressions still need processing. The source page embeds the definitions; the final
`version_json.json` carries them under `meta.migration.styleDefinitions` alongside the resolved
node styles. ArkUI still reads that single JSON, never this cache file or Android source.

### Generate a page

Use the standalone CLI. It calls the same library function used by real-page capture
and the source-only regression harness; it does not invoke UIAutomator or read screenshots.
The snapshot and contract must belong to the same source inventory. The explicit
style file is loaded into the document, not discovered from the working directory.

```bash
python3 "$SKILL_ROOT/scripts/generate_source_page.py" \
  --snapshot "$SNAPSHOT" --contract "$CONTRACT" \
  --style-definitions "$PROJECT_STYLES" \
  --root-source "$ROOT_SOURCE" --root-composable "$ROOT_COMPOSABLE" \
  --page-id "$PAGE_ID" --state-id "$STATE_ID" \
  --output "$SOURCE_PAGE"
```

The source tree preserves project-component expansion, parents/children, sibling order,
argument bindings, modifiers, static styles and unresolved expressions. Its calculated frames
are source reference geometry, not a claim of measured Android bounds. No device means no
runtime proof of font/platform-default behavior; capture the actual page later for validation.

Alternative: `generate_real_android_page_json.py` also produces `source-page.json` when capturing
a running page. See [the capture commands](page-snapshot.md#capture-real-pages-and-bind-runtime-nodes-to-source).
Pass `--style-definitions "$PROJECT_STYLES"` to reuse the same project styles (created from the
contract if absent). Without the option, the existing per-page extraction remains available.
Use that file at step 4; do not substitute its runtime `page.json`. The alternative requires a
live device or paired offline screenshot/UIAutomator XML. It is not the source-only path.

## 3. Specify exactly one page state

Create `STATE_FIXTURE` with this format, replacing the sample fields with values actually read
by the selected source. This example is for a root using `title` and `showContinue`:

```json
{
  "schema": "android-to-harmony.page-state-fixture.v1",
  "page": {"id": "home", "state": "default"},
  "values": {"title": "Home", "showContinue": true},
  "symbols": {}
}
```

`page` must equal `source-page.json.page` exactly. `values` supplies typed strings, numbers,
booleans, nulls, records or lists for that one state. `symbols` supplies explicitly resolved
symbol values when needed; it is merged after `values`, so avoid duplicate keys. This is not
Kotlin execution and not a declaration of every business state. Follow the actual source
expressions/bindings; do not invent replacement text, styles or layout facts to clear a gate.
For another state, create another page run and matching fixture. Unresolvable branch selection
produces a partial candidate: both source subtrees remain in JSON with
`source.state_resolution.status=unresolved`. They are not selected for rendering until resolved.
For fully static pages, omit `--state-fixture`; unresolved state is never guessed automatically.

For a captured `viewModel.rows.collectAsState()` value, prefer binding the Flow receiver:
`"values": {"viewModel": {"rows": [{"name": "Shopping"}]}}`. The bounded Compose adapter
creates the State container; `by` or `.value` reads its value. If binding the entire call in
`symbols` instead, supply its actual return shape, e.g.
`"viewModel.rows.collectAsState()": {"value": [{"name": "Shopping"}]}`; a bare list is not State.
`remember` preserves its calculation's type, including `mutableStateOf` containers.

Capture business data from the selected running state rather than executing repositories,
network calls or arbitrary business code in the layout evaluator. UIAutomator may supply mapped
visible text/selection; hidden internal state needs an explicit fixture or a minimal test probe.
Record the capture origin. A partial visible list is not the complete dataset, and absence from
the runtime tree never proves a source branch is hidden. The merged scene still produces one
page JSON for ArkUI; runtime data must not overwrite source layout or styles.

### Layout expression parser setup

Source layout projection uses Kotlin compiler PSI for modifier expressions, aliases, conditional
arguments and layout alignment/arrangement. Public command arguments are unchanged. ArkUI still
reads only the emitted `version_json.json`; it does not start PSI or reopen Android sources.
Selected text/style values and modifiers use the same AST evaluator for if/when, operators,
nullable members and Elvis expressions. Framework value adapters remain bounded; an unresolved
expression cannot invoke a second string-based branch parser. This does not provide complete
compiler symbol/type resolution. Run `test_fixed_state_value_parity` to check both entry paths.
TextStyle aliases and nested `copy` properties are selected individually; explicit Text
arguments override those properties. Unknown style values remain unresolved without removing
the control. Pixel comparison and runtime geometry remain separate acceptance checks.

Use JDK 17 or newer (`JAVA_HOME` with `bin/java` and `bin/javac`). The parser reads these pinned
JARs from `GRADLE_USER_HOME/caches/modules-2/files-2.1` (default `~/.gradle`):

| Maven artifact | Version |
| --- | --- |
| org.jetbrains.kotlin:kotlin-compiler-embeddable | 1.9.22 |
| org.jetbrains.kotlin:kotlin-stdlib | 1.9.22 |
| org.jetbrains.kotlin:kotlin-reflect | 1.6.10 |
| org.jetbrains.intellij.deps:trove4j | 1.0.20200330 |
| org.jetbrains:annotations | 13.0 |
| com.google.code.gson:gson | 2.10.1 |

For offline/internal-network machines, provision the same dependencies through your approved
artifact mirror and set `KOTLIN_PSI_CLASSPATH` to their platform-separated absolute JAR paths.
Nothing is downloaded automatically. Missing dependencies fail with a setup error, rather than
silently returning to string-based branch scanning. The Java bridge compiles with `--release 17`
into the external user cache and a process/cache is reused within each Python invocation.
No class files, Android build outputs or source images belong in the skill repository.

Regenerate `source-page.json` with the current analyzer before projecting scenes. Its raw
`syntax_expression` fields preserve Kotlin newlines and lambda boundaries. Layout branches are
selected before extracting dimensions/padding; an unknown condition becomes unresolved and does
not apply either branch. Literal framework adapters remain bounded, not arbitrary Kotlin execution.

### UI-only previews when business values are unavailable

For UI prototyping rather than business parity, use the explicit preview projector below.
Regenerate the source inventory/page with the current analyzer first: it preserves complete
`if / else if / else` and supported `when` condition chains. Supply a small input file for the
states to demonstrate; do not switch internal branches independently or enumerate their Cartesian
product. For example, for source `if (cardUi != null) ... else if (isCardLoading) ...`:

```json
{
  "schema": "android-to-harmony.ui-state-inputs.v1",
  "page_id": "saving-details",
  "common_values": {},
  "scenes": [
    {"id": "loaded", "values": {"cardUi": {"isPrimary": false}, "isCardLoading": false}},
    {"id": "loading", "values": {"cardUi": null, "isCardLoading": true}},
    {"id": "no-card", "values": {"cardUi": null, "isCardLoading": false}}
  ]
}
```

Supply additional source-required style/state values in the real project's input records.
`common_values` and optional `common_symbols` are shallow-merged with each scene's `values` and
`symbols`. Scene IDs must be unique; `page_id` must match the source page. This file belongs to
the upstream state projector, not to the ArkUI generator's inputs.

```bash
python3 "$SKILL_ROOT/scripts/generate_ui_state_previews.py" \
  --source-page "$SOURCE_PAGE" --states "$STATE_INPUTS" \
  --output-dir "$PAGE_RUN/ui-previews" \
  --viewport-width-dp "$WIDTH_DP" --viewport-height-dp "$HEIGHT_DP" \
  --slice-scale "$SLICE_SCALE"
```

The output directory must be new. This emits `state-catalog.json`, `preview-report.json`, a
human-readable `preview-report.md`, and a
directory for each scene containing its projected fixture and a **single** `version_json.json`.
Pass one scene's version file to the unchanged `generate_arkui_page.py --page-json` entry. The
ArkUI generator never reads Android source, UIAutomator, or a second page JSON in this path.

Rules and limits:

- The catalog inventories source condition chains, including nested and separately invoked
  business components. Scenes evaluate those conditions with explicit inputs and retain fixed
  call parameters: `actionLabel=null` cannot become a visible action by preview selection.
  If a non-null card and loading are both supplied, the source's first branch wins. Unknown
  structural conditions remain deferred facts in a partial scene, not a generation exception.
  No state inputs means inventory only, not automatically invented scenes or business reachability.
- Whole-page branches, local loading/error branches and dialog branches remain source-owned.
  Independent source roots (for example Scaffold plus Dialog) require an explicit `root_id`
  per scene and get **separate previews** with
  `scope=isolated-source-root`; they are not forced into an invented Stack. A dialog-only preview
  is not a claim that the background page/window/dimming composition has been reproduced.
- Static text and statically resolved list data are preserved. Unresolved display text uses
  explicitly marked `Sample text`; unknown collection data retains its original item template
  as deferred source facts, without inventing a number of items.
  To show an empty list, supply the source collection as `[]` in a separate scene. Fixed source
  lists remain fixed; `choices` and `collection_counts` branch/count overrides are rejected.
- Each emitted sample is recorded in `stateProjection.ui_preview.display_data` and text facts
  use `origin=ui_preview_sample`. To use representative values instead, edit a scene fixture's
  `ui_preview.display_values` using exact source component IDs, then regenerate that one scene.
  Example: `{"source-...": {"text": "123.45", "origin": "ui_preview_sample"}}`.
- Do not invent colors, dimensions, shapes, asset references or unresolved platform defaults.
  Those remain normal unresolved facts and continue to fail their existing gates. Unimplemented
  custom drawing/third-party widgets remain partial output, not fake replacements.
- `generated_count` means files were emitted. Inspect each scene's `verdict`, unresolved facts,
  subsequent ArkUI manifest, build and same-state screenshot comparison separately. The report
  always states `business_verified=false` and `visual_acceptance=not_verified`.
- Preview fixtures are implementation/test inputs, not production business logic. A preview host
  can switch generated scenes; do not add preview-state controls to the production screen.

#### Optional UIAutomator display text

UIAutomator is optional and supplies **text only**, never source layout coordinates. Capture the
intended Android page/state with the existing real-page capture process. Create a binding file:

```json
{
  "page": {"id": "home", "state": "default"},
  "text_bindings": {"source-exact-component-id": "com.example:id/balance"}
}
```

`page` must match `SOURCE_PAGE.page`. Add both `--uiautomator-xml /absolute/window.xml` and
`--text-bindings /absolute/text-bindings.json` to the preview command. Each resource ID must occur
exactly once; missing/duplicate IDs and password nodes are rejected. Do not guess correspondence
from repeated labels or screen positions. Compose nodes without a stable resource ID/test tag
continue to use explicit sample data. Runtime input path, resource ID and XML SHA-256 are recorded.
The binding author must verify the actual page/state; the XML alone does not attest route identity.
Imported strings may be reused as specimen content across scenes, not as runtime-state evidence.
Use sanitized accounts: imported text appears in the generated JSON and UI.

Do not merge this display-data policy into the strict fixture path above. Strict migration
continues to require resolved branch values and real behavioral acceptance evidence.

## 4. Generate version_json.json

```bash
python3 "$SKILL_ROOT/scripts/generate_lanhu_source_page.py" \
  --source-page "$SOURCE_PAGE" \
  --state-fixture "$STATE_FIXTURE" \
  --viewport-width-dp "$WIDTH_DP" \
  --viewport-height-dp "$HEIGHT_DP" \
  --slice-scale "$SLICE_SCALE" \
  --output-dir "$LANHU_PAGE_DIR" > "$PAGE_RUN/lanhu-result.json"
```

Outputs are `version_json.json`, `component-manifest.json`, `page-state-manifest.json`,
`unresolved-worklist.json` and the
captured stdout result. Inspect `generation_complete`, `verdict`, `unresolved`,
`required_fact_gate` and `phase_consumption_gate`. The version document embeds equivalent
diagnostics in `meta.sourceGeneration` and per-node `migration.requiredFacts`.

### Resolve only unresolved facts

The CLI exits 0 when it emits files, including `status=partial_generation`. An unresolved theme,
style expression, state predicate or collection value must not discard the rest of the page.
Malformed documents, page/state identity mismatch, broken hierarchy, invalid viewport and
ambiguous page roots remain errors. `generation_complete=false` / `verdict=fail` means the
candidate is incomplete, not that its JSON file is missing. Target generation retains that
incompleteness and must not claim a visual pass.

`unresolved-worklist.json` binds the exact version file SHA and groups tasks by expression,
property and related source context. Each task provides affected component IDs, source locations,
reasons and transitively related parameter/local bindings. It is a **diagnostic report**, not an
AI solver queue or review gate. The CLI does not invoke a model or require a provider dependency.

`has_unresolved=true` reports remaining facts; it does not dispatch a repair stage. There is no
AI value-completion step in the migration workflow. Supported parsers, explicit fixed-state inputs
and verified runtime facts supply values. Missing evidence remains unresolved while known output
continues. Reusable parser/adapter defects are separate maintenance work, not per-page AI overrides.
Do not patch the final JSON to erase diagnostics. Build, structural and screenshot checks remain
script-driven; none is replaced by a model declaring the page correct.

The final page JSON already contains the hierarchy and implementation facts. Do not insert
an `implementation-page.json` reduction, a second runtime JSON or a source-reader fallback.
Native flow/alignment and declared sizes drive target layout; reference frames must not become
fallback global coordinates. Supported outer surface padding becomes layout wrappers and stays
separate from inner `contentPadding`; do not combine both into one padding value.

## 5. Prepare the target and resources

Skip initialization when the target already belongs to this migration. For a new target:

```bash
python3 "$SKILL_ROOT/scripts/init_harmony_project.py" \
  --output "$TARGET" --project-name "$PROJECT_NAME" \
  --bundle-name "$BUNDLE_NAME" --sdk-version "$SDK_VERSION" --contract "$CONTRACT"
python3 "$SKILL_ROOT/scripts/generate_harmony_theme_resources.py" \
  --contract "$CONTRACT" --target "$TARGET" --module entry
```

Prepare the page's referenced images and fonts **before** ArkUI generation. Select exact
`version_json.json.assets` resource names from the safe manifest. For example, only when the
page really references `ic_back`:

```bash
python3 "$SKILL_ROOT/scripts/materialize_static_drawables.py" \
  --manifest "$SNAPSHOT/.android-to-harmony-safe.json" \
  --target "$TARGET" --module entry --name ic_back
```

Inspect that command's skipped/unresolved results. Not every drawable XML is a VectorDrawable.
Use the [approved copy/vector/font procedures](../SKILL.md#implement-page-fact-driven-visual-parity)
for other resources. Referenced fonts must be copied to their declared target resource paths and
match their SHA. Target-owned resources are dependencies, not a second page-fact input.

## 6. Generate ArkUI from the single JSON

```bash
python3 "$SKILL_ROOT/scripts/generate_arkui_page.py" \
  --target "$TARGET" --module entry \
  --page-json "$LANHU_PAGE_DIR/version_json.json" > "$PAGE_RUN/arkui-result.json"
```

The result names `output` (the generated `.ets` file under the target) and `manifest` (under
`.migration/arkui-pages/`). The manifest binds the page SHA, resolved root and emitted files;
it reports `input_mode=page-json-only`, `source_fallback_count=0`, `generation_complete`,
`verdict`, `unresolved` and source/target phase-consumption gates.

Retired generator parameters `--contract`, `--root-source`, `--root-composable`,
`--android-page-json`, `--android-runtime-page-json` and `--lanhu-component-manifest` are not
accepted by this CLI. They must not be restored by changing the command to a legacy helper.
Upstream analysis and runtime capture still have their own contract/root arguments.
For regeneration, use a fresh target or `--force` only when the generator's existing outputs
are unchanged. Do not hand-edit generated layouts to improve the first-pass score.

## 7. Build, capture and compare

Mount the emitted root component in the target's chosen route, configure the actual SDK/signing,
then compile/install with the existing project build workflow. The generator does not launch the
page, implement business callbacks, or prove a successful HAP build.

Open the same source-reachable page/state on both platforms, then use
[the real Android/Harmony capture commands](page-snapshot.md#capture-real-pages-and-bind-runtime-nodes-to-source)
to obtain fresh capture directories. Set `ANDROID_CAPTURE` and `HARMONY_CAPTURE` to those directories:

```bash
python3 "$SKILL_ROOT/scripts/compare_local_screenshots.py" \
  --left "$ANDROID_CAPTURE/screenshot.png" \
  --right "$HARMONY_CAPTURE/screenshot.png" \
  --left-components "$ANDROID_CAPTURE/page.json" \
  --right-components "$HARMONY_CAPTURE/page.json" \
  --min-ssim 0.95 --output-dir "$PAGE_RUN/comparison"
```

Read `comparison-summary.md` for the human-readable component/control diagnostics and
`comparison.json` for exact geometry/style/SSIM evidence. Runtime page JSON, not implementation
reference frames, supplies measured comparison bounds. Physical density may differ, but logical
content viewport, page/state, orientation, font scale, theme and scroll state must be compatible.
Automatic crops use recorded application content bounds; inspect them instead of subtracting a
fixed status-bar height. `--target-size` does not make incompatible page states/viewports equivalent.
No image-model recognition is required; pixel analysis is local Pillow processing.

## Result semantics and troubleshooting

| Result | Meaning / next action |
| --- | --- |
| Generator exit `0`, `generation_complete=true`, `verdict=pass` | Supported facts were emitted; build and runtime visual verification still required |
| Generator exit `0`, `generation_complete=false`, `verdict=fail` | Partial output exists; inspect component/path/expression and phase failures; not accepted UI |
| Nonzero generator exit | Malformed/ambiguous input, unsafe asset, ownership or other fatal error; do not reuse stale output |
| Comparator exit `0`, `verdict=fail` | Comparison ran successfully but UI acceptance failed; inspect the report |
| Missing source root | Recheck the exact source-relative path/composable and regenerate a current contract |
| Missing image/font | Reconcile the safe manifest, target resource path and SHA; do not use a placeholder |
| Geometry/style unresolved | Repair the parser/JSON/consumer responsible, then regenerate; do not fill from screenshot coordinates |
| Source/target state mismatch | Correct the fixture/capture pair, not the similarity threshold |

The script's final verdict is not approval of full business migration. Business actions and
runtime scenarios continue through the separate [behavior contract](behavior-contract-v2.md).

### Blank pages and missing components

Use this sequence when a generated page is nearly blank, missing sections, or has
incorrect sizes. Diagnose the first stage that loses the selected state's UI; do
not start by adding accessibility tags or manually editing generated layouts.

1. **Confirm the actual run.** Record the installed skill version/revision, exact
   commands, page entry and selected state, source-page input, the actual
   `--page-json` path, generation manifest, emitted `.ets`, build/install results
   and captured page. Confirm outputs belong to this run, not a stale build.
   The generator input must be the source-generated `version_json.json`, not a
   runtime `page.json` or UIAutomator tree renamed to look like one.
2. **Check source collection and state selection.** Follow the page entry's UI
   calls, business components, slots, lists and active branches into
   `source-page.json`. Identify expected visible sections for that state. Raw
   source-call totals include definitions/inactive content and cannot be treated
   as an expected runtime control count. Unknown conditions/data must remain
   explicit diagnostics rather than silently selecting an empty state.
3. **Check the selected JSON tree.** For each missing section, follow source
   identity into the JSON layers. Check children, component kind, visibility,
   sizing modes/constraints, ordered modifiers, style/default references and
   unresolved facts. If the section was collected but vanished here, fix state
   projection/export. Do not substitute runtime coordinates for source layout.
4. **Check generated code.** If the JSON retains the section, trace its identity
   through the generation manifest and corresponding builder/call. Check skipped
   controls, unsupported APIs, slot expansion and field consumption. Repair the
   responsible shared emitter/adapter; do not patch the generated page by hand.
5. **Check native layout.** If code contains the section, build and install that
   exact output and inspect runtime geometry and logs. Check zero sizes, parent
   constraints, visibility, clipping, scroll position, resource loading and
   exceptions. Use scripted pixel/geometry comparisons for the same page/state
   and compatible viewport; do not diagnose a layout from a global score alone.
6. **Regenerate and verify.** Add a focused regression at the first failing stage,
   regenerate from source with the shared fix, then build/run and compare the
   affected section. Record any remaining unsupported content. Successful command
   execution or partial output is not page acceptance.

Report each finding as: **section/component -> last correct artifact -> first
incorrect artifact -> evidence -> responsible module -> repair -> verification**.
Request only the necessary sanitized artifacts for private projects; do not ask
users to upload private repository contents indiscriminately.

#### Runtime mapping is a separate diagnosis

`semantic_mapping_ratio=0` and `source_binding` unresolved records show that
runtime nodes were not bound to source identities. They do **not**, by themselves,
prove why target rendering is blank. Runtime evidence supplements selected values
and verification; it is not the primary source hierarchy in this generation flow.
Already-known source controls and layouts must not disappear solely because a
runtime node lacks a resource ID or testTag.

Check the pipeline above first. If a required runtime value or verification
boundary genuinely cannot be matched, use a verified runtime-source map or minimal
test instrumentation for that ambiguity. Do not guess matches from text/order or
require blanket tagging as the first response to every blank page.

#### JSON size and null fields

Source-page writers now deduplicate repeated analysis values in the same file.
Large repeated scopes, imports, function bodies and style structures are stored
once in `source_page_storage.shared`; occurrences use `{"$sourceRef":"v123"}`.
This is lossless storage, not a new layout model: nulls, node order, types,
source identities, diagnostics and UI alternatives are retained. The storage
descriptor is `android-to-harmony.source-page-storage.v1`.

Existing commands automatically expand references before analysis/projection.
Install the complete updated skill: older readers do not understand these
references. Inline legacy source JSON remains accepted. For a custom Python
consumer, normalize once with:

```python
from ui_migration.contracts.source_storage import unpack_source_page
page = unpack_source_page(json.loads(path.read_text(encoding="utf-8")))
```

No separate file, hash cache or Android source lookup is needed to expand the
table. Dangling/cyclic references fail explicitly. `version_json.json` remains
the same Lanhu layout format and the ArkUI generator still has one page input.
This reduces repeated data, not unique source inventories; it is not a claim
that every two-million-line company document shrinks to a particular size.

Removing indentation outside strings preserves JSON values and does not change
rendering. File digests/byte counts do change, so regenerate any bound manifests;
do not hand-edit an already frozen input.

Do not recursively delete every `null`: the current schema requires some keys
even when their value is null (for example `migration.customDraw`), and unresolved
text has an explicit null-plus-diagnostic contract. Not-applicable, explicitly
absent, inherited/defaulted and unresolved values are different cases. A compact
schema would need coordinated writer/reader normalization and equivalence tests.
Null deletion is not a fix for missing UI. Keep unresolved evidence, selected
layout/style/resource facts and source identities; diagnostic extraction is a
separate format change, not a troubleshooting shortcut.

#### Page roots and non-visual Composables

`@Composable` is not itself proof of visual output. Proven value/Modifier
declarations and expression-bodied callback/reference factories do not become
UI roots. They remain in the source value inventory. An expression-bodied UI
call such as `fun Header() = Text("Title")` is still content. The analyzer does
not classify by `get`/`on` name prefixes or delete all assigned calls.

Same-file overloads are not concatenated into one page. A unique declaration
is selected by source identity; when one overload delegates to another, the
unique outer caller is the entry and the callee remains its child. The chosen
identity is recorded as `root_declaration_id`. Independent ambiguous overloads
are reported with signatures/locations and need an unambiguous entry wrapper.

For multiple real UI roots, the selected function alone does not imply Column
or Box. PSI can verify a **direct** selected-page invocation in the content of
an official `androidx.navigation.compose.composable` inside `NavHost`. That
external destination host is recorded in `page_host` and projected as an
overlay Box, preserving sibling order, NavHost modifier and content alignment.
Insets still need supported runtime/fixture facts; no fixed status-bar height
is invented. Navigation transitions and back-stack behavior are not migrated
by this static host mapping.

This initial recognizer accepts explicit/aliased/wildcard official imports and
resolved page declaration identity. It does not infer a host through an
intervening Row, arbitrary routing wrapper, deferred callback or ambiguous
multiple route hosts. Existing Row/Column/Box business-component composition
keeps its real parent. Unproven multiple roots remain an explicit diagnostic
with component names, source locations and IDs, not silent node deletion or
an arbitrary wrapper. Correct upstream modeling and regenerate; do not patch
the output ArkTS or erase roots to pass the gate.
