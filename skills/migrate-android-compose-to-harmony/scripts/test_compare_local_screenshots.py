#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("compare_local_screenshots.py")
HAS_PILLOW = importlib.util.find_spec("PIL") is not None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def write_ppm(path: Path, width: int, height: int, changed: bool = False) -> None:
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            if changed and width // 3 <= x < width * 2 // 3 and height // 3 <= y < height * 2 // 3:
                pixels.extend((255, 0, 0))
            else:
                pixels.extend((x * 3 % 256, y * 5 % 256, 80))
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + pixels)


def write_checkerboard(path: Path, width: int, height: int, inverted: bool) -> None:
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            lit = ((x // 4 + y // 4) % 2 == 0) != inverted
            value = 255 if lit else 0
            pixels.extend((value, value, value))
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + pixels)


def write_solid_ppm(path: Path, width: int, height: int, color: tuple[int, int, int] = (80, 90, 100)) -> None:
    path.write_bytes(
        f"P6\n{width} {height}\n255\n".encode("ascii")
        + bytes(color) * width * height
    )


def write_inset_ppm(
    path: Path,
    width: int,
    height: int,
    top: int,
    bottom: int,
    bar_color: tuple[int, int, int],
) -> None:
    pixels = bytearray()
    for y in range(height):
        color = bar_color if y < top or y >= height - bottom else (80, 90, 100)
        pixels.extend(bytes(color) * width)
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + pixels)


def write_component_inventory(path: Path, side: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "android-to-harmony.component-bounds.v1",
                "screenshot_dimensions": {"width": 64, "height": 48},
                "components": [
                    {
                        "id": f"{side}-summary-card",
                        "type": "Card",
                        "semantic_key": "summary-card",
                        "bounds": {"x": 16, "y": 8, "width": 32, "height": 32},
                    },
                    {
                        "id": f"{side}-footer",
                        "type": "NavigationBar",
                        "bounds": {"x": 0, "y": 40, "width": 64, "height": 8},
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_page_snapshot(path: Path, side: str, screenshot: Path) -> None:
    component_x = 16 if side == "android" else 18
    path.write_text(
        json.dumps(
            {
                "schema": "android-to-harmony.page-snapshot.v1",
                "status": "candidate_requires_review",
                "authoritative": False,
                "platform": side,
                "page": {"id": "home", "state": "default"},
                "viewport": {
                    "width_px": 64,
                    "height_px": 48,
                    "density": 1,
                    "width_dp": 64,
                    "height_dp": 48,
                },
                "capture": {
                    "screenshot": {
                        "file": screenshot.name,
                        "byte_count": screenshot.stat().st_size,
                        "sha256": sha256_file(screenshot),
                    }
                },
                "input_hashes": {"component_inventory_sha256": "a" * 64},
                "components": [
                    {
                        "id": f"{side}-summary-card",
                        "type": "Card",
                        "semantic_key": "summary-card",
                        "bounds_px": {"x": component_x, "y": 8, "width": 32, "height": 32},
                        "bounds_dp": {"x": component_x, "y": 8, "width": 32, "height": 32},
                        "parent_id": None,
                        "parent_mapping": "smallest-containing-runtime-component",
                    }
                ],
                "unmapped_source_components": [],
                "limitations": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_page_snapshot_v2(
    path: Path,
    side: str,
    screenshot: Path,
    density: float,
    radius_dp: float,
    font_size_sp: float,
    background: str,
    asset_sha256: str,
    page_id: str = "home",
    state_id: str = "default",
    font_scale: float = 1,
    logical_content_size: tuple[float, float] = (64, 48),
    unresolved: list[dict[str, str]] | None = None,
    content_insets_px: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> None:
    width, height = (192, 144) if side == "android" else (128, 96)
    bounds = (
        {"x": 48, "y": 24, "width": 96, "height": 96}
        if side == "android"
        else {"x": 32, "y": 16, "width": 64, "height": 64}
    )
    empty_style = {
        "layout": {
            "padding_dp": {"left": 4, "top": 4, "right": 4, "bottom": 4},
            "margin_dp": None,
            "layout_direction": "ltr",
            "z_index": 0,
        },
        "surface": {
            "background": {"type": "solid", "color": background},
            "corner_radius_dp": {
                "top_left": radius_dp,
                "top_right": radius_dp,
                "bottom_right": radius_dp,
                "bottom_left": radius_dp,
            },
            "border": None,
            "shadows": [],
            "alpha": 1,
            "clip": True,
        },
        "typography": {
            "font_size_sp": font_size_sp,
            "font_weight": 500,
            "font_style": "normal",
            "font_family": None,
            "letter_spacing_sp": 0,
            "line_height_sp": 20,
            "text_align": "center",
            "max_lines": 1,
            "overflow": "ellipsis",
            "color": "#FFFFFFFF",
        },
        "asset": {
            "resource": "app.media.icon",
            "sha256": asset_sha256,
            "width_px": 72 if side == "android" else 48,
            "height_px": 72 if side == "android" else 48,
            "width_dp": 24,
            "height_dp": 24,
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
    }
    inset_left, inset_top, inset_right, inset_bottom = content_insets_px
    content_width = width - inset_left - inset_right
    content_height = height - inset_top - inset_bottom
    path.write_text(
        json.dumps(
            {
                "schema": "android-to-harmony.page-snapshot.v2",
                "status": "candidate_requires_review",
                "authoritative": False,
                "platform": side,
                "page": {"id": page_id, "state": state_id},
                "viewport": {
                    "width_px": width,
                    "height_px": height,
                    "density": density,
                    "font_scale": font_scale,
                    "orientation": "landscape",
                    "width_dp": 64,
                    "height_dp": 48,
                    "safe_area_px": {
                        "left": inset_left, "top": inset_top,
                        "right": inset_right, "bottom": inset_bottom,
                    },
                    "safe_area_dp": {
                        "left": inset_left / density, "top": inset_top / density,
                        "right": inset_right / density, "bottom": inset_bottom / density,
                    },
                    "content_bounds_px": {
                        "x": inset_left, "y": inset_top,
                        "width": content_width, "height": content_height,
                    },
                    "content_bounds_dp": {
                        "x": inset_left / density,
                        "y": inset_top / density,
                        "width": logical_content_size[0],
                        "height": logical_content_size[1],
                    },
                },
                "capture": {
                    "screenshot": {
                        "file": screenshot.name,
                        "byte_count": screenshot.stat().st_size,
                        "sha256": sha256_file(screenshot),
                    }
                },
                "input_hashes": {"component_inventory_sha256": "a" * 64},
                "components": [
                    {
                        "id": f"{side}-summary-card",
                        "type": "Card",
                        "semantic_key": "summary-card",
                        "bounds_px": bounds,
                        "bounds_dp": {"x": 16, "y": 8, "width": 32, "height": 32},
                        "parent_id": None,
                        "parent_mapping": "smallest-containing-runtime-component",
                        "children_ids": [],
                        "sibling_index": 0,
                        "style": empty_style,
                        "provenance": [],
                        "unresolved": unresolved or [],
                    }
                ],
                "unmapped_source_components": [],
                "unmapped_visual_fact_components": [],
                "limitations": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_source_attribute_inventory(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "android-to-harmony.source-attribute-inventory.v1",
                "status": "candidate_requires_review",
                "authoritative": False,
                "root": {
                    "source": "app/src/main/java/example/Summary.kt",
                    "composable": "SummaryCard",
                },
                "contract_sha256": "a" * 64,
                "semantic_input_sha256": "b" * 64,
                "components": [
                    {
                        "semantic_key": "summary-card",
                        "source": "app/src/main/java/example/Summary.kt",
                        "composable": "SummaryCard",
                        "attributes": [
                            {
                                "call_id": "app/src/main/java/example/Summary.kt:12:Column:1",
                                "line": 12,
                                "component": "Column",
                                "origin": "modifier",
                                "name": "padding",
                                "modifier_index": 0,
                                "groups": ["geometry"],
                                "dimensions": [{"value": "16", "unit": "dp"}],
                                "dimension_resources": [],
                            },
                            {
                                "call_id": "app/src/main/java/example/Summary.kt:18:Text:2",
                                "line": 18,
                                "component": "Text",
                                "origin": "semantic_argument",
                                "name": "fontSize",
                                "groups": ["typography"],
                                "dimensions": [{"value": "18", "unit": "sp"}],
                                "dimension_resources": [],
                            },
                            {
                                "call_id": "app/src/main/java/example/Summary.kt:18:Text:2",
                                "line": 18,
                                "component": "Text",
                                "origin": "semantic_argument",
                                "name": "color",
                                "groups": ["color"],
                                "dimensions": [],
                                "dimension_resources": [],
                            },
                        ],
                    }
                ],
                "limitations": ["candidate only"],
            }
        )
        + "\n",
        encoding="utf-8",
    )


@unittest.skipUnless(HAS_PILLOW, "Pillow is required")
class LocalScreenshotComparisonTests(unittest.TestCase):
    def run_compare(
        self,
        *arguments: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_identical_images_produce_perfect_metrics_and_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-label", "android",
                "--right-label", "harmony",
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            command_result = json.loads(result.stdout)
            self.assertTrue(command_result["ok"])
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], "android-to-harmony.local-image-comparison.v1")
            self.assertEqual(report["metrics"]["ssim_color"], 1.0)
            self.assertEqual(report["metrics"]["ssim_luma"], 1.0)
            self.assertEqual(report["metrics"]["ssim_edges"], 1.0)
            self.assertEqual(report["raw_metrics"]["ssim_color"], 1.0)
            self.assertEqual(report["raw_metrics"]["ssim_luma"], 1.0)
            self.assertEqual(
                report["rasterization_comparison"],
                {
                    "tolerance": "gaussian",
                    "radius_px": 0.5,
                    "scope": ["ssim_color", "ssim_luma"],
                },
            )
            self.assertEqual(
                report["edge_comparison"],
                {
                    "detector": "Pillow FIND_EDGES",
                    "tolerance": "gaussian",
                    "radius_px": 1.0,
                },
            )
            self.assertTrue((output / "normalized-left.png").is_file())
            self.assertTrue((output / "normalized-right.png").is_file())
            self.assertTrue((output / "difference.png").is_file())
            self.assertTrue((output / "side-by-side.png").is_file())
            self.assertNotIn(str(left), json.dumps(report))
            self.assertNotIn(str(right), json.dumps(report))
            self.assertEqual(command_result["verdict"], "fail")
            self.assertEqual(report["verdict"]["status"], "fail")

    def test_changed_pixels_lower_metrics_without_computing_a_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48, changed=True)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertLess(report["metrics"]["ssim_color"], 1.0)
            self.assertLess(report["metrics"]["ssim_luma"], 1.0)
            self.assertLess(report["metrics"]["ssim_edges"], 1.0)
            self.assertFalse(report["authoritative"])
            self.assertEqual(report["quality"], "diagnostic_candidate")

    def test_half_pixel_rasterization_tolerance_preserves_raw_metrics(self) -> None:
        from PIL import Image, ImageDraw, ImageFilter

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.png"
            right = root / "harmony.png"
            output = root / "comparison"
            for path, x in ((left, 31), (right, 32)):
                image = Image.new("RGB", (64, 64), "white")
                draw = ImageDraw.Draw(image)
                draw.line((x, 8, x, 55), fill="black", width=1)
                image.filter(ImageFilter.GaussianBlur(0.35)).save(path)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertGreater(
                report["metrics"]["ssim_color"],
                report["raw_metrics"]["ssim_color"],
            )
            self.assertGreater(
                report["metrics"]["ssim_luma"],
                report["raw_metrics"]["ssim_luma"],
            )

    def test_explicit_crops_and_target_size_are_bound_to_hashed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            write_ppm(left, 80, 60)
            write_ppm(right, 100, 90, changed=True)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-crop", "10,8,40,30",
                "--right-crop", "20,15,60,45",
                "--target-size", "32x24",
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            command_result = json.loads(result.stdout)
            report_path = output / "comparison.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(command_result["report_sha256"], sha256_file(report_path))
            self.assertEqual(report["inputs"][0]["crop"], {"x": 10, "y": 8, "width": 40, "height": 30})
            self.assertEqual(report["inputs"][1]["crop"], {"x": 20, "y": 15, "width": 60, "height": 45})
            self.assertEqual(report["inputs"][0]["crop_source"], "explicit")
            self.assertEqual(report["inputs"][1]["crop_source"], "explicit")
            self.assertEqual(report["normalization"]["width"], 32)
            self.assertEqual(report["normalization"]["height"], 24)
            self.assertEqual(report["comparator"]["sha256"], sha256_file(SCRIPT))
            region = report["difference_analysis"]["regions"][0]
            self.assertEqual(region["left_input_bounds"], {"x": 10, "y": 8, "width": 40, "height": 30})
            self.assertEqual(region["right_input_bounds"], {"x": 20, "y": 15, "width": 60, "height": 45})
            for artifact in report["artifacts"]:
                self.assertEqual(artifact["sha256"], sha256_file(output / artifact["file"]))

    def test_out_of_bounds_crop_fails_without_leaving_an_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            write_ppm(left, 32, 24)
            write_ppm(right, 32, 24)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-crop", "20,10,20,20",
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("left crop exceeds screenshot bounds", result.stderr)
            self.assertFalse(output.exists())

    def test_existing_output_directory_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            sentinel = output / "keep.txt"
            write_ppm(left, 32, 24)
            write_ppm(right, 32, 24)
            output.mkdir()
            sentinel.write_text("owned by caller\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("output directory already exists", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "owned by caller\n")

    def test_pillow_comparison_does_not_require_external_image_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            write_ppm(left, 32, 24)
            write_ppm(right, 32, 24)
            environment = os.environ.copy()
            environment["PATH"] = ""

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--output-dir", str(output),
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(len(report["tools"]), 1)
            self.assertEqual(report["tools"][0]["name"], "Pillow")
            self.assertNotIn("executable_sha256", report["tools"][0])

    def test_symbolic_link_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.ppm"
            linked = root / "linked.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            write_ppm(original, 32, 24)
            write_ppm(right, 32, 24)
            linked.symlink_to(original)

            result = self.run_compare(
                "--left", str(linked),
                "--right", str(right),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("left screenshot must not be a symbolic link", result.stderr)
            self.assertFalse(output.exists())

    def test_negative_ssim_is_reported_for_inverted_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            write_checkerboard(left, 64, 64, inverted=False)
            write_checkerboard(right, 64, 64, inverted=True)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertLess(report["metrics"]["ssim_color"], 0.0)

    def test_changed_pixels_are_reported_as_ranked_mapped_regions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48, changed=True)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            analysis = report["difference_analysis"]
            self.assertGreater(analysis["changed_pixel_ratio"], 0.0)
            self.assertGreater(analysis["mean_absolute_channel_delta"], 0.0)
            self.assertGreaterEqual(len(analysis["regions"]), 1)
            region = analysis["regions"][0]
            bounds = region["normalized_bounds"]
            self.assertLessEqual(bounds["x"], 32)
            self.assertLessEqual(bounds["y"], 24)
            self.assertGreater(bounds["x"] + bounds["width"], 32)
            self.assertGreater(bounds["y"] + bounds["height"], 24)
            self.assertEqual(region["left_input_bounds"], bounds)
            self.assertEqual(region["right_input_bounds"], bounds)
            self.assertGreater(region["severity"], 0.0)
            self.assertGreaterEqual(len(analysis["hotspots"]), 1)
            hotspot = next(
                candidate
                for candidate in analysis["hotspots"]
                if candidate["normalized_bounds"]["x"] <= 32
                < candidate["normalized_bounds"]["x"] + candidate["normalized_bounds"]["width"]
                and candidate["normalized_bounds"]["y"] <= 24
                < candidate["normalized_bounds"]["y"] + candidate["normalized_bounds"]["height"]
            )
            hotspot_bounds = hotspot["normalized_bounds"]
            self.assertLessEqual(hotspot_bounds["x"], 32)
            self.assertLessEqual(hotspot_bounds["y"], 24)
            self.assertGreater(hotspot_bounds["x"] + hotspot_bounds["width"], 32)
            self.assertGreater(hotspot_bounds["y"] + hotspot_bounds["height"], 24)
            self.assertTrue((output / "annotated-difference.png").is_file())
            self.assertNotIn("suggested_fix", json.dumps(analysis))

    def test_hotspots_map_to_sanitized_components_on_both_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_components = root / "android-components.json"
            right_components = root / "harmony-components.json"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48, changed=True)
            write_component_inventory(left_components, "android")
            write_component_inventory(right_components, "harmony")

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-components", str(left_components),
                "--right-components", str(right_components),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(len(report["component_inventories"]), 2)
            inventory_records = {
                inventory["side"]: inventory
                for inventory in report["component_inventories"]
            }
            self.assertEqual(inventory_records["left"]["sha256"], sha256_file(left_components))
            self.assertEqual(inventory_records["right"]["sha256"], sha256_file(right_components))
            serialized = json.dumps(report)
            self.assertNotIn(str(left_components), serialized)
            self.assertNotIn(str(right_components), serialized)
            mapped_hotspot = next(
                hotspot
                for hotspot in report["difference_analysis"]["hotspots"]
                if hotspot["left_component_candidates"]
                and hotspot["right_component_candidates"]
            )
            self.assertEqual(
                mapped_hotspot["left_component_candidates"][0]["component_id"],
                "android-summary-card",
            )
            self.assertEqual(
                mapped_hotspot["right_component_candidates"][0]["component_id"],
                "harmony-summary-card",
            )
            pair = mapped_hotspot["semantic_pair_candidates"][0]
            self.assertEqual(pair["semantic_key"], "summary-card")
            self.assertEqual(pair["left_component_id"], "android-summary-card")
            self.assertEqual(pair["right_component_id"], "harmony-summary-card")
            impact_summary = report["difference_analysis"]["component_impact_summary"]
            self.assertFalse(impact_summary["authoritative"])
            right_summary = next(
                component
                for component in impact_summary["right"]
                if component["source_component"] == "summary-card"
            )
            self.assertEqual(right_summary["component_id"], "harmony-summary-card")
            self.assertGreaterEqual(right_summary["hotspot_count"], 1)
            self.assertEqual(right_summary["hotspot_count"], len(right_summary["hotspot_ids"]))
            self.assertGreater(right_summary["max_match_score"], 0.0)
            self.assertNotIn("text", serialized)
            self.assertNotIn("suggested_fix", serialized)

    def test_component_impacts_map_to_sanitized_source_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_components = root / "android-components.json"
            right_components = root / "harmony-components.json"
            source_attributes = root / "source-attributes.json"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48, changed=True)
            write_component_inventory(left_components, "android")
            write_component_inventory(right_components, "harmony")
            write_source_attribute_inventory(source_attributes)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-components", str(left_components),
                "--right-components", str(right_components),
                "--source-attributes", str(source_attributes),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(
                report["source_attribute_inventory"]["sha256"],
                sha256_file(source_attributes),
            )
            right_summary = next(
                component
                for component in report["difference_analysis"]["component_impact_summary"]["right"]
                if component["source_component"] == "summary-card"
            )
            source_candidate = right_summary["source_attribute_candidates"][0]
            self.assertEqual(
                source_candidate["source"],
                "app/src/main/java/example/Summary.kt",
            )
            self.assertEqual(source_candidate["composable"], "SummaryCard")
            self.assertEqual(
                set(source_candidate["candidate_attribute_groups"]),
                {"color", "geometry", "typography"},
            )
            self.assertTrue(
                any(
                    attribute["name"] == "padding"
                    and attribute["line"] == 12
                    and attribute["modifier_index"] == 0
                    for attribute in source_candidate["attributes"]
                )
            )
            serialized = json.dumps(report)
            self.assertNotIn(str(source_attributes), serialized)
            self.assertNotIn("expression", serialized)
            self.assertNotIn("suggested_fix", serialized)

    def test_page_snapshots_map_hotspots_and_are_bound_to_the_exact_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48, changed=True)
            write_page_snapshot(left_page, "android", left)
            write_page_snapshot(right_page, "harmony", right)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-components", str(left_page),
                "--right-components", str(right_page),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            records = {item["side"]: item for item in report["component_inventories"]}
            self.assertEqual(records["left"]["schema"], "android-to-harmony.page-snapshot.v1")
            self.assertEqual(records["right"]["schema"], "android-to-harmony.page-snapshot.v1")
            hotspot = next(
                item
                for item in report["difference_analysis"]["hotspots"]
                if item["semantic_pair_candidates"]
            )
            self.assertEqual(hotspot["semantic_pair_candidates"][0]["semantic_key"], "summary-card")
            geometry = report["difference_analysis"]["component_geometry_deltas"][0]
            self.assertEqual(geometry["semantic_key"], "summary-card")
            self.assertEqual(geometry["delta_dp"]["x"], 2.0)
            self.assertEqual(geometry["max_abs_delta_dp"], 2.0)
            self.assertTrue(geometry["over_1dp"])

    def test_v2_page_snapshots_compare_style_and_allow_equal_logical_viewports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_ppm(left, 192, 144)
            write_ppm(right, 128, 96)
            write_page_snapshot_v2(
                left_page, "android", left, 3, 12, 16, "#FF3366FF", "a" * 64
            )
            write_page_snapshot_v2(
                right_page, "harmony", right, 2, 15, 18, "#FF3377FF", "b" * 64
            )

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-components", str(left_page),
                "--right-components", str(right_page),
                "--target-size", "64x48",
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            viewport = report["viewport_compatibility"]
            self.assertFalse(viewport["same_pixel_size"])
            self.assertTrue(viewport["same_logical_content_size"])
            self.assertTrue(viewport["pixel_comparison_compatible"])
            style = report["difference_analysis"]["component_style_deltas"][0]
            by_path = {item["path"]: item for item in style["comparisons"]}
            radius = by_path["style.surface.corner_radius_dp.top_left"]
            self.assertEqual(radius["delta"], 3.0)
            self.assertTrue(radius["over_tolerance"])
            font_size = by_path["style.typography.font_size_sp"]
            self.assertEqual(font_size["delta"], 2.0)
            self.assertTrue(font_size["over_tolerance"])
            color = by_path["style.surface.background.color"]
            self.assertEqual(color["max_channel_delta"], 17)
            self.assertTrue(color["over_tolerance"])
            asset = by_path["style.asset.sha256"]
            self.assertFalse(asset["equal"])
            self.assertTrue(asset["over_tolerance"])
            self.assertNotIn("style.asset.width_px", by_path)
            self.assertEqual(by_path["style.asset.width_dp"]["delta"], 0.0)

    def test_v2_page_snapshots_accept_exact_inactive_source_branch_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
            write_page_snapshot_v2(right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64)
            inactive = [{
                "source_semantic_key": "HomeScreen_Snackbar_80_9",
                "source_call_id": "app/src/main/java/example/HomeScreen.kt:80:Snackbar:9",
                "reason": "inactive_source_branch",
            }]
            for page in (left_page, right_page):
                payload = json.loads(page.read_text(encoding="utf-8"))
                payload["inactive_source_components"] = inactive
                page.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(report["verdict"]["status"], "pass")

    def test_v2_page_snapshot_rejects_malformed_inactive_source_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            output = root / "comparison"
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
            payload = json.loads(left_page.read_text(encoding="utf-8"))
            payload["inactive_source_components"] = [{
                "source_semantic_key": "HomeScreen_Snackbar_80_9",
                "source_call_id": "app/src/main/java/example/HomeScreen.kt:80:Snackbar:9",
                "reason": "unmatched_component",
            }]
            left_page.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("inactive source component is malformed", result.stderr)
            self.assertFalse(output.exists())

    def test_v2_reports_missing_semantic_components_and_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
            write_page_snapshot_v2(right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64)
            payload = json.loads(right_page.read_text(encoding="utf-8"))
            payload["components"] = []
            right_page.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            command = json.loads(result.stdout)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(report["difference_analysis"]["component_presence"]["missing_in_right"], ["summary-card"])
            self.assertEqual(report["verdict"]["status"], "fail")
            self.assertEqual(command["verdict"], "fail")

    def test_v2_hierarchy_and_sibling_order_changes_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
            write_page_snapshot_v2(right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64)
            for page, prefix in ((left_page, "android"), (right_page, "harmony")):
                payload = json.loads(page.read_text(encoding="utf-8"))
                card = payload["components"][0]
                root_component = {
                    **card,
                    "id": f"{prefix}-root",
                    "semantic_key": "root",
                    "bounds_px": {"x": 0, "y": 0, "width": 192 if prefix == "android" else 128, "height": 144 if prefix == "android" else 96},
                    "bounds_dp": {"x": 0, "y": 0, "width": 64, "height": 48},
                    "parent_id": None,
                    "children_ids": [f"{prefix}-summary-card"] if prefix == "android" else [],
                    "sibling_index": 0,
                }
                card["parent_id"] = root_component["id"] if prefix == "android" else None
                card["sibling_index"] = 0 if prefix == "android" else 1
                payload["components"] = [root_component, card]
                page.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            hierarchy = next(
                item for item in report["difference_analysis"]["component_hierarchy_deltas"]
                if item["semantic_key"] == "summary-card"
            )
            self.assertTrue(hierarchy["parent_changed"])
            self.assertTrue(hierarchy["sibling_index_changed"])
            root_hierarchy = next(
                item for item in report["difference_analysis"]["component_hierarchy_deltas"]
                if item["semantic_key"] == "root"
            )
            self.assertTrue(root_hierarchy["children_order_changed"])
            self.assertEqual(report["verdict"]["status"], "fail")

    def test_v2_rejects_different_page_or_state_before_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
            write_page_snapshot_v2(
                right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64,
                page_id="settings", state_id="error",
            )

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("page/state mismatch", result.stderr)
            self.assertFalse(output.exists())

    def test_v2_logical_viewport_or_font_scale_mismatch_disables_pixels_and_fails(self) -> None:
        for case, logical_size, font_scale in (
            ("logical-size", (60, 48), 1.0),
            ("font-scale", (64, 48), 1.3),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                left = root / "android.ppm"
                right = root / "harmony.ppm"
                left_page = root / "android-page.json"
                right_page = root / "harmony-page.json"
                output = root / "comparison"
                write_solid_ppm(left, 192, 144)
                write_solid_ppm(right, 128, 96)
                write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
                write_page_snapshot_v2(
                    right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64,
                    logical_content_size=logical_size, font_scale=font_scale,
                )
                result = self.run_compare(
                    "--left", str(left), "--right", str(right),
                    "--left-components", str(left_page), "--right-components", str(right_page),
                    "--target-size", "64x48", "--output-dir", str(output),
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
                self.assertFalse(report["viewport_compatibility"]["pixel_comparison_compatible"])
                self.assertEqual(report["verdict"]["status"], "fail")

    def test_v2_unresolved_facts_are_blocking_even_without_numeric_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            unresolved = [{
                "path": "style.surface.background.dynamic_theme",
                "expression": "theme.primary",
                "reason": "runtime theme was not resolved",
            }]
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64, unresolved=unresolved)
            write_page_snapshot_v2(right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64)

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            style = report["difference_analysis"]["component_style_deltas"][0]
            self.assertEqual(style["over_tolerance_count"], 0)
            self.assertEqual(style["unresolved_count"], 1)
            self.assertEqual(style["blocking_issue_count"], 1)
            self.assertEqual(style["status"], "fail")
            self.assertEqual(report["verdict"]["status"], "fail")

    def test_v2_identical_complete_inputs_emit_pass_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
            write_page_snapshot_v2(right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64)

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["verdict"], "pass")
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(report["verdict"]["status"], "pass")

    def test_v2_automatically_crops_system_bars_and_compares_content_relative_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_inset_ppm(left, 192, 144, 12, 12, (255, 0, 0))
            write_inset_ppm(right, 128, 96, 12, 4, (0, 0, 255))
            write_page_snapshot_v2(
                left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64,
                logical_content_size=(64, 40), content_insets_px=(0, 12, 0, 12),
            )
            write_page_snapshot_v2(
                right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64,
                logical_content_size=(64, 40), content_insets_px=(0, 12, 0, 4),
            )
            right_payload = json.loads(right_page.read_text(encoding="utf-8"))
            right_component = right_payload["components"][0]
            right_component["bounds_px"]["y"] = 20
            right_component["bounds_dp"]["y"] = 10
            right_page.write_text(json.dumps(right_payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x40", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(report["inputs"][0]["crop_source"], "page_snapshot_content_bounds")
            self.assertEqual(report["inputs"][0]["crop"], {"x": 0, "y": 12, "width": 192, "height": 120})
            self.assertEqual(report["inputs"][1]["crop"], {"x": 0, "y": 12, "width": 128, "height": 80})
            self.assertTrue(report["viewport_compatibility"]["pixel_comparison_compatible"])
            self.assertEqual(report["metrics"]["ssim_color"], 1.0)
            geometry = report["difference_analysis"]["component_geometry_deltas"][0]
            self.assertEqual(geometry["coordinate_space"], "content_relative_logical_units")
            self.assertEqual(geometry["max_abs_delta_dp"], 0.0)
            self.assertEqual(report["verdict"]["status"], "pass")

    def test_v2_uses_proven_pre_transform_contract_instead_of_platform_runtime_aabb(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
            write_page_snapshot_v2(right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64)
            proven_paths = [
                "style.layout.height_dp",
                "style.transform.translation_x_dp",
                "style.transform.translation_y_dp",
                "style.transform.scale_x",
                "style.transform.scale_y",
                "style.transform.rotation_degrees",
            ]
            for page in (left_page, right_page):
                payload = json.loads(page.read_text(encoding="utf-8"))
                component = payload["components"][0]
                component["style"]["layout"]["height_dp"] = 40
                component["style"]["transform"] = {
                    "translation_x_dp": 12,
                    "translation_y_dp": 0,
                    "scale_x": 1,
                    "scale_y": 1,
                    "rotation_degrees": -45,
                }
                component["provenance"] = [
                    {
                        "paths": proven_paths,
                        "origin": "source_resolved",
                        "source": "source-attribute-inventory",
                    }
                ]
                page.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            right_payload = json.loads(right_page.read_text(encoding="utf-8"))
            right_component = right_payload["components"][0]
            right_component["bounds_px"] = {"x": 32, "y": 40, "width": 64, "height": 16}
            right_component["bounds_dp"] = {"x": 16, "y": 20, "width": 32, "height": 8}
            right_page.write_text(json.dumps(right_payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            geometry = report["difference_analysis"]["component_geometry_deltas"][0]
            self.assertEqual(
                geometry["coordinate_space"],
                "source_resolved_pre_transform_layout_and_transform",
            )
            self.assertEqual(
                geometry["runtime_bounds_diagnostic"]["delta_dp"]["height"], -24.0
            )
            self.assertFalse(geometry["over_1dp"])
            self.assertEqual(report["verdict"]["status"], "pass")

    def test_v2_does_not_exempt_transformed_runtime_aabb_without_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            right_page = root / "harmony-page.json"
            output = root / "comparison"
            write_solid_ppm(left, 192, 144)
            write_solid_ppm(right, 128, 96)
            write_page_snapshot_v2(left_page, "android", left, 3, 12, 16, "#FFFFFFFF", "a" * 64)
            write_page_snapshot_v2(right_page, "harmony", right, 2, 12, 16, "#FFFFFFFF", "a" * 64)
            for page in (left_page, right_page):
                payload = json.loads(page.read_text(encoding="utf-8"))
                component = payload["components"][0]
                component["style"]["layout"]["height_dp"] = 40
                component["style"]["transform"] = {
                    "translation_x_dp": 12,
                    "translation_y_dp": 0,
                    "scale_x": 1,
                    "scale_y": 1,
                    "rotation_degrees": -45,
                }
                page.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            right_payload = json.loads(right_page.read_text(encoding="utf-8"))
            right_payload["components"][0]["bounds_dp"]["height"] = 8
            right_payload["components"][0]["bounds_px"]["height"] = 16
            right_page.write_text(json.dumps(right_payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left), "--right", str(right),
                "--left-components", str(left_page), "--right-components", str(right_page),
                "--target-size", "64x48", "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            geometry = report["difference_analysis"]["component_geometry_deltas"][0]
            self.assertEqual(geometry["coordinate_space"], "content_relative_logical_units")
            self.assertTrue(geometry["over_1dp"])
            self.assertEqual(report["verdict"]["status"], "fail")

    def test_page_snapshot_rejects_a_stale_screenshot_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            left_page = root / "android-page.json"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48)
            write_page_snapshot(left_page, "android", left)
            write_ppm(left, 64, 48, changed=True)

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-components", str(left_page),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("screenshot SHA-256 does not match", result.stderr)
            self.assertFalse(output.exists())

    def test_source_attribute_inventory_rejects_expression_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            source_attributes = root / "source-attributes.json"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48)
            write_source_attribute_inventory(source_attributes)
            payload = json.loads(source_attributes.read_text(encoding="utf-8"))
            payload["components"][0]["attributes"][0]["expression"] = "privateValue"
            source_attributes.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--source-attributes", str(source_attributes),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported attribute fields", result.stderr)
            self.assertNotIn("privateValue", result.stderr)
            self.assertFalse(output.exists())

    def test_component_inventory_rejects_display_text_without_leaking_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            components = root / "components.json"
            output = root / "comparison"
            write_ppm(left, 64, 48)
            write_ppm(right, 64, 48)
            write_component_inventory(components, "android")
            payload = json.loads(components.read_text(encoding="utf-8"))
            payload["components"][0]["text"] = "private-account-balance"
            components.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-components", str(components),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported component fields", result.stderr)
            self.assertNotIn("private-account-balance", result.stderr)
            self.assertFalse(output.exists())

    def test_component_inventory_dimensions_must_match_its_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "android.ppm"
            right = root / "harmony.ppm"
            components = root / "components.json"
            output = root / "comparison"
            write_ppm(left, 80, 60)
            write_ppm(right, 80, 60)
            write_component_inventory(components, "android")

            result = self.run_compare(
                "--left", str(left),
                "--right", str(right),
                "--left-components", str(components),
                "--output-dir", str(output),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("dimensions do not match the screenshot", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
