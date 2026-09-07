from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from generate_arkui_page import (
    ArkUIPageError,
    Renderer,
    build_target_phase_consumption_gate,
    derive_page_root,
    generate,
    main,
    is_direct_native_wrapper,
    load_lanhu_page_input,
    parse_args,
    runtime_overlay_style_path_allowed,
)


def empty_style() -> dict[str, dict[str, object | None]]:
    return {
        "layout": {},
        "surface": {},
        "typography": {},
        "asset": {},
        "content": {},
        "transform": {},
        "state": {},
    }


class GenerateArkUILanhuInputTest(unittest.TestCase):
    def test_page_json_render_does_not_execute_unused_source_translation(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.root = {"source": "Profile.kt", "composable": "ProfileScreen"}
        renderer.reached_keys = [("Profile.kt", "ProfileScreen")]
        renderer.android_page_input = {
            "viewport": {
                "content_bounds_dp": {"x": 0, "y": 0, "width": 360, "height": 800}
            }
        }
        renderer.root_public_parameters = Mock(
            side_effect=AssertionError("unused source parameter translation executed")
        )
        renderer.render_definition = Mock(
            side_effect=AssertionError("unused source definition translation executed")
        )
        renderer.render_android_page_snapshot = Mock(
            return_value=[
                "  @Builder",
                "  private renderAndroidPageSnapshot() {}",
            ]
        )
        renderer.selected_calls = []
        renderer.android_page_by_call_id = {}
        renderer.resource_names = set()
        renderer.data_class_interface_properties = {}
        renderer._arkts_interfaces = []
        renderer.state_fields = {}
        renderer.verified_font_faces = []
        renderer._uses_resource_manager = False
        renderer._uses_resource_str_resolver = False
        renderer._uses_greeting_helper = False
        renderer._uses_rupee_formatter = False
        renderer._uses_android_color_parser = False
        renderer._uses_drawing_color_filter = False
        renderer._uses_fallback_list_item = False

        source = renderer.render()

        self.assertIn("this.renderAndroidPageSnapshot()", source)
        renderer.root_public_parameters.assert_not_called()
        renderer.render_definition.assert_not_called()

    def test_generator_accepts_exactly_one_page_json_argument(self) -> None:
        argv = [
            "generate_arkui_page.py",
            "--target", "target",
            "--page-json", "version_json.json",
        ]

        with patch.object(sys, "argv", argv):
            args = parse_args()

        self.assertEqual(args.page_json, Path("version_json.json"))
        self.assertFalse(hasattr(args, "android_page_json"))
        self.assertFalse(hasattr(args, "android_runtime_page_json"))
        self.assertFalse(hasattr(args, "lanhu_version_json"))
        self.assertFalse(hasattr(args, "contract"))
        self.assertFalse(hasattr(args, "root_source"))
        self.assertFalse(hasattr(args, "root_composable"))

    def test_page_json_renderer_needs_no_contract_closure_or_source_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            page = load_lanhu_page_input(version_json)
            root_component = next(
                component for component in page["components"]
                if component["parent_id"] is None
            )
            root = {
                "source": root_component["source"]["source"],
                "composable": root_component["source"]["composable"],
            }

            renderer = Renderer(
                root,
                set(),
                {},
                page,
            )

            self.assertEqual(renderer.selected_calls, [])
            self.assertEqual(renderer.reached_keys, [])
            self.assertEqual(renderer.android_page_by_call_id, {})

    def test_renderer_rejects_missing_page_json_instead_of_translating_source(self) -> None:
        with self.assertRaisesRegex(
            ArkUIPageError, "source translation fallback is disabled"
        ):
            Renderer(
                {"source": "ProfileScreen.kt", "composable": "ProfileScreen"},
                set(),
                {},
                None,
            )

    def test_page_json_render_never_calls_legacy_source_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            page = load_lanhu_page_input(version_json)
            renderer = Renderer(
                derive_page_root(page),
                {"media:ic_cover_ellipse"},
                {},
                page,
            )
            fallback_methods = (
                "page_snapshot_source_lines",
                "painter_resource_expression",
                "arrangement_space",
                "page_snapshot_source_radius",
                "android_page_instances",
                "page_snapshot_elided_surfaces",
            )
            mocks = {}
            for method in fallback_methods:
                mocks[method] = Mock(
                    side_effect=AssertionError(f"legacy source fallback executed: {method}")
                )
                setattr(renderer, method, mocks[method])

            source = renderer.render()

            self.assertIn("this.renderAndroidPageSnapshot()", source)
            for fallback in mocks.values():
                fallback.assert_not_called()

    def test_missing_page_image_fact_is_unresolved_without_source_fallback(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_layout_mode = "source-tree"
        renderer.android_page_by_id = {}
        renderer.android_page_applied_component_paths = {}
        renderer.android_page_processed_component_ids = set()
        renderer.android_source_layout_by_subject = {}
        renderer.android_source_tree_by_id = {}
        renderer.tinted_vector_resources = {}
        renderer.resource_names = set()
        renderer.verified_font_faces = []
        renderer.unresolved = []
        renderer._unresolved_keys = set()
        renderer.painter_resource_expression = Mock(
            side_effect=AssertionError("source painter fallback executed")
        )
        component = {
            "id": "missing-image",
            "semantic_key": "MissingImage",
            "type": "Image",
            "parent_id": None,
            "children_ids": [],
            "call_ids": ["Profile.kt:1:Image:1"],
            "sibling_index": 0,
            "bounds_dp": {"x": 0, "y": 0, "width": 24, "height": 24},
            "source_layout_bounds_dp": {"x": 0, "y": 0, "width": 24, "height": 24},
            "source": {"modifiers": []},
            "style": {
                "layout": {"padding_dp": None},
                "surface": {
                    "background": None,
                    "border": None,
                    "corner_radius_dp": None,
                    "shadows": None,
                },
                "typography": {},
                "asset": {"resource": None, "tint": None, "content_scale": "fit"},
                "content": {"text": None},
            },
        }
        renderer.android_page_by_id[component["id"]] = component

        lines = renderer.page_snapshot_component_lines(
            component,
            {"x": 0, "y": 0, "width": 360, "height": 800},
            None,
            0,
        )

        self.assertEqual(lines, [])
        renderer.painter_resource_expression.assert_not_called()
        self.assertEqual(renderer.unresolved[0]["kind"], "page_json_missing_fact")
        self.assertEqual(renderer.unresolved[0]["path"], "style.asset.resource")

    def test_generation_manifest_proves_page_json_only_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            version_json, _component_manifest = self.write_inputs(root)
            payload = json.loads(version_json.read_text())
            payload["meta"]["sourceGeneration"] = {"layoutRelationships": []}
            self.add_required_facts(payload["artboard"]["layers"][0])
            version_json.write_text(json.dumps(payload) + "\n")
            target = (root / "target").resolve()
            target.mkdir()
            with (
                patch(
                    "generate_arkui_page.normalize_target",
                    return_value=target,
                ),
                patch("generate_arkui_page.require_module"),
                patch(
                    "generate_arkui_page.load_theme_resources",
                    return_value=({"media:ic_cover_ellipse"}, {}),
                ),
            ):
                result = generate(target, "entry", version_json, False)

            manifest = json.loads((target / result["manifest"]).read_text())
            self.assertEqual(manifest["input_mode"], "page-json-only")
            self.assertEqual(manifest["source_fallback_count"], 0)
            self.assertEqual(manifest["source_fallbacks"], [])
            self.assertNotIn("contract_sha256", manifest)
            self.assertNotIn("source_revision", manifest)
            self.assertEqual(manifest["expanded_definition_count"], 0)
            self.assertEqual(manifest["selected_call_count"], 0)

    def test_source_flow_component_type_is_not_inferred_from_coordinates(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_layout_mode = "source-tree"
        renderer.android_page_by_id = {
            "column": {
                "id": "column",
                "type": "Column",
                "children_ids": ["first", "second"],
            },
            "first": {
                "id": "first",
                "sibling_index": 0,
                "bounds_dp": {"x": 0, "y": 0, "width": 100, "height": 40},
            },
            "second": {
                "id": "second",
                "sibling_index": 1,
                "bounds_dp": {"x": 0, "y": 20, "width": 100, "height": 40},
            },
        }

        self.assertEqual(
            renderer.page_snapshot_flow_container(
                renderer.android_page_by_id["column"]
            ),
            "Column",
        )

    def test_constraint_layout_uses_relative_container(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_layout_mode = "source-tree"

        self.assertEqual(
            renderer.page_snapshot_layout_container({"type": "ConstraintLayout"}),
            "RelativeContainer",
        )

    def test_constraint_relationships_emit_align_rules_without_coordinates(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_layout_mode = "source-tree"
        renderer.android_page_by_id = {
            "header": {
                "id": "header",
                "type": "ConstraintLayout",
                "semantic_key": "Header",
                "children_ids": ["cover", "panel"],
            },
            "cover": {
                "id": "cover",
                "type": "Box",
                "semantic_key": "HeaderCover",
                "parent_id": "header",
                "children_ids": [],
            },
            "panel": {
                "id": "panel",
                "type": "Box",
                "semantic_key": "HeaderPanel",
                "parent_id": "header",
                "children_ids": [],
            },
        }
        renderer.android_source_layout_by_subject = {
            "cover": {
                "unresolved": [],
                "active_constraints": [
                    {
                        "kind": "link_to",
                        "subject_anchor": "start",
                        "target_id": "header",
                        "target_reference": "parent",
                        "target_anchor": "start",
                        "margin_dp": 0,
                    },
                    {
                        "kind": "link_to",
                        "subject_anchor": "end",
                        "target_id": "header",
                        "target_reference": "parent",
                        "target_anchor": "end",
                        "margin_dp": 0,
                    },
                    {
                        "kind": "link_to",
                        "subject_anchor": "top",
                        "target_id": "header",
                        "target_reference": "parent",
                        "target_anchor": "top",
                        "margin_dp": 0,
                    },
                ],
            },
            "panel": {
                "unresolved": [],
                "active_constraints": [
                    {
                        "kind": "center_around",
                        "subject_anchor": "center",
                        "target_id": "cover",
                        "target_reference": "cover",
                        "target_anchor": "bottom",
                        "margin_dp": 0,
                    },
                ],
            },
        }

        cover_lines = renderer.page_snapshot_constraint_alignment_lines(
            renderer.android_page_by_id["cover"]
        )
        panel_lines = renderer.page_snapshot_constraint_alignment_lines(
            renderer.android_page_by_id["panel"]
        )

        self.assertEqual(
            cover_lines,
            [
                ".alignRules({ left: { anchor: '__container__', align: HorizontalAlign.Start }, "
                "right: { anchor: '__container__', align: HorizontalAlign.End }, "
                "top: { anchor: '__container__', align: VerticalAlign.Top } })"
            ],
        )
        self.assertEqual(
            panel_lines,
            [
                ".alignRules({ center: { anchor: 'HeaderCover', align: VerticalAlign.Bottom } })"
            ],
        )
        renderer.android_page_by_id['header']['source'] = {'layoutRules': [{
            'kind': 'sizing', 'axes': ['width', 'height'], 'mode': 'wrap_content',
        }]}
        wrapped_lines = renderer.page_snapshot_constraint_alignment_lines(renderer.android_page_by_id['cover'])
        self.assertEqual(wrapped_lines, [
            ".alignRules({ left: { anchor: '__container__', align: HorizontalAlign.Start }, "
            "right: { anchor: '__container__', align: HorizontalAlign.End } })"
        ])
        self.assertFalse(
            renderer.page_snapshot_requires_position(
                renderer.android_page_by_id["cover"],
                {"x": 0, "y": 0, "width": 377, "height": 216},
                renderer.android_page_by_id["header"],
                "RelativeContainer",
            )
        )

    def test_same_bounds_single_child_wrapper_does_not_use_position(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_layout_mode = "source-tree"
        parent = {
            "id": "wrapper",
            "type": "Box",
            "children_ids": ["content"],
            "bounds_dp": {"x": 24, "y": 120, "width": 329, "height": 120},
        }
        child = {
            "id": "content",
            "type": "Column",
            "parent_id": "wrapper",
            "bounds_dp": {"x": 24, "y": 120, "width": 329, "height": 120},
        }

        self.assertFalse(
            renderer.page_snapshot_requires_position(
                child,
                child["bounds_dp"],
                parent,
                "Stack",
            )
        )

    def test_source_tree_overlay_does_not_turn_measured_frames_into_positions(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_layout_mode = "source-tree"
        parent = {
            "id": "icon-background",
            "type": "Box",
            "children_ids": ["icon"],
            "bounds_dp": {"x": 16, "y": 40, "width": 40, "height": 40},
            "style": {
                "layout": {
                    "alignment": None,
                    "padding_dp": {"left": 8, "top": 8, "right": 8, "bottom": 8},
                }
            },
        }
        child = {
            "id": "icon",
            "type": "Image",
            "parent_id": "icon-background",
            "bounds_dp": {"x": 24, "y": 48, "width": 24, "height": 24},
        }

        self.assertFalse(
            renderer.page_snapshot_requires_position(
                child,
                child["bounds_dp"],
                parent,
                "Stack",
            )
        )

    def test_explicit_box_offset_is_emitted_as_local_translation(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_layout_mode = "source-tree"
        renderer._page_constraint_states = {}
        parent = {
            "id": "cover",
            "type": "BoxWithConstraints",
            "children_ids": ["ring"],
            "source_layout_bounds_dp": {
                "x": 0,
                "y": 0,
                "width": 377.143,
                "height": 136,
            },
            "style": {
                "layout": {"alignment": "TopEnd", "padding_dp": None, "height_dp": 136}
            },
        }
        child = {
            "id": "ring",
            "type": "Image",
            "parent_id": "cover",
            "source_layout_bounds_dp": {
                "x": 211.143,
                "y": -34,
                "width": 200,
                "height": 200,
            },
            "source": {
                "attributes": [],
                "layoutRules": [{
                    "kind": "offset",
                    "x": {
                        "kind": "parent_fraction",
                        "axis": "height",
                        "fraction": 0.25,
                    },
                    "y": {
                        "kind": "parent_fraction",
                        "axis": "height",
                        "fraction": -0.25,
                    },
                    "source_modifier_index": 0,
                }],
            },
        }

        self.assertEqual(
            renderer.page_snapshot_explicit_offset_line(child, parent),
            ".translate({ x: this.pageConstraint0Height * 0.25, y: this.pageConstraint0Height * -0.25 })",
        )

    def test_source_generated_lanhu_carries_constraint_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            payload = json.loads(version_json.read_text(encoding="utf-8"))
            root = payload["artboard"]["layers"][0]
            root["migration"]["componentType"] = "ConstraintLayout"
            self.add_required_facts(root)
            payload["meta"]["sourceGeneration"] = {
                "layoutRelationships": [{
                    "id": "layout-ring",
                    "container_id": "root",
                    "container_type": "ConstraintLayout",
                    "subject_id": "ring",
                    "subject_reference": "ring",
                    "composition": "constraint",
                    "draw_order": 0,
                    "source_expression": "{ end.linkTo(parent.end); top.linkTo(parent.top) }",
                    "branch_resolution": "not_conditional",
                    "active_constraints": [
                        {
                            "kind": "link_to",
                            "subject_anchor": "end",
                            "target_id": "root",
                            "target_reference": "parent",
                            "target_anchor": "end",
                            "margin_expression": None,
                            "margin_dp": 0,
                        },
                        {
                            "kind": "link_to",
                            "subject_anchor": "top",
                            "target_id": "root",
                            "target_reference": "parent",
                            "target_anchor": "top",
                            "margin_expression": None,
                            "margin_dp": 0,
                        },
                    ],
                    "unresolved": [],
                }],
            }
            version_json.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            page = load_lanhu_page_input(version_json)

            self.assertEqual(len(page["layout_relationships"]), 1)
            self.assertEqual(
                page["layout_relationships"][0]["subject_id"],
                "ring",
            )

    def test_target_draw_gate_rejects_parsed_visual_fact_without_emitter(self) -> None:
        component = {
            "id": "avatar",
            "source": {"call_id": "profile:avatar"},
            "required_facts": [
                {
                    "path": "structure.type",
                    "status": "resolved",
                    "origin": "structure",
                    "source_name": "type",
                    "expression": "Image",
                    "reason": "test fact",
                },
                {
                    "path": "style.asset.resource",
                    "status": "resolved",
                    "origin": "semantic_argument",
                    "source_name": "asset",
                    "expression": "R.drawable.avatar",
                    "reason": "test fact",
                },
            ],
        }
        page = {"components": [component]}

        missing = build_target_phase_consumption_gate(
            page,
            {"avatar"},
            {"profile:avatar"},
            {"profile:avatar": {"bounds_dp.width", "bounds_dp.height"}},
        )
        self.assertEqual(missing["verdict"], "fail")
        self.assertIn("style.asset.resource", {item["path"] for item in missing["failures"]})

        consumed = build_target_phase_consumption_gate(
            page,
            {"avatar"},
            {"profile:avatar"},
            {
                "profile:avatar": {
                    "bounds_dp.width",
                    "bounds_dp.height",
                    "style.asset.resource",
                }
            },
            {"avatar": {"structure.type", "style.asset.resource"}},
        )
        self.assertEqual(consumed["verdict"], "pass")

    @staticmethod
    def add_required_facts(layer: dict, status: str = "resolved") -> None:
        layer["migration"]["requiredFacts"] = [{
            "path": "structure.type",
            "status": status,
            "origin": "structure",
            "source_name": "type",
            "expression": layer["migration"]["componentType"],
            "reason": "test fact",
        }]
        for child in layer.get("layers", []):
            GenerateArkUILanhuInputTest.add_required_facts(child, status)

    def write_inputs(self, root: Path, *, wrong_parent: bool = False) -> tuple[Path, Path]:
        version_json = root / "version_json.json"
        component_manifest = root / "component-manifest.json"
        base_lanhu_style = {
            "isEnabled": True,
            "opacity": 1,
            "blendMode": 0,
            "fills": [],
            "borders": [],
            "shadows": [],
            "blurs": [],
        }
        ring_style = empty_style()
        ring_style["asset"] = {
            "resource": "ic_cover_ellipse",
            "sha256": "4" * 64,
            "width_dp": 200,
            "height_dp": 200,
            "content_scale": "fit",
        }
        ring_style["content"] = {"role": "image"}
        root_frame = {"left": 0, "top": 0, "width": 1320.0005, "height": 2674}
        ring_frame = {"left": 739.0005, "top": -119, "width": 700, "height": 700}
        version_json.write_text(
            json.dumps(
                {
                    "meta": {"sliceScale": 3.5, "device": "Android source layout"},
                    "assets": ["ic_cover_ellipse"],
                    "artboard": {
                        "id": "profile--populated",
                        "name": "profile",
                        "type": "artboard",
                        "visible": True,
                        "clipped": True,
                        "opacity": 1,
                        "frame": root_frame,
                        "realFrame": root_frame,
                        "combinedFrame": root_frame,
                        "style": base_lanhu_style,
                        "layers": [
                            {
                                "id": "root",
                                "name": "ProfileRoot",
                                "type": "group",
                                "visible": True,
                                "clipped": False,
                                "isMask": False,
                                "opacity": 1,
                                "rotation": 0,
                                "frame": root_frame,
                                "realFrame": root_frame,
                                "combinedFrame": root_frame,
                                "radius": {
                                    "topLeft": 0,
                                    "topRight": 0,
                                    "bottomRight": 0,
                                    "bottomLeft": 0,
                                },
                                "paths": [],
                                "style": base_lanhu_style,
                                "hasExportImage": False,
                                "hasExportDDSImage": False,
                                "migration": {
                                    "schema": "android-to-harmony.lanhu-node.v1",
                                    "componentType": "Box",
                                    "semanticKey": "ProfileRoot",
                                    "source": {
                                        "attributes": [],
                                        "call_id": "ProfileScreen.kt:1:Box:1",
                                        "composable": "ProfileScreen",
                                        "custom_component": False,
                                        "line": 1,
                                        "source": "ProfileScreen.kt",
                                        "modifiers": [],
                                    },
                                    "style": empty_style(),
                                    "customDraw": None,
                                    "provenance": [],
                                    "unresolved": [],
                                    "geometryStatus": "source_resolved",
                                    "geometryEvidence": [],
                                },
                                "layers": [
                                    {
                                        "id": "ring",
                                        "name": "HeaderRing",
                                        "type": "image",
                                        "visible": True,
                                        "clipped": False,
                                        "isMask": False,
                                        "opacity": 1,
                                        "rotation": 0,
                                        "frame": ring_frame,
                                        "realFrame": ring_frame,
                                        "combinedFrame": ring_frame,
                                        "radius": {
                                            "topLeft": 0,
                                            "topRight": 0,
                                            "bottomRight": 0,
                                            "bottomLeft": 0,
                                        },
                                        "paths": [],
                                        "style": base_lanhu_style,
                                        "hasExportImage": True,
                                        "hasExportDDSImage": False,
                                        "exportImageUrl": "ic_cover_ellipse",
                                        "migration": {
                                            "schema": "android-to-harmony.lanhu-node.v1",
                                            "componentType": "Image",
                                            "semanticKey": "HeaderRing",
                                            "source": {
                                                "call_id": "ScreenHeaderLayout.kt:70:Image:6",
                                                "composable": "ScreenHeader",
                                                "custom_component": False,
                                                "line": 70,
                                                "source": "ScreenHeaderLayout.kt",
                                                "modifiers": [],
                                                "attributes": [
                                                    {
                                                        "call_id": "ScreenHeaderLayout.kt:70:Image:6",
                                                        "line": 70,
                                                        "component": "Image",
                                                        "origin": "semantic_argument",
                                                        "name": "painter",
                                                        "groups": ["asset"],
                                                        "dimensions": [],
                                                        "dimension_resources": [],
                                                    }
                                                ]
                                            },
                                            "style": ring_style,
                                            "customDraw": None,
                                            "provenance": [
                                                {
                                                    "paths": [
                                                        "style.asset.resource",
                                                        "style.asset.sha256",
                                                    ],
                                                    "origin": "source_resolved",
                                                    "source": "ScreenHeaderLayout.kt:70",
                                                }
                                            ],
                                            "unresolved": [],
                                            "geometryStatus": "source_resolved",
                                            "geometryEvidence": [],
                                        },
                                        "layers": [],
                                    }
                                ],
                            }
                        ],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        component_manifest.write_text(
            json.dumps(
                {
                    "schema": "android-to-harmony.lanhu-component-manifest.v1",
                    "page": {"id": "profile", "state": "populated"},
                    "source_schema": "android-to-harmony.source-page-spec.v1",
                    "source_status": "candidate_requires_runtime_verification",
                    "root_instance_id": "root",
                    "source_instance_count": 2,
                    "definitions": [],
                    "instances": [
                        {
                            "id": "root",
                            "type": "Box",
                            "semantic_key": "ProfileRoot",
                            "definition_id": None,
                            "parent_id": None,
                            "children_ids": ["ring"],
                            "sibling_index": 0,
                            "frame_dp": {"x": 0, "y": 0, "width": 10, "height": 10},
                            "resolved_layout": {"padding_dp": {}},
                            "geometry_status": "source_resolved",
                            "geometry_evidence": [],
                            "style": empty_style(),
                            "custom_draw": None,
                            "source": {"attributes": []},
                            "provenance": [],
                            "unresolved": [],
                        },
                        {
                            "id": "ring",
                            "type": "Image",
                            "semantic_key": "HeaderRing",
                            "definition_id": None,
                            "parent_id": None if wrong_parent else "root",
                            "children_ids": [],
                            "sibling_index": 0,
                            "frame_dp": {"x": 1, "y": 1, "width": 10, "height": 10},
                            "resolved_layout": {"padding_dp": {}},
                            "geometry_status": "source_resolved",
                            "geometry_evidence": [],
                            "style": ring_style,
                            "custom_draw": None,
                            "source": {
                                "attributes": [
                                    {
                                        "call_id": "ScreenHeaderLayout.kt:70:Image:6",
                                        "line": 70,
                                        "component": "Image",
                                        "origin": "semantic_argument",
                                        "name": "painter",
                                        "groups": ["asset"],
                                        "dimensions": [],
                                        "dimension_resources": [],
                                    }
                                ]
                            },
                            "provenance": [
                                {
                                    "paths": ["style.asset.resource", "style.asset.sha256"],
                                    "origin": "source_resolved",
                                    "source": "ScreenHeaderLayout.kt:70",
                                }
                            ],
                            "unresolved": [],
                        },
                    ],
                    "layout_relationships": [],
                    "limitations": [],
                    "state_projection": None,
                    "geometry_summary": {"source_resolved": 2},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return version_json, component_manifest

    def test_version_json_frame_is_preserved_as_reference_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, component_manifest = self.write_inputs(Path(directory))

            page = load_lanhu_page_input(version_json)

            self.assertEqual(page["page"], {"id": "profile", "state": "populated"})
            self.assertEqual(page["viewport"]["content_bounds_dp"]["width"], 377.143)
            ring = page["by_id"]["ring"]
            self.assertEqual(
                ring["source_layout_bounds_dp"],
                {"x": 211.143, "y": -34.0, "width": 200.0, "height": 200.0},
            )
            self.assertEqual(
                ring["bounds_dp"],
                {"x": 211.143, "y": 0.0, "width": 166.0, "height": 166.0},
            )
            self.assertEqual(ring["parent_id"], "root")
            self.assertEqual(ring["call_ids"], ["ScreenHeaderLayout.kt:70:Image:6"])
            self.assertEqual(ring["style"]["asset"]["resource"], "ic_cover_ellipse")

            renderer = object.__new__(Renderer)
            bounds, relative_x, relative_y = renderer.page_snapshot_bounds(
                ring,
                page["by_id"]["root"]["source_layout_bounds_dp"],
            )
            self.assertEqual(bounds, ring["source_layout_bounds_dp"])
            self.assertEqual(relative_x, 211.143)
            self.assertEqual(relative_y, -34.0)
            renderer.android_page_layout_mode = "source-tree"
            self.assertFalse(
                renderer.page_snapshot_requires_position(
                    ring,
                    bounds,
                    page["by_id"]["root"],
                    "Stack",
                )
            )

    def test_source_generated_lanhu_requires_component_fact_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            payload = json.loads(version_json.read_text())
            payload["meta"]["sourceGeneration"] = {"layoutRelationships": []}
            version_json.write_text(json.dumps(payload) + "\n")

            with self.assertRaisesRegex(ArkUIPageError, "migration is malformed"):
                load_lanhu_page_input(version_json)

    def test_unresolved_required_fact_keeps_candidate_and_failure_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            payload = json.loads(version_json.read_text())
            payload["meta"]["sourceGeneration"] = {"layoutRelationships": []}
            root = payload["artboard"]["layers"][0]
            self.add_required_facts(root)
            root["layers"][0]["migration"]["requiredFacts"].append({
                "path": "source.arguments.filterquality", "status": "unresolved",
                "origin": "semantic_argument", "source_name": "filterQuality",
                "expression": "FilterQuality.High", "reason": "unsupported filtering mode",
            })
            version_json.write_text(json.dumps(payload) + "\n")

            page = load_lanhu_page_input(version_json)

            self.assertEqual(page["required_fact_gate"]["failure_count"], 1)
            target = (Path(directory) / "target").resolve()
            target.mkdir()
            with (
                patch("generate_arkui_page.normalize_target", return_value=target),
                patch("generate_arkui_page.require_module"),
                patch("generate_arkui_page.load_theme_resources",
                      return_value=({"media:ic_cover_ellipse"}, {})),
            ):
                result = generate(target, "entry", version_json, False)
            output = (target / result["output"]).read_text()
            manifest = json.loads((target / result["manifest"]).read_text())
            self.assertIn("Image($r('app.media.ic_cover_ellipse'))", output)
            self.assertIn(".id('HeaderRing')", output)
            self.assertFalse(result["generation_complete"])
            self.assertEqual(result["verdict"], "fail")
            self.assertEqual(manifest["verdict"], "fail")
            self.assertEqual(manifest["required_fact_gate"]["failure_count"], 1)
            self.assertTrue(any(item.get("page_component_id") == "ring"
                                and item.get("path") == "source.arguments.filterquality"
                                and item.get("expression") == "FilterQuality.High"
                                for item in manifest["unresolved"]))

    def test_upstream_phase_failure_survives_target_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            version_json, _ = self.write_inputs(root)
            payload = json.loads(version_json.read_text())
            failure = {"component_id": "root", "phase": "layout",
                       "relationship_id": "unmapped-anchor", "reason": "unsupported anchor"}
            payload["meta"]["sourceGeneration"] = {"layoutRelationships": [],
                "phaseConsumptionGate": {"verdict": "fail", "failure_count": 1, "failures": [failure]}}
            self.add_required_facts(payload["artboard"]["layers"][0])
            version_json.write_text(json.dumps(payload) + "\n")
            page = load_lanhu_page_input(version_json)
            renderer = Renderer(derive_page_root(page), {"media:ic_cover_ellipse"}, {}, page)
            renderer.render()
            self.assertTrue(any(item.get("relationship_id") == "unmapped-anchor"
                                and item.get("phase") == "layout" for item in renderer.unresolved))

    def test_cli_partial_generation_is_artifact_success_not_completeness_pass(self) -> None:
        partial = {"generation_complete": False, "verdict": "fail", "unresolved_count": 2}
        with (patch("generate_arkui_page.parse_args") as args,
              patch("generate_arkui_page.generate", return_value=partial),
              contextlib.redirect_stdout(io.StringIO()) as output):
            args.return_value.target = Path("target")
            result = main()
        self.assertEqual(result, 0)
        record = json.loads(output.getvalue())
        self.assertTrue(record["ok"])
        self.assertFalse(record["generation_complete"])
        self.assertEqual(record["verdict"], "fail")

    def test_unsupported_constraint_is_recorded_without_position_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _ = self.write_inputs(Path(directory))
            page = load_lanhu_page_input(version_json)
            renderer = Renderer(derive_page_root(page), {"media:ic_cover_ellipse"}, {}, page)
            renderer.android_page_layout_mode = "source-tree"
            renderer.android_source_layout_by_subject["ring"] = {
                "active_constraints": [{"kind": "link_to", "subject_anchor": "baseline",
                    "target_anchor": "baseline", "target_id": "root", "target_reference": "parent",
                    "margin_dp": 0}], "unresolved": [],
            }
            lines = renderer.page_snapshot_constraint_alignment_lines(page["by_id"]["ring"])
            self.assertEqual(lines, [])
            self.assertTrue(any(item.get("page_component_id") == "ring"
                                and "baseline" in item["reason"] for item in renderer.unresolved))

    def test_flow_layout_does_not_reapply_cross_axis_runtime_offset(self) -> None:
        from test_generate_lanhu_source_page import source_component
        from test_layout_mapping_contract import render_nodes
        parent = source_component('row', 'Row', parent_id=None, sibling_index=0, children_ids=['icon', 'label'])
        parent['style']['layout'].update(horizontal_arrangement='Arrangement.spacedBy(16.dp)', alignment='CenterVertically')
        icon = source_component('icon', 'Box', parent_id='row', sibling_index=0, width_dp=40, height_dp=40)
        label = source_component('label', 'Box', parent_id='row', sibling_index=1, width_dp=80, height_dp=20)
        output, gate, _ = render_nodes([parent, icon, label])
        changed, _, _ = render_nodes([parent, icon, label], perturb_reference_frames=True)
        self.assertEqual(output, changed)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('Row({ space: this.layoutPx(16) })', output)
        self.assertNotIn('.margin(', output)
        self.assertFalse(hasattr(Renderer, 'page_snapshot_flow_margin'))

    def test_custom_component_native_button_follows_runtime_container(self) -> None:
        target = {
            "id": "logout-wrapper",
            "source": {"custom_component": True},
        }
        descendant = {
            "id": "logout-button",
            "parent_id": "logout-wrapper",
            "type": "TextButton",
        }

        self.assertTrue(is_direct_native_wrapper(target, descendant))

    def test_business_runtime_overlay_does_not_invent_surface_style(self) -> None:
        self.assertTrue(
            runtime_overlay_style_path_allowed(
                "business_component_id", "style.state.clickable"
            )
        )
        self.assertFalse(
            runtime_overlay_style_path_allowed(
                "business_component_id", "style.surface.background"
            )
        )
        self.assertTrue(
            runtime_overlay_style_path_allowed(
                "semantic_key", "style.surface.background"
            )
        )

    def test_zero_cross_axis_spacer_remains_in_source_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            payload = json.loads(version_json.read_text(encoding="utf-8"))
            payload["artboard"]["layers"][0]["migration"]["componentType"] = "Row"
            spacer = json.loads(
                json.dumps(payload["artboard"]["layers"][0]["layers"][0])
            )
            spacer.update({
                "id": "weighted-spacer",
                "name": "MenuButton_Spacer",
                "type": "group",
                "frame": {"left": 700, "top": 700, "width": 342, "height": 0},
                "realFrame": {"left": 700, "top": 700, "width": 342, "height": 0},
                "combinedFrame": {"left": 700, "top": 700, "width": 342, "height": 0},
                "hasExportImage": False,
                "layers": [],
                "migration": {
                    "schema": "android-to-harmony.lanhu-node.v1",
                    "componentType": "Spacer",
                    "semanticKey": "MenuButton_Spacer",
                    "source": {
                        "attributes": [{
                            "call_id": "Buttons.kt:170:Spacer:7",
                            "line": 170,
                            "component": "Spacer",
                            "origin": "modifier",
                            "name": "weight",
                            "groups": ["geometry"],
                            "dimensions": [],
                            "dimension_resources": [],
                        }]
                    },
                    "style": empty_style(),
                    "customDraw": None,
                    "provenance": [],
                    "unresolved": [],
                    "geometryStatus": "source_resolved",
                    "geometryEvidence": [],
                },
            })
            spacer.pop("exportImageUrl", None)
            payload["artboard"]["layers"][0]["layers"].append(spacer)
            version_json.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            page = load_lanhu_page_input(version_json)

            self.assertIn("weighted-spacer", page["by_id"])
            self.assertEqual(page["by_id"]["weighted-spacer"]["type"], "Spacer")
            self.assertEqual(page["by_id"]["weighted-spacer"]["bounds_dp"]["height"], 0)

    def test_zero_cross_axis_column_spacer_remains_in_source_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            payload = json.loads(version_json.read_text(encoding="utf-8"))
            payload["artboard"]["layers"][0]["migration"]["componentType"] = "Column"
            spacer = json.loads(
                json.dumps(payload["artboard"]["layers"][0]["layers"][0])
            )
            spacer.update({
                "id": "weighted-column-spacer",
                "name": "ProfileScreen_Spacer",
                "type": "group",
                "frame": {"left": 0, "top": 1200, "width": 0, "height": 588},
                "realFrame": {"left": 0, "top": 1200, "width": 0, "height": 588},
                "combinedFrame": {"left": 0, "top": 1200, "width": 0, "height": 588},
                "hasExportImage": False,
                "layers": [],
                "migration": {
                    "schema": "android-to-harmony.lanhu-node.v1",
                    "componentType": "Spacer",
                    "semanticKey": "ProfileScreen_Spacer",
                    "source": {
                        "attributes": [{
                            "call_id": "ProfileScreen.kt:262:Spacer:9",
                            "line": 262,
                            "component": "Spacer",
                            "origin": "modifier",
                            "name": "weight",
                            "groups": ["geometry"],
                            "dimensions": [],
                            "dimension_resources": [],
                        }],
                        "layoutRules": [{
                            "kind": "weight",
                            "value": 1.0,
                            "fill": True,
                            "source_modifier_index": 0,
                        }],
                    },
                    "style": empty_style(),
                    "customDraw": None,
                    "provenance": [],
                    "unresolved": [],
                    "geometryStatus": "source_resolved",
                    "geometryEvidence": [],
                },
            })
            spacer.pop("exportImageUrl", None)
            payload["artboard"]["layers"][0]["layers"].append(spacer)
            version_json.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            page = load_lanhu_page_input(version_json)

            self.assertIn("weighted-column-spacer", page["by_id"])
            self.assertEqual(page["by_id"]["weighted-column-spacer"]["type"], "Spacer")
            self.assertEqual(page["by_id"]["weighted-column-spacer"]["bounds_dp"]["width"], 0)

    def test_page_snapshot_root_remeasures_without_global_scale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            page = load_lanhu_page_input(version_json)
            renderer = Renderer(
                derive_page_root(page),
                {"media:ic_cover_ellipse"},
                {},
                page,
            )

            source = renderer.render()

            self.assertNotIn("pageSnapshotScale", source)
            self.assertNotIn("pageSnapshotOffsetX", source)
            self.assertNotIn(".scale({", source)
            self.assertNotIn(".onAreaChange(", source)

    def test_root_fills_host_but_matching_child_frame_does_not_imply_fill(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_input = {
            "viewport": {
                "content_bounds_dp": {"x": 0, "y": 0, "width": 377.143, "height": 764}
            }
        }
        parent = {
            "id": "panel",
            "type": "Box",
            "parent_id": "root",
            "children_ids": ["content"],
            "bounds_dp": {"x": 0, "y": 96, "width": 377.143, "height": 80},
            "source_layout_bounds_dp": {"x": 0, "y": 96, "width": 377.143, "height": 80},
            "source": {"attributes": [], "layoutRules": []},
            "style": {
                "layout": {
                    "width_dp": None,
                    "height_dp": None,
                    "padding_dp": {"left": 24.0, "right": 24.0, "top": 0.0, "bottom": 0.0},
                },
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        content = {
            "id": "content",
            "type": "ProfileCard",
            "parent_id": "panel",
            "children_ids": [],
            "bounds_dp": {"x": 24, "y": 96, "width": 329.143, "height": 80},
            "source_layout_bounds_dp": {"x": 24, "y": 96, "width": 329.143, "height": 80},
            "source": {"attributes": [], "layoutRules": []},
            "style": {
                "layout": {"width_dp": None, "height_dp": None},
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        root = {
            "id": "root",
            "type": "Column",
            "parent_id": None,
            "children_ids": ["panel"],
            "bounds_dp": {"x": 0, "y": 0, "width": 377.143, "height": 764},
            "source": {"attributes": [], "layoutRules": []},
            "style": {
                "layout": {"width_dp": None, "height_dp": None},
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        renderer.android_page_by_id = {
            "root": root,
            "panel": parent,
            "content": content,
        }

        self.assertEqual(
            renderer.page_snapshot_dimension_lines(
                root,
                root["bounds_dp"],
                None,
                None,
                False,
            ),
            [".width('100%')", ".height('100%')"],
        )
        self.assertEqual(
            renderer.page_snapshot_dimension_lines(
                content,
                content["bounds_dp"],
                parent,
                "Stack",
                False,
            ),
            [],
        )

    def test_structural_spacer_weight_is_read_from_lanhu_migration_source(self) -> None:
        component = {
            "source": {
                "modifiers": [
                    {"name": "weight", "arguments": "1f", "dimensions": []}
                ]
            }
        }

        self.assertEqual(
            Renderer.page_snapshot_source_layout_weight(component),
            ".layoutWeight(1)",
        )

    def test_normalized_layout_weight_is_read_without_source_modifier_fallback(self) -> None:
        component = {
            "source": {
                "attributes": [],
                "layoutRules": [{
                    "kind": "weight",
                    "value": 2.5,
                    "fill": True,
                    "source_modifier_index": 0,
                }],
            }
        }

        self.assertEqual(
            Renderer.page_snapshot_source_layout_weight(component),
            ".layoutWeight(2.5)",
        )

    def test_normalized_sizing_rules_control_generated_dimensions(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_by_id = {}
        component = {
            "id": "content",
            "type": "Column",
            "children_ids": [],
            "source": {
                "attributes": [],
                "layoutRules": [
                    {
                        "kind": "sizing",
                        "axes": ["width"],
                        "mode": "fill_parent",
                        "fraction": 1.0,
                        "source_modifier_index": 0,
                    },
                    {
                        "kind": "sizing",
                        "axes": ["height"],
                        "mode": "wrap_content",
                        "source_modifier_index": 1,
                    },
                ],
            },
            "style": {
                "layout": {"width_dp": None, "height_dp": None},
                "asset": {"width_dp": None, "height_dp": None},
            },
        }

        self.assertEqual(
            renderer.page_snapshot_dimension_lines(
                component,
                {"width": 320.0, "height": 240.0},
                None,
                None,
                False,
            ),
            [".width('100%')"],
        )

    def test_wrap_content_parent_allows_single_child_to_measure_intrinsically(self) -> None:
        renderer = object.__new__(Renderer)
        parent = {
            "id": "text-btn",
            "children_ids": ["button"],
            "source": {
                "attributes": [],
                "layoutRules": [{
                    "kind": "sizing",
                    "axes": ["width", "height"],
                    "mode": "wrap_content",
                    "source_modifier_index": 0,
                }],
            },
        }
        component = {
            "id": "button",
            "type": "TextButton",
            "children_ids": ["label"],
            "source": {"attributes": [], "layoutRules": []},
            "style": {
                "layout": {"width_dp": None, "height_dp": None},
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        renderer.android_page_by_id = {"text-btn": parent, "button": component}

        self.assertEqual(
            renderer.page_snapshot_dimension_lines(
                component,
                {"width": 69.9, "height": 48.0},
                parent,
                "Stack",
                False,
            ),
            [],
        )

    def test_material_text_button_keeps_intrinsic_label_and_minimum_height(self) -> None:
        renderer = object.__new__(Renderer)
        parent = {
            "id": "button",
            "type": "TextButton",
            "children_ids": ["label"],
            "source": {
                "custom_component": False,
                "attributes": [],
                "layoutRules": [{
                    "kind": "sizing",
                    "axes": ["height"],
                    "mode": "wrap_content",
                    "source_modifier_index": 0,
                }],
            },
            "bounds_dp": {"x": 0, "y": 0, "width": 70, "height": 48},
            "source_layout_bounds_dp": {"x": 0, "y": 0, "width": 70, "height": 48},
            "style": {
                "layout": {
                    "width_dp": None,
                    "height_dp": None,
                    "padding_dp": {"left": 16, "right": 16, "top": 0, "bottom": 0},
                },
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        label = {
            "id": "label",
            "type": "Text",
            "parent_id": "button",
            "children_ids": [],
            "source": {"attributes": [], "layoutRules": []},
            "bounds_dp": {"x": 16, "y": 14, "width": 38, "height": 20},
            "source_layout_bounds_dp": {"x": 16, "y": 14, "width": 38, "height": 20},
            "style": {
                "layout": {"width_dp": None, "height_dp": None},
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        renderer.android_page_by_id = {"button": parent, "label": label}

        self.assertFalse(renderer.page_snapshot_fills_parent_inner_axis(label, parent, "width"))
        self.assertEqual(
            renderer.page_snapshot_minimum_constraint_line(parent, parent["bounds_dp"]),
            ".constraintSize({ minHeight: this.layoutPx(48) })",
        )

    def test_project_component_internal_root_wraps_even_when_reference_frames_match(self) -> None:
        renderer = object.__new__(Renderer)
        parent = {
            "id": "header",
            "type": "ScreenHeader",
            "children_ids": ["layout"],
            "source": {"custom_component": True, "attributes": [], "layoutRules": []},
            "bounds_dp": {"x": 0, "y": 0, "width": 379.31, "height": 176},
            "source_layout_bounds_dp": {"x": 0, "y": 0, "width": 379.31, "height": 176},
            "style": {
                "layout": {"width_dp": None, "height_dp": None, "padding_dp": None},
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        child = {
            "id": "layout",
            "type": "ConstraintLayout",
            "parent_id": "header",
            "children_ids": [],
            "source": {
                "custom_component": False,
                "attributes": [],
                "layoutRules": [{
                    "kind": "sizing",
                    "axes": ["width", "height"],
                    "mode": "wrap_content",
                    "source_modifier_index": 0,
                }],
            },
            "bounds_dp": {"x": 0, "y": 0, "width": 379.31, "height": 176},
            "source_layout_bounds_dp": {"x": 0, "y": 0, "width": 379.31, "height": 176},
            "style": {
                "layout": {"width_dp": None, "height_dp": None, "padding_dp": None},
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        renderer.android_page_by_id = {"header": parent, "layout": child}

        self.assertEqual(
            renderer.page_snapshot_dimension_lines(
                child,
                child["bounds_dp"],
                parent,
                "Stack",
                False,
            ),
            [".width('auto')", ".height('auto')"],
        )

        parent["source"]["layoutRules"] = [{
            "kind": "sizing",
            "axes": ["height"],
            "mode": "wrap_content",
            "source_modifier_index": 0,
        }]
        self.assertEqual(
            renderer.page_snapshot_dimension_lines(
                child,
                child["bounds_dp"],
                parent,
                "Stack",
                False,
            ),
            [".width('auto')", ".height('auto')"],
        )

    def test_compose_box_default_alignment_and_flow_shrink_are_preserved(self) -> None:
        renderer = object.__new__(Renderer)
        box = {
            "id": "surface",
            "type": "Box",
            "children_ids": ["content"],
            "source": {"attributes": [], "layoutRules": []},
            "style": {"layout": {"alignment": None}},
        }
        fixed_child = {
            "id": "header",
            "type": "ScreenHeader",
            "source": {"attributes": [], "layoutRules": []},
        }
        weighted_child = {
            "id": "space",
            "type": "Spacer",
            "source": {
                "attributes": [],
                "layoutRules": [{
                    "kind": "weight",
                    "value": 1.0,
                    "fill": True,
                    "source_modifier_index": 0,
                }],
            },
        }

        self.assertEqual(
            renderer.page_snapshot_container_alignment_lines(box),
            [".alignContent(Alignment.TopStart)"],
        )
        column = {
            "id": "labels",
            "type": "Column",
            "children_ids": [],
            "style": {"layout": {"alignment": None, "vertical_arrangement": None}},
        }
        row = {
            "id": "actions",
            "type": "Row",
            "children_ids": [],
            "style": {"layout": {"alignment": None, "horizontal_arrangement": None}},
        }
        self.assertEqual(
            renderer.page_snapshot_container_alignment_lines(column),
            [".alignItems(HorizontalAlign.Start)"],
        )
        self.assertEqual(
            renderer.page_snapshot_container_alignment_lines(row),
            [".alignItems(VerticalAlign.Top)"],
        )
        self.assertEqual(
            renderer.page_snapshot_flow_shrink_line(fixed_child, "Column"),
            ".flexShrink(0)",
        )
        self.assertIsNone(
            renderer.page_snapshot_flow_shrink_line(weighted_child, "Column")
        )

    def test_fill_parent_child_stretches_inside_intrinsic_parent_axis(self) -> None:
        renderer = object.__new__(Renderer)
        parent = {
            "id": "actions",
            "children_ids": ["action"],
            "source": {
                "attributes": [],
                "layoutRules": [{
                    "kind": "intrinsic_size",
                    "axis": "height",
                    "mode": "max",
                    "source_modifier_index": 0,
                }],
            },
        }
        component = {
            "id": "action",
            "type": "MenuButton",
            "children_ids": [],
            "source": {
                "attributes": [],
                "layoutRules": [{
                    "kind": "sizing",
                    "axes": ["height"],
                    "mode": "fill_parent",
                    "fraction": 1.0,
                    "source_modifier_index": 0,
                }],
            },
            "style": {
                "layout": {"width_dp": None, "height_dp": None},
                "asset": {"width_dp": None, "height_dp": None},
            },
        }
        renderer.android_page_by_id = {"actions": parent, "action": component}

        self.assertEqual(
            renderer.page_snapshot_dimension_lines(
                component,
                {"width": 141.9, "height": 72.0},
                parent,
                "Row",
                False,
            ),
            [".alignSelf(ItemAlign.Stretch)"],
        )

    def test_forwarded_parent_color_is_consumed_only_when_descendant_draws_same_value(self) -> None:
        renderer = object.__new__(Renderer)
        parent = {
            "id": "text-btn",
            "children_ids": ["label"],
            "style": {"typography": {"color": "#FFFF552F"}},
        }
        child = {
            "id": "label",
            "children_ids": [],
            "style": {"typography": {"color": "#FFFF552F"}},
        }
        renderer.android_page_by_id = {"text-btn": parent, "label": child}
        renderer.android_page_applied_component_paths = {
            "label": {"style.typography.color"}
        }

        self.assertTrue(
            renderer.page_snapshot_descendant_consumes_typography_color(
                parent, "#FFFF552F"
            )
        )
        child["style"]["typography"]["color"] = "#FF000000"
        self.assertFalse(
            renderer.page_snapshot_descendant_consumes_typography_color(
                parent, "#FFFF552F"
            )
        )

    def test_malformed_normalized_layout_rule_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            payload = json.loads(version_json.read_text(encoding="utf-8"))
            payload["artboard"]["layers"][0]["migration"]["source"]["layoutRules"] = [{
                "kind": "sizing",
                "axes": ["depth"],
                "mode": "fill_parent",
                "fraction": 1.0,
                "source_modifier_index": 0,
            }]
            version_json.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ArkUIPageError, "layoutRules"):
                load_lanhu_page_input(version_json)

    def test_single_button_child_uses_parent_center_instead_of_absolute_position(self) -> None:
        renderer = object.__new__(Renderer)
        renderer.android_page_layout_mode = "source-tree"
        renderer.android_page_by_id = {
            "button": {
                "id": "button",
                "children_ids": ["label"],
            },
            "label": {
                "id": "label",
                "type": "Text",
                "parent_id": "button",
                "children_ids": [],
                "call_ids": [],
                "semantic_key": "label",
                "bounds_dp": {"x": 16, "y": 10, "width": 50, "height": 20},
                "source_layout_bounds_dp": {"x": 16, "y": 10, "width": 50, "height": 20},
                "style": {
                    "layout": {"padding_dp": None},
                    "surface": {"background": None, "border": None, "corner_radius_dp": None, "shadows": None},
                    "typography": {
                        "font_family": None, "font_size_sp": 14, "font_weight": 600,
                        "color": "#FF000000", "line_height_sp": 20,
                        "letter_spacing_sp": None, "text_align": None, "max_lines": 1,
                        "overflow": None, "decoration": None,
                    },
                    "asset": {"tint": None},
                    "content": {"text": "Log out"},
                    "state": {},
                    "transform": {},
                },
            },
        }
        renderer.selected_calls_by_id = {}
        renderer.tinted_vector_resources = {}
        renderer.resource_names = set()
        renderer.verified_font_faces = []
        renderer._page_constraint_states = {}

        lines = renderer.page_snapshot_component_lines(
            renderer.android_page_by_id["label"],
            {"x": 0, "y": 0, "width": 82, "height": 48},
            "TextButton",
            0,
        )

        self.assertIn("  .align(Alignment.Center)", lines)
        self.assertFalse(any(".position(" in line for line in lines))

    def test_version_json_and_manifest_hierarchy_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, component_manifest = self.write_inputs(
                Path(directory), wrong_parent=True
            )

            with self.assertRaisesRegex(ArkUIPageError, "hierarchy mismatch"):
                load_lanhu_page_input(version_json, component_manifest)

    def test_missing_required_lanhu_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_json, _component_manifest = self.write_inputs(Path(directory))
            payload = json.loads(version_json.read_text(encoding="utf-8"))
            del payload["artboard"]["layers"][0]["layers"][0]["combinedFrame"]
            version_json.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ArkUIPageError, "combinedFrame"):
                load_lanhu_page_input(version_json)


if __name__ == "__main__":
    unittest.main()
