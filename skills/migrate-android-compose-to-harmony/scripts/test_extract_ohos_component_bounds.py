#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("extract_ohos_component_bounds.py")


def inventory() -> dict[str, object]:
    return {
        "schema": "android-to-harmony.component-bounds.v1",
        "screenshot_dimensions": {"width": 1320, "height": 2856},
        "components": [
            {
                "id": "home_auto_tracking",
                "type": "Column",
                "semantic_key": "AutoTrackingCard",
                "bounds": {"x": 70, "y": 427, "width": 1180, "height": 574},
            }
        ],
    }


class ExtractOhosComponentBoundsTests(unittest.TestCase):
    def test_extracts_v2_runtime_content_insets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "harmony-components.json"
            payload = inventory()
            payload["schema"] = "android-to-harmony.component-bounds.v2"
            payload["content_insets_px"] = {"left": 0, "top": 48, "right": 0, "bottom": 64}
            log = "OHOS_COMPONENT_BOUNDS:" + json.dumps(payload) + "\n"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)],
                input=log, check=False, capture_output=True, text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), payload)

    def test_extracts_one_sanitized_hilog_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "harmony-components.json"
            payload = inventory()
            log = (
                "08-03 15:13:19 I JSAPP: OHOS_COMPONENT_BOUNDS:"
                + json.dumps(payload)
                + "\n"
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)],
                input=log,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), payload)
            command_result = json.loads(result.stdout)
            self.assertTrue(command_result["ok"])
            self.assertEqual(command_result["component_count"], 1)
            self.assertEqual(
                command_result["sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )

    def test_rejects_multiple_records_to_prevent_stale_bounds_pairing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "harmony-components.json"
            record = "OHOS_COMPONENT_BOUNDS:" + json.dumps(inventory()) + "\n"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)],
                input=record + record,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("expected exactly one", result.stderr)
            self.assertFalse(output.exists())

    def test_rejects_display_content_without_leaking_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "harmony-components.json"
            payload = inventory()
            payload["components"][0]["text"] = "private-account-balance"
            log = "OHOS_COMPONENT_BOUNDS:" + json.dumps(payload) + "\n"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)],
                input=log,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported component fields", result.stderr)
            self.assertNotIn("private-account-balance", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
