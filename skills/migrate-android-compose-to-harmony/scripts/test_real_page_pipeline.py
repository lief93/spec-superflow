from __future__ import annotations

import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

from real_page_pipeline import (
    RealPageError,
    apply_screenshot_visual_facts,
    build_runtime_page_snapshot,
    build_source_page_spec,
    parse_harmony_layout_json,
    parse_uiautomator_xml,
    semantic_runtime_component,
)
from generate_real_android_page_json import android_capture_commands, device_insets
from generate_real_harmony_page_json import harmony_capture_commands


ROOT_SOURCE = "app/src/main/java/example/Login.kt"


def fixture_contract() -> dict:
    calls = [
        {
            "source": ROOT_SOURCE,
            "composable": "LoginScreen",
            "line": 10,
            "component": "Column",
            "call_id": f"{ROOT_SOURCE}:10:Column:1",
            "parent_call_id": None,
            "semantic_arguments": {},
            "positional_arguments": [],
            "ordered_modifier_chain": [
                {
                    "name": "padding",
                    "arguments": "16.dp",
                    "dimensions": [{"value": "16", "unit": "dp"}],
                    "dimension_resources": [],
                }
            ],
            "state_slots": [],
            "trailing_lambda_parameters": [],
        },
        {
            "source": ROOT_SOURCE,
            "composable": "LoginScreen",
            "line": 12,
            "component": "Text",
            "call_id": f"{ROOT_SOURCE}:12:Text:2",
            "parent_call_id": f"{ROOT_SOURCE}:10:Column:1",
            "semantic_arguments": {
                "text": {
                    "expression": "stringResource(R.string.login_title)",
                    "dimensions": [],
                    "dimension_resources": [],
                }
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
            "state_slots": [],
            "trailing_lambda_parameters": [],
        },
        {
            "source": ROOT_SOURCE,
            "composable": "LoginScreen",
            "line": 13,
            "component": "Image",
            "call_id": f"{ROOT_SOURCE}:13:Image:3",
            "parent_call_id": f"{ROOT_SOURCE}:10:Column:1",
            "semantic_arguments": {
                "painter": {
                    "expression": "painterResource(R.drawable.login_cover)",
                    "dimensions": [],
                    "dimension_resources": [],
                },
                "contentDescription": {
                    "expression": '"Cover"',
                    "dimensions": [],
                    "dimension_resources": [],
                },
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [
                {
                    "name": "size",
                    "arguments": "72.dp",
                    "dimensions": [{"value": "72", "unit": "dp"}],
                    "dimension_resources": [],
                }
            ],
            "state_slots": [],
            "trailing_lambda_parameters": [],
        },
        {
            "source": ROOT_SOURCE,
            "composable": "LoginScreen",
            "line": 16,
            "component": "Button",
            "call_id": f"{ROOT_SOURCE}:16:Button:4",
            "parent_call_id": f"{ROOT_SOURCE}:10:Column:1",
            "semantic_arguments": {
                "onClick": {
                    "expression": "onSubmit",
                    "dimensions": [],
                    "dimension_resources": [],
                }
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
            "state_slots": [],
            "trailing_lambda_parameters": [],
        },
        {
            "source": ROOT_SOURCE,
            "composable": "LoginScreen",
            "line": 17,
            "component": "Text",
            "call_id": f"{ROOT_SOURCE}:17:Text:5",
            "parent_call_id": f"{ROOT_SOURCE}:16:Button:4",
            "semantic_arguments": {},
            "positional_arguments": [
                {
                    "expression": "stringResource(R.string.sign_in)",
                    "dimensions": [],
                    "dimension_resources": [],
                }
            ],
            "ordered_modifier_chain": [],
            "state_slots": [],
            "trailing_lambda_parameters": [],
        },
    ]
    return {
        "ui": {
            "semantic_translation_candidates": {"calls": calls},
            "custom_composable_call_graph": {
                "transitive_closures": [
                    {
                        "root": {"source": ROOT_SOURCE, "composable": "LoginScreen"},
                        "reached_definitions": [
                            {"source": ROOT_SOURCE, "composable": "LoginScreen"}
                        ],
                        "cycle_edges": [],
                    }
                ]
            },
            "composables": [
                {"source": ROOT_SOURCE, "name": "LoginScreen", "parameters": []}
            ],
            "android_value_resource_inventory": {
                "resources": [
                    {
                        "source": "app/src/main/res/values/strings.xml",
                        "qualifier": "values",
                        "type": "string",
                        "name": "login_title",
                        "value": "Welcome",
                        "attributes": {},
                        "items": [],
                    },
                    {
                        "source": "app/src/main/res/values/strings.xml",
                        "qualifier": "values",
                        "type": "string",
                        "name": "sign_in",
                        "value": "Sign in",
                        "attributes": {},
                        "items": [],
                    },
                ]
            },
        }
    }


UI_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[0,0][1080,2400]">
    <node index="0" text="" resource-id="" class="android.view.View" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[0,72][1080,2304]">
      <node index="0" text="Welcome" resource-id="" class="android.widget.TextView" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[96,240][600,330]" />
      <node index="1" text="" resource-id="example:id/LoginScreen_Image_13_3" class="android.widget.ImageView" package="example" content-desc="Cover" clickable="false" enabled="true" checked="false" selected="false" bounds="[96,360][312,576]" />
      <node index="2" text="" resource-id="" class="android.view.View" package="example" content-desc="" clickable="true" enabled="true" checked="false" selected="false" bounds="[96,630][984,780]">
        <node index="0" text="Sign in" resource-id="" class="android.widget.TextView" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[420,666][660,744]" />
      </node>
    </node>
  </node>
</hierarchy>
"""


HARMONY_LAYOUT = {
    "attributes": {"bounds": "[0,0][1080,2400]", "type": ""},
    "children": [
        {
            "attributes": {
                "bounds": "[0,0][1080,2400]",
                "type": "root",
                "visible": "true",
                "enabled": "true",
                "pagePath": "pages/Index",
                "bundleName": "example.harmony",
            },
            "children": [
                {
                    "attributes": {
                        "bounds": "[0,72][1080,2304]",
                        "type": "Column",
                        "id": "LoginScreen_Column_10_1",
                        "key": "LoginScreen_Column_10_1",
                        "visible": "true",
                        "enabled": "true",
                        "backgroundColor": "#FFFFFFFF",
                    },
                    "children": [
                        {
                            "attributes": {
                                "bounds": "[96,240][600,330]",
                                "type": "Text",
                                "id": "LoginScreen_Text_12_2",
                                "key": "LoginScreen_Text_12_2",
                                "text": "Welcome",
                                "originalText": "Welcome",
                                "visible": "true",
                                "enabled": "true",
                                "backgroundColor": "#00000000",
                            },
                            "children": [],
                        },
                        {
                            "attributes": {
                                "bounds": "[96,360][312,576]",
                                "type": "Image",
                                "id": "LoginScreen_Image_13_3",
                                "key": "LoginScreen_Image_13_3",
                                "description": "Cover",
                                "visible": "true",
                                "enabled": "true",
                                "backgroundColor": "#00000000",
                            },
                            "children": [],
                        },
                        {
                            "attributes": {
                                "bounds": "[96,630][984,780]",
                                "type": "Button",
                                "id": "LoginScreen_Button_16_4",
                                "key": "LoginScreen_Button_16_4",
                                "clickable": "false",
                                "visible": "true",
                                "enabled": "true",
                                "backgroundColor": "#FF6650A4",
                                "opacity": "1.000000",
                                "clip": "false",
                                "zIndex": "0",
                            },
                            "children": [
                                {
                                    "attributes": {
                                        "bounds": "[420,666][660,744]",
                                        "type": "Text",
                                        "id": "LoginScreen_Text_17_5",
                                        "key": "LoginScreen_Text_17_5",
                                        "text": "Sign in",
                                        "originalText": "Sign in",
                                        "visible": "true",
                                        "enabled": "true",
                                        "backgroundColor": "#00000000",
                                    },
                                    "children": [],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
    ],
}


class RealPagePipelineTest(unittest.TestCase):
    def test_harmony_capture_removes_stale_remote_artifacts_before_capture(self) -> None:
        commands = harmony_capture_commands(
            "hdc",
            "127.0.0.1:5555",
            "/data/local/tmp/screen.png",
            "/data/local/tmp/layout.json",
            Path("screen.png"),
            Path("layout.json"),
        )

        self.assertEqual(commands[0], [
            "hdc", "-t", "127.0.0.1:5555", "shell", "rm", "-f",
            "/data/local/tmp/screen.png", "/data/local/tmp/layout.json",
        ])
        self.assertEqual(commands[1][-3:], ["dumpLayout", "-p", "/data/local/tmp/layout.json"])
        self.assertEqual(commands[2][-3:], ["screenCap", "-p", "/data/local/tmp/screen.png"])
        self.assertEqual(commands[3][-3:], ["recv", "/data/local/tmp/screen.png", "screen.png"])
        self.assertEqual(commands[4][-3:], ["recv", "/data/local/tmp/layout.json", "layout.json"])

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is not installed")
    def test_button_pixel_facts_do_not_depend_on_runtime_clickable_flag(self) -> None:
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as temporary:
            screenshot = Path(temporary) / "button.png"
            image = Image.new("RGB", (100, 60), (254, 247, 255))
            ImageDraw.Draw(image).rounded_rectangle(
                (0, 0, 99, 59),
                radius=20,
                fill=(102, 80, 164),
            )
            image.save(screenshot)
            style = {
                "layout": {},
                "surface": {"background": None, "corner_radius_dp": None},
                "typography": {},
                "asset": {},
                "transform": {},
                "state": {"clickable": False},
                "content": {},
            }
            components = [{
                "id": "runtime-button",
                "type": "Button",
                "bounds_px": {"x": 0, "y": 0, "width": 100, "height": 60},
                "style": style,
            }]

            result = apply_screenshot_visual_facts(screenshot, components, 1.0, 1.0)

            self.assertEqual(result["sampled_component_count"], 1)
            self.assertEqual(
                components[0]["style"]["surface"]["background"],
                {"type": "solid", "color": "#FF6650A4"},
            )
            self.assertEqual(
                components[0]["style"]["surface"]["corner_radius_dp"],
                {
                    "top_left": 16.0,
                    "top_right": 16.0,
                    "bottom_right": 16.0,
                    "bottom_left": 16.0,
                },
            )

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is not installed")
    def test_clickable_layout_pixel_facts_include_rendered_corner_radius(self) -> None:
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as temporary:
            screenshot = Path(temporary) / "clickable-layout.png"
            image = Image.new("RGB", (100, 60), (254, 247, 255))
            ImageDraw.Draw(image).rounded_rectangle((0, 0, 99, 59), radius=20, fill=(102, 80, 164))
            image.save(screenshot)
            components = [{
                "id": "runtime-clickable-stack",
                "type": "Stack",
                "bounds_px": {"x": 0, "y": 0, "width": 100, "height": 60},
                "style": {
                    "layout": {},
                    "surface": {"background": None, "corner_radius_dp": None},
                    "typography": {},
                    "asset": {},
                    "transform": {},
                    "state": {"clickable": True},
                    "content": {},
                },
            }]

            apply_screenshot_visual_facts(screenshot, components, 1.0, 1.0)

            self.assertEqual(
                components[0]["style"]["surface"]["corner_radius_dp"],
                {
                    "top_left": 16.0,
                    "top_right": 16.0,
                    "bottom_right": 16.0,
                    "bottom_left": 16.0,
                },
            )

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is not installed")
    def test_layout_surface_color_is_sampled_from_rendered_page(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            screenshot = Path(temporary) / "surface.png"
            Image.new("RGB", (100, 60), (254, 247, 255)).save(screenshot)
            components = [{
                "id": "runtime-surface",
                "type": "Stack",
                "bounds_px": {"x": 0, "y": 0, "width": 100, "height": 60},
                "style": {
                    "layout": {},
                    "surface": {"background": None, "corner_radius_dp": None},
                    "typography": {},
                    "asset": {},
                    "transform": {},
                    "state": {"clickable": False},
                    "content": {},
                },
            }]

            result = apply_screenshot_visual_facts(screenshot, components, 1.0, 1.0)

            self.assertEqual(result["sampled_component_count"], 1)
            self.assertEqual(
                components[0]["style"]["surface"]["background"],
                {"type": "solid", "color": "#FFFEF7FF"},
            )

    def test_device_insets_uses_visible_status_and_navigation_bar_frames(self) -> None:
        import generate_real_android_page_json as command

        original = command.run
        command.run = lambda _arguments: """
          InsetsSource type=ITYPE_STATUS_BAR frame=[0,0][1080,72] visible=true
          InsetsSource type=ITYPE_NAVIGATION_BAR frame=[0,2304][1080,2400] visible=true
        """
        try:
            self.assertEqual(
                device_insets("adb", "device", (1080, 2400)),
                {"left": 0, "top": 72, "right": 0, "bottom": 96},
            )
        finally:
            command.run = original

    def test_android_capture_removes_stale_layout_before_dump_and_screenshot(self) -> None:
        commands = android_capture_commands(
            "adb", "emulator-5554", "/sdcard/android-to-harmony-window.xml"
        )

        self.assertEqual(
            commands[0],
            [
                "adb", "-s", "emulator-5554", "shell", "rm", "-f",
                "/sdcard/android-to-harmony-window.xml",
            ],
        )
        self.assertEqual(
            commands[1][-3:],
            ["uiautomator", "dump", "/sdcard/android-to-harmony-window.xml"],
        )
        self.assertEqual(commands[2][-3:], ["exec-out", "screencap", "-p"])
        self.assertEqual(
            commands[3][-3:],
            ["exec-out", "cat", "/sdcard/android-to-harmony-window.xml"],
        )

    def test_source_page_spec_emits_every_call_with_hierarchy_and_resolved_facts(self) -> None:
        payload = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )

        self.assertEqual(payload["schema"], "android-to-harmony.source-page-spec.v1")
        self.assertEqual(payload["coverage"]["source_call_count"], 5)
        self.assertEqual(payload["coverage"]["emitted_call_count"], 5)
        self.assertEqual(payload["coverage"]["emitted_call_ratio"], 1.0)
        self.assertEqual(payload["coverage"]["expanded_instance_count"], 5)
        self.assertEqual(len(payload["components"]), 5)
        title = next(item for item in payload["components"] if item["source"]["line"] == 12)
        image = next(item for item in payload["components"] if item["source"]["line"] == 13)
        button = next(item for item in payload["components"] if item["source"]["line"] == 16)
        button_text = next(item for item in payload["components"] if item["source"]["line"] == 17)
        self.assertEqual(title["style"]["content"]["text"], "Welcome")
        self.assertEqual(image["style"]["asset"]["resource"], "login_cover")
        self.assertEqual(image["style"]["asset"]["width_dp"], 72.0)
        self.assertEqual(image["style"]["asset"]["height_dp"], 72.0)
        self.assertIs(button["style"]["surface"]["clip"], True)
        self.assertEqual(button_text["parent_id"], button["id"])
        self.assertEqual(button["children_ids"], [button_text["id"]])
        self.assertEqual([item["sibling_index"] for item in payload["components"] if item["parent_id"] == title["parent_id"]], [0, 1, 2])
        self.assertEqual(title["semantic_key"], "LoginScreen_Text_12_2")

    def test_explicit_null_content_description_is_resolved_absence(self) -> None:
        contract = fixture_contract()
        image_call = contract["ui"]["semantic_translation_candidates"]["calls"][2]
        image_call["semantic_arguments"]["contentDescription"]["expression"] = "null"

        payload = build_source_page_spec(
            contract, ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )

        image = next(item for item in payload["components"] if item["source"]["line"] == 13)
        self.assertIsNone(image["style"]["content"]["content_description"])
        self.assertFalse(
            any(item["path"] == "style.content.content_description" for item in image["unresolved"])
        )

    def test_empty_non_clickable_button_wrapper_is_not_a_semantic_control(self) -> None:
        component = parse_uiautomator_xml(
            b'''<hierarchy rotation="0"><node index="0" text="" resource-id="" class="android.widget.Button" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[0,0][100,100]" /></hierarchy>''',
            (100, 100),
            "example",
        )[0]

        self.assertFalse(semantic_runtime_component(component))

    def test_uiautomator_parser_preserves_runtime_parent_and_sibling_order(self) -> None:
        components = parse_uiautomator_xml(UI_XML.encode("utf-8"), (1080, 2400), "example")

        self.assertEqual(len(components), 6)
        sign_in = next(item for item in components if item["style"]["content"]["text"] == "Sign in")
        button = next(item for item in components if item["style"]["state"]["clickable"])
        self.assertEqual(sign_in["parent_id"], button["id"])
        self.assertEqual(sign_in["sibling_index"], 0)
        self.assertEqual(button["children_ids"], [sign_in["id"]])
        self.assertEqual(button["bounds_px"], {"x": 96, "y": 630, "width": 888, "height": 150})

    def test_harmony_parser_preserves_complete_runtime_tree_and_rendered_attributes(self) -> None:
        components = parse_harmony_layout_json(
            json.dumps(HARMONY_LAYOUT).encode("utf-8"), (1080, 2400)
        )

        self.assertEqual(len(components), 6)
        title = next(item for item in components if item["runtime_id"] == "LoginScreen_Text_12_2")
        button = next(item for item in components if item["runtime_id"] == "LoginScreen_Button_16_4")
        sign_in = next(item for item in components if item["runtime_id"] == "LoginScreen_Text_17_5")
        self.assertEqual(title["style"]["content"]["text"], "Welcome")
        self.assertEqual(button["style"]["surface"]["background"], {"type": "solid", "color": "#FF6650A4"})
        self.assertTrue(button["style"]["state"]["clickable"])
        self.assertIsNone(button["style"]["surface"]["alpha"])
        self.assertIsNone(button["style"]["surface"]["clip"])
        self.assertIsNone(button["style"]["layout"]["z_index"])
        self.assertEqual(sign_in["parent_id"], button["id"])
        self.assertEqual(button["children_ids"], [sign_in["id"]])
        self.assertEqual(sign_in["sibling_index"], 0)

    def test_harmony_parser_filters_other_bundles_and_system_windows(self) -> None:
        layout = json.loads(json.dumps(HARMONY_LAYOUT))
        layout["children"].append(
            {
                "attributes": {
                    "bounds": "[0,0][1080,72]",
                    "type": "WindowScene",
                    "id": "system_status_bar",
                    "bundleName": "com.ohos.sceneboard",
                    "visible": "true",
                },
                "children": [],
            }
        )

        components = parse_harmony_layout_json(
            json.dumps(layout).encode("utf-8"), (1080, 2400), "example.harmony"
        )

        self.assertEqual(len(components), 6)
        self.assertNotIn("system_status_bar", {item["runtime_id"] for item in components})

    def test_runtime_snapshot_maps_real_facts_and_reports_honest_coverage(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_uiautomator_xml(UI_XML.encode("utf-8"), (1080, 2400), "example")
        snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="b" * 64,
            screenshot_byte_count=1234,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
            device={"id": "emulator-5554", "model": "Pixel", "os_version": "35"},
            timings_ms={"source": 12.5, "capture": 40.0, "merge": 3.0},
        )

        self.assertEqual(snapshot["schema"], "android-to-harmony.page-snapshot.v2")
        self.assertEqual(snapshot["capture"]["screenshot"]["sha256"], "b" * 64)
        self.assertEqual(metrics["verdict"], "fail")
        self.assertEqual(metrics["source"]["primitive_visible_candidate_count"], 5)
        self.assertEqual(metrics["source"]["primitive_mapped_count"], 5)
        self.assertEqual(metrics["source"]["primitive_mapping_ratio"], 1.0)
        self.assertEqual(metrics["runtime"]["component_count"], 6)
        self.assertEqual(metrics["runtime"]["source_mapped_count"], 5)
        self.assertEqual(metrics["checks"]["exact_text_matches"], 2)
        self.assertEqual(metrics["checks"]["stable_runtime_id_matches"], 1)
        self.assertEqual(metrics["checks"]["exact_content_description_matches"], 0)
        self.assertGreater(metrics["source"]["unresolved_required_visual_fact_count"], 0)
        self.assertFalse(metrics["claims"]["all_visual_styles_resolved"])
        self.assertEqual(metrics["timings_ms"]["total"], 55.5)
        mapped = [item for item in snapshot["components"] if item.get("source")]
        self.assertEqual(len(mapped), 5)
        self.assertEqual(len(snapshot["components"]), 5)
        self.assertTrue(all(item["parent_mapping"] == "source-semantic-ancestor" for item in snapshot["components"]))
        sign_in = next(item for item in snapshot["components"] if item["style"]["content"]["text"] == "Sign in")
        button = next(item for item in snapshot["components"] if item["type"] == "Button")
        self.assertEqual(sign_in["parent_id"], button["id"])
        self.assertEqual(button["children_ids"], [sign_in["id"]])

    def test_harmony_runtime_ids_take_priority_over_heuristic_matching(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_harmony_layout_json(
            json.dumps(HARMONY_LAYOUT).encode("utf-8"), (1080, 2400)
        )
        snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="c" * 64,
            screenshot_byte_count=4321,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
            device={"id": "127.0.0.1:5555", "model": "emulator", "os_version": "OpenHarmony"},
            timings_ms={"source": 10.0, "capture": 20.0, "merge": 2.0},
            platform="harmony",
            runtime_origin="OpenHarmony uitest dumpLayout from bound capture",
        )

        self.assertEqual(snapshot["platform"], "harmony")
        self.assertEqual(metrics["checks"]["stable_runtime_id_matches"], 5)
        self.assertEqual(metrics["source"]["primitive_mapped_count"], 5)
        self.assertEqual(metrics["source"]["primitive_mapping_ratio"], 1.0)
        self.assertEqual(metrics["runtime"]["semantic_mapping_ratio"], 1.0)
        self.assertEqual(len(snapshot["components"]), 5)
        self.assertTrue(all(item["parent_mapping"] == "source-semantic-ancestor" for item in snapshot["components"]))

    def test_explicit_runtime_source_map_binds_business_ids_to_exact_source_calls(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        layout = json.loads(json.dumps(HARMONY_LAYOUT))
        business_ids = ["login_root", "login_title", "login_cover", "login_submit", "login_submit_label"]
        source_calls = [
            f"{ROOT_SOURCE}:10:Column:1",
            f"{ROOT_SOURCE}:12:Text:2",
            f"{ROOT_SOURCE}:13:Image:3",
            f"{ROOT_SOURCE}:16:Button:4",
            f"{ROOT_SOURCE}:17:Text:5",
        ]
        runtime_nodes = layout["children"][0]["children"][0]
        runtime_nodes["attributes"]["id"] = business_ids[0]
        runtime_nodes["attributes"]["key"] = business_ids[0]
        for node, runtime_id in zip(runtime_nodes["children"], business_ids[1:4], strict=True):
            node["attributes"]["id"] = runtime_id
            node["attributes"]["key"] = runtime_id
        runtime_nodes["children"][2]["children"][0]["attributes"]["id"] = business_ids[4]
        runtime_nodes["children"][2]["children"][0]["attributes"]["key"] = business_ids[4]
        runtime = parse_harmony_layout_json(json.dumps(layout).encode("utf-8"), (1080, 2400))
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "harmony",
            "page": {"id": "login", "state": "default"},
            "mappings": [
                {
                    "runtime_id": runtime_id,
                    "source_semantic_key": source["semantic_key"],
                    "source_call_id": call_id,
                }
                for runtime_id, call_id, source in zip(
                    business_ids, source_calls, source["components"], strict=True
                )
            ],
        }

        snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="d" * 64,
            screenshot_byte_count=4321,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
            device={"id": "127.0.0.1:5555", "model": "emulator", "os_version": "OpenHarmony"},
            timings_ms={"source": 10.0, "capture": 20.0, "merge": 2.0},
            platform="harmony",
            runtime_source_map=mapping,
            runtime_source_map_sha256="e" * 64,
        )

        self.assertEqual(metrics["checks"]["explicit_runtime_source_map_matches"], 5)
        self.assertEqual(metrics["source"]["proven_primitive_mapping_ratio"], 1.0)
        self.assertEqual(metrics["runtime"]["proven_semantic_mapping_ratio"], 1.0)
        self.assertEqual(snapshot["input_hashes"]["runtime_source_map_sha256"], "e" * 64)
        mapped = [component for component in snapshot["components"] if component.get("semantic_key")]
        self.assertEqual(
            {component["source_mapping"]["method"] for component in mapped},
            {"explicit_runtime_source_map"},
        )

    def test_runtime_source_map_rejects_ambiguous_runtime_ids_and_text_only_is_not_proof(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_harmony_layout_json(
            json.dumps(HARMONY_LAYOUT).encode("utf-8"), (1080, 2400)
        )
        runtime[1]["runtime_id"] = "duplicate"
        runtime[2]["runtime_id"] = "duplicate"
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "harmony",
            "page": {"id": "login", "state": "default"},
            "mappings": [
                {
                    "runtime_id": "duplicate",
                    "source_semantic_key": "LoginScreen_Text_12_2",
                    "source_call_id": f"{ROOT_SOURCE}:12:Text:2",
                }
            ],
        }
        with self.assertRaisesRegex(RealPageError, "ambiguous runtime_id"):
            build_runtime_page_snapshot(
                source_spec=source,
                runtime_components=runtime,
                screenshot_path=Path("screen.png"),
                screenshot_sha256="f" * 64,
                screenshot_byte_count=1,
                dimensions=(1080, 2400),
                density=3.0,
                font_scale=1.0,
                insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
                device={},
                timings_ms={},
                platform="harmony",
                runtime_source_map=mapping,
            )

        text_only_runtime = parse_uiautomator_xml(UI_XML.encode("utf-8"), (1080, 2400), "example")
        _snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=text_only_runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="f" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
            device={},
            timings_ms={},
        )
        self.assertGreater(metrics["checks"]["exact_text_matches"], 0)
        self.assertLess(metrics["source"]["proven_primitive_mapping_ratio"], 1.0)
        self.assertEqual(metrics["verdict"], "fail")

    def test_capture_bound_runtime_component_mapping_rejects_tree_hash_drift(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_uiautomator_xml(UI_XML.encode("utf-8"), (1080, 2400), "example")
        title_runtime = next(item for item in runtime if item["style"]["content"]["text"] == "Welcome")
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "android",
            "page": {"id": "login", "state": "default"},
            "runtime_tree_sha256": "1" * 64,
            "mappings": [{
                "runtime_component_id": title_runtime["id"],
                "source_semantic_key": "LoginScreen_Text_12_2",
                "source_call_id": f"{ROOT_SOURCE}:12:Text:2",
            }],
        }

        snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="2" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
            device={},
            timings_ms={},
            runtime_source_map=mapping,
            runtime_tree_sha256="1" * 64,
        )
        title = next(item for item in snapshot["components"] if item["id"] == title_runtime["id"])
        self.assertEqual(title["source_mapping"]["method"], "explicit_runtime_source_map")
        self.assertEqual(metrics["checks"]["explicit_runtime_source_map_matches"], 1)

        with self.assertRaisesRegex(RealPageError, "runtime tree SHA-256"):
            build_runtime_page_snapshot(
                source_spec=source,
                runtime_components=runtime,
                screenshot_path=Path("screen.png"),
                screenshot_sha256="2" * 64,
                screenshot_byte_count=1,
                dimensions=(1080, 2400),
                density=3.0,
                font_scale=1.0,
                insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
                device={},
                timings_ms={},
                runtime_source_map=mapping,
                runtime_tree_sha256="3" * 64,
            )

    def test_capture_bound_android_compose_view_maps_exact_image_source_call(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        xml = UI_XML.replace(
            'class="android.widget.ImageView"',
            'class="android.view.View"',
        )
        runtime = parse_uiautomator_xml(xml.encode("utf-8"), (1080, 2400), "example")
        image_runtime = next(
            item for item in runtime if item.get("resource_id") == "example:id/LoginScreen_Image_13_3"
        )
        image_runtime["style"]["surface"]["background"] = {
            "type": "solid", "color": "#FFFFFFFF"
        }
        image_runtime["pixel_provenance_paths"] = ["style.surface.background"]
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "android",
            "page": {"id": "login", "state": "default"},
            "runtime_tree_sha256": "4" * 64,
            "mappings": [{
                "runtime_component_id": image_runtime["id"],
                "source_semantic_key": "LoginScreen_Image_13_3",
                "source_call_id": f"{ROOT_SOURCE}:13:Image:3",
            }],
        }

        snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="5" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
            device={},
            timings_ms={},
            runtime_source_map=mapping,
            runtime_tree_sha256="4" * 64,
        )

        image = next(item for item in snapshot["components"] if item["id"] == image_runtime["id"])
        self.assertEqual(image["semantic_key"], "LoginScreen_Image_13_3")
        self.assertEqual(image["source_mapping"]["method"], "explicit_runtime_source_map")
        self.assertIsNone(image["style"]["surface"]["background"])
        self.assertEqual(metrics["checks"]["explicit_runtime_source_map_matches"], 1)

    def test_runtime_source_map_applies_hash_bound_resolved_asset_fact(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        image_source = next(item for item in source["components"] if item["type"] == "Image")
        image_source["style"]["asset"]["resource"] = None
        image_source["style"]["asset"]["sha256"] = None
        image_source["unresolved"] = [{
            "path": "style.asset.resource",
            "expression": "painterResource(id = imageRes)",
            "reason": "dynamic source expression",
        }]
        runtime = parse_uiautomator_xml(UI_XML.encode("utf-8"), (1080, 2400), "example")
        image_runtime = next(item for item in runtime if item["type"] == "Image")
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "android",
            "page": {"id": "login", "state": "default"},
            "runtime_tree_sha256": "7" * 64,
            "resolved_source_facts": [
                {
                    "source_semantic_key": "LoginScreen_Image_13_3",
                    "source_call_id": f"{ROOT_SOURCE}:13:Image:3",
                    "path": "style.asset.resource",
                    "value": "login_cover",
                    "origin": "source_resolved",
                    "source": f"{ROOT_SOURCE}:state=default",
                },
                {
                    "source_semantic_key": "LoginScreen_Image_13_3",
                    "source_call_id": f"{ROOT_SOURCE}:13:Image:3",
                    "path": "style.asset.sha256",
                    "value": "8" * 64,
                    "origin": "source_resolved",
                    "source": "app/src/main/res/drawable/login_cover.png",
                },
            ],
            "mappings": [{
                "runtime_component_id": image_runtime["id"],
                "source_semantic_key": "LoginScreen_Image_13_3",
                "source_call_id": f"{ROOT_SOURCE}:13:Image:3",
            }],
        }

        snapshot, _metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="9" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
            device={},
            timings_ms={},
            runtime_source_map=mapping,
            runtime_tree_sha256="7" * 64,
        )

        image = next(item for item in snapshot["components"] if item["semantic_key"] == "LoginScreen_Image_13_3")
        self.assertEqual(image["style"]["asset"]["resource"], "login_cover")
        self.assertEqual(image["style"]["asset"]["sha256"], "8" * 64)
        self.assertEqual(image["unresolved"], [])
        self.assertTrue(any(
            fact["origin"] == "source_resolved"
            and "style.asset.sha256" in fact["paths"]
            for fact in image["provenance"]
        ))

    def test_runtime_source_map_rejects_conflicting_resolved_asset_fact(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_uiautomator_xml(UI_XML.encode("utf-8"), (1080, 2400), "example")
        image_runtime = next(item for item in runtime if item["type"] == "Image")
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "android",
            "page": {"id": "login", "state": "default"},
            "runtime_tree_sha256": "7" * 64,
            "resolved_source_facts": [{
                "source_semantic_key": "LoginScreen_Image_13_3",
                "source_call_id": f"{ROOT_SOURCE}:13:Image:3",
                "path": "style.asset.resource",
                "value": "different_cover",
                "origin": "source_resolved",
                "source": f"{ROOT_SOURCE}:state=default",
            }],
            "mappings": [{
                "runtime_component_id": image_runtime["id"],
                "source_semantic_key": "LoginScreen_Image_13_3",
                "source_call_id": f"{ROOT_SOURCE}:13:Image:3",
            }],
        }

        with self.assertRaisesRegex(RealPageError, "resolved source fact conflicts"):
            build_runtime_page_snapshot(
                source_spec=source,
                runtime_components=runtime,
                screenshot_path=Path("screen.png"),
                screenshot_sha256="9" * 64,
                screenshot_byte_count=1,
                dimensions=(1080, 2400),
                density=3.0,
                font_scale=1.0,
                insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
                device={},
                timings_ms={},
                runtime_source_map=mapping,
                runtime_tree_sha256="7" * 64,
            )

    def test_source_page_resolves_positional_material_icon_asset(self) -> None:
        contract = fixture_contract()
        contract["ui"]["semantic_translation_candidates"]["calls"].append({
            "source": ROOT_SOURCE,
            "composable": "LoginScreen",
            "line": 20,
            "component": "Icon",
            "call_id": f"{ROOT_SOURCE}:20:Icon:6",
            "parent_call_id": f"{ROOT_SOURCE}:10:Column:1",
            "semantic_arguments": {},
            "positional_arguments": [
                {"expression": "Icons.Filled.Add", "dimensions": [], "dimension_resources": []},
                {"expression": '"Add"', "dimensions": [], "dimension_resources": []},
            ],
            "ordered_modifier_chain": [],
            "state_slots": [],
            "trailing_lambda_parameters": [],
        })

        source = build_source_page_spec(
            contract, ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        icon = next(item for item in source["components"] if item["type"] == "Icon")

        self.assertEqual(icon["style"]["asset"]["resource"], "Icons.Filled.Add")
        self.assertEqual(icon["style"]["asset"]["content_scale"], "fit")
        self.assertEqual(icon["style"]["content"]["content_description"], "Add")
        self.assertEqual(icon["unresolved"], [])

    def test_runtime_source_map_declares_inactive_state_branch_without_hiding_runtime_nodes(self) -> None:
        contract = fixture_contract()
        contract["ui"]["semantic_translation_candidates"]["calls"].append({
            "source": ROOT_SOURCE,
            "composable": "LoginScreen",
            "line": 20,
            "component": "Text",
            "call_id": f"{ROOT_SOURCE}:20:Text:6",
            "parent_call_id": f"{ROOT_SOURCE}:10:Column:1",
            "semantic_arguments": {"text": {
                "expression": '"Only shown after failure"',
                "dimensions": [],
                "dimension_resources": [],
            }},
            "positional_arguments": [],
            "ordered_modifier_chain": [],
            "state_slots": [],
            "trailing_lambda_parameters": [],
        })
        source = build_source_page_spec(
            contract, ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_harmony_layout_json(
            json.dumps(HARMONY_LAYOUT).encode("utf-8"), (1080, 2400)
        )
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "harmony",
            "page": {"id": "login", "state": "default"},
            "mappings": [],
            "inactive_source_components": [{
                "source_semantic_key": "LoginScreen_Text_20_6",
                "source_call_id": f"{ROOT_SOURCE}:20:Text:6",
                "reason": "inactive_source_branch",
            }],
        }

        snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="6" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
            device={},
            timings_ms={},
            platform="harmony",
            runtime_source_map=mapping,
        )

        self.assertNotIn("LoginScreen_Text_20_6", snapshot["unmapped_source_components"])
        self.assertEqual(
            snapshot["inactive_source_components"],
            [{
                "source_semantic_key": "LoginScreen_Text_20_6",
                "source_call_id": f"{ROOT_SOURCE}:20:Text:6",
                "reason": "inactive_source_branch",
            }],
        )
        self.assertEqual(metrics["source"]["inactive_primitive_count"], 1)
        self.assertEqual(metrics["runtime"]["semantic_component_count"], 5)

    def test_runtime_source_map_rejects_mapping_an_inactive_source_branch(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_uiautomator_xml(UI_XML.encode("utf-8"), (1080, 2400), "example")
        image_runtime = next(item for item in runtime if item["type"] == "Image")
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "android",
            "page": {"id": "login", "state": "default"},
            "runtime_tree_sha256": "7" * 64,
            "mappings": [{
                "runtime_component_id": image_runtime["id"],
                "source_semantic_key": "LoginScreen_Image_13_3",
                "source_call_id": f"{ROOT_SOURCE}:13:Image:3",
            }],
            "inactive_source_components": [{
                "source_semantic_key": "LoginScreen_Image_13_3",
                "source_call_id": f"{ROOT_SOURCE}:13:Image:3",
                "reason": "inactive_source_branch",
            }],
        }

        with self.assertRaisesRegex(RealPageError, "maps an inactive source component"):
            build_runtime_page_snapshot(
                source_spec=source,
                runtime_components=runtime,
                screenshot_path=Path("screen.png"),
                screenshot_sha256="9" * 64,
                screenshot_byte_count=1,
                dimensions=(1080, 2400),
                density=3.0,
                font_scale=1.0,
                insets_px={"left": 0, "top": 72, "right": 0, "bottom": 96},
                device={},
                timings_ms={},
                runtime_source_map=mapping,
                runtime_tree_sha256="7" * 64,
            )


if __name__ == "__main__":
    unittest.main()
