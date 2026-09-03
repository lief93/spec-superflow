from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def write_png(path: Path, width: int, height: int) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\0" + b"\xff\xff\xff" * width for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


class GeneratePageSnapshotTest(unittest.TestCase):
    def write_capture(self, root: Path, name: str, button_x: int) -> tuple[Path, Path]:
        screenshot = root / f"{name}.png"
        write_png(screenshot, 1080, 2400)
        components = root / f"{name}-components.json"
        components.write_text(
            json.dumps(
                {
                    "schema": "android-to-harmony.component-bounds.v1",
                    "screenshot_dimensions": {"width": 1080, "height": 2400},
                    "components": [
                        {
                            "id": f"{name}-root",
                            "type": "Column",
                            "semantic_key": "HomeScreen",
                            "bounds": {"x": 0, "y": 0, "width": 1080, "height": 2400},
                        },
                        {
                            "id": f"{name}-button",
                            "type": "Button",
                            "semantic_key": "PrimaryButton",
                            "bounds": {"x": button_x, "y": 420, "width": 984, "height": 144},
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return screenshot, components

    def write_source_attributes(self, root: Path) -> Path:
        output = root / "source-attributes.json"
        output.write_text(
            json.dumps(
                {
                    "schema": "android-to-harmony.source-attribute-inventory.v1",
                    "status": "candidate_requires_review",
                    "authoritative": False,
                    "root": {"source": "Home.kt", "composable": "HomeScreen"},
                    "contract_sha256": "1" * 64,
                    "semantic_input_sha256": "2" * 64,
                    "components": [
                        {
                            "semantic_key": "PrimaryButton",
                            "source": "Home.kt",
                            "composable": "PrimaryButton",
                            "attributes": [
                                {
                                    "call_id": "home-button",
                                    "line": 42,
                                    "component": "Button",
                                    "origin": "modifier",
                                    "name": "padding",
                                    "groups": ["geometry"],
                                    "dimensions": [{"value": "16", "unit": "dp"}],
                                    "dimension_resources": [],
                                    "modifier_index": 0,
                                }
                            ],
                        }
                    ],
                    "limitations": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return output

    def write_visual_facts(self, root: Path, platform: str) -> Path:
        output = root / f"{platform}-visual-facts.json"
        output.write_text(
            json.dumps(
                {
                    "schema": "android-to-harmony.component-visual-facts.v1",
                    "platform": platform,
                    "components": [
                        {
                            "semantic_key": "PrimaryButton",
                            "style": {
                                "layout": {
                                    "padding_dp": {"left": 16, "top": 12, "right": 16, "bottom": 12},
                                    "margin_dp": {"left": 0, "top": 8, "right": 0, "bottom": 8},
                                    "layout_direction": "ltr",
                                    "z_index": 2,
                                },
                                "surface": {
                                    "background": {
                                        "type": "linear_gradient",
                                        "colors": ["#FF3366FF", "#FF8844FF"],
                                        "angle_degrees": 90,
                                    },
                                    "corner_radius_dp": {
                                        "top_left": 12,
                                        "top_right": 12,
                                        "bottom_right": 12,
                                        "bottom_left": 12,
                                    },
                                    "border": {"width_dp": 1, "color": "#22000000", "style": "solid"},
                                    "shadows": [
                                        {
                                            "color": "#33000000",
                                            "offset_x_dp": 0,
                                            "offset_y_dp": 4,
                                            "blur_radius_dp": 12,
                                            "spread_radius_dp": 0,
                                        }
                                    ],
                                    "alpha": 1,
                                    "clip": True,
                                },
                                "typography": {
                                    "font_size_sp": 16,
                                    "font_weight": 600,
                                    "font_style": "normal",
                                    "font_family": "sans-serif",
                                    "letter_spacing_sp": 0,
                                    "line_height_sp": 22,
                                    "text_align": "center",
                                    "max_lines": 1,
                                    "overflow": "ellipsis",
                                    "color": "#FFFFFFFF",
                                },
                                "asset": {
                                    "resource": "app.media.primary_icon",
                                    "sha256": "a" * 64,
                                    "width_px": 48,
                                    "height_px": 48,
                                    "content_scale": "fit",
                                    "tint": "#FFFFFFFF",
                                },
                                "transform": {
                                    "translation_x_dp": 0,
                                    "translation_y_dp": 0,
                                    "scale_x": 1,
                                    "scale_y": 1,
                                    "rotation_degrees": 0,
                                },
                                "state": {
                                    "visible": True,
                                    "enabled": True,
                                    "selected": False,
                                    "checked": False,
                                    "clickable": True,
                                },
                                "content": {
                                    "text": "Continue",
                                    "placeholder": None,
                                    "content_description": "Continue",
                                    "role": "button",
                                    "locale": "zh-CN",
                                },
                            },
                            "provenance": [
                                {
                                    "paths": ["style.surface.background", "style.surface.corner_radius_dp"],
                                    "origin": "source_resolved",
                                    "source": "Home.kt:42",
                                },
                                {
                                    "paths": ["style.typography.font_size_sp"],
                                    "origin": "runtime",
                                    "source": "instrumentation",
                                },
                            ],
                            "unresolved": [
                                {
                                    "path": "style.surface.background.dynamic_theme",
                                    "expression": "MaterialTheme.colorScheme.primary",
                                    "reason": "theme value is state dependent",
                                }
                            ],
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return output

    def run_generator(
        self,
        platform: str,
        screenshot: Path,
        components: Path,
        output: Path,
        source_attributes: Path | None = None,
        visual_facts: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT_DIR / f"generate_{platform}_page_json.py"),
            "--page-id",
            "home",
            "--state-id",
            "default",
            "--screenshot",
            str(screenshot),
            "--components",
            str(components),
            "--density",
            "3",
            "--font-scale",
            "1.15",
            "--orientation",
            "portrait",
            "--insets-px",
            "0,72,0,96",
            "--output",
            str(output),
        ]
        if source_attributes is not None:
            command.extend(["--source-attributes", str(source_attributes)])
        if visual_facts is not None:
            command.extend(["--visual-facts", str(visual_facts)])
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_android_and_harmony_emit_the_same_page_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_attributes = self.write_source_attributes(root)
            for platform, button_x in (("android", 48), ("harmony", 60)):
                screenshot, components = self.write_capture(root, platform, button_x)
                visual_facts = self.write_visual_facts(root, platform)
                output = root / f"{platform}-page.json"
                result = self.run_generator(
                    platform,
                    screenshot,
                    components,
                    output,
                    source_attributes,
                    visual_facts,
                )
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                payload = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(payload["schema"], "android-to-harmony.page-snapshot.v2")
                self.assertEqual(payload["platform"], platform)
                self.assertEqual(payload["page"], {"id": "home", "state": "default"})
                self.assertEqual(payload["viewport"]["width_dp"], 360.0)
                self.assertEqual(payload["viewport"]["height_dp"], 800.0)
                self.assertEqual(payload["viewport"]["font_scale"], 1.15)
                self.assertEqual(payload["viewport"]["orientation"], "portrait")
                self.assertEqual(payload["viewport"]["safe_area_dp"]["top"], 24.0)
                self.assertEqual(payload["viewport"]["content_bounds_dp"]["height"], 744.0)
                self.assertEqual(payload["capture"]["screenshot"]["sha256"].__len__(), 64)
                button = next(item for item in payload["components"] if item["semantic_key"] == "PrimaryButton")
                self.assertEqual(button["parent_id"], f"{platform}-root")
                self.assertEqual(button["bounds_dp"]["x"], button_x / 3)
                self.assertEqual(button["source"]["source"], "Home.kt")
                self.assertEqual(button["source"]["attributes"][0]["name"], "padding")
                self.assertEqual(button["style"]["surface"]["background"]["type"], "linear_gradient")
                self.assertEqual(button["style"]["surface"]["corner_radius_dp"]["top_left"], 12.0)
                self.assertEqual(button["style"]["typography"]["font_size_sp"], 16.0)
                self.assertEqual(button["style"]["asset"]["sha256"], "a" * 64)
                self.assertEqual(button["style"]["asset"]["width_dp"], 16.0)
                self.assertEqual(button["style"]["asset"]["height_dp"], 16.0)
                self.assertEqual(button["style"]["layout"]["padding_dp"]["left"], 16.0)
                self.assertEqual(button["style"]["content"]["text"], "Continue")
                self.assertEqual(button["children_ids"], [])
                self.assertEqual(button["sibling_index"], 0)
                self.assertEqual(button["unresolved"][0]["expression"], "MaterialTheme.colorScheme.primary")
                self.assertEqual(button["provenance"][0]["origin"], "source_resolved")

    def test_visual_facts_platform_must_match_generator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            screenshot, components = self.write_capture(root, "android", 48)
            visual_facts = self.write_visual_facts(root, "harmony")
            output = root / "android-page.json"
            result = self.run_generator(
                "android", screenshot, components, output, visual_facts=visual_facts
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("visual facts platform does not match", result.stderr)
            self.assertFalse(output.exists())

    def test_rejects_a_screenshot_that_does_not_match_component_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            screenshot, components = self.write_capture(root, "android", 48)
            write_png(screenshot, 720, 1600)
            output = root / "android-page.json"
            result = self.run_generator("android", screenshot, components, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dimensions do not match", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
