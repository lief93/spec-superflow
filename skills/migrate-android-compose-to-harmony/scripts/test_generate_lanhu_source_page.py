from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_lanhu_source_page import (
    SourceLayout,
    SourceTree,
    build_phase_consumption_gate,
    evaluate_expression,
    lanhu_layer,
    project_source_page,
    resolved_alignment,
)


SCRIPT_DIR = Path(__file__).resolve().parent
GENERATOR = SCRIPT_DIR / "generate_lanhu_source_page.py"
LANHU_SUMMARY = Path(
    "/Users/lief123/.codex/skills/lanhu-android-ui/scripts/summarize_lanhu_json.py"
)


def source_component(
    component_id: str,
    component_type: str,
    *,
    parent_id: str | None,
    sibling_index: int,
    children_ids: list[str] | None = None,
    definition_id: str | None = None,
    width_dp: float | None = None,
    height_dp: float | None = None,
    padding_dp: dict[str, float] | None = None,
    text: str | None = None,
    font_size_sp: float | None = None,
) -> dict:
    return {
        "id": component_id,
        "type": component_type,
        "semantic_key": component_id,
        "parent_id": parent_id,
        "children_ids": children_ids or [],
        "sibling_index": sibling_index,
        "definition_id": definition_id,
        "component_kind": "project" if definition_id else "platform",
        "arguments": {},
        "modifiers": [],
        "source": {
            "source": "app/src/main/java/example/HomeScreen.kt",
            "line": sibling_index + 10,
            "composable": "HomeScreen",
        },
        "style": {
            "layout": {
                "width_dp": width_dp,
                "height_dp": height_dp,
                "padding_dp": padding_dp,
                "margin_dp": None,
                "alignment": None,
                "horizontal_arrangement": None,
                "vertical_arrangement": None,
            },
            "surface": {
                "background": None,
                "border": None,
                "corner_radius_dp": None,
                "shadows": None,
                "alpha": 1,
                "clip": None,
            },
            "typography": {
                "font_size_sp": font_size_sp,
                "line_height_sp": None,
                "font_weight": None,
                "color": None,
                "text_align": None,
            },
            "asset": {
                "resource": None,
                "sha256": None,
                "width_dp": None,
                "height_dp": None,
                "content_scale": None,
                "tint": None,
            },
            "content": {"text": text, "content_description": None},
            "transform": {
                "translation_x_dp": None,
                "translation_y_dp": None,
                "scale_x": None,
                "scale_y": None,
                "rotation_degrees": None,
            },
            "state": {"visible": True, "enabled": True, "clickable": False},
        },
        "unresolved": [],
    }


class GenerateLanhuSourcePageTest(unittest.TestCase):
    def single_state_payload(self) -> tuple[dict, dict]:
        main = source_component("main", "Column", parent_id=None, sibling_index=0,
                                children_ids=["label"])
        label = source_component("label", "Text", parent_id="main", sibling_index=0,
                                 text="Content", font_size_sp=16)
        overlay = source_component("overlay", "UnsupportedDialog", parent_id=None,
                                   sibling_index=1, children_ids=["overlay-child"])
        overlay["visibility_condition"] = {"expression": "state.showDialog"}
        child = source_component("overlay-child", "UnknownControl", parent_id="overlay",
                                 sibling_index=0)
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "sample", "state": "content"},
            "root": {"source": "Sample.kt", "composable": "Sample"},
            "components": [overlay, child, main, label],
            "component_definitions": [], "layout_relationships": [],
        }
        fixture = {"schema": "android-to-harmony.page-state-fixture.v1",
                   "page": payload["page"], "values": {"state": {"showDialog": False}}}
        return payload, fixture

    def test_single_state_prunes_hidden_root_before_validating_render_tree(self) -> None:
        payload, fixture = self.single_state_payload()
        original = copy.deepcopy(payload)
        projected, report = project_source_page(payload, fixture)
        self.assertEqual([n["id"] for n in projected["components"]], ["main", "label"])
        self.assertEqual(projected["components"][0]["children_ids"], ["label"])
        self.assertEqual(projected["components"][1]["parent_id"], "main")
        self.assertEqual(report["active_root_id"], "main")
        self.assertEqual(report["inactive_source_ids"], ["overlay", "overlay-child"])
        self.assertEqual(payload, original)
        self.assertEqual(SourceTree(projected).root_id, "main")

    def test_single_state_exclusive_roots_resolve_bound_conditions(self) -> None:
        payload, fixture = self.single_state_payload()
        main = next(n for n in payload["components"] if n["id"] == "main")
        main["parameter_bindings"] = {"ready": "state.ready"}
        main["visibility_condition"] = {"expression": "ready"}
        overlay = payload["components"][0]
        overlay["visibility_condition"] = {"expression": "!state.ready"}
        fixture["values"]["state"]["ready"] = True
        projected, _ = project_source_page(payload, fixture)
        self.assertEqual([n["id"] for n in projected["components"]], ["main", "label"])

    def test_single_state_unknown_root_condition_is_not_rendered(self) -> None:
        payload, fixture = self.single_state_payload()
        fixture["values"] = {}
        with self.assertRaisesRegex(ValueError, "overlay.*state.showDialog"):
            project_source_page(payload, fixture)

    def test_single_state_unknown_nested_condition_is_not_rendered(self) -> None:
        payload, fixture = self.single_state_payload()
        payload["components"] = payload["components"][2:]
        payload["components"][1]["visibility_condition"] = {"expression": "state.hasLabel"}
        with self.assertRaisesRegex(ValueError, "label.*state.hasLabel"):
            project_source_page(payload, fixture)

    def test_single_state_non_boolean_condition_is_not_assumed_visible(self) -> None:
        payload, fixture = self.single_state_payload()
        payload["components"] = payload["components"][2:]
        payload["components"][1]["visibility_condition"] = {"expression": "state.hasLabel"}
        fixture["values"]["state"]["hasLabel"] = "false"
        with self.assertRaisesRegex(ValueError, "label.*state.hasLabel"):
            project_source_page(payload, fixture)

    def test_single_state_multiple_active_roots_need_parent_layout_fact(self) -> None:
        payload, fixture = self.single_state_payload()
        fixture["values"]["state"]["showDialog"] = True
        with self.assertRaisesRegex(ValueError, "multiple active roots.*main.*overlay"):
            project_source_page(payload, fixture)

    def test_single_state_no_active_root_is_explicit_failure(self) -> None:
        payload, fixture = self.single_state_payload()
        next(n for n in payload["components"] if n["id"] == "main")["visibility_condition"] = {
            "expression": "state.showDialog"}
        with self.assertRaisesRegex(ValueError, "no active root"):
            project_source_page(payload, fixture)

    def test_single_state_boolean_short_circuit_does_not_require_inactive_data(self) -> None:
        self.assertIs(evaluate_expression("false && state.missing", {}), False)
        self.assertIs(evaluate_expression("true || state.missing", {}), True)

    def test_single_state_boolean_precedence_matches_source(self) -> None:
        self.assertIs(evaluate_expression("true || false && state.missing", {}), True)
        self.assertIs(evaluate_expression("false && state.missing || true", {}), True)

    def test_single_state_nullable_error_binding_excludes_error_text(self) -> None:
        payload, fixture = self.single_state_payload()
        payload["components"] = payload["components"][2:]
        label = payload["components"][1]
        label["parameter_bindings"] = {"error": "state.error?.asString()"}
        label["visibility_condition"] = {"expression": "error != null"}
        fixture["values"]["state"]["error"] = None
        projected, _ = project_source_page(payload, fixture)
        self.assertEqual([n["id"] for n in projected["components"]], ["main"])
        fixture["values"]["state"]["error"] = {"__string__": "Invalid"}
        projected, _ = project_source_page(payload, fixture)
        self.assertEqual([n["id"] for n in projected["components"]], ["main", "label"])

    def test_single_state_inactive_constraints_do_not_enter_layout(self) -> None:
        payload, fixture = self.single_state_payload()
        payload["layout_relationships"] = [{"id": "hidden-constraint", "kind": "constraint",
            "container_id": "overlay", "source_id": "overlay-child", "target_id": "overlay"}]
        projected, _ = project_source_page(payload, fixture)
        self.assertEqual(projected["layout_relationships"], [])

    def test_single_state_negation_does_not_coerce_bad_fixture_values(self) -> None:
        payload, fixture = self.single_state_payload()
        payload["components"][0]["visibility_condition"] = {"expression": "!state.showDialog"}
        fixture["values"]["state"]["showDialog"] = "false"
        with self.assertRaisesRegex(ValueError, "overlay.*!state.showDialog"):
            project_source_page(payload, fixture)

    def test_single_state_missing_list_data_does_not_emit_a_fake_item(self) -> None:
        payload, fixture = self.single_state_payload()
        payload["components"] = payload["components"][2:]
        payload["components"][1]["list_item_context"] = {
            "collection": "state.items", "item_parameter": "item"}
        with self.assertRaisesRegex(ValueError, "label.*state.items"):
            project_source_page(payload, fixture)

    def test_single_state_unknown_binding_cannot_reuse_parent_state(self) -> None:
        for field in ("parameter_bindings", "local_values"):
            with self.subTest(field=field):
                payload, fixture = self.single_state_payload()
                payload["components"] = payload["components"][2:]
                payload["components"][1][field] = {"shown": "state.missing"}
                payload["components"][1]["visibility_condition"] = {"expression": "shown"}
                fixture["values"]["shown"] = False
                with self.assertRaisesRegex(ValueError, "label.*shown"):
                    project_source_page(payload, fixture)

    def test_single_state_cli_keeps_unresolved_selection_without_guessing_visibility(self) -> None:
        payload, _ = self.single_state_payload()
        payload["components"] = payload["components"][2:]
        payload["components"][1]["visibility_condition"] = {"expression": "state.hasLabel"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_generator(source, root / "out")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("state.hasLabel", result.stdout)
            version = json.loads((root / "out/version_json.json").read_text())
            self.assertFalse(version['meta']['sourceGeneration']['generationComplete'])
            self.assertEqual(version['meta']['sourceGeneration']['verdict'], 'fail')
            label = version['artboard']['layers'][0]['layers'][0]
            self.assertEqual(label['id'], 'label')
            self.assertEqual(label['migration']['source']['state_resolution']['status'], 'unresolved')

    def test_single_state_cli_only_emits_selected_tree(self) -> None:
        payload, fixture = self.single_state_payload()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, state = root / "source.json", root / "state.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            state.write_text(json.dumps(fixture), encoding="utf-8")
            result = self.run_generator(source, root / "out", state)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            version = json.loads((root / "out/version_json.json").read_text())
            layer = version["artboard"]["layers"][0]
            self.assertEqual(layer["id"], "main")
            self.assertEqual([n["id"] for n in layer["layers"]], ["label"])
            self.assertEqual(version["meta"]["sourceGeneration"]["stateProjection"]["active_root_id"], "main")

    def test_constraint_center_around_participates_in_measure_and_layout(self) -> None:
        root = source_component(
            "root",
            "Column",
            parent_id=None,
            sibling_index=0,
            children_ids=["header", "body"],
        )
        header = source_component(
            "header",
            "ConstraintLayout",
            parent_id="root",
            sibling_index=0,
            children_ids=["cover", "panel"],
        )
        cover = source_component(
            "cover",
            "Box",
            parent_id="header",
            sibling_index=0,
            height_dp=136,
        )
        cover["modifiers"] = [{"name": "fillMaxWidth", "arguments": "", "dimensions": []}]
        panel = source_component(
            "panel",
            "Box",
            parent_id="header",
            sibling_index=1,
            width_dp=329,
            height_dp=80,
        )
        body = source_component(
            "body",
            "Text",
            parent_id="root",
            sibling_index=1,
            height_dp=20,
            text="Body",
            font_size_sp=16,
        )
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "populated"},
            "components": [root, header, cover, panel, body],
            "layout_relationships": [
                {
                    "id": "cover-constraints",
                    "container_id": "header",
                    "subject_id": "cover",
                    "subject_reference": "cover",
                    "composition": "constraint",
                    "draw_order": 0,
                    "active_constraints": [
                        {
                            "kind": "link_to",
                            "subject_anchor": "top",
                            "target_anchor": "top",
                            "target_id": "header",
                            "target_reference": "parent",
                            "margin_dp": 0,
                        }
                    ],
                },
                {
                    "id": "panel-constraints",
                    "container_id": "header",
                    "subject_id": "panel",
                    "subject_reference": "panel",
                    "composition": "overlay",
                    "draw_order": 1,
                    "active_constraints": [
                        {
                            "kind": "center_around",
                            "subject_anchor": "center",
                            "target_anchor": "bottom",
                            "target_id": "cover",
                            "target_reference": "cover",
                            "margin_dp": 0,
                        }
                    ],
                },
            ],
        }

        layout = SourceLayout(SourceTree(payload), 377, 800)
        frames = layout.calculate()

        self.assertEqual(frames["cover"], {"x": 0.0, "y": 0.0, "width": 377, "height": 136.0})
        self.assertEqual(frames["panel"], {"x": 0.0, "y": 96.0, "width": 329.0, "height": 80.0})
        self.assertEqual(frames["header"]["height"], 176.0)
        self.assertEqual(frames["body"]["y"], 176.0)
        lanhu_layer(layout.tree, layout, "root", 1.0)
        phase_gate = build_phase_consumption_gate(layout)
        self.assertEqual(phase_gate["verdict"], "pass")
        self.assertEqual(phase_gate["phase_order"], ["measure", "layout", "draw"])
        self.assertEqual(phase_gate["measured_component_count"], 5)
        self.assertEqual(phase_gate["laid_out_component_count"], 5)
        self.assertEqual(
            phase_gate["consumed_relationship_ids"],
            ["cover-constraints", "panel-constraints"],
        )

    def test_circle_clip_uses_laid_out_frame_for_lanhu_radius(self) -> None:
        root = source_component(
            "root",
            "Box",
            parent_id=None,
            sibling_index=0,
            children_ids=["avatar"],
        )
        avatar = source_component(
            "avatar",
            "AsyncImage",
            parent_id="root",
            sibling_index=0,
            width_dp=48,
            height_dp=48,
        )
        avatar["style"]["surface"]["clip"] = True
        avatar["style"]["asset"]["width_dp"] = 48
        avatar["style"]["asset"]["height_dp"] = 48
        avatar["modifiers"] = [
            {"name": "clip", "arguments": "CircleShape", "dimensions": []}
        ]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "populated"},
            "components": [root, avatar],
        }
        tree = SourceTree(payload)
        layout = SourceLayout(tree, 360, 800)
        layout.calculate()

        layer = lanhu_layer(tree, layout, "avatar", 3.0)

        self.assertEqual(
            layer["radius"],
            {"topLeft": 72, "topRight": 72, "bottomRight": 72, "bottomLeft": 72},
        )
        self.assertIn(
            "style.surface.clip",
            layer["migration"]["phaseTrace"]["draw"]["emittedPaths"],
        )

    def test_phase_gate_rejects_constraint_that_was_parsed_but_not_supported(self) -> None:
        root = source_component(
            "root", "ConstraintLayout", parent_id=None, sibling_index=0,
            children_ids=["label"],
        )
        label = source_component(
            "label", "Text", parent_id="root", sibling_index=0,
            text="Label", font_size_sp=16,
        )
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "default"},
            "components": [root, label],
            "layout_relationships": [{
                "id": "unsupported-baseline",
                "container_id": "root",
                "subject_id": "label",
                "active_constraints": [{
                    "kind": "link_to",
                    "subject_anchor": "baseline",
                    "target_anchor": "baseline",
                    "target_id": "root",
                    "target_reference": "parent",
                    "margin_dp": 0,
                }],
            }],
        }
        layout = SourceLayout(SourceTree(payload), 360, 800)

        layout.calculate()
        lanhu_layer(layout.tree, layout, "root", 1.0)
        phase_gate = build_phase_consumption_gate(layout)

        self.assertEqual(phase_gate["verdict"], "fail")
        self.assertEqual(phase_gate["failure_count"], 2)
        self.assertEqual(
            {item["relationship_id"] for item in phase_gate["failures"]},
            {"unsupported-baseline"},
        )

    def test_lanhu_migration_metadata_preserves_structural_modifiers(self) -> None:
        spacer = source_component(
            "spacer",
            "Spacer",
            parent_id=None,
            sibling_index=0,
            width_dp=100,
            height_dp=0,
        )
        spacer["modifiers"] = [
            {"name": "weight", "arguments": "1f", "dimensions": []}
        ]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "populated"},
            "components": [spacer],
        }
        tree = SourceTree(payload)
        layout = SourceLayout(tree, 360, 800)
        layout.calculate()

        layer = lanhu_layer(tree, layout, "spacer", 3.0)

        self.assertEqual(
            layer["migration"]["source"]["modifiers"], spacer["modifiers"]
        )
        self.assertEqual(
            layer["migration"]["source"]["layoutRules"],
            [{
                "kind": "weight",
                "value": 1.0,
                "fill": True,
                "source_modifier_index": 0,
            }],
        )

    def test_preview_placeholder_is_removed_from_projected_runtime_page(self) -> None:
        image = source_component(
            "avatar",
            "AsyncImage",
            parent_id=None,
            sibling_index=0,
            width_dp=48,
            height_dp=48,
        )
        image["arguments"] = {
            "semantic": {
                "model": {"expression": "state.profilePicUrl"},
                "placeholder": {
                    "expression": "debugPlaceholder(R.drawable.ic_profile_filled)"
                },
            },
            "positional": [],
        }
        image["unresolved"] = [
            {
                "path": "style.content.placeholder",
                "expression": "debugPlaceholder(R.drawable.ic_profile_filled)",
                "reason": "slot or dynamic source expression",
            },
            {
                "path": "style.asset.resource",
                "expression": "state.profilePicUrl",
                "reason": "dynamic source expression",
            },
        ]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "populated"},
            "root": {"source": "Profile.kt", "composable": "Profile"},
            "components": [image],
            "component_definitions": [],
            "source_assets": [],
        }

        projected, _summary = project_source_page(payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "profile", "state": "populated"},
            "values": {"state": {"profilePicUrl": "ic_profile_filled"}},
            "symbols": {},
        })
        projected_image = projected["components"][0]

        self.assertEqual(
            projected_image["style"]["asset"]["resource"], "ic_profile_filled"
        )
        self.assertFalse(
            any(
                item["path"] == "style.content.placeholder"
                for item in projected_image["unresolved"]
            )
        )
        self.assertFalse(
            any(
                item["path"] == "style.content.placeholder"
                for item in projected_image["required_facts"]
            )
        )

    def test_projection_resolves_literal_and_forwarded_text_colors(self) -> None:
        wrapper = source_component(
            "text-btn",
            "TextBtn",
            parent_id=None,
            sibling_index=0,
            children_ids=["label"],
        )
        wrapper["arguments"] = {
            "semantic": {"color": {"expression": "Color(0xFFFF552F)"}},
            "positional": [],
        }
        label = source_component(
            "label",
            "Text",
            parent_id="text-btn",
            sibling_index=0,
            text="Log out",
            font_size_sp=14,
        )
        label["arguments"] = {
            "semantic": {"color": {"expression": "color"}},
            "positional": [],
        }
        label["parameter_bindings"] = {"color": "Color(0xFFFF552F)"}
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "populated"},
            "root": {"source": "Profile.kt", "composable": "Profile"},
            "components": [wrapper, label],
            "component_definitions": [],
            "source_assets": [],
        }

        projected, _summary = project_source_page(payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "profile", "state": "populated"},
            "values": {},
            "symbols": {},
        })
        by_id = {component["id"]: component for component in projected["components"]}

        self.assertEqual(
            by_id["text-btn"]["style"]["typography"]["color"],
            "#FFFF552F",
        )
        self.assertEqual(
            by_id["label"]["style"]["typography"]["color"],
            "#FFFF552F",
        )
        self.assertFalse(
            any(
                fact["status"] == "symbolic"
                and fact["path"] == "style.typography.color"
                for component in projected["components"]
                for fact in component["required_facts"]
            )
        )

    def test_sealed_list_values_select_matching_when_branches(self) -> None:
        root = source_component(
            "root",
            "Column",
            parent_id=None,
            sibling_index=0,
            children_ids=["section", "item"],
        )
        section = source_component(
            "section",
            "Text",
            parent_id="root",
            sibling_index=0,
            height_dp=24,
            font_size_sp=16,
        )
        item = source_component(
            "item",
            "MenuButton",
            parent_id="root",
            sibling_index=1,
            height_dp=48,
        )
        item["style"]["asset"]["resource"] = None
        items_expression = (
            'listOf(MenuItem.Section(UiText.DynamicString("More")), '
            "MenuItem.Item(MenuEntry.Help), MenuItem.Item(MenuEntry.AppSettings))"
        )
        for component in (section, item):
            component["parameter_bindings"] = {"items": items_expression}
            component["list_item_context"] = {
                "collection": "items",
                "item_parameter": "it",
            }
        section["visibility_condition"] = {"expression": "it is MenuItem.Section"}
        section["unresolved"] = [{
            "path": "style.content.text",
            "expression": "it.title.asString()",
            "reason": "dynamic source expression",
        }]
        item["visibility_condition"] = {
            "expression": "(it is MenuItem.Item) && !(it is MenuItem.Section)"
        }
        item["unresolved"] = [
            {
                "path": "style.content.text",
                "expression": "it.entry.uiTitle.asString()",
                "reason": "dynamic source expression",
            },
            {
                "path": "style.asset.resource",
                "expression": "painterResource(id = it.entry.iconRes)",
                "reason": "dynamic source expression",
            },
        ]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "populated"},
            "components": [root, section, item],
        }
        fixture = {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "profile", "state": "populated"},
            "values": {},
            "symbols": {
                "__constructors__": {
                    "UiText.DynamicString": {
                        "fields": ["value"],
                        "string_field": "value",
                    },
                    "MenuItem.Section": {"fields": ["title"]},
                    "MenuItem.Item": {"fields": ["entry"]},
                },
                "MenuEntry.Help": {
                    "uiTitle": "Help and Privacy",
                    "iconRes": "ic_help",
                },
                "MenuEntry.AppSettings": {
                    "uiTitle": "App Settings",
                    "iconRes": "ic_settings",
                },
            },
        }

        projected, _state = project_source_page(payload, fixture)
        projected_by_id = {component["id"]: component for component in projected["components"]}

        self.assertEqual(
            set(projected_by_id),
            {"root", "section__item1", "item__item2", "item__item3"},
        )
        self.assertEqual(
            projected_by_id["section__item1"]["style"]["content"]["text"],
            "More",
        )
        self.assertEqual(
            projected_by_id["item__item2"]["style"]["content"]["text"],
            "Help and Privacy",
        )
        self.assertEqual(
            projected_by_id["item__item3"]["style"]["asset"]["resource"],
            "ic_settings",
        )

    def test_local_conditional_background_and_circle_shape_are_projected(self) -> None:
        box = source_component(
            "action-background",
            "Box",
            parent_id=None,
            sibling_index=0,
            width_dp=48,
            height_dp=48,
        )
        box["parameter_bindings"] = {"isAvailable": "state.available"}
        box["local_values"] = {
            "bgColor": (
                "if (isAvailable) { Color(0xFFECE7FF) } "
                "else { Color(0xFFDEDEDE) }"
            )
        }
        box["unresolved"] = [{
            "path": "style.surface.background",
            "expression": "bgColor, CircleShape",
            "reason": "dynamic source expression",
        }]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "home", "state": "populated"},
            "root": {"source": "Home.kt", "composable": "Home"},
            "components": [box],
            "component_definitions": [],
            "source_assets": [],
        }

        projected, _summary = project_source_page(payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "home", "state": "populated"},
            "values": {"state": {"available": True}},
            "symbols": {},
        })

        surface = projected["components"][0]["style"]["surface"]
        self.assertEqual(
            surface["background"],
            {"type": "solid", "color": "#FFECE7FF"},
        )
        self.assertEqual(
            surface["corner_radius_dp"],
            {
                "top_left": 24,
                "top_right": 24,
                "bottom_right": 24,
                "bottom_left": 24,
            },
        )
        self.assertEqual(projected["components"][0]["unresolved"], [])

    def test_transparent_color_expression_is_resolved(self) -> None:
        self.assertEqual(evaluate_expression("Color.Transparent", {}), "#00000000")

    def test_nested_modifier_background_uses_local_color_and_shape(self) -> None:
        card = source_component(
            "card",
            "Box",
            parent_id=None,
            sibling_index=0,
            width_dp=312,
            height_dp=175,
        )
        card["parameter_bindings"] = {"corners": "10.dp"}
        card["local_values"] = {
            "containerColor": "Color.White",
            "shape": "RoundedCornerShape(corners)",
        }
        card["modifiers"] = [{
            "name": "then",
            "arguments": (
                "Modifier.shadow(20.dp, shape = shape) "
                ".background(color = containerColor, shape = shape)"
            ),
        }]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "home", "state": "populated"},
            "root": {"source": "Home.kt", "composable": "Home"},
            "components": [card],
            "component_definitions": [],
            "source_assets": [],
        }

        projected, _summary = project_source_page(payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "home", "state": "populated"},
            "values": {},
            "symbols": {},
        })

        surface = projected["components"][0]["style"]["surface"]
        self.assertEqual(
            surface["background"],
            {"type": "solid", "color": "#FFFFFFFF"},
        )
        self.assertEqual(
            surface["corner_radius_dp"],
            {
                "top_left": 10,
                "top_right": 10,
                "bottom_right": 10,
                "bottom_left": 10,
            },
        )

    def test_modifier_shape_is_projected_when_background_color_was_already_resolved(self) -> None:
        image = source_component(
            "image",
            "AsyncImage",
            parent_id=None,
            sibling_index=0,
            width_dp=48,
            height_dp=48,
        )
        image["style"]["surface"]["background"] = {
            "type": "solid",
            "color": "#FFF2F2F2",
        }
        image["style"]["layout"]["width_dp"] = None
        image["style"]["layout"]["height_dp"] = None
        image["style"]["asset"]["width_dp"] = 48
        image["style"]["asset"]["height_dp"] = 48
        image["modifiers"] = [{
            "name": "background",
            "arguments": "color = Color(0xFFF2F2F2), shape = CircleShape",
        }]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "home", "state": "populated"},
            "root": {"source": "Home.kt", "composable": "Home"},
            "components": [image],
            "component_definitions": [],
            "source_assets": [],
        }

        projected, _summary = project_source_page(payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "home", "state": "populated"},
            "values": {},
            "symbols": {},
        })

        self.assertEqual(
            projected["components"][0]["style"]["surface"]["corner_radius_dp"],
            {
                "top_left": 24,
                "top_right": 24,
                "bottom_right": 24,
                "bottom_left": 24,
            },
        )

    def test_two_canvas_arcs_project_to_a_resolved_progress_ring(self) -> None:
        canvas = source_component(
            "progress",
            "Canvas",
            parent_id=None,
            sibling_index=0,
            width_dp=48,
            height_dp=48,
        )
        canvas["parameter_bindings"] = {
            "percentage": "state.progress",
            "thickness": "5.dp",
            "accentColor": "#FF100D40",
            "emptyColor": "Color(0xFFF2F2F2)",
        }
        canvas["custom_draw_commands"] = [
            {
                "kind": "arc",
                "arguments": {
                    "color": "emptyColor",
                    "startAngle": "0F",
                    "sweepAngle": "360F",
                    "useCenter": "false",
                    "style": "Stroke(thickness.toPx())",
                },
            },
            {
                "kind": "arc",
                "arguments": {
                    "color": "accentColor",
                    "startAngle": "0F",
                    "sweepAngle": "percentage * 360F",
                    "useCenter": "false",
                    "style": "Stroke(thickness.toPx())",
                },
            },
        ]
        canvas["unresolved"] = [{
            "path": "style.custom_draw",
            "expression": "Canvas trailing lambda at ProgressRing.kt:20",
            "reason": "custom draw commands require structural extraction or a target renderer",
        }]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "home", "state": "populated"},
            "root": {"source": "ProgressRing.kt", "composable": "ProgressRing"},
            "components": [canvas],
            "component_definitions": [],
            "source_assets": [],
        }

        projected, _summary = project_source_page(payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "home", "state": "populated"},
            "values": {"state": {"progress": 0.8}},
            "symbols": {},
        })

        ring = projected["components"][0]
        self.assertEqual(ring["type"], "ProgressRing")
        self.assertEqual(ring["style"]["content"]["text"], "80%")
        self.assertEqual(
            ring["custom_draw"],
            {
                "kind": "ring_progress",
                "value": 80,
                "total": 100,
                "start_angle_degrees": 0,
                "stroke_width_dp": 5,
                "track_color": "#FFF2F2F2",
                "active_color": "#FF100D40",
            },
        )
        self.assertEqual(ring["unresolved"], [])

    def test_image_request_builder_resolves_its_state_bound_data_source(self) -> None:
        self.assertEqual(
            evaluate_expression(
                "ImageRequest.Builder(context) .data(item.imageUrl) .crossfade(true) .build()",
                {"item": {"imageUrl": "ic_car"}},
            ),
            "ic_car",
        )

    def test_state_bound_asset_uses_safe_manifest_sha(self) -> None:
        image = source_component(
            "image",
            "AsyncImage",
            parent_id=None,
            sibling_index=0,
            width_dp=48,
            height_dp=48,
        )
        image["arguments"] = {
            "semantic": {"model": {"expression": "state.icon"}},
            "positional": [],
        }
        image["unresolved"] = [{
            "path": "style.asset.resource",
            "expression": "state.icon",
            "reason": "dynamic source expression",
        }]
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "home", "state": "populated"},
            "root": {"source": "Home.kt", "composable": "Home"},
            "components": [image],
            "component_definitions": [],
            "source_assets": [{
                "resource": "ic_car",
                "path": "app/src/main/res/drawable/ic_car.xml",
                "sha256": "b" * 64,
            }],
        }
        projected, _summary = project_source_page(payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "home", "state": "populated"},
            "values": {"state": {"icon": "ic_car"}},
            "symbols": {},
        })

        self.assertEqual(projected["components"][0]["style"]["asset"]["resource"], "ic_car")
        self.assertEqual(projected["components"][0]["style"]["asset"]["sha256"], "b" * 64)

    def test_state_bound_image_color_filter_projects_to_tint(self) -> None:
        image = source_component(
            "image",
            "Image",
            parent_id=None,
            sibling_index=0,
            width_dp=32,
            height_dp=32,
        )
        image["parameter_bindings"] = {"isAvailable": "state.available"}
        image["local_values"] = {
            "fgColorFilter": (
                "if (isAvailable) null "
                "else ColorFilter.tint(Color(0xFF858585))"
            )
        }
        image["arguments"] = {
            "semantic": {"colorFilter": {"expression": "fgColorFilter"}},
            "positional": [],
        }
        payload = {
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "home", "state": "populated"},
            "root": {"source": "Home.kt", "composable": "Home"},
            "components": [image],
            "component_definitions": [],
            "source_assets": [],
        }
        projected, _summary = project_source_page(payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": {"id": "home", "state": "populated"},
            "values": {"state": {"available": False}},
            "symbols": {},
        })

        self.assertEqual(
            projected["components"][0]["style"]["asset"]["tint"],
            "#FF858585",
        )

    def test_overlay_uses_parent_alignment_and_relative_offset(self) -> None:
        root = source_component(
            "root",
            "BoxWithConstraints",
            parent_id=None,
            sibling_index=0,
            children_ids=["cover"],
            width_dp=360,
            height_dp=136,
        )
        root["style"]["layout"]["alignment"] = "TopEnd"
        cover = source_component(
            "cover",
            "Image",
            parent_id="root",
            sibling_index=0,
        )
        cover["style"]["asset"]["width_dp"] = 200
        cover["style"]["asset"]["height_dp"] = 200
        cover["modifiers"] = [{
            "name": "offset",
            "arguments": "x = maxHeight / 4, y = -maxHeight / 4",
        }]
        tree = SourceTree({
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "home", "state": "default"},
            "root": {"source": "Home.kt", "composable": "Home"},
            "components": [root, cover],
            "component_definitions": [],
        })
        layout = SourceLayout(tree, 360, 136)

        layout.calculate()

        self.assertEqual(
            layout.frames["cover"],
            {"x": 258.0, "y": -34.0, "width": 136.0, "height": 136.0},
        )

    def write_source_page(self, root: Path) -> Path:
        source_page = root / "source-page.json"
        components = [
            source_component(
                "root",
                "Column",
                parent_id=None,
                sibling_index=0,
                children_ids=["header", "content"],
                padding_dp={"left": 16, "top": 12, "right": 16, "bottom": 12},
            ),
            source_component(
                "header",
                "Text",
                parent_id="root",
                sibling_index=0,
                text="Welcome",
                font_size_sp=20,
                height_dp=28,
            ),
            source_component(
                "content",
                "Row",
                parent_id="root",
                sibling_index=1,
                children_ids=["action-one", "action-two"],
                height_dp=48,
            ),
            source_component(
                "action-one",
                "PrimaryAction",
                parent_id="content",
                sibling_index=0,
                definition_id="definition-primary-action",
                width_dp=120,
                height_dp=48,
            ),
            source_component(
                "action-two",
                "PrimaryAction",
                parent_id="content",
                sibling_index=1,
                definition_id="definition-primary-action",
                width_dp=120,
                height_dp=48,
            ),
        ]
        next(c for c in components if c['id'] == 'header')['style']['typography'].update(font_weight=400, color='#FF222222')
        source_page.write_text(
            json.dumps(
                {
                    "schema": "android-to-harmony.source-page-spec.v1",
                    "status": "candidate_requires_runtime_verification",
                    "page": {"id": "home", "state": "default"},
                    "root": {
                        "source": "app/src/main/java/example/HomeScreen.kt",
                        "composable": "HomeScreen",
                    },
                    "components": components,
                    "component_definitions": [
                        {
                            "id": "definition-primary-action",
                            "type": "PrimaryAction",
                            "identity": "example.PrimaryAction",
                            "component_kind": "project",
                            "declared_from": "app/src/main/java/example/PrimaryAction.kt",
                            "dependency": None,
                        }
                    ],
                    "layout_relationships": [],
                    "limitations": ["runtime typography is not available"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return source_page

    def run_generator(
        self,
        source_page: Path,
        output_dir: Path,
        state_fixture: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
                sys.executable,
                str(GENERATOR),
                "--source-page",
                str(source_page),
                "--output-dir",
                str(output_dir),
                "--viewport-width-dp",
                "360",
                "--viewport-height-dp",
                "800",
                "--slice-scale",
                "2",
            ]
        if state_fixture is not None:
            command.extend(["--state-fixture", str(state_fixture)])
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_generates_lanhu_tree_and_sidecars_from_source_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = self.write_source_page(root)
            output_dir = root / "output"

            result = self.run_generator(source_page, output_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            version_json = json.loads((output_dir / "version_json.json").read_text())
            self.assertEqual(set(version_json), {"meta", "assets", "artboard"})
            self.assertEqual(version_json["meta"]["sliceScale"], 2)
            self.assertEqual(
            version_json["meta"]["migration"],
            {
                "schema": "android-to-harmony.lanhu-document.v1",
                "fontFaces": [],
                "componentDefinitions": json.loads(source_page.read_text()).get('component_definitions') or [],
                    "page": {"id": "home", "state": "default"},
                },
            )
            self.assertEqual(
                version_json["meta"]["sourceGeneration"]["sourceInstanceCount"],
                5,
            )
            self.assertEqual(
                sum(version_json["meta"]["sourceGeneration"]["geometrySummary"].values()),
                5,
            )
            self.assertEqual(
                version_json["meta"]["sourceGeneration"]["requiredFactGate"]["verdict"],
                "pass",
            )
            self.assertEqual(
                version_json["meta"]["sourceGeneration"]["phaseConsumptionGate"]["verdict"],
                "pass",
            )
            self.assertEqual(
                version_json["meta"]["sourceGeneration"]["layoutRelationships"],
                [],
            )
            self.assertIsNone(
                version_json["meta"]["sourceGeneration"]["stateProjection"]
            )
            self.assertEqual(version_json["artboard"]["frame"]["width"], 720)
            self.assertEqual(version_json["artboard"]["frame"]["height"], 1600)

            root_layer = version_json["artboard"]["layers"][0]
            self.assertEqual(root_layer["id"], "root")
            self.assertEqual(
                root_layer["migration"]["schema"],
                "android-to-harmony.lanhu-node.v1",
            )
            self.assertEqual(root_layer["migration"]["componentType"], "Column")
            self.assertEqual(root_layer["migration"]["semanticKey"], "root")
            self.assertGreater(len(root_layer["migration"]["requiredFacts"]), 0)
            self.assertEqual(
                root_layer["migration"]["phaseTrace"]["phaseOrder"],
                ["measure", "layout", "draw"],
            )
            self.assertEqual(
                root_layer["migration"]["phaseTrace"]["measure"]["status"],
                "consumed",
            )
            self.assertEqual(
                root_layer["migration"]["phaseTrace"]["layout"]["status"],
                "consumed",
            )
            self.assertEqual(
                root_layer["migration"]["phaseTrace"]["draw"]["status"],
                "consumed",
            )
            self.assertEqual([child["id"] for child in root_layer["layers"]], ["header", "content"])
            self.assertEqual(
                [child["id"] for child in root_layer["layers"][1]["layers"]],
                ["action-one", "action-two"],
            )
            for node in [root_layer, *root_layer["layers"], *root_layer["layers"][1]["layers"]]:
                self.assertEqual(set(node["frame"]), {"left", "top", "width", "height"})
                self.assertTrue(all(isinstance(value, (int, float)) for value in node["frame"].values()))

            component_manifest = json.loads(
                (output_dir / "component-manifest.json").read_text()
            )
            definition = component_manifest["definitions"][0]
            self.assertEqual(definition["id"], "definition-primary-action")
            self.assertEqual(definition["instance_ids"], ["action-one", "action-two"])
            self.assertEqual(component_manifest["source_instance_count"], 5)
            self.assertTrue(
                all("required_facts" in item for item in component_manifest["instances"])
            )

            state_manifest = json.loads(
                (output_dir / "page-state-manifest.json").read_text()
            )
            self.assertEqual(state_manifest["page_id"], "home")
            self.assertEqual(state_manifest["states"][0]["id"], "default")
            self.assertEqual(state_manifest["states"][0]["version_json"], "version_json.json")
            self.assertIsNone(state_manifest["states"][0]["base_state_id"])
            self.assertEqual(state_manifest["states"][0]["overlay_layer_ids"], [])

            summary = subprocess.run(
                [sys.executable, str(LANHU_SUMMARY), str(output_dir / "version_json.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertIn("artboard x=0.0 y=0.0 w=360.0 h=800.0", summary.stdout)
            self.assertIn("text=Welcome", summary.stdout)

    def test_cli_writes_partial_candidate_when_required_constant_is_not_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = self.write_source_page(root)
            payload = json.loads(source_page.read_text())
            header = next(item for item in payload["components"] if item["id"] == "header")
            header["arguments"] = {
                "semantic": {"maxLines": {"expression": "1"}}
            }
            header["style"]["typography"]["max_lines"] = 2
            source_page.write_text(json.dumps(payload) + "\n")
            output_dir = root / "output"

            result = self.run_generator(source_page, output_dir)

            self.assertEqual(result.returncode, 0, result.stdout)
            report = json.loads(result.stdout)
            self.assertFalse(report["generation_complete"])
            self.assertEqual(report["verdict"], "fail")
            self.assertEqual(report["required_fact_gate"]["failure_count"], 1)
            self.assertTrue(any(item["component_id"] == "header"
                                and item["path"] == "style.typography.max_lines"
                                and item["expression"] == "1"
                                for item in report["unresolved"]))
            document = json.loads((output_dir / "version_json.json").read_text())
            generation = document["meta"]["sourceGeneration"]
            self.assertFalse(generation["generationComplete"])
            self.assertEqual(generation["unresolved"], report["unresolved"])
            manifest = json.loads((output_dir / "component-manifest.json").read_text())
            self.assertEqual({node["id"] for node in manifest["instances"]},
                             {node["id"] for node in payload["components"]})

    def test_cli_retains_unresolved_visual_expression_without_required_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = self.write_source_page(root)
            payload = json.loads(source_page.read_text())
            header = next(item for item in payload["components"] if item["id"] == "header")
            header["unresolved"] = [{"path": "style.typography.color",
                "expression": "unsupportedColor(state)", "reason": "unknown color function"}]
            source_page.write_text(json.dumps(payload) + "\n")
            result = self.run_generator(source_page, root / "output")
            self.assertEqual(result.returncode, 0, result.stdout)
            report = json.loads(result.stdout)
            self.assertFalse(report["generation_complete"])
            self.assertEqual(report["verdict"], "fail")
            self.assertTrue(any(item["expression"] == "unsupportedColor(state)"
                                for item in report["unresolved"]))

    def test_unknown_text_writes_valid_partial_json_without_stringifying_state_object(self) -> None:
        from generate_arkui_page import load_lanhu_page_input, Renderer, derive_page_root
        for value in (None, {"value": "not-a-text-fact"}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source_page = self.write_source_page(root)
                payload = json.loads(source_page.read_text())
                for node in payload["components"]:
                    node["source"]["attributes"] = []
                sibling = next(item for item in payload["components"] if item["id"] == "action-one")
                sibling["type"] = "Text"
                sibling["style"]["content"]["text"] = "Save"
                header = next(item for item in payload["components"] if item["id"] == "header")
                header["style"]["content"]["text"] = value
                header["arguments"] = {"semantic": {"text": {"expression": "state.title"}}}
                source_page.write_text(json.dumps(payload) + "\n")
                result = self.run_generator(source_page, root / "output")
                self.assertEqual(result.returncode, 0, result.stdout)
                page = load_lanhu_page_input(root / "output/version_json.json")
                self.assertIsNone(page["by_id"]["header"]["style"]["content"]["text"])
                self.assertTrue(any(item["path"] == "style.content.text"
                                    and item["expression"] == "state.title"
                                    for item in page["by_id"]["header"]["unresolved"]))
                renderer = Renderer(derive_page_root(page), set(), {}, page)
                output = renderer.render()
                self.assertNotIn("not-a-text-fact", output)
                self.assertIn("Text('Save')", output)
                self.assertTrue(renderer.unresolved)

    def test_constraint_overlay_contributes_its_offset_extent_to_following_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = root / "source-page.json"
            components = [
                source_component(
                    "root",
                    "Column",
                    parent_id=None,
                    sibling_index=0,
                    children_ids=["header", "following"],
                ),
                source_component(
                    "header",
                    "ConstraintLayout",
                    parent_id="root",
                    sibling_index=0,
                    children_ids=["cover", "panel"],
                ),
                source_component(
                    "cover",
                    "Box",
                    parent_id="header",
                    sibling_index=0,
                    width_dp=360,
                    height_dp=100,
                ),
                source_component(
                    "panel",
                    "Box",
                    parent_id="header",
                    sibling_index=1,
                    width_dp=320,
                    height_dp=60,
                ),
                source_component(
                    "following",
                    "Text",
                    parent_id="root",
                    sibling_index=1,
                    text="After header",
                    font_size_sp=16,
                    height_dp=20,
                ),
            ]
            source_page.write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.source-page-spec.v1",
                        "status": "candidate_requires_runtime_verification",
                        "page": {"id": "home", "state": "default"},
                        "root": {"source": "Home.kt", "composable": "HomeScreen"},
                        "components": components,
                        "component_definitions": [],
                        "layout_relationships": [
                            {
                                "container_id": "header",
                                "subject_id": "cover",
                                "draw_order": 0,
                                "active_constraints": [
                                    {
                                        "kind": "link_to",
                                        "subject_anchor": "top",
                                        "target_anchor": "top",
                                        "target_id": "header",
                                        "target_reference": "parent",
                                        "margin_dp": 0,
                                    }
                                ],
                            },
                            {
                                "container_id": "header",
                                "subject_id": "panel",
                                "draw_order": 1,
                                "active_constraints": [
                                    {
                                        "kind": "link_to",
                                        "subject_anchor": "top",
                                        "target_anchor": "bottom",
                                        "target_id": "cover",
                                        "target_reference": "cover",
                                        "margin_dp": -20,
                                    }
                                ],
                            },
                        ],
                        "limitations": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "output"

            result = self.run_generator(source_page, output_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output_dir / "component-manifest.json").read_text())
            frames = {item["id"]: item["frame_dp"] for item in manifest["instances"]}
            self.assertEqual(frames["header"]["height"], 140)
            self.assertEqual(frames["panel"]["y"], 80)
            self.assertEqual(frames["following"]["y"], 140)
            version_json = json.loads((output_dir / "version_json.json").read_text())
            relationships = version_json["meta"]["sourceGeneration"]["layoutRelationships"]
            self.assertEqual(len(relationships), 2)
            self.assertEqual(relationships[0]["container_id"], "header")
            self.assertEqual(relationships[0]["subject_id"], "cover")
            self.assertEqual(relationships[1]["subject_id"], "panel")

    def test_material_toolbar_defaults_and_wrapper_width_are_source_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = root / "source-page.json"
            components = [
                source_component(
                    "root",
                    "Column",
                    parent_id=None,
                    sibling_index=0,
                    children_ids=["toolbar-wrapper"],
                ),
                source_component(
                    "toolbar-wrapper",
                    "ProjectToolbar",
                    parent_id="root",
                    sibling_index=0,
                    children_ids=["toolbar"],
                    definition_id="definition-project-toolbar",
                ),
                source_component(
                    "toolbar",
                    "TopAppBar",
                    parent_id="toolbar-wrapper",
                    sibling_index=0,
                    children_ids=["title", "action"],
                ),
                source_component(
                    "title",
                    "Box",
                    parent_id="toolbar",
                    sibling_index=0,
                    width_dp=100,
                    height_dp=40,
                ),
                source_component(
                    "action",
                    "IconButton",
                    parent_id="toolbar",
                    sibling_index=1,
                    children_ids=["icon"],
                ),
                source_component(
                    "icon",
                    "Icon",
                    parent_id="action",
                    sibling_index=0,
                    width_dp=24,
                    height_dp=24,
                ),
            ]
            components[1]["modifiers"] = [{"name": "fillMaxWidth", "arguments": ""}]
            source_page.write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.source-page-spec.v1",
                        "status": "candidate_requires_runtime_verification",
                        "page": {"id": "home", "state": "default"},
                        "root": {"source": "Home.kt", "composable": "HomeScreen"},
                        "components": components,
                        "component_definitions": [
                            {
                                "id": "definition-project-toolbar",
                                "type": "ProjectToolbar",
                                "identity": "example.ProjectToolbar",
                                "component_kind": "project",
                                "declared_from": "ProjectToolbar.kt",
                                "dependency": None,
                            }
                        ],
                        "layout_relationships": [],
                        "limitations": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "output"

            result = self.run_generator(source_page, output_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output_dir / "component-manifest.json").read_text())
            frames = {item["id"]: item["frame_dp"] for item in manifest["instances"]}
            self.assertEqual(frames["toolbar-wrapper"]["width"], 360)
            self.assertEqual(frames["toolbar"]["width"], 360)
            self.assertEqual(frames["action"]["width"], 48)
            self.assertEqual(frames["action"]["height"], 48)
            self.assertEqual(frames["action"]["x"], 308)
            self.assertEqual(frames["icon"]["x"], 320)
            self.assertEqual(frames["icon"]["y"], 12)

    def test_project_wrapper_forwards_width_and_row_space_between(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = root / "source-page.json"
            components = [
                source_component(
                    "root",
                    "Column",
                    parent_id=None,
                    sibling_index=0,
                    children_ids=["section"],
                ),
                source_component(
                    "section",
                    "ProjectSection",
                    parent_id="root",
                    sibling_index=0,
                    children_ids=["row"],
                    definition_id="definition-project-section",
                ),
                source_component(
                    "row",
                    "Row",
                    parent_id="section",
                    sibling_index=0,
                    children_ids=["title", "action"],
                ),
                source_component(
                    "title",
                    "Text",
                    parent_id="row",
                    sibling_index=0,
                    width_dp=40,
                    height_dp=20,
                    text="Title",
                    font_size_sp=16,
                ),
                source_component(
                    "action",
                    "TextButton",
                    parent_id="row",
                    sibling_index=1,
                    children_ids=["action-label"],
                ),
                source_component(
                    "action-label",
                    "Text",
                    parent_id="action",
                    sibling_index=0,
                    width_dp=40,
                    height_dp=20,
                    text="Open",
                    font_size_sp=14,
                ),
            ]
            components[1]["modifiers"] = [{"name": "fillMaxWidth", "arguments": ""}]
            components[2]["arguments"] = {
                "semantic": {
                    "horizontalArrangement": {"expression": "Arrangement.SpaceBetween"},
                    "verticalAlignment": {"expression": "Alignment.CenterVertically"},
                }
            }
            source_page.write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.source-page-spec.v1",
                        "status": "candidate_requires_runtime_verification",
                        "page": {"id": "home", "state": "default"},
                        "root": {"source": "Home.kt", "composable": "HomeScreen"},
                        "components": components,
                        "component_definitions": [
                            {
                                "id": "definition-project-section",
                                "type": "ProjectSection",
                                "identity": "example.ProjectSection",
                                "component_kind": "project",
                                "declared_from": "ProjectSection.kt",
                                "dependency": None,
                            }
                        ],
                        "layout_relationships": [],
                        "limitations": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "output"

            result = self.run_generator(source_page, output_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output_dir / "component-manifest.json").read_text())
            frames = {item["id"]: item["frame_dp"] for item in manifest["instances"]}
            self.assertEqual(frames["section"]["width"], 360)
            self.assertEqual(frames["row"]["width"], 360)
            self.assertEqual(frames["action"]["width"], 64)
            self.assertEqual(frames["action"]["x"], 296)
            self.assertEqual(frames["title"]["y"], 14)
            self.assertEqual(frames["action-label"]["x"], 308)

    def test_project_padding_parameter_and_max_width_are_propagated_to_internal_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = root / "source-page.json"
            components = [
                source_component(
                    "root",
                    "Column",
                    parent_id=None,
                    sibling_index=0,
                    children_ids=["action-row"],
                ),
                source_component(
                    "action-row",
                    "ProjectActionRow",
                    parent_id="root",
                    sibling_index=0,
                    children_ids=["internal-row"],
                    definition_id="definition-action-row",
                ),
                source_component(
                    "internal-row",
                    "Row",
                    parent_id="action-row",
                    sibling_index=0,
                    children_ids=["item"],
                ),
                source_component(
                    "item",
                    "Box",
                    parent_id="internal-row",
                    sibling_index=0,
                    width_dp=48,
                    height_dp=48,
                ),
            ]
            components[1]["modifiers"] = [{"name": "width", "arguments": "maxWidth"}]
            components[1]["arguments"] = {
                "invocation": [
                    {
                        "name": "paddingValues",
                        "expression": (
                            "PaddingValues(top = 16.dp, bottom = 8.dp, "
                            "start = 12.dp, end = 12.dp)"
                        ),
                    }
                ],
                "semantic": {},
            }
            components[2]["modifiers"] = [
                {"name": "then", "arguments": "Modifier.padding(paddingValues)"}
            ]
            source_page.write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.source-page-spec.v1",
                        "status": "candidate_requires_runtime_verification",
                        "page": {"id": "home", "state": "default"},
                        "root": {"source": "Home.kt", "composable": "HomeScreen"},
                        "components": components,
                        "component_definitions": [
                            {
                                "id": "definition-action-row",
                                "type": "ProjectActionRow",
                                "identity": "example.ProjectActionRow",
                                "component_kind": "project",
                                "declared_from": "ProjectActionRow.kt",
                                "dependency": None,
                            }
                        ],
                        "layout_relationships": [],
                        "limitations": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "output"

            result = self.run_generator(source_page, output_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output_dir / "component-manifest.json").read_text())
            instances = {item["id"]: item for item in manifest["instances"]}
            self.assertEqual(instances["action-row"]["frame_dp"]["width"], 360)
            self.assertEqual(instances["internal-row"]["frame_dp"]["width"], 360)
            self.assertEqual(instances["internal-row"]["resolved_layout"]["padding_dp"], {
                "left": 12,
                "top": 16,
                "right": 12,
                "bottom": 8,
            })
            self.assertEqual(instances["item"]["frame_dp"]["x"], 12)
            self.assertEqual(instances["item"]["frame_dp"]["y"], 16)
            version_json = json.loads((output_dir / "version_json.json").read_text())
            internal_row = version_json["artboard"]["layers"][0]["layers"][0]["layers"][0]
            self.assertEqual(
                internal_row["migration"]["style"]["layout"]["padding_dp"],
                {"left": 12, "top": 16, "right": 12, "bottom": 8},
            )

    def test_top_center_alignment_places_child_at_top(self) -> None:
        root = source_component(
            "root",
            "Column",
            parent_id=None,
            sibling_index=0,
            children_ids=["cover"],
        )
        cover = source_component(
            "cover",
            "Box",
            parent_id="root",
            sibling_index=0,
            children_ids=["toolbar"],
            height_dp=136,
        )
        cover["modifiers"] = [{"name": "fillMaxWidth", "arguments": ""}]
        cover["style"]["layout"]["alignment"] = "TopCenter"
        toolbar = source_component(
            "toolbar",
            "Box",
            parent_id="cover",
            sibling_index=0,
            width_dp=104,
            height_dp=36,
        )
        tree = SourceTree({
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "default"},
            "root": {"source": "Profile.kt", "composable": "Profile"},
            "components": [root, cover, toolbar],
        })

        frames = SourceLayout(tree, 360, 800).calculate()

        self.assertEqual(frames["toolbar"]["x"], 128)
        self.assertEqual(frames["toolbar"]["y"], 0)

    def test_box_positional_content_alignment_is_preserved(self) -> None:
        root = source_component(
            "root",
            "Column",
            parent_id=None,
            sibling_index=0,
            children_ids=["container"],
        )
        container = source_component(
            "container",
            "Box",
            parent_id="root",
            sibling_index=0,
            children_ids=["action"],
            height_dp=100,
        )
        container["modifiers"] = [{"name": "fillMaxWidth", "arguments": ""}]
        container["arguments"] = {
            "positional": [{"expression": "Alignment.Center"}],
        }
        action = source_component(
            "action",
            "Box",
            parent_id="container",
            sibling_index=0,
            width_dp=80,
            height_dp=40,
        )
        tree = SourceTree({
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "default"},
            "root": {"source": "Profile.kt", "composable": "Profile"},
            "components": [root, container, action],
        })
        layout = SourceLayout(tree, 360, 800)

        frames = layout.calculate()
        layer = lanhu_layer(tree, layout, "container", 2)

        self.assertEqual(frames["action"]["x"], 140)
        self.assertEqual(frames["action"]["y"], 30)
        self.assertEqual(
            layer["migration"]["style"]["layout"]["alignment"],
            "Center",
        )

    def test_compose_container_default_alignments_are_explicit(self) -> None:
        column = source_component(
            "column",
            "Column",
            parent_id=None,
            sibling_index=0,
        )
        row = source_component(
            "row",
            "Row",
            parent_id=None,
            sibling_index=0,
        )
        box = source_component(
            "box",
            "Box",
            parent_id=None,
            sibling_index=0,
        )

        self.assertEqual(resolved_alignment(column), "Start")
        self.assertEqual(resolved_alignment(row), "Top")
        self.assertEqual(resolved_alignment(box), "TopStart")

    def test_forwarded_weight_modifier_fills_internal_project_surface(self) -> None:
        root = source_component(
            "root",
            "Column",
            parent_id=None,
            sibling_index=0,
            children_ids=["row"],
        )
        row = source_component(
            "row",
            "Row",
            parent_id="root",
            sibling_index=0,
            children_ids=["menu"],
            height_dp=72,
        )
        row["modifiers"] = [{"name": "fillMaxWidth", "arguments": ""}]
        menu = source_component(
            "menu",
            "MenuButton",
            parent_id="row",
            sibling_index=0,
            children_ids=["card"],
            definition_id="definition-menu",
        )
        menu["modifiers"] = [
            {"name": "weight", "arguments": "1f"},
            {"name": "fillMaxHeight", "arguments": ""},
        ]
        card = source_component(
            "card",
            "PrimaryCard",
            parent_id="menu",
            sibling_index=0,
            children_ids=["surface"],
            definition_id="definition-card",
        )
        card["arguments"] = {
            "invocation": [{"name": "modifier", "expression": "modifier"}],
        }
        card["parameter_bindings"] = {
            "modifier": "Modifier.weight(1f).fillMaxHeight()",
        }
        surface = source_component(
            "surface",
            "Box",
            parent_id="card",
            sibling_index=0,
            width_dp=40,
            height_dp=40,
        )
        surface["parameter_bindings"] = {
            "modifier": "Modifier.weight(1f).fillMaxHeight()",
        }
        tree = SourceTree({
            "schema": "android-to-harmony.source-page-spec.v1",
            "page": {"id": "profile", "state": "default"},
            "root": {"source": "Profile.kt", "composable": "Profile"},
            "components": [root, row, menu, card, surface],
        })

        frames = SourceLayout(tree, 360, 800).calculate()

        self.assertEqual(frames["menu"]["width"], 360)
        self.assertEqual(frames["card"]["width"], 360)
        self.assertEqual(frames["surface"]["width"], 360)
        self.assertEqual(frames["menu"]["height"], 72)
        self.assertEqual(frames["card"]["height"], 72)
        self.assertEqual(frames["surface"]["height"], 72)

    def test_state_fixture_selects_branches_expands_lists_and_resolves_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = root / "source-page.json"
            components = [
                source_component(
                    "root", "Column", parent_id=None, sibling_index=0,
                    children_ids=["content", "empty", "item"],
                ),
                source_component(
                    "content", "Text", parent_id="root", sibling_index=0,
                    height_dp=24, font_size_sp=16,
                ),
                source_component(
                    "empty", "Text", parent_id="root", sibling_index=1,
                    height_dp=24, text="Empty", font_size_sp=16,
                ),
                source_component(
                    "item", "Column", parent_id="root", sibling_index=2,
                    children_ids=["item-label"], height_dp=24,
                ),
                source_component(
                    "item-label", "Text", parent_id="item", sibling_index=0,
                    height_dp=24, font_size_sp=16,
                ),
            ]
            components[1]["visibility_condition"] = {
                "expression": "state.items.isNotEmpty()"
            }
            components[1]["unresolved"] = [{
                "path": "style.content.text",
                "expression": "state.title",
                "reason": "dynamic source expression",
            }]
            components[2]["visibility_condition"] = {
                "expression": "!(state.items.isNotEmpty())"
            }
            components[3]["list_item_context"] = {
                "collection": "state.items",
                "item_parameter": "it",
            }
            components[3]["parameter_bindings"] = {"item": "it"}
            components[4]["unresolved"] = [{
                "path": "style.content.text",
                "expression": "item.label",
                "reason": "dynamic source expression",
            }]
            source_page.write_text(json.dumps({
                "schema": "android-to-harmony.source-page-spec.v1",
                "status": "candidate_requires_runtime_verification",
                "page": {"id": "home", "state": "populated"},
                "root": {"source": "Home.kt", "composable": "HomeScreen"},
                "components": components,
                "component_definitions": [],
                "layout_relationships": [],
                "limitations": [],
            }) + "\n", encoding="utf-8")
            fixture = root / "state.json"
            fixture.write_text(json.dumps({
                "schema": "android-to-harmony.page-state-fixture.v1",
                "page": {"id": "home", "state": "populated"},
                "values": {
                    "state": {
                        "title": "Welcome",
                        "items": [{"label": "First"}, {"label": "Second"}],
                    }
                },
                "symbols": {},
            }) + "\n", encoding="utf-8")
            output_dir = root / "output"

            result = self.run_generator(source_page, output_dir, fixture)

            self.assertEqual(result.returncode, 0, result.stderr)
            version_json = json.loads((output_dir / "version_json.json").read_text())
            root_layer = version_json["artboard"]["layers"][0]
            self.assertEqual(
                [layer["id"] for layer in root_layer["layers"]],
                ["content", "item__item1", "item__item2"],
            )
            self.assertEqual(root_layer["layers"][0]["text"], "Welcome")
            self.assertEqual(root_layer["layers"][1]["layers"][0]["text"], "First")
            self.assertEqual(root_layer["layers"][2]["layers"][0]["text"], "Second")
            manifest = json.loads((output_dir / "component-manifest.json").read_text())
            instance_keys = [
                item["semantic_key"]
                for item in manifest["instances"]
                if item["id"].startswith("item__item")
            ]
            self.assertEqual(len(instance_keys), len(set(instance_keys)))
            self.assertTrue(all("__instance_item" in key for key in instance_keys))
            self.assertEqual(manifest["state_projection"]["inactive_source_ids"], ["empty"])
            self.assertEqual(manifest["state_projection"]["expanded_list_instances"], 2)

    def test_source_dimension_tokens_size_project_wrapper_and_internal_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_page = root / "source-page.json"
            components = [
                source_component(
                    "root", "Column", parent_id=None, sibling_index=0,
                    children_ids=["project"],
                ),
                source_component(
                    "project", "ProjectButton", parent_id="root", sibling_index=0,
                    children_ids=["button"], definition_id="project-button",
                ),
                source_component(
                    "button", "Button", parent_id="project", sibling_index=0,
                    children_ids=["label"],
                ),
                source_component(
                    "label", "Text", parent_id="button", sibling_index=0,
                    width_dp=80, height_dp=20, text="Add a Card", font_size_sp=14,
                ),
            ]
            components[1]["modifiers"] = [
                {"name": "width", "arguments": "CARD_WIDTH_FIXED"},
                {"name": "height", "arguments": "CARD_HEIGHT_FIXED"},
            ]
            source_page.write_text(json.dumps({
                "schema": "android-to-harmony.source-page-spec.v1",
                "status": "candidate_requires_runtime_verification",
                "page": {"id": "home", "state": "default"},
                "root": {"source": "Home.kt", "composable": "HomeScreen"},
                "components": components,
                "component_definitions": [],
                "layout_relationships": [],
                "source_tokens": [
                    {"name": "CARD_WIDTH_FIXED", "dimensions": [{"value": "300", "unit": "dp"}]},
                    {"name": "CARD_HEIGHT_FIXED", "dimensions": [{"value": "200", "unit": "dp"}]},
                ],
                "limitations": [],
            }) + "\n", encoding="utf-8")
            output_dir = root / "output"

            result = self.run_generator(source_page, output_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output_dir / "component-manifest.json").read_text())
            instances = {item["id"]: item for item in manifest["instances"]}
            self.assertEqual(instances["project"]["frame_dp"]["width"], 300)
            self.assertEqual(instances["project"]["frame_dp"]["height"], 200)
            self.assertEqual(instances["button"]["frame_dp"]["width"], 300)
            self.assertEqual(instances["button"]["frame_dp"]["height"], 200)


if __name__ == "__main__":
    unittest.main()
