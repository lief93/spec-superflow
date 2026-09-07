# Source to Lanhu JSON to ArkUI

This is the implementation-stage recipe used inside the migration workflow. It is not a
second planning entry point: normal runs still start/resume through `migration_agent.py`.
The examples below use the existing scripts and one existing Python library function.
They do not require a new source-page CLI that does not exist.

## Inputs and outputs

```text
read-only Android project
  -> validated safe snapshot
  -> analyze_compose_project.py -> migration-contract.json
  -> build_source_page_spec(...) -> source-page.json
  -> one explicit state fixture
  -> generate_lanhu_source_page.py -> version_json.json
  -> generate_arkui_page.py -> generated ArkUI + generation manifest

running Android/Harmony pages -> screenshots + runtime page.json -> comparison
```

| File | Producer / purpose | Implementation input? |
| --- | --- | --- |
| `migration-contract.json` | Source analyzer; source calls, definitions, resources and candidate business inventory | Only upstream of the page JSON |
| `source-page.json` | `real_page_pipeline.build_source_page_spec`; expanded source component tree and expressions | Input to the Lanhu generator |
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

There is currently no standalone source-only CLI for this step. This executable snippet calls
the same library function used by real-page capture and the source-only regression harness.
It does not invoke UIAutomator or read screenshots. `source_root` is the safe snapshot, so local
source values and approved asset metadata can be resolved without reopening the original tree.

```bash
mkdir -p "$PAGE_RUN"
PYTHONPATH="$SKILL_ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 -B - <<'PY'
import json
import os
from pathlib import Path
from init_harmony_project import load_contract, sha256_file
from real_page_pipeline import build_source_page_spec

contract, contract_path = load_contract(Path(os.environ["CONTRACT"]))
page = build_source_page_spec(
    contract,
    os.environ["ROOT_SOURCE"],
    os.environ["ROOT_COMPOSABLE"],
    os.environ["PAGE_ID"],
    os.environ["STATE_ID"],
    sha256_file(contract_path),
    Path(os.environ["SNAPSHOT"]),
)
with Path(os.environ["SOURCE_PAGE"]).open("x", encoding="utf-8") as output:
    json.dump(page, output, ensure_ascii=False, indent=2)
    output.write("\n")
PY
```

The source tree preserves project-component expansion, parents/children, sibling order,
argument bindings, modifiers, static styles and unresolved expressions. Its calculated frames
are source reference geometry, not a claim of measured Android bounds. No device means no
runtime proof of font/platform-default behavior; capture the actual page later for validation.

Alternative: `generate_real_android_page_json.py` also produces `source-page.json` when capturing
a running page. See [the capture commands](page-snapshot.md#capture-real-pages-and-bind-runtime-nodes-to-source).
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
can be fatal; an unsupported selected control/property can instead yield a partial candidate.
For fully static pages, omit `--state-fixture`; unresolved state is never guessed automatically.

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

Outputs are `version_json.json`, `component-manifest.json`, `page-state-manifest.json` and the
captured stdout result. Inspect `generation_complete`, `verdict`, `unresolved`,
`required_fact_gate` and `phase_consumption_gate`. The version document embeds equivalent
diagnostics in `meta.sourceGeneration` and per-node `migration.requiredFacts`.

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
