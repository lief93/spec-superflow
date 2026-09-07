from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from real_page_pipeline import static_style_for_call


class SourceThemeResolutionTest(unittest.TestCase):
    def test_unparsed_canvas_is_explicitly_unresolved(self) -> None:
        call = {
            "source": "Progress.kt",
            "line": 30,
            "component": "Canvas",
            "semantic_arguments": {},
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }

        _style, _provenance, unresolved = static_style_for_call(call, {}, None)

        self.assertEqual(unresolved[0]["path"], "style.custom_draw")
        self.assertIn("structural extraction", unresolved[0]["reason"])

    def test_material_color_scheme_role_resolves_from_selected_source_theme(self) -> None:
        call = {
            "source": "Home.kt",
            "line": 10,
            "component": "Box",
            "semantic_arguments": {},
            "positional_arguments": [],
            "ordered_modifier_chain": [{
                "name": "background",
                "arguments": "MaterialTheme.colorScheme.primary",
                "dimensions": [],
            }],
        }

        style, _provenance, unresolved = static_style_for_call(
            call,
            {},
            None,
            theme_colors={"primary": "#FF100D40"},
        )

        self.assertEqual(
            style["surface"]["background"],
            {"type": "solid", "color": "#FF100D40"},
        )
        self.assertEqual(unresolved, [])

    def test_safe_snapshot_asset_sha_is_used_when_asset_bytes_are_local_only(self) -> None:
        call = {
            "source": "Header.kt",
            "line": 12,
            "component": "Image",
            "semantic_arguments": {
                "painter": {"expression": "painterResource(R.drawable.ic_cover)"},
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }

        style, provenance, unresolved = static_style_for_call(
            call,
            {},
            None,
            asset_index={
                "ic_cover": {
                    "path": "app/src/main/res/drawable/ic_cover.xml",
                    "sha256": "a" * 64,
                }
            },
        )

        self.assertEqual(style["asset"]["resource"], "ic_cover")
        self.assertEqual(style["asset"]["sha256"], "a" * 64)
        self.assertIn(
            {
                "paths": ["style.asset.sha256"],
                "origin": "source_resolved",
                "source": "app/src/main/res/drawable/ic_cover.xml",
            },
            provenance,
        )
        self.assertEqual(unresolved, [])

    def test_box_content_alignment_is_preserved(self) -> None:
        call = {
            "source": "Header.kt",
            "line": 20,
            "component": "BoxWithConstraints",
            "semantic_arguments": {
                "contentAlignment": {"expression": "Alignment.TopEnd"},
            },
            "positional_arguments": [],
            "ordered_modifier_chain": [],
        }

        style, _provenance, unresolved = static_style_for_call(call, {}, None)

        self.assertEqual(style["layout"]["alignment"], "TopEnd")
        self.assertEqual(unresolved, [])

    def test_custom_dashed_border_is_structured_from_source_arguments(self) -> None:
        call = {
            "source": "Buttons.kt",
            "line": 10,
            "component": "Button",
            "semantic_arguments": {},
            "positional_arguments": [],
            "ordered_modifier_chain": [{
                "name": "then",
                "arguments": (
                    "Modifier.dashedBorder("
                    "strokeWidth = 1.5.dp, "
                    "color = MaterialTheme.colorScheme.primary, "
                    "cornerRadiusDp = 10.dp)"
                ),
                "dimensions": [
                    {"unit": "dp", "value": "1.5"},
                    {"unit": "dp", "value": "10"},
                ],
            }],
        }

        style, _provenance, unresolved = static_style_for_call(
            call,
            {},
            None,
            theme_colors={"primary": "#FF100D40"},
        )

        self.assertEqual(
            style["surface"]["border"],
            {
                "width_dp": 1.5,
                "color": "#FF100D40",
                "style": "dashed",
            },
        )
        self.assertEqual(
            style["surface"]["corner_radius_dp"],
            {
                "top_left": 10.0,
                "top_right": 10.0,
                "bottom_right": 10.0,
                "bottom_left": 10.0,
            },
        )
        self.assertEqual(unresolved, [])


if __name__ == "__main__":
    unittest.main()
