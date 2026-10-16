"""Public-command tests for compact page/state closures derived from a full contract."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ui_migration.contracts.identity import canonical_sha256
from ui_migration.contracts.source_storage import unpack_source_page


SCRIPTS = Path(__file__).parent


class EffectivePageClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="effective page closure ")
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "android"
        cls.source.mkdir()
        (cls.source / "Page.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.ui.res.stringResource
@Composable fun Page(activeSheet: String?) {
  Column {
    Text(stringResource(R.string.underlying))
    if (activeSheet == "settings") {
      Box { Text("SCRIM"); Settings() }
    } else if (activeSheet == "profile") {
      Profile()
    }
  }
}
'''
        )
        (cls.source / "Settings.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
import androidx.compose.foundation.Image
import androidx.compose.ui.res.painterResource
@Composable fun Settings() {
  Text("Settings visible")
  Image(painterResource(R.drawable.settings_icon), contentDescription = "Settings icon")
}
'''
        )
        (cls.source / "Profile.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
@Composable fun Profile() { Text("PROFILE_SENTINEL") }
'''
        )
        (cls.source / "Analytics.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
@Composable fun Analytics() { Text("ANALYTICS_SENTINEL") }
'''
        )
        (cls.source / "Host.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
@Composable fun Host() {
  Page(activeSheet = "settings")
}
'''
        )
        (cls.source / "BusinessPage.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
@Composable fun BusinessPage(viewModel: BusinessViewModel) {
  Text(viewModel.state.title)
}

@Composable fun BusinessPage_Preview() {
  BusinessPage(BusinessViewModel(PreviewBusinessRepository()))
}
'''
        )
        (cls.source / "BusinessViewModel.kt").write_text(
            '''package example
class BusinessViewModel(private val repository: BusinessRepository) {
  var state = BusinessState()
  fun emitIntent(intent: BusinessIntent) {
    when (intent) {
      BusinessIntent.Refresh -> state = state.copy(title = repository.loadTitle())
    }
  }
}
data class BusinessState(val title: String = "Initial")
sealed interface BusinessIntent { data object Refresh : BusinessIntent }
'''
        )
        (cls.source / "BusinessRepository.kt").write_text(
            '''package example
interface BusinessRepository { fun loadTitle(): String }
class PreviewBusinessRepository : BusinessRepository {
  override fun loadTitle(): String = "Preview"
}
'''
        )
        (cls.source / "LeafScreen.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
import androidx.compose.material3.Button
import androidx.compose.material3.Text
@Composable fun LeafScreen(
  title: String,
  onRefresh: () -> Unit,
  onBack: () -> Unit = {},
  onDetails: (String) -> Unit = {},
) {
  Text(title)
  Button(onClick = onRefresh) { Text("Refresh") }
  Button(onClick = onBack) { Text("Back") }
  Button(onClick = { onDetails(title) }) { Text("Details") }
}
'''
        )
        (cls.source / "LeafRoute.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
@Composable fun LeafRoute(
  viewModel: LeafViewModel,
  onBack: () -> Unit = {},
  onDetails: (String) -> Unit = {},
) {
  LeafScreen(viewModel.title, { viewModel.refresh() }, onBack, onDetails)
}
@Composable fun UnrelatedRoute(service: UnrelatedService) { service.run() }
'''
        )
        (cls.source / "LeafViewModel.kt").write_text(
            '''package example
class LeafViewModel(private val repository: LeafRepository) {
  var title: String = "Initial"
  fun refresh() { title = repository.load() }
}
'''
        )
        (cls.source / "LeafRepository.kt").write_text(
            '''package example
interface LeafRepository { fun load(): String }
'''
        )
        (cls.source / "UnrelatedService.kt").write_text(
            '''package example
class UnrelatedService {
  fun run() = Unit
  fun open(id: String) = Unit
}
'''
        )
        (cls.source / "AppHost.kt").write_text(
            '''package example
import androidx.compose.runtime.Composable
@Composable fun AppHost(viewModel: LeafViewModel, service: UnrelatedService) {
  LeafRoute(
    viewModel,
    onBack = { service.run() },
    onDetails = { id -> service.open(id) },
  )
  UnrelatedRoute(service)
}
'''
        )
        values = cls.source / "app/src/main/res/values/strings.xml"
        values.parent.mkdir(parents=True)
        values.write_text(
            '''<resources>
  <string name="underlying">Underlying page</string>
  <string name="unrelated">UNRELATED_RESOURCE_SENTINEL</string>
</resources>'''
        )
        drawable = cls.source / "app/src/main/res/drawable/settings_icon.xml"
        drawable.parent.mkdir(parents=True, exist_ok=True)
        drawable.write_text(
            '<vector xmlns:android="http://schemas.android.com/apk/res/android" '
            'android:width="24dp" android:height="24dp" android:viewportWidth="24" '
            'android:viewportHeight="24"><path android:fillColor="#FF000000" '
            'android:pathData="M0,0L24,0L24,24L0,24Z"/></vector>'
        )
        cls.snapshot = cls.root / "snapshot"
        cls.contract = cls.root / "migration-contract.json"
        cls.styles = cls.root / "styles.json"
        cls.run_tool("prepare_safe_snapshot.py", "--source", cls.source, "--snapshot", cls.snapshot)
        cls.run_tool("analyze_compose_project.py", "--snapshot", cls.snapshot, "--output", cls.contract)
        cls.run_tool("generate_project_style_definitions.py", "--contract", cls.contract, "--output", cls.styles)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_tool(cls, script, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *map(str, args)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=SCRIPTS,
        )
        if result.returncode != expected:
            raise AssertionError(result.stdout + result.stderr)
        return json.loads(result.stdout) if expected == 0 else result

    @staticmethod
    def sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_selected_business_scope_preserves_context_and_changes_closure_identity(self):
        args = ['--contract', self.contract, '--style-definitions', self.styles,
                '--root-source', 'BusinessPage.kt', '--root-composable', 'BusinessPage',
                '--page-id', 'business', '--state-id', 'default']
        original_path = self.root/'business-boundary-original.json'
        self.run_tool('generate_effective_page_closure.py', *args, '--output', original_path)
        original = json.loads(original_path.read_text())
        scope = original['business_transcription']['scope']
        scope['definition_boundaries'] = [{
            'path': 'BusinessViewModel.kt', 'symbol': 'BusinessViewModel',
            'behavior_ranges': [{'start_line': 3, 'end_line': 3}],
            'context_reason': 'This fixture page only reads the initial state; it has no event callback.',
            'resolved_dependencies': [], 'unresolved': [],
        }]
        scope_path = self.root/'business-boundary-scope.json'
        scope_path.write_text(json.dumps(scope))
        selected_path = self.root/'business-boundary-selected.json'
        self.run_tool('generate_effective_page_closure.py', *args,
                      '--behavior-source-scope', scope_path, '--output', selected_path)
        selected = json.loads(selected_path.read_text())
        business = selected['business_transcription']
        self.assertEqual(business['scope'], scope)
        roundtrip_scope = self.root/'business-boundary-roundtrip-scope.json'
        roundtrip_scope.write_text(json.dumps(business['scope']))
        roundtrip_census = self.run_tool('audit_behavior_source.py', 'census',
                                        '--snapshot', self.snapshot, '--scope', roundtrip_scope)
        self.assertEqual(roundtrip_census['census_sha256'], business['census_sha256'])
        self.assertLess(business['obligation_summary']['total'],
                        original['business_transcription']['obligation_summary']['total'])
        self.assertNotEqual(business['census_sha256'], original['business_transcription']['census_sha256'])
        self.assertEqual(business['reading_context'][0]['symbol'], 'BusinessViewModel')
        self.assertIn('BusinessViewModel.kt', [f['path'] for f in selected['source_scope']['entry_files']])
        self.assertNotIn('BusinessRepository.kt', [f['path'] for f in business['files']])

    def closure_args(self):
        return [
            "--contract", self.contract,
            "--style-definitions", self.styles,
            "--root-source", "Page.kt",
            "--root-composable", "Page",
            "--page-id", "page",
            "--state-id", "settings-expanded",
        ]

    def test_contract_closure_uses_the_same_snapshot_bound_source_page_identity(self):
        source_page_path = self.root / "identity-source-page.json"
        self.run_tool(
            "generate_source_page.py",
            "--snapshot", self.snapshot,
            "--contract", self.contract,
            "--style-definitions", self.styles,
            "--root-source", "Page.kt",
            "--root-composable", "Page",
            "--page-id", "page",
            "--state-id", "settings-expanded",
            "--output", source_page_path,
        )
        source_page = unpack_source_page(json.loads(source_page_path.read_text()))
        closure_path = self.root / "identity-source-page-closure.json"

        self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--output", closure_path,
        )

        closure = json.loads(closure_path.read_text())
        self.assertEqual(
            closure["identity"]["source_input_sha256"],
            canonical_sha256(source_page),
        )

    def test_fixture_selects_only_visible_page_layers_and_referenced_resources(self):
        fixture = self.root / "settings-state.json"
        fixture.write_text(json.dumps({
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "page", "state": "settings-expanded"},
            "values": {"activeSheet": "settings"},
        }))
        output = self.root / "settings-closure.json"
        contract_before = self.sha256(self.contract)

        result = self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--state-fixture", fixture,
            "--output", output,
        )

        closure = json.loads(output.read_text())
        texts = [item.get("display", {}).get("text") for item in closure["visible_components"]]
        self.assertEqual(closure["schema"], "android-to-harmony.effective-page-closure.v1")
        self.assertEqual(closure["status"], "candidate_complete")
        self.assertTrue(closure["selection"]["complete"])
        self.assertTrue(closure["source_scope"]["reading_required"])
        self.assertEqual(closure["source_scope"]["status"], "ready")
        scoped_files = {
            item["path"]: item for item in closure["source_scope"]["entry_files"]
        }
        self.assertEqual(
            set(scoped_files), {"Host.kt", "Page.kt", "Profile.kt", "Settings.kt"}
        )
        self.assertNotIn("Analytics.kt", scoped_files)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in scoped_files.values()))
        self.assertEqual(
            closure["identity"]["source_scope_sha256"],
            closure["source_scope"]["sha256"],
        )
        self.assertIn("Underlying page", texts)
        self.assertIn("SCRIM", texts)
        self.assertIn("Settings visible", texts)
        self.assertNotIn("PROFILE_SENTINEL", json.dumps(closure))
        self.assertNotIn("ANALYTICS_SENTINEL", json.dumps(closure))
        self.assertNotIn("UNRELATED_RESOURCE_SENTINEL", json.dumps(closure))
        self.assertEqual(closure["resources"]["strings"], {"underlying": "Underlying page"})
        self.assertEqual([item["resource"] for item in closure["resources"]["assets"]],
                         ["settings_icon"])
        self.assertEqual(closure["identity"]["contract_sha256"], contract_before)
        self.assertEqual(self.sha256(self.contract), contract_before)
        self.assertEqual(result["visible_component_count"], len(closure["visible_components"]))

    def test_production_page_adds_transitive_business_source_denominator(self):
        output = self.root / "business-closure.json"
        self.run_tool(
            "generate_effective_page_closure.py",
            "--contract", self.contract,
            "--style-definitions", self.styles,
            "--root-source", "BusinessPage.kt",
            "--root-composable", "BusinessPage",
            "--page-id", "business",
            "--output", output,
        )

        closure = json.loads(output.read_text())
        business = closure["business_transcription"]
        self.assertTrue(business["required"])
        self.assertEqual(business["root_kind"], "production_page")
        self.assertEqual(business["status"], "ready_for_source_transcription")
        self.assertEqual(
            {item["path"] for item in business["files"]},
            {"BusinessPage.kt", "BusinessRepository.kt", "BusinessViewModel.kt"},
        )
        scoped = {item["path"]: item for item in closure["source_scope"]["entry_files"]}
        self.assertIn("business_dependency", scoped["BusinessViewModel.kt"]["reasons"])
        self.assertIn("business_dependency", scoped["BusinessRepository.kt"]["reasons"])
        self.assertGreater(business["obligation_summary"]["total"], 0)
        self.assertEqual(len(business["obligation_index_sha256"]), 64)
        self.assertNotIn("obligations", business)
        self.assertEqual(
            closure["identity"]["business_census_sha256"], business["census_sha256"]
        )
        self.assertIn("state", business["required_target_mappings"])
        self.assertIn("side_effect_order", business["required_target_mappings"])

    def test_leaf_ui_root_traces_host_callback_and_business_dependencies_by_symbol(self):
        output = self.root / "leaf-business-closure.json"
        self.run_tool(
            "generate_effective_page_closure.py",
            "--contract", self.contract,
            "--style-definitions", self.styles,
            "--root-source", "LeafScreen.kt",
            "--root-composable", "LeafScreen",
            "--page-id", "leaf",
            "--output", output,
        )

        closure = json.loads(output.read_text())
        business = closure["business_transcription"]
        self.assertEqual(business["status"], "ready_for_source_transcription")
        self.assertEqual(
            business["scope"]["entry_symbols"],
            {
                "LeafRoute.kt": ["LeafRoute"],
                "LeafScreen.kt": ["LeafScreen"],
            },
        )
        self.assertEqual(
            {item["path"] for item in business["files"]},
            {"LeafRoute.kt", "LeafScreen.kt", "LeafViewModel.kt", "LeafRepository.kt"},
        )
        self.assertNotIn("UnrelatedService.kt", {item["path"] for item in business["files"]})
        scoped = {item["path"] for item in closure["source_scope"]["entry_files"]}
        self.assertTrue({"LeafRoute.kt", "LeafScreen.kt", "LeafViewModel.kt", "LeafRepository.kt"} <= scoped)

    def test_state_owning_route_keeps_navigation_host_context_out_of_business_denominator(self):
        output = self.root / "route-business-closure.json"
        self.run_tool(
            "generate_effective_page_closure.py",
            "--contract", self.contract,
            "--style-definitions", self.styles,
            "--root-source", "LeafRoute.kt",
            "--root-composable", "LeafRoute",
            "--page-id", "leaf-route",
            "--output", output,
        )

        closure = json.loads(output.read_text())
        business = closure["business_transcription"]
        self.assertEqual(
            business["scope"]["entry_symbols"],
            {"LeafRoute.kt": ["LeafRoute"]},
        )
        self.assertEqual(
            {item["path"] for item in business["files"]},
            {"LeafRoute.kt", "LeafScreen.kt", "LeafViewModel.kt", "LeafRepository.kt"},
        )
        self.assertNotIn("AppHost.kt", {item["path"] for item in business["files"]})
        self.assertNotIn("UnrelatedService.kt", {item["path"] for item in business["files"]})
        scoped = {item["path"]: item for item in closure["source_scope"]["entry_files"]}
        self.assertIn("page_host", scoped["AppHost.kt"]["reasons"])
        callbacks = business["host_callback_obligations"]
        self.assertEqual(
            {item["parameter"] for item in callbacks},
            {"onBack", "onDetails"},
        )
        self.assertTrue(all(item["caller"] == {
            "source": "AppHost.kt", "composable": "AppHost"
        } for item in callbacks))
        expressions = "\n".join(item["expression"] for item in callbacks)
        self.assertIn("service.run()", expressions)
        self.assertIn("service.open(id)", expressions)

    def test_preview_root_requires_explicit_ui_only_mode(self):
        args = [
            "--contract", self.contract,
            "--style-definitions", self.styles,
            "--root-source", "BusinessPage.kt",
            "--root-composable", "BusinessPage_Preview",
            "--page-id", "business-preview",
        ]
        failed = self.run_tool(
            "generate_effective_page_closure.py",
            *args,
            "--output", self.root / "rejected-preview-closure.json",
            expected=1,
        )
        self.assertIn("--ui-only-preview", failed.stdout)

        output = self.root / "explicit-preview-closure.json"
        self.run_tool(
            "generate_effective_page_closure.py",
            *args,
            "--ui-only-preview",
            "--output", output,
        )
        business = json.loads(output.read_text())["business_transcription"]
        self.assertFalse(business["required"])
        self.assertEqual(business["root_kind"], "ui_only_preview")
        self.assertEqual(business["status"], "explicitly_out_of_scope")

    def test_unresolved_dynamic_state_retains_both_source_branches_without_calling_either_visible(self):
        output = self.root / "unresolved-closure.json"
        self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--output", output,
        )
        closure = json.loads(output.read_text())
        encoded = json.dumps(closure)
        self.assertEqual(closure["status"], "candidate_requires_runtime_facts")
        self.assertFalse(closure["selection"]["complete"])
        self.assertTrue(closure["selection"]["unresolved_branches"])
        visible = json.dumps(closure["visible_components"])
        alternatives = json.dumps(closure["unresolved_branch_components"])
        self.assertNotIn("PROFILE_SENTINEL", visible)
        self.assertNotIn("Settings visible", visible)
        self.assertIn("PROFILE_SENTINEL", alternatives)
        self.assertIn("Settings visible", alternatives)
        self.assertTrue(all(
            item.get("source", {}).get("state_resolution", {}).get("business_verified") is False
            for item in closure["unresolved_branch_components"]
        ))
        self.assertNotIn("ANALYTICS_SENTINEL", encoded)

    def test_identity_changes_with_state_fixture_and_output_is_never_overwritten(self):
        identities = []
        for state in ("settings", "profile"):
            fixture = self.root / f"{state}-identity-state.json"
            fixture.write_text(json.dumps({
                "schema": "android-to-harmony.page-state-fixture.v1",
                "page": {"id": "page", "state": "settings-expanded"},
                "values": {"activeSheet": state},
            }))
            output = self.root / f"{state}-identity-closure.json"
            self.run_tool(
                "generate_effective_page_closure.py",
                *self.closure_args(),
                "--state-fixture", fixture,
                "--output", output,
            )
            identities.append(json.loads(output.read_text())["identity"]["sha256"])
        self.assertNotEqual(*identities)
        failed = self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--output", self.root / "settings-closure.json",
            expected=1,
        )
        self.assertIn("already exists", failed.stdout)

    def test_android_page_json_adds_hash_bound_runtime_geometry_without_reading_image(self):
        fixture = self.root / "runtime-state.json"
        fixture.write_text(json.dumps({
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "page", "state": "settings-expanded"},
            "values": {"activeSheet": "settings"},
        }))
        android_page = self.root / "android-page.json"
        android_page.write_text(json.dumps({
            "schema": "android-to-harmony.page-snapshot.v2",
            "platform": "android",
            "page": {"id": "page", "state": "settings-expanded"},
            "capture": {
                "screenshot": {
                    "file": "must-not-be-opened.png",
                    "sha256": "a" * 64,
                    "byte_count": 123,
                }
            },
            "components": [
                {
                    "id": "runtime-settings-title",
                    "type": "Text",
                    "parent_id": None,
                    "children_ids": [],
                    "sibling_index": 0,
                    "semantic_key": "Settings_Text_1_1",
                    "source_mapping": {
                        "method": "exact_text",
                        "source_call_id": "Settings.kt:1:Text:1",
                    },
                    "bounds_dp": {"x": 10.0, "y": 209.0, "width": 100.0, "height": 30.0},
                    "style": {
                        "content": {"text": "Settings visible", "role": "text"},
                        "typography": {"font_size_sp": 22.0},
                        "state": {"visible": True},
                    },
                    "provenance": [
                        {"origin": "runtime", "paths": ["style.content.text"]}
                    ],
                    "unresolved": [],
                }
            ],
            "inactive_source_components": [],
            "runtime_elided_source_components": [],
        }))
        output = self.root / "runtime-closure.json"

        result = self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--state-fixture", fixture,
            "--android-page-json", android_page,
            "--output", output,
        )

        closure = json.loads(output.read_text())
        self.assertEqual(result["android_page_sha256"], self.sha256(android_page))
        self.assertEqual(
            closure["identity"]["android_page_sha256"], self.sha256(android_page)
        )
        self.assertEqual(
            closure["runtime_facts"]["components"][0]["bounds_dp"]["y"], 209.0
        )
        self.assertEqual(
            closure["runtime_facts"]["components"][0]["source_call_id"],
            "Settings.kt:1:Text:1",
        )
        self.assertEqual(
            closure["runtime_facts"]["screenshot_sha256"], "a" * 64
        )
        self.assertNotIn("must-not-be-opened.png", json.dumps(closure))

    def test_android_page_json_must_match_platform_page_and_state(self):
        for label, update, expected in (
            ("platform", {"platform": "harmony"}, "platform must be android"),
            (
                "page",
                {"page": {"id": "other", "state": "settings-expanded"}},
                "page/state must match",
            ),
        ):
            android_page = self.root / f"invalid-{label}-page.json"
            payload = {
                "schema": "android-to-harmony.page-snapshot.v2",
                "platform": "android",
                "page": {"id": "page", "state": "settings-expanded"},
                "capture": {"screenshot": {"sha256": "b" * 64}},
                "components": [],
            }
            payload.update(update)
            android_page.write_text(json.dumps(payload))
            failed = self.run_tool(
                "generate_effective_page_closure.py",
                *self.closure_args(),
                "--android-page-json", android_page,
                "--output", self.root / f"invalid-{label}-closure.json",
                expected=1,
            )
            self.assertIn(expected, failed.stdout)

    def test_android_page_json_must_match_the_selected_source_page_identity(self):
        android_page = self.root / "wrong-source-page.json"
        android_page.write_text(json.dumps({
            "schema": "android-to-harmony.page-snapshot.v2",
            "platform": "android",
            "page": {"id": "page", "state": "settings-expanded"},
            "capture": {"screenshot": {"sha256": "d" * 64}},
            "input_hashes": {"source_page_spec_sha256": "e" * 64},
            "components": [],
        }))

        failed = self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--android-page-json", android_page,
            "--output", self.root / "wrong-source-page-closure.json",
            expected=1,
        )

        self.assertIn("source page identity must match", failed.stdout)

    def test_android_page_json_visible_content_must_match_the_state_fixture(self):
        fixture = self.root / "runtime-content-state.json"
        fixture.write_text(json.dumps({
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "page", "state": "settings-expanded"},
            "values": {"activeSheet": "settings"},
        }))
        projected_output = self.root / "runtime-content-projected-closure.json"
        self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--state-fixture", fixture,
            "--output", projected_output,
        )
        projected = json.loads(projected_output.read_text())
        settings_title = next(
            item for item in projected["visible_components"]
            if item.get("display", {}).get("text") == "Settings visible"
        )
        android_page = self.root / "runtime-content-mismatch-page.json"
        android_page.write_text(json.dumps({
            "schema": "android-to-harmony.page-snapshot.v2",
            "platform": "android",
            "page": {"id": "page", "state": "settings-expanded"},
            "capture": {"screenshot": {"sha256": "f" * 64}},
            "components": [{
                "id": "runtime-settings-title",
                "type": "Text",
                "component_context": {
                    "source_component_id": settings_title["id"],
                },
                "style": {"content": {"text": "Different runtime text"}},
            }],
        }))

        failed = self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--state-fixture", fixture,
            "--android-page-json", android_page,
            "--output", self.root / "runtime-content-mismatch-closure.json",
            expected=1,
        )

        self.assertIn(
            "state fixture visible content must match Android page capture",
            failed.stdout,
        )
        self.assertNotIn("Different runtime text", failed.stdout)

    def test_runtime_formatted_textbox_content_keeps_fixture_value_private(self):
        from generate_effective_page_closure import require_matching_runtime_content

        require_matching_runtime_content(
            {
                "components": [{
                    "source_component_id": "card-number",
                    "style": {"content": {"role": "textbox", "text": "6304-0000"}},
                }],
            },
            [{
                "id": "card-number",
                "style": {"content": {"role": "textbox", "text": "63040000"}},
                "parameter_bindings": {
                    "visualTransformation": "{ value -> formatCardNumber(value) }",
                },
            }],
        )

    def test_android_runtime_theme_is_hash_bound_and_available_to_transcription(self):
        theme_facts = self.root / "android-theme-facts.json"
        theme_facts.write_text(json.dumps({
            "schema": "android-to-harmony.compose-theme-facts.v1",
            "platform": "android",
            "theme_id": "buckwheat-light",
            "capture": {
                "sdk_int": 35,
                "density": 3.5,
                "font_scale": 1.0,
                "layout_direction": "ltr",
            },
            "theme": {
                "colors": {
                    "primary": "#FF00658B",
                    "surface": "#FFF5FAFD",
                    "onSurface": "#FF171C1F",
                },
                "typography": {
                    "displayMedium": {
                        "font_size_sp": 45.0,
                        "font_weight": None,
                        "font_style": None,
                        "font_family": None,
                        "letter_spacing_sp": 0.0,
                        "line_height_sp": 52.0,
                    }
                },
                "shapes": {
                    "extraLarge": {
                        "runtime_type": "RoundedCornerShape",
                        "description": "RoundedCornerShape(28.0.dp)",
                    }
                },
            },
            "provenance": [{
                "paths": ["theme.colors", "theme.typography", "theme.shapes"],
                "origin": "runtime",
                "source": "MaterialTheme",
            }],
            "unresolved": [{
                "path": "theme.typography.displayMedium.font_family",
                "expression": "getFont(900)",
                "reason": "runtime TextStyle does not expose the backing font asset",
            }],
        }))
        output = self.root / "runtime-theme-closure.json"

        result = self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--android-theme-facts", theme_facts,
            "--output", output,
        )

        closure = json.loads(output.read_text())
        self.assertEqual(result["android_theme_sha256"], self.sha256(theme_facts))
        self.assertEqual(
            closure["identity"]["android_theme_sha256"], self.sha256(theme_facts)
        )
        self.assertEqual(
            closure["runtime_theme"]["theme"]["colors"]["surface"], "#FFF5FAFD"
        )
        self.assertEqual(
            closure["runtime_theme"]["theme"]["typography"]["displayMedium"]["font_size_sp"],
            45.0,
        )

    def test_android_runtime_theme_rejects_untrusted_shape_and_color_fields(self):
        for label, update, expected in (
            ("platform", {"platform": "harmony"}, "platform must be android"),
            (
                "color",
                {"theme": {"colors": {"surface": "blue"}, "typography": {}, "shapes": {}}},
                "theme color must use #AARRGGBB",
            ),
        ):
            theme_facts = self.root / f"invalid-{label}-theme-facts.json"
            payload = {
                "schema": "android-to-harmony.compose-theme-facts.v1",
                "platform": "android",
                "theme_id": "test-light",
                "capture": {
                    "sdk_int": 35,
                    "density": 3.5,
                    "font_scale": 1.0,
                    "layout_direction": "ltr",
                },
                "theme": {"colors": {}, "typography": {}, "shapes": {}},
                "provenance": [],
                "unresolved": [],
            }
            payload.update(update)
            theme_facts.write_text(json.dumps(payload))
            failed = self.run_tool(
                "generate_effective_page_closure.py",
                *self.closure_args(),
                "--android-theme-facts", theme_facts,
                "--output", self.root / f"invalid-{label}-theme-closure.json",
                expected=1,
            )
            self.assertIn(expected, failed.stdout)

    def test_android_runtime_theme_must_match_bound_page_capture_environment(self):
        android_page = self.root / "theme-environment-page.json"
        android_page.write_text(json.dumps({
            "schema": "android-to-harmony.page-snapshot.v2",
            "platform": "android",
            "page": {"id": "page", "state": "settings-expanded"},
            "capture": {"screenshot": {"sha256": "c" * 64}},
            "viewport": {"density": 3.5, "font_scale": 1.0},
            "components": [],
        }))
        theme_facts = self.root / "mismatched-environment-theme.json"
        theme_facts.write_text(json.dumps({
            "schema": "android-to-harmony.compose-theme-facts.v1",
            "platform": "android",
            "theme_id": "other-device-light",
            "capture": {
                "sdk_int": 30,
                "density": 1.0,
                "font_scale": 1.0,
                "layout_direction": "ltr",
            },
            "theme": {"colors": {}, "typography": {}, "shapes": {}},
            "provenance": [],
            "unresolved": [],
        }))

        failed = self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--android-page-json", android_page,
            "--android-theme-facts", theme_facts,
            "--output", self.root / "mismatched-environment-closure.json",
            expected=1,
        )

        self.assertIn("capture density does not match", failed.stdout)

    def test_closure_indexes_bounded_source_caller_context_from_full_contract(self):
        output = self.root / "caller-context-closure.json"
        self.run_tool(
            "generate_effective_page_closure.py",
            *self.closure_args(),
            "--output", output,
        )

        context = json.loads(output.read_text())["source_context"]
        self.assertEqual(context["status"], "bounded-candidate-context")
        self.assertFalse(context["truncated"])
        self.assertIn(
            {
                "depth": 1,
                "caller": {"source": "Host.kt", "composable": "Host"},
                "callee": {"source": "Page.kt", "composable": "Page"},
                "line": 4,
                "call_id": "Host.kt:4:Page:1",
                "invocation_arguments": [
                    {"name": "activeSheet", "expression": '"settings"'}
                ],
            },
            context["caller_edges"],
        )


if __name__ == "__main__":
    unittest.main()
