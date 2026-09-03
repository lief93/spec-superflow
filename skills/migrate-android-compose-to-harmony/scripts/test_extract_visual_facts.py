from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


class ExtractVisualFactsTest(unittest.TestCase):
    def payload(self, platform: str) -> dict[str, object]:
        return {
            "schema": "android-to-harmony.component-visual-facts.v1",
            "platform": platform,
            "components": [
                {
                    "semantic_key": "PrimaryButton",
                    "style": {
                        "surface": {
                            "background": {"type": "solid", "color": "#FFFFFFFF"},
                            "corner_radius_dp": {
                                "top_left": 12,
                                "top_right": 12,
                                "bottom_right": 12,
                                "bottom_left": 12,
                            },
                        },
                        "content": {"text": "Continue", "role": "button"},
                    },
                    "provenance": [
                        {
                            "paths": ["style.surface.background"],
                            "origin": "runtime",
                            "source": "page-capture",
                        }
                    ],
                    "unresolved": [],
                }
            ],
        }

    def test_platform_extractors_validate_and_hash_one_marker(self) -> None:
        for platform, marker in (
            ("android", "ANDROID_VISUAL_FACTS:"),
            ("harmony", "HARMONY_VISUAL_FACTS:"),
        ):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / f"{platform}-visual-facts.json"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT_DIR / f"extract_{platform}_visual_facts.py"),
                        "--output",
                        str(output),
                    ],
                    input=f"test output\n{marker}{json.dumps(self.payload(platform))}\n",
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                command = json.loads(result.stdout)
                self.assertEqual(command["component_count"], 1)
                self.assertEqual(command["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
                self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["platform"], platform)

    def test_extractor_rejects_cross_platform_marker_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "android-visual-facts.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "extract_android_visual_facts.py"),
                    "--output",
                    str(output),
                ],
                input="ANDROID_VISUAL_FACTS:" + json.dumps(self.payload("harmony")) + "\n",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("platform does not match", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
