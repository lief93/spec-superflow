from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from benchmark_real_page_pipeline import build_benchmark, semantic_mapping_evidence


ANDROID_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="Title" resource-id="example:id/title" class="android.widget.TextView" package="example" content-desc="" clickable="false" enabled="true" checked="false" selected="false" bounds="[10,20][110,60]" />
</hierarchy>'''

HARMONY_LAYOUT = {
    "attributes": {"bounds": "[0,0][120,200]", "type": ""},
    "children": [
        {
            "attributes": {
                "bounds": "[10,20][110,60]",
                "type": "Text",
                "visible": "true",
                "id": "title",
                "text": "Title",
            },
            "children": [],
        }
    ],
}


def style() -> dict:
    return {
        "asset": {"resource": None, "content_scale": None},
        "content": {"text": "Title", "content_description": None, "placeholder": None},
        "layout": {},
        "state": {"clickable": False, "visible": True},
        "surface": {},
        "transform": {},
        "typography": {"font_size_sp": 16.0, "color": "#FF000000"},
    }


class RealPageBenchmarkTest(unittest.TestCase):
    def test_content_match_requires_stable_id_or_explicit_call_binding_to_count_as_proof(self) -> None:
        source = {"components": [{"semantic_key": "TitleCall", "style": style()}]}
        runtime = {
            "components": [{
                "id": "runtime-1",
                "runtime_id": "business_title",
                "resource_id": None,
                "style": style(),
            }]
        }
        page_component = {
            "id": "runtime-1",
            "semantic_key": "TitleCall",
            "style": style(),
        }

        content_only = semantic_mapping_evidence(source, runtime, {"components": [page_component]})
        self.assertEqual(content_only["exact_source_runtime_content_count"], 1)
        self.assertEqual(content_only["independently_proven_count"], 0)

        page_component["source_mapping"] = {
            "method": "explicit_runtime_source_map",
            "source_call_id": "app/src/main/java/example/Page.kt:10:Text:1",
        }
        explicit = semantic_mapping_evidence(source, runtime, {"components": [page_component]})
        self.assertEqual(explicit["explicit_runtime_source_map_count"], 1)
        self.assertEqual(explicit["independently_proven_ratio"], 1.0)

    def test_real_artifacts_are_independently_bound_and_measured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            android = root / "android"
            harmony = root / "harmony"
            android.mkdir()
            harmony.mkdir()
            screenshot = b"not-a-real-png-but-hash-bound"
            for directory in (android, harmony):
                (directory / "screenshot.png").write_bytes(screenshot)
            (android / "uiautomator.xml").write_bytes(ANDROID_XML)
            (harmony / "uitest-layout.json").write_text(json.dumps(HARMONY_LAYOUT), encoding="utf-8")
            sha = hashlib.sha256(screenshot).hexdigest()
            android_component = {
                "id": "runtime-0",
                "runtime_id": None,
                "resource_id": "example:id/title",
                "type": "Text",
                "bounds_px": {"x": 10, "y": 20, "width": 100, "height": 40},
                "parent_id": None,
                "children_ids": [],
                "sibling_index": 0,
                "semantic_key": "title",
                "style": style(),
                "unresolved": [],
            }
            harmony_component = dict(
                android_component, id="runtime-h-0", runtime_id="title", resource_id=None
            )
            source_component = {
                "id": "source-title",
                "semantic_key": "title",
                "type": "Text",
                "style": style(),
            }
            page_common = {
                "schema": "android-to-harmony.page-snapshot.v2",
                "status": "candidate_requires_review",
                "authoritative": False,
                "page": {"id": "login", "state": "default"},
                "viewport": {"width_px": 120, "height_px": 200},
                "capture": {"screenshot": {"file": "screenshot.png", "sha256": sha}},
            }
            runtime_common = {
                "schema": "android-to-harmony.runtime-tree.v1",
                "screenshot_sha256": sha,
            }
            metrics = {
                "verdict": "pass",
                "source": {
                    "call_count": 1,
                    "emitted_call_count": 1,
                    "emitted_call_ratio": 1.0,
                    "primitive_visible_candidate_count": 1,
                    "primitive_mapped_count": 1,
                    "primitive_mapping_ratio": 1.0,
                    "mapped_unresolved_fact_count": 0,
                    "unresolved_required_visual_fact_count": 0,
                },
                "runtime": {
                    "component_count": 1,
                    "semantic_component_count": 1,
                    "semantic_mapped_count": 1,
                    "semantic_mapping_ratio": 1.0,
                },
                "timings_ms": {"total": 10.0},
            }
            for directory, platform, component in (
                (android, "android", android_component),
                (harmony, "harmony", harmony_component),
            ):
                (directory / "page.json").write_text(
                    json.dumps(dict(page_common, platform=platform, components=[component])), encoding="utf-8"
                )
                (directory / "runtime-tree.json").write_text(
                    json.dumps(dict(runtime_common, platform=platform, components=[component])), encoding="utf-8"
                )
                (directory / "source-page.json").write_text(
                    json.dumps({"components": [source_component]}), encoding="utf-8"
                )
                (directory / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
            comparison = root / "comparison.json"
            comparison.write_text(
                json.dumps(
                    {
                        "verdict": {"status": "pass", "failure_reasons": []},
                        "metrics": {"ssim_color": 1.0, "ssim_luma": 1.0, "ssim_edges": 1.0},
                        "difference_analysis": {
                            "component_presence": {"status": "pass", "missing_in_left": [], "missing_in_right": []},
                            "component_geometry_deltas": [],
                            "component_hierarchy_deltas": [],
                            "component_style_deltas": [],
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = build_benchmark(android, harmony, comparison, "example")

            self.assertEqual(result["verdict"], "pass")
            self.assertEqual(result["extraction_verdict"], "pass")
            self.assertEqual(result["android"]["raw_tree_accuracy"]["exact_ratio"], 1.0)
            self.assertEqual(result["harmony"]["raw_tree_accuracy"]["exact_ratio"], 1.0)
            self.assertEqual(
                result["android"]["semantic_mapping_evidence"]["independently_proven_ratio"], 1.0
            )
            self.assertEqual(
                result["android"]["required_visual_fact_coverage"]["resolved_ratio"], 1.0
            )
            self.assertEqual(
                result["harmony"]["semantic_mapping_evidence"]["direct_stable_id_count"], 1
            )
            self.assertEqual(result["completeness"]["android"]["source_call_ratio"], 1.0)
            self.assertEqual(result["fidelity"]["verdict"], "pass")
            self.assertEqual(result["android"]["artifact_set"], "android")
            self.assertEqual(result["harmony"]["artifact_set"], "harmony")
            self.assertNotIn(str(root), json.dumps(result))

    def test_hash_drift_forces_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            android = root / "android"
            harmony = root / "harmony"
            android.mkdir()
            harmony.mkdir()
            for directory in (android, harmony):
                (directory / "screenshot.png").write_bytes(b"changed")
                (directory / "page.json").write_text(
                    json.dumps(
                        {
                            "page": {"id": "login", "state": "default"},
                            "viewport": {"width_px": 120, "height_px": 200},
                            "capture": {"screenshot": {"sha256": "0" * 64}},
                            "components": [],
                        }
                    ),
                    encoding="utf-8",
                )
                (directory / "runtime-tree.json").write_text(
                    json.dumps({"screenshot_sha256": "0" * 64, "components": []}), encoding="utf-8"
                )
                (directory / "source-page.json").write_text(
                    json.dumps({"components": []}), encoding="utf-8"
                )
                (directory / "metrics.json").write_text(
                    json.dumps(
                        {
                            "verdict": "fail",
                            "source": {"emitted_call_ratio": 0.0, "primitive_mapping_ratio": 0.0},
                            "runtime": {"semantic_mapping_ratio": 0.0},
                            "timings_ms": {"total": 0.0},
                        }
                    ),
                    encoding="utf-8",
                )
            (android / "uiautomator.xml").write_bytes(b"<hierarchy />")
            (harmony / "uitest-layout.json").write_text("{}", encoding="utf-8")
            comparison = root / "comparison.json"
            comparison.write_text(json.dumps({"verdict": {"status": "fail"}, "metrics": {}}), encoding="utf-8")

            result = build_benchmark(android, harmony, comparison, "example")

            self.assertEqual(result["verdict"], "fail")
            self.assertEqual(result["extraction_verdict"], "fail")
            self.assertFalse(result["android"]["capture_binding"]["page_matches_screenshot"])


if __name__ == "__main__":
    unittest.main()
