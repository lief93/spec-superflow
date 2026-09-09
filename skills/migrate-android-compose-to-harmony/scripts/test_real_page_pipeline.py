from __future__ import annotations

import copy
import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

from component_required_facts import (
    build_required_facts,
    normalized_layout_rules,
    required_fact_gate,
)
from real_page_pipeline import (
    RealPageError,
    apply_screenshot_visual_facts,
    build_runtime_page_snapshot,
    build_source_page_spec,
    clip_projected_layout_bounds,
    match_source_to_runtime,
    parse_harmony_layout_json,
    parse_uiautomator_xml,
    screenshot_surface_regions,
    select_most_specific_surface_owner,
    semantic_runtime_component,
    static_style_for_call,
    stable_runtime_fallback_key,
    surface_height_matches_source,
)
from generate_real_android_page_json import android_capture_commands, device_insets
from generate_real_harmony_page_json import harmony_capture_commands
from generate_arkui_page import normalize_source_component_tree


ROOT_SOURCE = "app/src/main/java/example/Login.kt"
HEADER_SOURCE = "app/src/main/java/example/ScreenHeader.kt"


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


def constraint_slot_contract() -> dict:
    def call(
        source: str,
        composable: str,
        line: int,
        component: str,
        ordinal: int,
        parent: str | None,
        *,
        modifiers: list[dict] | None = None,
        slot_argument_name: str | None = None,
        slot_invocation: str | None = None,
        custom: dict | None = None,
    ) -> dict:
        call_id = f"{source}:{line}:{component}:{ordinal}"
        result = {
            "source": source,
            "composable": composable,
            "line": line,
            "component": component,
            "call_id": call_id,
            "parent_call_id": parent,
            "semantic_arguments": {},
            "positional_arguments": [],
            "ordered_modifier_chain": modifiers or [],
            "state_slots": [],
            "trailing_lambda_parameters": [],
        }
        if slot_argument_name is not None:
            result["slot_argument_name"] = slot_argument_name
        if slot_invocation is not None:
            result["slot_invocation"] = {"name": slot_invocation}
        if custom is not None:
            result["custom_composable"] = custom
        return result

    root_column = f"{ROOT_SOURCE}:10:Column:1"
    header = f"{ROOT_SOURCE}:11:ScreenHeader:2"
    constraint = f"{HEADER_SOURCE}:20:ConstraintLayout:1"
    cover = f"{HEADER_SOURCE}:22:Box:2"
    panel = f"{HEADER_SOURCE}:30:Box:4"
    calls = [
        call(ROOT_SOURCE, "LoginScreen", 10, "Column", 1, None),
        call(
            ROOT_SOURCE,
            "LoginScreen",
            11,
            "ScreenHeader",
            2,
            root_column,
            custom={
                "status": "resolved_project_definition",
                "definitions": [{"source": HEADER_SOURCE, "composable": "ScreenHeader"}],
                "arguments": [{
                    "name": "panelVerticalOffset",
                    "expression": "24.dp",
                    "dimensions": [{"value": "24", "unit": "dp"}],
                    "dimension_resources": [],
                }],
            },
        ),
        call(
            ROOT_SOURCE,
            "LoginScreen",
            12,
            "Text",
            3,
            header,
            slot_argument_name="toolbar",
        ),
        call(
            ROOT_SOURCE,
            "LoginScreen",
            13,
            "Button",
            4,
            header,
            slot_argument_name="content",
        ),
        call(HEADER_SOURCE, "ScreenHeader", 20, "ConstraintLayout", 1, None),
        call(
            HEADER_SOURCE,
            "ScreenHeader",
            22,
            "Box",
            2,
            constraint,
            modifiers=[{
                "name": "constrainAs",
                "arguments": "cover",
                "dimensions": [],
                "dimension_resources": [],
                "trailing_lambda": (
                    "{ start.linkTo(parent.start) end.linkTo(parent.end) "
                    "top.linkTo(parent.top) }"
                ),
            }],
        ),
        call(
            HEADER_SOURCE,
            "ScreenHeader",
            23,
            "toolbar",
            3,
            cover,
            slot_invocation="toolbar",
        ),
        call(
            HEADER_SOURCE,
            "ScreenHeader",
            30,
            "Box",
            4,
            constraint,
            modifiers=[{
                "name": "constrainAs",
                "arguments": "panel",
                "dimensions": [],
                "dimension_resources": [],
                "trailing_lambda": (
                    "{ if (panelVerticalOffset == null) { centerAround(cover.bottom) } "
                    "else { top.linkTo(cover.bottom, margin = -panelVerticalOffset) } "
                    "start.linkTo(cover.start) end.linkTo(cover.end) }"
                ),
            }],
        ),
        call(
            HEADER_SOURCE,
            "ScreenHeader",
            31,
            "content",
            5,
            panel,
            slot_invocation="content",
        ),
    ]
    return {
        "ui": {
            "semantic_translation_candidates": {"calls": calls},
            "custom_composable_call_graph": {
                "transitive_closures": [{
                    "root": {"source": ROOT_SOURCE, "composable": "LoginScreen"},
                    "reached_definitions": [
                        {"source": ROOT_SOURCE, "composable": "LoginScreen"},
                        {"source": HEADER_SOURCE, "composable": "ScreenHeader"},
                    ],
                    "cycle_edges": [],
                }]
            },
            "composables": [
                {"source": ROOT_SOURCE, "name": "LoginScreen", "parameters": []},
                {
                    "source": HEADER_SOURCE,
                    "name": "ScreenHeader",
                    "parameters": [
                        {"name": "toolbar", "type": "@Composable () -> Unit", "default": "{}"},
                        {"name": "panelVerticalOffset", "type": "Dp?", "default": "null"},
                        {"name": "content", "type": "@Composable BoxScope.() -> Unit"},
                    ],
                },
            ],
            "android_value_resource_inventory": {"resources": []},
        }
    }


def component_scoped_runtime_fixture() -> tuple[dict, list[dict]]:
    source = build_source_page_spec(
        fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
    )
    originals = {component["source"]["line"]: component for component in source["components"]}
    root = copy.deepcopy(originals[10])
    root["children_ids"] = []

    def project_component(component_id: str, component_type: str, line: int) -> dict:
        component = copy.deepcopy(originals[16])
        component.update({
            "id": component_id,
            "type": component_type,
            "definition_id": f"definition-{component_id}",
            "semantic_key": component_type,
            "parent_id": root["id"],
            "children_ids": [],
            "sibling_index": len(root["children_ids"]),
            "component_kind": "project_component",
        })
        component["source"].update({
            "line": line,
            "call_id": f"{ROOT_SOURCE}:{line}:{component_type}:1",
            "custom_component": True,
        })
        component["style"] = copy.deepcopy(originals[16]["style"])
        component["unresolved"] = []
        root["children_ids"].append(component_id)
        source["component_definitions"].append({
            "id": component["definition_id"],
            "type": component_type,
            "component_kind": "project_component",
            "identity": {
                "status": "resolved_project_component",
                "qualified_name": f"example.{component_type}",
                "source": ROOT_SOURCE,
                "symbol": component_type,
            },
            "dependency": None,
            "declared_from": {
                "source": ROOT_SOURCE,
                "composable": "LoginScreen",
                "package": "example",
            },
        })
        return component

    def primitive_component(
        component_id: str,
        component_type: str,
        line: int,
        parent: dict,
        sibling_index: int,
    ) -> dict:
        template = originals[13] if component_type in {"Image", "AsyncImage"} else originals[17]
        component = copy.deepcopy(template)
        component.update({
            "id": component_id,
            "type": component_type,
            "semantic_key": f"{parent['type']}_{component_type}_{line}",
            "parent_id": parent["id"],
            "children_ids": [],
            "sibling_index": sibling_index,
            "component_kind": "compose_primitive",
        })
        component["source"].update({
            "line": line,
            "call_id": f"{ROOT_SOURCE}:{line}:{component_type}:{sibling_index + 1}",
            "custom_component": False,
        })
        component["unresolved"] = []
        return component

    action = project_component("source-action", "AccountActionItem", 30)
    action_column = primitive_component("source-action-column", "Column", 31, action, 0)
    icon_box = primitive_component("source-action-box", "Box", 32, action_column, 0)
    icon_box["style"]["layout"].update({"width_dp": 48.0, "height_dp": 48.0})
    icon = primitive_component("source-action-image", "Image", 33, icon_box, 0)
    icon["style"]["asset"].update({
        "width_dp": 32.0,
        "height_dp": 32.0,
        "content_scale": "fit",
    })
    icon["unresolved"] = [{
        "path": "style.asset.resource",
        "expression": "action.icon",
        "reason": "dynamic source expression",
    }]
    icon_box["children_ids"] = [icon["id"]]
    spacer = primitive_component("source-action-spacer", "Spacer", 34, action_column, 1)
    spacer["style"]["layout"]["height_dp"] = 10.0
    request = primitive_component("source-action-text", "Text", 35, action_column, 2)
    request["style"]["content"]["role"] = "text"
    request["style"]["typography"].update({
        "font_size_sp": 14.0,
        "line_height_sp": 20.0,
        "font_weight": 400,
        "font_family": "primaryFontFamily",
        "color": "#FF100D40",
    })
    request["unresolved"] = [{
        "path": "style.content.text",
        "expression": "action.uiTitle",
        "reason": "dynamic source expression",
    }]
    action_column["children_ids"] = [icon_box["id"], spacer["id"], request["id"]]
    action["children_ids"] = [action_column["id"]]

    saving = project_component("source-saving", "SavingCard", 40)
    saving_image = primitive_component("source-saving-image", "AsyncImage", 41, saving, 0)
    saving_image["style"]["asset"].update({
        "width_dp": 48.0,
        "height_dp": 48.0,
        "content_scale": "fit",
    })
    saving_image["unresolved"] = [{
        "path": "style.asset.resource",
        "expression": "saving.imageUrl",
        "reason": "dynamic source expression",
    }]
    saving_title = primitive_component("source-saving-text", "Text", 42, saving, 1)
    saving_title["style"]["content"]["role"] = "text"
    saving_title["style"]["typography"].update({
        "font_size_sp": 14.0,
        "line_height_sp": 20.0,
        "font_weight": 600,
        "font_family": "primaryFontFamily",
        "color": "#FF100D40",
    })
    saving_title["unresolved"] = [{
        "path": "style.content.text",
        "expression": "saving.title",
        "reason": "dynamic source expression",
    }]
    saving["children_ids"] = [saving_image["id"], saving_title["id"]]

    source["components"] = [
        root,
        action,
        action_column,
        icon_box,
        icon,
        spacer,
        request,
        saving,
        saving_image,
        saving_title,
    ]
    source["runtime_asset_rules"] = [
        {
            "role": "labeled_asset_object",
            "label": "Request",
            "asset": {"resource": "ic_request", "sha256": "1" * 64},
            "selected_asset": None,
            "availability": "unavailable",
            "route": None,
            "model_type": "Action",
            "source": {"source": ROOT_SOURCE, "line": 1},
        },
        {
            "role": "titled_asset_record",
            "label": "Buy Car Remote",
            "asset": {"resource": "ic_car", "sha256": "2" * 64},
            "selected_asset": None,
            "availability": "unknown",
            "route": None,
            "model_type": "Saving",
            "source": {"source": ROOT_SOURCE, "line": 2},
        },
    ]
    runtime = parse_uiautomator_xml(
        b'''<hierarchy rotation="0"><node index="0" text="" resource-id="" class="android.view.View" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[0,0][1080,1200]"><node index="0" text="Request" resource-id="" class="android.widget.TextView" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[300,300][480,360]" /><node index="1" text="" resource-id="" class="android.widget.Button" package="example" content-desc="" clickable="true" enabled="true" checked="false" selected="false" bounds="[60,600][1020,840]"><node index="0" text="Buy Car Remote" resource-id="" class="android.widget.TextView" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[300,648][660,708]" /></node></node></hierarchy>''',
        (1080, 1200),
        "example",
    )
    return source, runtime


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
    def test_preview_only_placeholder_is_not_a_runtime_page_fact(self) -> None:
        call = {
            "source": ROOT_SOURCE,
            "composable": "ProfileCard",
            "line": 74,
            "component": "AsyncImage",
            "semantic_arguments": {
                "model": {"expression": "imageReq"},
                "placeholder": {
                    "expression": "debugPlaceholder(R.drawable.ic_profile_filled)"
                },
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }

        style, provenance, unresolved = static_style_for_call(call, {}, None)
        component = {
            "id": "avatar",
            "type": "AsyncImage",
            "parent_id": None,
            "children_ids": [],
            "sibling_index": 0,
            "arguments": {"semantic": call["semantic_arguments"]},
            "modifiers": [],
            "style": style,
            "provenance": provenance,
            "unresolved": unresolved,
        }

        self.assertIsNone(style["content"]["placeholder"])
        self.assertFalse(
            any(item["path"] == "style.content.placeholder" for item in unresolved)
        )
        self.assertFalse(
            any(
                item["path"] == "style.content.placeholder"
                for item in build_required_facts(component)
            )
        )
        self.assertTrue(
            any(item["path"] == "style.asset.resource" for item in unresolved)
        )

    def test_layout_modifiers_are_normalized_instead_of_left_symbolic(self) -> None:
        component = {
            "id": "content",
            "type": "Row",
            "parent_id": None,
            "children_ids": [],
            "sibling_index": 0,
            "arguments": {"semantic": {}},
            "modifiers": [
                {"name": "fillMaxWidth", "arguments": ""},
                {"name": "height", "arguments": "intrinsicSize = IntrinsicSize.Max"},
                {"name": "weight", "arguments": "1f, fill = true"},
                {
                    "name": "offset",
                    "arguments": "x = maxHeight / 4, y = -maxHeight / 4",
                },
                {"name": "then", "arguments": "Modifier.wrapContentHeight()"},
            ],
            "style": {
                "layout": {"height_dp": None},
            },
            "unresolved": [],
        }

        rules = normalized_layout_rules(component)
        facts = build_required_facts({**component, "layout_rules": rules})

        self.assertEqual(
            rules,
            [
                {
                    "kind": "sizing",
                    "axes": ["width"],
                    "mode": "fill_parent",
                    "fraction": 1.0,
                    "source_modifier_index": 0,
                },
                {
                    "kind": "intrinsic_size",
                    "axis": "height",
                    "mode": "max",
                    "source_modifier_index": 1,
                },
                {
                    "kind": "weight",
                    "value": 1.0,
                    "fill": True,
                    "source_modifier_index": 2,
                },
                {
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
                    "source_modifier_index": 3,
                },
                {
                    "kind": "sizing",
                    "axes": ["height"],
                    "mode": "wrap_content",
                    "source_modifier_index": 4,
                    "source_modifier_name": "wrapContentHeight",
                },
            ],
        )
        self.assertFalse(any(item["status"] == "symbolic" for item in facts), facts)

    def test_forwarded_static_text_color_is_resolved(self) -> None:
        call = {
            "source": ROOT_SOURCE,
            "composable": "TextBtn",
            "line": 109,
            "component": "Text",
            "semantic_arguments": {
                "text": {"expression": "text"},
                "color": {"expression": "color"},
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }

        style, _provenance, unresolved = static_style_for_call(
            call,
            {},
            None,
            {"text": '"Log out"', "color": "Color(0xFFFF552F)"},
        )

        self.assertEqual(style["typography"]["color"], "#FFFF552F")
        self.assertFalse(
            any(item["path"] == "style.typography.color" for item in unresolved)
        )

    def test_required_facts_honor_explicit_text_override_precedence(self) -> None:
        call = {
            "source": ROOT_SOURCE,
            "composable": "LoginScreen",
            "line": 9,
            "component": "Text",
            "semantic_arguments": {
                "text": {"expression": '"Log out"'},
                "style": {"expression": "MaterialTheme.typography.titleSmall"},
                "fontWeight": {"expression": "FontWeight.SemiBold"},
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }

        style, provenance, unresolved = static_style_for_call(call, {}, None)
        component = {
            "id": "logout",
            "type": "Text",
            "parent_id": None,
            "children_ids": [],
            "sibling_index": 0,
            "arguments": {"semantic": call["semantic_arguments"]},
            "modifiers": [],
            "style": style,
            "provenance": provenance,
            "unresolved": unresolved,
        }
        facts = build_required_facts(component)

        self.assertEqual(style["typography"]["font_weight"], 600)
        direct = next(item for item in facts if item["source_name"] == "fontWeight")
        self.assertEqual(direct["status"], "resolved")

    def test_required_facts_accept_transparent_button_without_invented_surface(self) -> None:
        style = static_style_for_call(
            {
                "source": ROOT_SOURCE,
                "composable": "LoginScreen",
                "line": 10,
                "component": "TextButton",
                "semantic_arguments": {"onClick": {"expression": "onClick"}},
                "positional_arguments": [],
                "ordered_modifier_chain": [],
            },
            {},
            None,
        )[0]
        component = {
            "id": "button",
            "type": "TextButton",
            "parent_id": None,
            "children_ids": [],
            "sibling_index": 0,
            "arguments": {"semantic": {"onClick": {"expression": "onClick"}}},
            "modifiers": [],
            "style": style,
            "unresolved": [],
        }

        facts = build_required_facts(component)

        self.assertEqual(style['surface']['background'], {'type': 'solid', 'color': '#00000000'})
        self.assertTrue(any(item['path'] == 'style.surface.background' and item['status'] == 'resolved' for item in facts))
        self.assertEqual(required_fact_gate([{**component, "required_facts": facts}])["verdict"], "pass")

    def test_required_facts_distinguish_symbolic_from_missing_constant(self) -> None:
        style = static_style_for_call(
            {
                "source": ROOT_SOURCE,
                "composable": "LoginScreen",
                "line": 11,
                "component": "Text",
                "semantic_arguments": {
                    "text": {"expression": "profile.fullName"},
                    "maxLines": {"expression": "1"},
                },
                "positional_arguments": [],
                "ordered_modifier_chain": [],
            },
            {},
            None,
        )
        component = {
            "id": "name",
            "type": "Text",
            "parent_id": None,
            "children_ids": [],
            "sibling_index": 0,
            "arguments": {
                "semantic": {
                    "text": {"expression": "profile.fullName"},
                    "maxLines": {"expression": "1"},
                }
            },
            "modifiers": [],
            "style": style[0],
            "unresolved": style[2],
        }
        facts = build_required_facts(component)
        text = next(item for item in facts if item["source_name"] == "text")
        max_lines = next(item for item in facts if item["source_name"] == "maxLines")

        self.assertEqual(text["status"], "symbolic")
        self.assertEqual(max_lines["status"], "resolved")
        component["style"]["typography"]["max_lines"] = 2
        broken = build_required_facts(component)
        broken_max_lines = next(item for item in broken if item["source_name"] == "maxLines")
        self.assertEqual(broken_max_lines["status"], "unresolved")
        self.assertEqual(
            required_fact_gate([{**component, "required_facts": broken}])["verdict"],
            "fail",
        )

    def test_static_source_style_preserves_text_and_shape_contracts(self) -> None:
        text_call = {
            "source": ROOT_SOURCE,
            "composable": "ProfileCard",
            "line": 20,
            "component": "Text",
            "semantic_arguments": {
                "text": {"expression": '"Alexander Michael"'},
                "maxLines": {"expression": "1"},
                "overflow": {"expression": "TextOverflow.Ellipsis"},
                "textDecoration": {"expression": "TextDecoration.Underline"},
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }
        text_style, _provenance, _unresolved = static_style_for_call(
            text_call, {}, None
        )
        self.assertEqual(text_style["typography"]["max_lines"], 1)
        self.assertEqual(text_style["typography"]["overflow"], "ellipsis")
        self.assertEqual(text_style["typography"]["decoration"], "underline")

        avatar_call = {
            "source": ROOT_SOURCE,
            "composable": "ProfileCard",
            "line": 21,
            "component": "AsyncImage",
            "semantic_arguments": {},
            "positional_arguments": [],
            "ordered_modifier_chain": [
                {"name": "clip", "arguments": "CircleShape", "dimensions": []}
            ],
        }
        avatar_style, _provenance, _unresolved = static_style_for_call(
            avatar_call, {}, None
        )
        self.assertIs(avatar_style["surface"]["clip"], True)

        tier_call = {
            "source": ROOT_SOURCE,
            "composable": "ProfileCard",
            "line": 22,
            "component": "Box",
            "semantic_arguments": {},
            "positional_arguments": [],
            "ordered_modifier_chain": [
                {
                    "name": "border",
                    "arguments": (
                        "width = 1.dp, color = Color(0xFF100D40), "
                        "shape = RoundedCornerShape(size = 32.dp)"
                    ),
                    "dimensions": [
                        {"value": "1", "unit": "dp"},
                        {"value": "32", "unit": "dp"},
                    ],
                }
            ],
        }
        tier_style, _provenance, _unresolved = static_style_for_call(
            tier_call, {}, None
        )
        self.assertEqual(
            tier_style["surface"]["border"],
            {"width_dp": 1.0, "color": "#FF100D40", "style": "solid"},
        )
        self.assertEqual(
            tier_style["surface"]["corner_radius_dp"],
            {
                "top_left": 32.0,
                "top_right": 32.0,
                "bottom_right": 32.0,
                "bottom_left": 32.0,
            },
        )

        row_call = {
            "source": ROOT_SOURCE,
            "composable": "MenuButton",
            "line": 23,
            "component": "Row",
            "semantic_arguments": {
                "verticalAlignment": {"expression": "Alignment.CenterVertically"}
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }
        row_style, _provenance, _unresolved = static_style_for_call(row_call, {}, None)
        self.assertEqual(row_style["layout"]["alignment"], "CenterVertically")

        button_call = {
            "source": ROOT_SOURCE,
            "composable": "TextBtn",
            "line": 24,
            "component": "TextButton",
            "semantic_arguments": {
                "contentPadding": {
                    "expression": "PaddingValues(vertical = 0.dp, horizontal = 16.dp)",
                    "dimensions": [
                        {"value": "0", "unit": "dp"},
                        {"value": "16", "unit": "dp"},
                    ],
                }
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }
        button_style, _provenance, _unresolved = static_style_for_call(
            button_call, {}, None
        )
        self.assertEqual(
            button_style["layout"]["padding_dp"],
            {"left": 16.0, "top": 0.0, "right": 16.0, "bottom": 0.0},
        )

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

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is not installed")
    def test_transparent_layout_does_not_claim_inherited_parent_background(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            screenshot = Path(temporary) / "inherited-surface.png"
            Image.new("RGB", (100, 100), (16, 13, 64)).save(screenshot)
            components = [
                {
                    "id": "runtime-parent",
                    "parent_id": None,
                    "type": "root",
                    "bounds_px": {"x": 0, "y": 0, "width": 100, "height": 100},
                    "style": {
                        "layout": {},
                        "surface": {"background": None, "corner_radius_dp": None},
                        "typography": {},
                        "asset": {},
                        "transform": {},
                        "state": {"clickable": False},
                        "content": {},
                    },
                },
                {
                    "id": "runtime-transparent-child",
                    "parent_id": "runtime-parent",
                    "type": "View",
                    "bounds_px": {"x": 10, "y": 10, "width": 80, "height": 80},
                    "style": {
                        "layout": {},
                        "surface": {"background": None, "corner_radius_dp": None},
                        "typography": {},
                        "asset": {},
                        "transform": {},
                        "state": {"clickable": False},
                        "content": {},
                    },
                },
            ]

            apply_screenshot_visual_facts(screenshot, components, 1.0, 1.0)

            self.assertEqual(
                components[0]["style"]["surface"]["background"],
                {"type": "solid", "color": "#FF100D40"},
            )
            self.assertIsNone(
                components[1]["style"]["surface"]["background"]
            )

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is not installed")
    def test_screenshot_surface_regions_recovers_runtime_elided_card(self) -> None:
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as temporary:
            screenshot = Path(temporary) / "surface.png"
            image = Image.new("RGB", (200, 220), (16, 13, 64))
            ImageDraw.Draw(image).rounded_rectangle(
                (20, 40, 179, 159), radius=10, fill=(255, 255, 255)
            )
            image.save(screenshot)

            surfaces = screenshot_surface_regions(screenshot, (200, 220), 1.0)

            self.assertIn(
                {
                    "bounds_px": {"x": 20, "y": 40, "width": 160, "height": 120},
                    "background": "#FFFFFFFF",
                    "corner_radius_dp": 14.0,
                    "qualified_rows": 120,
                },
                surfaces,
            )

    def test_surface_owner_prefers_nested_component_over_broader_ancestor(self) -> None:
        selected = select_most_specific_surface_owner([
            (12, 1, "screen-header", [{"id": "broad"}]),
            (5, 2, "account-panel", [{"id": "nested"}]),
        ])

        self.assertEqual(selected[2], "account-panel")

    def test_fixed_height_child_cannot_claim_full_business_surface(self) -> None:
        density = 2.625
        full_surface_height_px = 467

        self.assertFalse(
            surface_height_matches_source(
                full_surface_height_px,
                density,
                {48.0},
            )
        )
        self.assertTrue(
            surface_height_matches_source(
                full_surface_height_px,
                density,
                set(),
            )
        )
        self.assertTrue(
            surface_height_matches_source(
                full_surface_height_px,
                density,
                {177.9},
            )
        )

    def test_nested_compose_elevation_uses_bound_source_default(self) -> None:
        style, provenance, unresolved = static_style_for_call(
            {
                "source": "app/src/main/java/example/PrimaryCard.kt",
                "line": 38,
                "component": "Box",
                "semantic_arguments": {},
                "positional_arguments": [],
                "ordered_modifier_chain": [{
                    "name": "then",
                    "arguments": (
                        "Modifier.requireCardElevation("
                        "shape = shape, ambientColor = Color.Gray, "
                        "spotColor = Color.Gray, requiredSize = elevation)"
                    ),
                    "dimensions": [],
                    "dimension_resources": [],
                }],
            },
            {},
            None,
            {"elevation": "20.dp"},
        )

        self.assertEqual(style["surface"]["shadows"], [{
            "color": "#1A000000",
            "offset_x_dp": 0.0,
            "offset_y_dp": 4.0,
            "blur_radius_dp": 20.0,
            "spread_radius_dp": 0.0,
        }])
        self.assertIn("style.surface.shadows", provenance[0]["paths"])
        self.assertEqual(unresolved, [])

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is not installed")
    def test_runtime_owned_surface_prevents_detached_screenshot_surface_duplicate(self) -> None:
        from PIL import Image, ImageDraw

        source, runtime = component_scoped_runtime_fixture()
        saving = next(item for item in source["components"] if item["id"] == "source-saving")
        saving["ordered_modifier_chain"] = [{
            "name": "background",
            "arguments": "Color.White",
            "dimensions": [],
            "dimension_resources": [],
        }, {
            "name": "shadow",
            "arguments": "12.dp",
            "dimensions": [{"value": "12", "unit": "dp"}],
            "dimension_resources": [],
        }]
        runtime_saving = next(item for item in runtime if item["type"] == "Button")
        runtime_saving["style"]["surface"]["background"] = {
            "type": "solid",
            "color": "#FFFFFFFF",
        }

        with tempfile.TemporaryDirectory() as temporary:
            screenshot = Path(temporary) / "surface.png"
            image = Image.new("RGB", (1080, 1200), (16, 13, 64))
            ImageDraw.Draw(image).rounded_rectangle(
                (190, 650, 889, 919), radius=24, fill=(255, 255, 255)
            )
            image.save(screenshot)

            snapshot, _metrics = build_runtime_page_snapshot(
                source_spec=source,
                runtime_components=runtime,
                screenshot_path=screenshot,
                screenshot_sha256="b" * 64,
                screenshot_byte_count=screenshot.stat().st_size,
                dimensions=(1080, 1200),
                density=3.0,
                font_scale=1.0,
                insets_px={"left": 0, "top": 0, "right": 0, "bottom": 0},
                device={},
                timings_ms={},
            )

        detached_surfaces = [
            component
            for component in snapshot["components"]
            if component["component_context"].get("business_component_id") == "source-saving"
            and component["component_context"].get("method") == "source_screenshot_surface_join"
        ]
        self.assertEqual(detached_surfaces, [])
        saving_button = next(
            component
            for component in snapshot["components"]
            if component["type"] == "Button"
            and component["component_context"].get("business_component_id") == "source-saving"
        )
        self.assertEqual(
            saving_button["style"]["surface"]["background"],
            {"type": "solid", "color": "#FFFFFFFF"},
        )

    def test_source_layout_projection_keeps_full_layout_and_clips_visible_bounds(self) -> None:
        self.assertEqual(
            clip_projected_layout_bounds(
                {"x": 245.334, "y": -9.905, "width": 200.0, "height": 200.0},
                {"x": 0.0, "y": 24.0, "width": 411.429, "height": 754.0},
            ),
            {"x": 245.334, "y": 24.0, "width": 166.095, "height": 166.095},
        )
        self.assertIsNone(
            clip_projected_layout_bounds(
                {"x": -100.0, "y": -100.0, "width": 20.0, "height": 20.0},
                {"x": 0.0, "y": 24.0, "width": 411.429, "height": 754.0},
            )
        )

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is not installed")
    def test_text_field_pixel_facts_separate_semantic_and_visible_surface_bounds(self) -> None:
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as temporary:
            screenshot = Path(temporary) / "text-field.png"
            image = Image.new("RGB", (120, 100), (255, 255, 255))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle(
                (10, 12, 109, 71),
                radius=4,
                fill=(255, 255, 255),
                outline=(207, 207, 211),
                width=2,
            )
            draw.rectangle((24, 34, 66, 45), fill=(51, 51, 51))
            image.save(screenshot)
            components = [{
                "id": "runtime-field",
                "type": "TextField",
                "bounds_px": {"x": 0, "y": 0, "width": 120, "height": 100},
                "style": {
                    "layout": {},
                    "surface": {"background": None, "border": None, "corner_radius_dp": None},
                    "typography": {},
                    "asset": {},
                    "transform": {},
                    "state": {"clickable": True},
                    "content": {},
                },
            }]

            result = apply_screenshot_visual_facts(screenshot, components, 2.0, 1.0)

            self.assertEqual(result["sampled_component_count"], 1)
            self.assertEqual(
                components[0]["visual_bounds_px"],
                {"x": 10, "y": 12, "width": 100, "height": 60},
            )
            self.assertEqual(
                components[0]["visual_bounds_dp"],
                {"x": 5.0, "y": 6.0, "width": 50.0, "height": 30.0},
            )
            self.assertEqual(
                components[0]["style"]["surface"]["border"],
                {"width_dp": 1.0, "color": "#FFCFCFD3", "style": "solid"},
            )
            self.assertEqual(
                components[0]["style"]["surface"]["background"],
                {"type": "solid", "color": "#FFFFFFFF"},
            )
            self.assertEqual(
                components[0]["style"]["layout"]["padding_dp"],
                {"left": 7.0, "right": 7.0, "top": 0.0, "bottom": 0.0},
            )

    def test_device_insets_uses_visible_status_and_navigation_bar_frames(self) -> None:
        import generate_real_android_page_json as command

        original = command.run
        command.run = lambda _arguments: """
          InsetsSource type=ITYPE_STATUS_BAR frame=[0,0][1080,72] visible=true
          InsetsSource type=ITYPE_NAVIGATION_BAR frame=[0,2304][1080,2400] visible=true
          InsetsSource type=TYPE_TOP_BAR frame=[0,0][1080,63] visible=true
          InsetsSource type=TYPE_SIDE_BAR_1 frame=[0,2274][1080,2400] visible=true
        """
        try:
            self.assertEqual(
                device_insets("adb", "device", (1080, 2400)),
                {"left": 0, "top": 72, "right": 0, "bottom": 126},
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
        self.assertEqual(image["style"]["layout"]["width_dp"], 72.0)
        self.assertEqual(image["style"]["layout"]["height_dp"], 72.0)
        self.assertIsNone(image["style"]["asset"]["width_dp"])
        self.assertIsNone(image["style"]["asset"]["height_dp"])
        root = next(item for item in payload["components"] if item["source"]["line"] == 10)
        self.assertIsNone(root["style"]["asset"]["height_dp"])
        self.assertIs(button["style"]["surface"]["clip"], True)
        self.assertEqual(button_text["parent_id"], button["id"])
        self.assertEqual(button["children_ids"], [button_text["id"]])
        self.assertEqual([item["sibling_index"] for item in payload["components"] if item["parent_id"] == title["parent_id"]], [0, 1, 2])
        self.assertEqual(title["semantic_key"], "LoginScreen_Text_12_2")

    def test_source_page_spec_preserves_slot_injection_and_constraint_overlay(self) -> None:
        payload = build_source_page_spec(
            constraint_slot_contract(),
            ROOT_SOURCE,
            "LoginScreen",
            "login",
            "default",
            "a" * 64,
        )
        by_type = {}
        for component in payload["components"]:
            by_type.setdefault(component["type"], []).append(component)

        header = by_type["ScreenHeader"][0]
        constraint = by_type["ConstraintLayout"][0]
        cover, panel = by_type["Box"]
        toolbar_slot = by_type["toolbar"][0]
        content_slot = by_type["content"][0]
        toolbar_content = by_type["Text"][0]
        panel_content = by_type["Button"][0]

        self.assertEqual(constraint["parent_id"], header["id"])
        self.assertEqual(cover["parent_id"], constraint["id"])
        self.assertEqual(panel["parent_id"], constraint["id"])
        self.assertEqual(toolbar_slot["parent_id"], cover["id"])
        self.assertEqual(content_slot["parent_id"], panel["id"])
        self.assertEqual(toolbar_content["parent_id"], toolbar_slot["id"])
        self.assertEqual(panel_content["parent_id"], content_slot["id"])

        panel_relation = next(
            relation
            for relation in payload["layout_relationships"]
            if relation["subject_id"] == panel["id"]
        )
        self.assertEqual(panel_relation["container_id"], constraint["id"])
        self.assertEqual(panel_relation["subject_reference"], "panel")
        self.assertEqual(panel_relation["composition"], "overlay")
        self.assertEqual(panel_relation["draw_order"], 1)
        self.assertIn(
            {
                "kind": "link_to",
                "subject_anchor": "top",
                "target_id": cover["id"],
                "target_reference": "cover",
                "target_anchor": "bottom",
                "margin_expression": "-panelVerticalOffset",
                "margin_dp": -24.0,
            },
            panel_relation["active_constraints"],
        )

        snapshot, _metrics = build_runtime_page_snapshot(
            source_spec=payload,
            runtime_components=[],
            screenshot_path=Path("missing-screen.png"),
            screenshot_sha256="b" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 2400),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 0, "right": 0, "bottom": 0},
            device={},
            timings_ms={},
        )
        source_tree = snapshot["source_component_tree"]
        self.assertEqual(
            source_tree["layout_relationships"], payload["layout_relationships"]
        )
        snapshot_by_type = {}
        for component in source_tree["components"]:
            snapshot_by_type.setdefault(component["type"], []).append(component)
        self.assertEqual(
            snapshot_by_type["Button"][0]["parent_id"],
            snapshot_by_type["content"][0]["id"],
        )
        normalized_tree = normalize_source_component_tree(source_tree)
        self.assertEqual(
            normalized_tree["layout_relationships"], payload["layout_relationships"]
        )

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

    def test_source_page_spec_resolves_inline_text_style_properties(self) -> None:
        contract = fixture_contract()
        contract["ui"]["compose_theme_token_inventory"] = {
            "tokens": [{
                "name": "primaryFontFamily",
                "kind": "font_family",
                "font_resource_keys": ["poppins", "poppins_semibold"],
            }]
        }
        title_call = contract["ui"]["semantic_translation_candidates"]["calls"][1]
        title_call["semantic_arguments"]["style"] = {
            "expression": (
                "TextStyle(fontSize = 12.sp, lineHeight = 18.sp, "
                "fontFamily = primaryFontFamily, fontWeight = FontWeight.SemiBold, "
                "color = Color(0xFF808289))"
            ),
            "dimensions": [
                {"value": "12", "unit": "sp"},
                {"value": "18", "unit": "sp"},
            ],
            "dimension_resources": [],
        }

        payload = build_source_page_spec(
            contract, ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )

        title = next(item for item in payload["components"] if item["source"]["line"] == 12)
        self.assertEqual(
            title["style"]["typography"],
            {
                "font_size_sp": 12.0,
                "font_weight": 600,
                "font_style": None,
                "font_family": "primaryFontFamily",
                "letter_spacing_sp": None,
                "line_height_sp": 18.0,
                "text_align": None,
                "max_lines": None,
                "overflow": None,
                "color": "#FF808289",
                "decoration": None,
                "soft_wrap": None,
                "min_lines": None,
                "baseline_shift": None,
                "include_font_padding": None,
                "line_height_alignment": None,
                "line_height_trim": None,
                "line_break": None,
            },
        )

    def test_component_scoped_source_facts_drive_dynamic_text_and_asset_spacing(self) -> None:
        source, runtime = component_scoped_runtime_fixture()

        snapshot, _metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=runtime,
            screenshot_path=Path("screen.png"),
            screenshot_sha256="b" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 1200),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 0, "right": 0, "bottom": 0},
            device={},
            timings_ms={},
        )

        by_text = {
            component["style"]["content"].get("text"): component
            for component in snapshot["components"]
        }
        by_asset = {
            component["style"]["asset"].get("resource"): component
            for component in snapshot["components"]
        }
        title = by_text["Buy Car Remote"]
        self.assertEqual(title["style"]["typography"]["font_weight"], 600)
        self.assertEqual(
            title["style"]["typography"]["font_family"], "primaryFontFamily"
        )
        self.assertEqual(
            title["component_context"]["business_component_id"], "source-saving"
        )

        request = by_text["Request"]
        request_icon = by_asset["ic_request"]
        self.assertEqual(
            request["component_context"]["business_component_id"], "source-action"
        )
        self.assertEqual(
            request["component_context"]["business_component_id"],
            request_icon["component_context"]["business_component_id"],
        )
        self.assertAlmostEqual(
            request["bounds_dp"]["y"]
            - request_icon["bounds_dp"]["y"]
            - request_icon["bounds_dp"]["height"],
            10.0,
            places=3,
        )

        harmony_runtime = copy.deepcopy(runtime)
        for component in harmony_runtime:
            text = component["style"]["content"].get("text")
            if text in {"Request", "Buy Car Remote"}:
                component["runtime_id"] = by_text[text]["semantic_key"]
        harmony_snapshot, _harmony_metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=harmony_runtime,
            screenshot_path=Path("harmony-screen.png"),
            screenshot_sha256="c" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 1200),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 0, "right": 0, "bottom": 0},
            device={},
            timings_ms={},
            platform="harmony",
        )
        harmony_by_text = {
            component["style"]["content"].get("text"): component
            for component in harmony_snapshot["components"]
        }
        self.assertEqual(
            harmony_by_text["Request"]["semantic_key"], request["semantic_key"]
        )
        self.assertEqual(
            harmony_by_text["Request"]["source_mapping"]["status"], "unbound"
        )
        self.assertEqual(
            harmony_by_text["Buy Car Remote"]["style"]["typography"]["font_weight"],
            600,
        )

    def test_empty_non_clickable_button_wrapper_is_not_a_semantic_control(self) -> None:
        component = parse_uiautomator_xml(
            b'''<hierarchy rotation="0"><node index="0" text="" resource-id="" class="android.widget.Button" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[0,0][100,100]" /></hierarchy>''',
            (100, 100),
            "example",
        )[0]

        self.assertFalse(semantic_runtime_component(component))

    def test_uiautomator_parser_preserves_control_role_before_clickability(self) -> None:
        components = parse_uiautomator_xml(
            b'''<hierarchy rotation="0">
              <node index="0" text="value" resource-id="" class="android.widget.EditText" package="example" content-desc="" clickable="true" enabled="true" checked="false" selected="false" bounds="[0,0][100,40]" />
              <node index="1" text="" resource-id="" class="android.widget.CheckBox" package="example" content-desc="" clickable="true" enabled="true" checked="true" selected="false" bounds="[0,40][40,80]" />
            </hierarchy>''',
            (100, 100),
            "example",
        )

        self.assertEqual(components[0]["style"]["content"]["role"], "textbox")
        self.assertEqual(components[1]["style"]["content"]["role"], "checkbox")

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

    def test_harmony_parser_preserves_text_input_role_before_clickability(self) -> None:
        components = parse_harmony_layout_json(
            json.dumps({
                "attributes": {"bounds": "[0,0][100,40]", "type": "TextInput", "visible": "true", "clickable": "true"},
                "children": [],
            }).encode("utf-8"),
            (100, 40),
        )

        self.assertEqual(components[0]["type"], "TextField")
        self.assertEqual(components[0]["style"]["content"]["role"], "textbox")

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

    def test_unmatched_stable_runtime_instance_id_is_not_reassigned_by_hierarchy(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        root = copy.deepcopy(next(
            component
            for component in source["components"]
            if component["semantic_key"] == "LoginScreen_Column_10_1"
        ))
        image = copy.deepcopy(next(
            component
            for component in source["components"]
            if component["semantic_key"] == "LoginScreen_Image_13_3"
        ))
        root["children_ids"] = [image["id"]]
        image["parent_id"] = root["id"]
        image["children_ids"] = []
        runtime = parse_harmony_layout_json(
            json.dumps({
                "attributes": {
                    "bounds": "[0,0][1080,2400]",
                    "type": "Column",
                    "id": root["semantic_key"],
                    "key": root["semantic_key"],
                    "visible": "true",
                    "enabled": "true",
                },
                "children": [{
                    "attributes": {
                        "bounds": "[96,360][312,576]",
                        "type": "Image",
                        "id": "SavingCard_AsyncImage_41__instance_item-1",
                        "key": "SavingCard_AsyncImage_41__instance_item-1",
                        "visible": "true",
                        "enabled": "true",
                    },
                    "children": [],
                }],
            }).encode("utf-8"),
            (1080, 2400),
        )

        source_to_runtime, checks, _active, _methods = match_source_to_runtime(
            [root, image], runtime
        )

        self.assertEqual(source_to_runtime, {root["id"]: runtime[0]["id"]})
        self.assertEqual(checks["stable_runtime_id_matches"], 1)
        self.assertEqual(checks["scoped_hierarchy_order_matches"], 0)
        self.assertEqual(
            stable_runtime_fallback_key(runtime[1]),
            "SavingCard_AsyncImage_41__instance_item-1",
        )

    def test_dynamic_text_is_scoped_after_its_runtime_ancestor_is_resolved(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        root = copy.deepcopy(next(
            component
            for component in source["components"]
            if component["semantic_key"] == "LoginScreen_Column_10_1"
        ))
        title = copy.deepcopy(next(
            component
            for component in source["components"]
            if component["semantic_key"] == "LoginScreen_Text_12_2"
        ))
        label = copy.deepcopy(next(
            component
            for component in source["components"]
            if component["semantic_key"] == "LoginScreen_Text_17_5"
        ))
        dynamic = copy.deepcopy(title)
        dynamic["id"] = "source-dynamic-name"
        dynamic["semantic_key"] = "LoginScreen_Text_13_dynamic"
        dynamic["source"]["call_id"] = f"{ROOT_SOURCE}:13:Text:dynamic"
        dynamic["style"]["content"]["text"] = None
        dynamic["parent_id"] = root["id"]
        dynamic["children_ids"] = []
        title["parent_id"] = root["id"]
        label["parent_id"] = root["id"]
        root["children_ids"] = [title["id"], dynamic["id"], label["id"]]

        runtime_root = {
            "id": "runtime-root",
            "type": "View",
            "parent_id": None,
            "children_ids": ["runtime-title", "runtime-dynamic", "runtime-label"],
            "style": copy.deepcopy(root["style"]),
        }
        runtime_title = {
            "id": "runtime-title",
            "type": "Text",
            "parent_id": runtime_root["id"],
            "children_ids": [],
            "style": copy.deepcopy(title["style"]),
        }
        runtime_dynamic = {
            "id": "runtime-dynamic",
            "type": "Text",
            "parent_id": runtime_root["id"],
            "children_ids": [],
            "style": copy.deepcopy(dynamic["style"]),
        }
        runtime_dynamic["style"]["content"]["text"] = "Alexander Michael"
        runtime_label = {
            "id": "runtime-label",
            "type": "Text",
            "parent_id": runtime_root["id"],
            "children_ids": [],
            "style": copy.deepcopy(label["style"]),
        }
        runtime_distractor = {
            "id": "runtime-distractor",
            "type": "Text",
            "parent_id": None,
            "children_ids": [],
            "style": copy.deepcopy(dynamic["style"]),
        }
        runtime_distractor["style"]["content"]["text"] = "Unrelated"

        source_to_runtime, checks, _active, methods = match_source_to_runtime(
            [root, title, dynamic, label],
            [runtime_root, runtime_title, runtime_dynamic, runtime_label, runtime_distractor],
        )

        self.assertEqual(source_to_runtime[root["id"]], runtime_root["id"])
        self.assertEqual(source_to_runtime[dynamic["id"]], runtime_dynamic["id"])
        self.assertEqual(methods[dynamic["id"]], "scoped_hierarchy_order")
        self.assertEqual(checks["scoped_hierarchy_order_matches"], 1)

    def test_dynamic_text_in_row_uses_unique_aligned_runtime_sibling(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        originals = {component["source"]["line"]: component for component in source["components"]}
        owner = copy.deepcopy(originals[10])
        owner.update({
            "id": "source-balance-panel",
            "type": "BalancePanel",
            "semantic_key": "BalancePanel",
            "parent_id": None,
            "children_ids": ["source-balance-row"],
        })
        owner["source"]["custom_component"] = True

        row = copy.deepcopy(originals[10])
        row.update({
            "id": "source-balance-row",
            "type": "Row",
            "semantic_key": "BalancePanel_Row",
            "parent_id": owner["id"],
            "children_ids": ["source-balance-label", "source-balance-spacer", "source-balance-value"],
        })
        row["source"]["custom_component"] = False

        label = copy.deepcopy(originals[12])
        label.update({
            "id": "source-balance-label",
            "semantic_key": "BalancePanel_Label",
            "parent_id": row["id"],
            "children_ids": [],
        })
        label["style"]["content"]["text"] = "Balance"

        spacer = copy.deepcopy(originals[10])
        spacer.update({
            "id": "source-balance-spacer",
            "type": "Spacer",
            "semantic_key": "BalancePanel_Spacer",
            "parent_id": row["id"],
            "children_ids": [],
        })
        spacer["source"]["custom_component"] = False

        value = copy.deepcopy(originals[12])
        value.update({
            "id": "source-balance-value",
            "semantic_key": "BalancePanel_Value",
            "parent_id": row["id"],
            "children_ids": [],
        })
        value["style"]["content"]["text"] = None
        value["unresolved"] = [{
            "path": "style.content.text",
            "expression": "state.balance",
            "reason": "dynamic source expression",
        }]

        runtime_owner = {
            "id": "runtime-panel",
            "type": "View",
            "parent_id": None,
            "children_ids": ["runtime-label", "runtime-value", "runtime-other-row"],
            "bounds_px": {"x": 0, "y": 0, "width": 1080, "height": 600},
            "style": copy.deepcopy(owner["style"]),
        }
        runtime_label = {
            "id": "runtime-label",
            "type": "Text",
            "parent_id": runtime_owner["id"],
            "children_ids": [],
            "bounds_px": {"x": 120, "y": 180, "width": 220, "height": 54},
            "style": copy.deepcopy(label["style"]),
        }
        runtime_value = {
            "id": "runtime-value",
            "type": "Text",
            "parent_id": runtime_owner["id"],
            "children_ids": [],
            "bounds_px": {"x": 900, "y": 176, "width": 60, "height": 60},
            "style": copy.deepcopy(value["style"]),
        }
        runtime_value["style"]["content"]["text"] = "$0"
        runtime_other_row = {
            "id": "runtime-other-row",
            "type": "Text",
            "parent_id": runtime_owner["id"],
            "children_ids": [],
            "bounds_px": {"x": 900, "y": 320, "width": 60, "height": 60},
            "style": copy.deepcopy(value["style"]),
        }
        runtime_other_row["style"]["content"]["text"] = "$1"

        source_to_runtime, checks, _active, methods = match_source_to_runtime(
            [owner, row, label, spacer, value],
            [runtime_owner, runtime_label, runtime_value, runtime_other_row],
        )

        self.assertEqual(source_to_runtime[value["id"]], runtime_value["id"])
        self.assertEqual(methods[value["id"]], "same_row_dynamic_text")
        self.assertEqual(checks["same_row_dynamic_text_matches"], 1)

        ambiguous_runtime = copy.deepcopy(runtime_value)
        ambiguous_runtime.update({
            "id": "runtime-ambiguous-value",
            "bounds_px": {"x": 760, "y": 178, "width": 60, "height": 58},
        })
        ambiguous_runtime["style"]["content"]["text"] = "$2"
        runtime_owner["children_ids"].append(ambiguous_runtime["id"])
        ambiguous_mapping, _checks, _active, _methods = match_source_to_runtime(
            [owner, row, label, spacer, value],
            [runtime_owner, runtime_label, runtime_value, runtime_other_row, ambiguous_runtime],
        )
        self.assertNotIn(value["id"], ambiguous_mapping)

    def test_static_icon_is_rejoined_to_runtime_icon_button(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        originals = {component["source"]["line"]: component for component in source["components"]}
        root = copy.deepcopy(originals[10])
        button = copy.deepcopy(originals[16])
        icon = copy.deepcopy(originals[13])
        button["type"] = "IconButton"
        button["children_ids"] = [icon["id"]]
        button["style"]["content"]["role"] = "button"
        button["style"]["state"]["clickable"] = True
        icon["type"] = "Icon"
        icon["parent_id"] = button["id"]
        icon["style"]["asset"].update({"width_dp": 24.0, "height_dp": 24.0})
        root["children_ids"] = [button["id"]]
        source["components"] = [root, button, icon]

        runtime_root = {
            "id": "runtime-root",
            "runtime_id": root["semantic_key"],
            "type": "View",
            "parent_id": None,
            "children_ids": ["runtime-icon-button"],
            "bounds_px": {"x": 0, "y": 0, "width": 1080, "height": 600},
            "style": copy.deepcopy(root["style"]),
        }
        runtime_button = {
            "id": "runtime-icon-button",
            "runtime_id": button["semantic_key"],
            "type": "IconButton",
            "parent_id": runtime_root["id"],
            "children_ids": [],
            "bounds_px": {"x": 900, "y": 60, "width": 144, "height": 144},
            "runtime_class": "android.view.View",
            "style": copy.deepcopy(button["style"]),
        }

        snapshot, _metrics = build_runtime_page_snapshot(
            source_spec=source,
            runtime_components=[runtime_root, runtime_button],
            screenshot_path=Path("missing-screen.png"),
            screenshot_sha256="b" * 64,
            screenshot_byte_count=1,
            dimensions=(1080, 600),
            density=3.0,
            font_scale=1.0,
            insets_px={"left": 0, "top": 0, "right": 0, "bottom": 0},
            device={},
            timings_ms={},
        )

        runtime_icon_button = next(
            component for component in snapshot["components"]
            if component["semantic_key"] == button["semantic_key"]
        )
        joined_icon = next(
            component for component in snapshot["components"]
            if component["semantic_key"] == icon["semantic_key"]
        )
        self.assertEqual(joined_icon["parent_id"], runtime_icon_button["id"])
        self.assertEqual(joined_icon["source_mapping"]["method"], "source_runtime_parent_join")
        self.assertEqual(joined_icon["bounds_dp"], {
            "x": 312.0,
            "y": 32.0,
            "width": 24.0,
            "height": 24.0,
        })

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

    def test_runtime_source_map_expands_repeated_dynamic_source_instances(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "populated", "a" * 64
        )
        title = copy.deepcopy(next(
            component
            for component in source["components"]
            if component["semantic_key"] == "LoginScreen_Text_12_2"
        ))
        title["parent_id"] = None
        title["children_ids"] = []
        title["unresolved"] = []
        title["style"]["typography"]["color"] = "#FF000000"
        source["components"] = [title]
        source["coverage"] = {
            "source_call_count": 1,
            "emitted_call_count": 1,
            "emitted_call_ratio": 1.0,
        }
        runtime = parse_harmony_layout_json(json.dumps({
            "attributes": {
                "bounds": "[0,0][1080,2400]",
                "type": "root",
                "visible": "true",
                "enabled": "true",
            },
            "children": [
                {
                    "attributes": {
                        "bounds": "[48,200][1032,320]",
                        "type": "Text",
                        "id": "task_title_1",
                        "key": "task_title_1",
                        "text": "Prepare the release",
                        "visible": "true",
                        "enabled": "true",
                    },
                    "children": [],
                },
                {
                    "attributes": {
                        "bounds": "[48,320][1032,440]",
                        "type": "Text",
                        "id": "task_title_2",
                        "key": "task_title_2",
                        "text": "Review pull requests",
                        "visible": "true",
                        "enabled": "true",
                    },
                    "children": [],
                },
            ],
        }).encode("utf-8"), (1080, 2400))
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "harmony",
            "page": {"id": "login", "state": "populated"},
            "mappings": [
                {
                    "runtime_id": f"task_title_{index}",
                    "source_semantic_key": "LoginScreen_Text_12_2",
                    "source_call_id": f"{ROOT_SOURCE}:12:Text:2",
                    "source_instance_key": f"item-{index}",
                }
                for index in (1, 2)
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
            device={},
            timings_ms={},
            platform="harmony",
            runtime_source_map=mapping,
        )

        self.assertEqual(metrics["checks"]["explicit_runtime_source_map_matches"], 2)
        self.assertEqual(metrics["source"]["primitive_visible_candidate_count"], 2)
        self.assertEqual(metrics["source"]["primitive_mapping_ratio"], 1.0)
        self.assertEqual(metrics["source"]["proven_primitive_mapping_ratio"], 1.0)
        self.assertEqual(
            [component["semantic_key"] for component in snapshot["components"]],
            [
                "LoginScreen_Text_12_2__instance_item-1",
                "LoginScreen_Text_12_2__instance_item-2",
            ],
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

    def test_runtime_source_map_records_nonsemantic_layout_elision(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_harmony_layout_json(
            json.dumps(HARMONY_LAYOUT).encode("utf-8"), (1080, 2400)
        )
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "harmony",
            "page": {"id": "login", "state": "default"},
            "mappings": [],
            "runtime_elided_source_components": [{
                "source_semantic_key": "LoginScreen_Column_10_1",
                "source_call_id": f"{ROOT_SOURCE}:10:Column:1",
                "reason": "runtime_nonsemantic_layout_elision",
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

        self.assertNotIn("LoginScreen_Column_10_1", snapshot["unmapped_source_components"])
        self.assertEqual(snapshot["runtime_elided_source_components"], mapping[
            "runtime_elided_source_components"
        ])
        self.assertEqual(metrics["source"]["runtime_elided_primitive_count"], 1)
        self.assertEqual(metrics["source"]["primitive_mapping_ratio"], 1.0)

    def test_runtime_source_map_records_semantic_descendant_flattened_into_mapped_parent(self) -> None:
        source = build_source_page_spec(
            fixture_contract(), ROOT_SOURCE, "LoginScreen", "login", "default", "a" * 64
        )
        runtime = parse_uiautomator_xml(UI_XML.encode("utf-8"), (1080, 2400), "example")
        button_runtime = next(
            item
            for item in runtime
            if item["type"] == "Button" and item["style"]["state"]["clickable"] is True
        )
        button_runtime["runtime_id"] = "submit-button"
        mapping = {
            "schema": "android-to-harmony.runtime-source-map.v1",
            "platform": "android",
            "page": {"id": "login", "state": "default"},
            "mappings": [{
                "runtime_id": "submit-button",
                "source_semantic_key": "LoginScreen_Button_16_4",
                "source_call_id": f"{ROOT_SOURCE}:16:Button:4",
            }],
            "runtime_elided_source_components": [{
                "source_semantic_key": "LoginScreen_Text_17_5",
                "source_call_id": f"{ROOT_SOURCE}:17:Text:5",
                "reason": "runtime_flattened_semantic_descendant",
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
            platform="android",
            runtime_source_map=mapping,
        )

        self.assertEqual(
            snapshot["runtime_elided_source_components"],
            mapping["runtime_elided_source_components"],
        )
        self.assertNotIn("LoginScreen_Text_17_5", snapshot["unmapped_source_components"])
        self.assertEqual(metrics["checks"]["explicit_runtime_source_map_matches"], 1)

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
