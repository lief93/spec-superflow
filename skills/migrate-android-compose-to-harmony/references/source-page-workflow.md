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
`--sdk-version` when creating a new target. Previously initialized targets retain
normal project/asset ownership checks. For an ordinary existing Harmony project,
use the explicit existing-project mode below. New targets use module `entry`;
existing targets may select `--module`.

### Custom component and page directories

Keep intermediate JSON/logs outside the target project with `--output-dir`.
Independently select an existing component scan directory and a generated-page directory:

```bash
# Add these options to the page command above:
--target "/path/to/existing-harmony-project" \
--existing-target \
--target-metadata-dir "/path/to/migration-records" \
--module entry \
--component-dir "entry/src/main/ets/components" \
--page-output-dir "entry/src/main/ets/pages/migrated" \
--output-dir "/path/to/new-migration-attempt"
```

Both directory options accept an absolute path or a path relative to `--target`
(not the shell working directory). Both must be inside the selected module's
`src/main/ets` tree; direct cross-module source imports are not introduced.
The component directory must exist. The page directory is created automatically;
new pages and generated components use Android source basenames with an `.ets`
suffix directly in that directory, without package or `_migration` subdirectories.
Owned legacy entry basenames are preserved, but nested entries are flattened on
regeneration; update host imports that referenced their old locations. Component scanning is recursive and
excludes the selected output subtree, legacy `generated` directories, dependency/build
directories and symlinks. Do not use the output directory as the scan root.
Without these options the original scan root and `ets/generated` output are unchanged.
Resources still go to the selected module's `src/main/resources`; existing components
are imported, not moved or copied. Custom directories alone do not disable project
ownership checks; add `--existing-target` for an ordinary project without a migration
marker. Neither mode rewrites routes or project configuration.

### Existing Harmony project output

`--existing-target --target-metadata-dir /path/to/migration-records` enables writes
into an existing project without reading or creating `TARGET/.migration/state.json`.
The selected project must already contain `build-profile.json5`, `oh-package.json5`,
and the selected module's `src/main/module.json5`, `ets`, and `resources` directories.
These are structural preflight checks, not SDK build verification. Directory/module
and symlink protections still apply. The project is never initialized or adopted by
forging a migration project marker.

Keep the metadata directory stable across runs and separate from the Android source,
snapshot, Harmony target, and each fresh `--output-dir`. It stores theme manifests,
asset/font/vector ledgers and page-generation manifests, partitioned by the canonical
target path and module. Preserve it when upgrading the tool. `result.json` reports the
resolved record directory and page manifest path. A fresh per-run output directory is
still required; do not use a new metadata directory for every attempt.

Theme resources use dedicated `migration_color.json` / `migration_float.json` files
under the selected module's resource qualifiers. Existing resource JSON files remain
byte-for-byte unchanged. Conflicting resource names, unowned destination files and
modified generated outputs are rejected, including with `--force`. `--force` only
regenerates outputs still matching their recorded hashes. If records are lost, the
tool refuses to overwrite existing generated files rather than guessing ownership.

For standalone reruns, pass the same two flags to `generate_harmony_theme_resources.py`,
`materialize_static_drawables.py`, `copy_local_asset.py`, `convert_android_vector.py`,
and `generate_arkui_page.py` as applicable. The page runner forwards these options to
all target-writing stages, including font copying. Source-page and Lanhu generation
do not require this project marker and retain their existing input flags.

This mode only generates page code and required resources. Host integration,
configuration, signing, SDK compilation, and runtime acceptance remain separate.

Standalone `generate_lanhu_source_page.py` accepts `--component-dir` and
`--page-output-dir` with `--harmony-target` / `--harmony-module`.
Standalone `generate_arkui_page.py` accepts `--page-output-dir` with `--target` / `--module`.
Supply the same output directory during discovery so it is excluded from scanning.
JSON/adapter relative module references keep their established `ets/generated` base;
the ArkUI emitter relocates relative imports for the actual page directory. Package
imports are unchanged, so changing the destination does not require rewriting adapters.
`--force` still only replaces unchanged owned output at the same path; relocating an
already generated page is not an implicit move/delete operation.

The page command automatically scans existing named components in the target module
and reuses a unique same-name declaration using target defaults only. Inspect
`lanhu/component-discovery.json` for selection decisions; explicit component adapters
take priority and can map source values. Automatic reuse omits all source arguments;
these omissions and required placeholder values remain diagnostic,
without preventing the reused call from being generated. Use `--no-auto-component-reuse` to disable this. See
[automatic component matching](business-component-reuse.md#automatic-matching-default-for-the-page-command)
for supported types, SDK parser configuration and limits. Standalone Lanhu generation
opts in with `--harmony-target` and optional `--harmony-module`; no target source is
read by the final ArkUI backend.

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

`diagnosis.md` is the single human-facing outstanding-issue list for the run.
Its headline uses `result.json.diagnosis.unresolved_count`, not the sum of stage
`unresolved_count` values. The count is diagnostic groups, not proven independent
root causes. `counts` separates `pending` (current UI), `defaulted` (visual defaults
still need review), `deferred_dynamic` (unresolved dynamic/business conditions, including preview selections),
and `other_state` (component-state variants). All four remain outstanding;
deferred conditions are not silently marked implemented. Collected UI branches may
use a marked default preview; unsupported templates can still leave content missing.
This report does not implement conditions or force source inputs true.
`resolved_reference` is excluded from the outstanding total only when a valid
reference and actual target consumption match the exact component/property and
no target error remains there. Unknown aliases or merely calling an adapter are
not resolution evidence. Other-state occurrences retain `component_ui_state`.
Without a final ArkUI manifest, the report explicitly labels its evidence incomplete.
The original stage reports, `generation_complete` and `verdict` remain unchanged;
this consolidated maintenance list is not a new generation/acceptance gate.

Use a new `--output-dir` for each attempt. Paths containing spaces are supported;
quote each argument normally, without embedding Python or setting `PYTHONPATH`.

## Live progress and slow-run diagnosis

Commands are unchanged. `migrate_compose_page.py`, `analyze_compose_project.py`,
`generate_source_page.py`, `generate_lanhu_source_page.py` and `generate_arkui_page.py`
emit flushed `[progress]` JSON records on **stderr**.
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
- `NN-lanhu.stderr.log`: internal state projection, component-state variants, layout
  calculation, layer export, validation and JSON packing/writing checkpoints.
- `NN-arkui.stderr.log`: JSON decoding, visual defaults, document validation,
  component-state decoding, ArkTS rendering and output writing checkpoints.
  Internal records are forwarded live to the terminal and kept in these child logs;
  `progress.jsonl` contains the parent-stage records, not all child records.

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
Internal steps emit `phase-start`, `phase-finished` (with `seconds`) or `phase-failed`.
Recursive projection/export/rendering reports the current component `unit` as work
advances; those checkpoints are throttled and do not emit while execution is idle.

Shared string, number, color and enum validation errors include a bounded `actual`
value preview and its Python type, plus length for strings/collections. Invisible
characters are escaped and control-character positions are reported. For example:

```text
...migration.unresolved[0].reason must be non-empty diagnostic text; actual='bad\x00reason' (type=str, length=10, control_positions=[3]; preview may be truncated)
```

The error appears in the child command result and failed-phase stderr record; the
full page command also forwards the command error into `result.json`. Long values
are truncated only in error previews, not in the input JSON. Diagnostic `reason`
strings accept newlines, tabs and more than 500 characters without truncation;
document-size limits still apply. Empty/non-string reasons and unsupported control
characters such as NUL remain errors. Identifier and other field limits are unchanged.
`provenance[].source` also retains multiline source evidence, up to 10,000
characters; blank values and controls other than CR/LF/tab remain invalid. It is
not an identifier and is not restricted to a 500-character single-line label.
Silence alone does not prove a deadlock; this change adds diagnostics,
not a performance fix or automatic timeout. Filenames and symbol names are logged,
not complete source bodies. Apply company log-handling policy to these files.

### Composed modifiers

Fixed-state projection expands `Modifier.composed { ... }` and bare `composed`
inside source Modifier extensions. The factory's `this` retains the incoming chain;
returning a new `Modifier` replaces it. Nested factories, named `factory` lambdas
and known `if`/`when` branches use the existing PSI evaluator. Inspector metadata
is not executed. For RTL conditions, provide `LocalLayoutDirection.current` as
`"rtl"` or `"ltr"` in fixture values; `LayoutDirection.Rtl/Ltr` resolve accordingly.

Unknown conditions, animation state and nonlocal side effects are not executed or
guessed. Their unresolved diagnostics remain visible and the candidate page may be
partial. Supporting the factory wrapper does not imply arbitrary Compose runtime
support. Full unsupported modifier text stays in `expression`, not duplicated in
the short `unsupported modifier expression` reason.

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
  structural conditions use a marked default UI branch in a partial scene when branch
  metadata is available; they are not reported as resolved business conditions.
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

Generated source modules preserve source method names where representable. A
single-use fixed-state rendering helper is merged into its source facade only
when its arguments and scope can be safely substituted; state dispatch and
effectful arguments retain their helpers. An unsupported declaration can still
require generated props rather than the original signature. Fixed dp lengths
emit logical numeric ArkUI lengths, without a pixel-rounding helper or a context
parameter just for constants. Actual measurement, font-metric and state dependencies
can still require a typed context. These rules do not imply business-state parity.

### Required regression after tooling changes

After each migration-tool change, rerun at least one previously adapted page through
fresh source/page generation, native build, installation, launch, capture and
comparison. Unit tests or an SDK build alone do not satisfy this regression gate.
Reuse its explicit state fixture and matching viewport, locale, theme and font scale;
retain the prior evidence and use a new run directory. Record revision, commands,
stage timings, generated/build hashes and comparison results. Never patch generated
ETS to make the check pass. Report execution success separately from visual
acceptance, including pre-existing failures and newly introduced regressions. A
missing device or incomplete comparison contract must be reported as unverified.

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

### Correlate measured differences with generation diagnostics

After the comparator finishes, refresh the same run's `diagnosis.md`:

```bash
python3 "$SKILL_ROOT/scripts/diagnose_page_fidelity.py" \
  --run-dir "$PAGE_RUN" \
  --comparison-report "$PAGE_RUN/comparison/comparison.json"
```

This command reads `result.json`, `source-page.json`, `lanhu/version_json.json`,
the worklist, the recorded ArkUI manifest and the comparator report. It does not
reanalyze source, execute adapters, compile, capture screens or edit ETS. It checks
available worklist/manifest hashes against the version JSON before associating
evidence. Copying an unrelated run's report is not a shortcut; missing/malformed
artifacts remain explicit evidence gaps.

The report places measured findings before the generation issue details and links
them by issue number. A unique source semantic identity is required; component
name, displayed text, similar position and repeated callsites are not guessed as
instance identity. Exact or containing structured property paths link directly;
other diagnostics on the same component are only contextual candidates. State
variant diagnostics are not attached to the current page's measured differences.

Sorting is deterministic: P0 incompatible page/state/viewport evidence, P1 missing
components/hierarchy/geometry, P2 resource/text/style/appearance differences, P3
insufficient mapping or one-sided measurement. Within a level the comparator's
component impact score orders inspection, not causality. No unresolved entry is
required for a measured difference to appear. Deferred business conditions remain
deferred, but a corresponding measured missing section stays visible as a P1
finding. The script does not implement the condition or force it true.

Each finding retains actual left/right evidence, source location when uniquely
bound, related diagnostic reasons/modules, target consumption and repair-verification
steps. For literal properties it compares source/version values with the Android
measurement to identify the last matching and first differing recorded artifact.
Unknown values and target calls remain unknown; no target expression is evaluated.
For missing sections and layout, artifact presence is evidence, not proof the
artifact was correct. Runtime binding gaps can resemble missing UI. Runtime theme,
locale, scroll/data alignment and the installed build still need confirmation.
The generation verdict is unchanged; visual findings and generation groups overlap
and must not be added together as independent bugs. AI/human investigation should
start with the explicitly unproven links, not reconstruct every known fact manually.

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

#### Unknown conditional UI previews

The normal partial-generation path projects controls and properties for all collected
alternatives of an undecidable `if`/`when` group. It displays the first alternative not
proven false; known source inputs still select the actual branch. Nested groups and
pager/list instances have independent choices. Source parameters are never fabricated
to make the preview condition true, so unrelated expressions may remain unresolved.

The selected nodes carry `source.state_resolution.status = preview_default` and an
unresolved diagnostic. `meta.sourceGeneration.stateProjection.preview_branch_choices`
records the selections; `retained_components` stores the other projected nodes once,
with their properties, source conditions and parent IDs. These nodes are outside the
active artboard tree and cannot take layout space. This is retained UI data, not a
runtime branch switch or automatic pager/button linkage. To display a different real
state, provide source fixture values and regenerate.

`diagnosis.md` explains the default preview and keeps its condition outstanding.
`selection_complete`, business parity and visual acceptance are not granted by
showing a default branch. Unknown collection counts still remain deferred. Legacy
source documents without `ui_state_path` cannot safely group alternatives and retain
their previous deferred behavior; regenerate source analysis for those documents.
For current source documents, rerun Lanhu generation and ArkUI; no contract rebuild
is needed for this projection-only change.

Verify with `python3 -m unittest test_conditional_ui_preview` and
`test_page_commands.PageCommandsTest.test_full_command_previews_unknown_branch_and_retains_alternative`.

#### Standard collection and repeat gaps

`arrayOf(...)` now participates in bounded fixed-state value evaluation, including
indexing, size and membership conditions. `repeat(times) { index -> ... }` is
extracted from PSI call/lambda scopes and uses the existing ordered list-instance
projection. Named `times`/`action`, the implicit `it`, qualified `kotlin.repeat`,
import aliases, nested scopes and forwarded component counts are covered.
Known nonpositive repeat counts emit no items. Unknown/noninteger counts and counts
above the existing 200-per-loop expansion bound remain deferred; no single item or
truncated prefix is invented. This is selected-state UI expansion, not translation
of arbitrary loop side effects or runtime data/state updates. Direct early control
transfers such as `return@repeat` retain an unsupported diagnostic instead of being
ignored while emitting the entire body.

Recognition uses PSI structure plus known API names, imports and declarations;
it is not compiler type/symbol resolution. Known same-name declarations and local
bindings do not become standard library calls just because their spelling matches.
Modifier argument spans are excluded from visual call extraction: a remembered
local named `focusRequester` cannot turn `.focusRequester(...)` into Text content.
The actual focus operation remains diagnostic until it has target behavior support.

After updating this parser, regenerate the migration contract from the unchanged
safe snapshot, then source-page JSON, Lanhu JSON and ArkUI. Reusing an old contract
would retain its missing iteration scopes and misclassified calls. Run
`python3 -m unittest test_ui_iteration_gaps test_source_control_flow test_source_callables
test_ui_state_semantics test_page_commands` for the affected paths. These tests do
not establish visual fidelity of a private project without paired runtime evidence.

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
table. Dangling/cyclic references fail explicitly. After reference expansion,
`version_json.json` retains the same Lanhu layout model and the ArkUI generator
still has one page input.
This reduces repeated data, not unique source inventories; it is not a claim
that every two-million-line company document shrinks to a particular size.

Business UI variants in `version_json.json` retain only decoder-consumed
`source_generation` fields: `layoutRelationships`, the `stateProjection` root
layout context, `warnings` and `phaseConsumptionGate`. Full projection reports,
duplicate required-fact summaries and duplicate unresolved lists are not embedded
in every variant. Variant failures remain in top-level
`meta.sourceGeneration.unresolved`, tagged with `component_ui_state`, and still
affect the final verdict even for unselected states. Layer facts, IDs, parameters
and state alternatives are unchanged. Legacy variants with full metadata remain
readable; no new CLI flag or external file is needed by the code generator.

Generated `version_json.json` also shares identical large values at the top level
in `lanhu_storage.shared`, with `{"$lanhuRef":"v123"}` at each occurrence.
The storage schema is `android-to-harmony.lanhu-storage.v1`. Repeated styles,
definition data, state metadata and diagnostic facts are shared by exact content,
not by component name. Small values remain inline when a reference would add
overhead. IDs, parameters, parent/child order and distinct instance values are
preserved; expanded instances do not share mutable objects.

Update the complete script set together. Legacy inline Lanhu documents still
work, but older tools that directly traverse JSON must normalize references first:

```python
from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
version = unpack_lanhu_document(json.loads(path.read_text(encoding="utf-8")))
```

The page generator, drawable/font collection and screenshot export normalize
automatically. File hashes describe the stored bytes, not the expanded document.

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
keeps its real parent; route discovery is not required to support multiple outputs.

`parent_id` preserves source ownership, including business-component identities.
A business invocation or content-slot invocation is not itself a layout container.
Reference measurement and placement traverse these boundaries to the actual
Row/Column/Box parent, matching the backend's transparent business builders.
Spacing counts actual emitted children. Business bounds are the union of child
outputs, not a new Box around them.

If the selected entry has multiple outputs without a known parent, they remain
ordered roots with `parent_id=null`. `stateProjection.active_root_ids` and the
manifest's `root_instance_ids` list them; the legacy singular ID is null for a
forest. `root_layout_context=caller_owned` also covers a single business boundary
emitting multiple layout roots. The generated builder emits siblings directly.
The document's preview Stack is only a preview host, not a source layout fact.
`layout.root_host` is a non-failing `warnings` entry, not an unresolved property.
It propagates to the ArkUI manifest and the page command's final `result.json`.
Legal multiple outputs can pass generation without an external parent. Their
reference geometry still does not prove placement in a caller; generation success
does not mean visual acceptance. Mount the component in its intended host for
runtime acceptance. Invalid parents/cycles and ambiguous entry declarations still
fail validation. Correct upstream modeling; do not erase nodes to pass the gate.
