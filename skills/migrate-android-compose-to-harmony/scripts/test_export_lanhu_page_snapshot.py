from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
EXPORTER = SCRIPT_DIR / "export_lanhu_page_snapshot.py"


class ExportLanhuPageSnapshotTest(unittest.TestCase):
    def test_cli_uses_lanhu_frames_and_manifest_semantics_without_pixel_inference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            version_json = root / "version_json.json"
            component_manifest = root / "component-manifest.json"
            screenshot = root / "android.png"
            output = root / "page.json"
            screenshot.write_bytes(b"not-used-as-generation-input")
            version_json.write_text(
                json.dumps(
                    {
                        "meta": {"sliceScale": 2, "device": "source"},
                        "assets": [],
                        "artboard": {
                            "id": "home--default",
                            "name": "home",
                            "type": "artboard",
                            "frame": {"left": 0, "top": 0, "width": 720, "height": 1600},
                            "layers": [
                                {
                                    "id": "root",
                                    "name": "Root",
                                    "type": "group",
                                    "frame": {"left": 0, "top": 0, "width": 720, "height": 1600},
                                    "layers": [
                                        {
                                            "id": "title",
                                            "name": "Title",
                                            "type": "text",
                                            "frame": {"left": 32, "top": 40, "width": 200, "height": 40},
                                            "layers": [],
                                        },
                                        {
                                            "id": "offscreen",
                                            "name": "Offscreen",
                                            "type": "text",
                                            "frame": {"left": 0, "top": 1800, "width": 100, "height": 40},
                                            "layers": [],
                                        },
                                    ],
                                }
                            ],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            empty_style = {
                "layout": {},
                "surface": {},
                "typography": {},
                "asset": {},
                "content": {},
                "transform": {},
                "state": {},
            }
            component_manifest.write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.lanhu-component-manifest.v1",
                        "page": {"id": "home", "state": "default"},
                        "source_schema": "android-to-harmony.source-page-spec.v1",
                        "source_status": "candidate_requires_runtime_verification",
                        "root_instance_id": "root",
                        "source_instance_count": 3,
                        "definitions": [],
                        "instances": [
                            {
                                "id": "root",
                                "type": "Column",
                                "semantic_key": "HomeRoot",
                                "definition_id": None,
                                "parent_id": None,
                                "children_ids": ["title", "offscreen"],
                                "sibling_index": 0,
                                "frame_dp": {"x": 0, "y": 0, "width": 360, "height": 800},
                                "resolved_layout": {"padding_dp": {}},
                                "geometry_status": "source_resolved",
                                "geometry_evidence": [],
                                "style": empty_style,
                                "custom_draw": {
                                    "kind": "ring_progress",
                                    "value": 80,
                                    "total": 100,
                                    "start_angle_degrees": 0,
                                    "stroke_width_dp": 5,
                                    "track_color": "#FFF2F2F2",
                                    "active_color": "#FF100D40",
                                },
                                "source": {"attributes": []},
                                "provenance": [],
                                "unresolved": [],
                            },
                            {
                                "id": "title",
                                "type": "Text",
                                "semantic_key": "HomeTitle",
                                "definition_id": None,
                                "parent_id": "root",
                                "children_ids": [],
                                "sibling_index": 0,
                                "frame_dp": {"x": 16, "y": 20, "width": 100, "height": 20},
                                "resolved_layout": {"padding_dp": {}},
                                "geometry_status": "source_resolved",
                                "geometry_evidence": [],
                                "style": empty_style,
                                "source": {"attributes": []},
                                "provenance": [],
                                "unresolved": [],
                            },
                            {
                                "id": "offscreen",
                                "type": "Text",
                                "semantic_key": "Offscreen",
                                "definition_id": None,
                                "parent_id": "root",
                                "children_ids": [],
                                "sibling_index": 1,
                                "frame_dp": {"x": 0, "y": 900, "width": 50, "height": 20},
                                "resolved_layout": {"padding_dp": {}},
                                "geometry_status": "source_resolved",
                                "geometry_evidence": [],
                                "style": empty_style,
                                "source": {"attributes": []},
                                "provenance": [],
                                "unresolved": [],
                            },
                        ],
                        "layout_relationships": [],
                        "limitations": [],
                        "geometry_summary": {},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(EXPORTER),
                    "--version-json",
                    str(version_json),
                    "--component-manifest",
                    str(component_manifest),
                    "--screenshot",
                    str(screenshot),
                    "--output",
                    str(output),
                    "--density",
                    "3",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["schema"], "android-to-harmony.page-snapshot.v2")
            self.assertEqual(payload["page"], {"id": "home", "state": "default"})
            self.assertEqual(payload["viewport"]["content_bounds_dp"], {
                "x": 0,
                "y": 0,
                "width": 360,
                "height": 800,
            })
            self.assertEqual([item["id"] for item in payload["components"]], ["root", "title"])
            title = payload["components"][1]
            self.assertEqual(title["bounds_dp"], {"x": 16, "y": 20, "width": 100, "height": 20})
            self.assertEqual(title["parent_id"], "root")
            self.assertEqual(payload["components"][0]["custom_draw"]["kind"], "ring_progress")
            self.assertEqual(payload["components"][0]["custom_draw"]["stroke_width_dp"], 5)
            self.assertEqual(payload["runtime_elided_source_components"], [
                {
                    "source_semantic_key": "Offscreen",
                    "source_call_id": "unavailable:offscreen",
                    "reason": "outside_artboard",
                }
            ])
            self.assertEqual(
                payload["capture"]["screenshot"]["sha256"],
                hashlib.sha256(screenshot.read_bytes()).hexdigest(),
            )
            self.assertEqual(payload["input_hashes"]["geometry_role"], "version_json")
            self.assertEqual(
                payload["input_hashes"]["semantics_and_style_role"],
                "component_manifest",
            )
            self.assertEqual(
                payload["input_hashes"]["screenshot_role"],
                "evidence_binding_only",
            )
            from ui_migration.contracts.lanhu_storage import pack_lanhu_document
            document = json.loads(version_json.read_text())
            repeated = {'detail':'diagnostic '*40}
            document['meta']['diagnostics'] = [repeated, repeated]
            version_json.write_text(json.dumps(pack_lanhu_document(document)))
            packed_result = subprocess.run(result.args, text=True, capture_output=True, check=False)
            self.assertEqual(packed_result.returncode, 0, packed_result.stderr)
            packed_payload = json.loads(output.read_text())
            self.assertEqual(packed_payload['components'], payload['components'])
            self.assertEqual(packed_payload['viewport'], payload['viewport'])


if __name__ == "__main__":
    unittest.main()
