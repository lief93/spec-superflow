from __future__ import annotations

import hashlib
import base64
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent


class ExtractAndroidThemeFactsTest(unittest.TestCase):
    def payload(self) -> dict[str, object]:
        return {
            "schema": "android-to-harmony.compose-theme-facts.v1",
            "platform": "android",
            "theme_id": "test-light",
            "capture": {
                "sdk_int": 35,
                "density": 3.5,
                "font_scale": 1.0,
                "layout_direction": "ltr",
            },
            "theme": {
                "colors": {"surface": "#FFF5FAFD"},
                "typography": {},
                "shapes": {},
            },
            "provenance": [{
                "paths": ["theme.colors"],
                "origin": "runtime",
                "source": "MaterialTheme",
            }],
            "unresolved": [],
        }

    def run_extractor(self, log: str, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "extract_android_theme_facts.py"),
                "--output",
                str(output),
            ],
            input=log,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_extracts_one_validated_runtime_theme_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "android-theme-facts.json"
            payload = self.payload()

            result = self.run_extractor(
                "device log\nANDROID_THEME_FACTS:" + json.dumps(payload) + "\n",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            command = json.loads(result.stdout)
            self.assertEqual(command["theme_id"], "test-light")
            self.assertEqual(command["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(json.loads(output.read_text())["theme"]["colors"]["surface"], "#FFF5FAFD")

    def test_rejects_duplicate_markers_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "android-theme-facts.json"
            marker = "ANDROID_THEME_FACTS:" + json.dumps(self.payload()) + "\n"

            result = self.run_extractor(marker + marker, output)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expected exactly one ANDROID_THEME_FACTS", result.stderr)
            self.assertFalse(output.exists())

    def test_extracts_one_gzip_base64_marker_without_logcat_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "android-theme-facts.json"
            encoded = base64.b64encode(
                gzip.compress(json.dumps(self.payload(), separators=(",", ":")).encode())
            ).decode()

            result = self.run_extractor(
                "ANDROID_THEME_FACTS_GZIP_BASE64:" + encoded + "\n",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertLess(len(encoded), 4096)
            self.assertEqual(json.loads(output.read_text())["theme_id"], "test-light")


if __name__ == "__main__":
    unittest.main()
