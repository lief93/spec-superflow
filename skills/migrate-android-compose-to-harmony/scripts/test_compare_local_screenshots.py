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
            self.assertTrue((output / "normalized-left.png").is_file())
            self.assertTrue((output / "normalized-right.png").is_file())
            self.assertTrue((output / "difference.png").is_file())
            self.assertTrue((output / "side-by-side.png").is_file())
            self.assertNotIn(str(left), json.dumps(report))
            self.assertNotIn(str(right), json.dumps(report))
            self.assertNotIn("passed", report)

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
