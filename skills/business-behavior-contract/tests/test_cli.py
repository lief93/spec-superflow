from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def run_cli(name: str, *arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / name), *map(str, arguments)],
        capture_output=True,
        text=True,
        check=False,
    )


class BehaviorContractCliTests(unittest.TestCase):
    def test_catalog_and_scaffold_expose_the_six_review_families(self) -> None:
        catalog = run_cli("collect_behavior_rules.py", "catalog")
        self.assertEqual(catalog.returncode, 0, catalog.stdout + catalog.stderr)
        payload = json.loads(catalog.stdout)
        self.assertEqual(
            [family["id"] for family in payload["families"]],
            [
                "ownership",
                "events_state_navigation",
                "data",
                "async_lifecycle",
                "validation_security",
                "scenarios_evidence",
            ],
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.json"
            output = root / "collection.json"
            inventory.write_text(
                json.dumps(
                    {
                        "schema_version": "behavior-source-inventory.v1",
                        "source_revision": "source-1",
                        "scope_id": "checkout",
                        "items": [
                            {
                                "id": "ACTION-SUBMIT",
                                "category": "action",
                                "record_kind": "action",
                                "summary": "Submit checkout",
                                "source_evidence": ["Checkout.kt:10"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            scaffold = run_cli(
                "collect_behavior_rules.py",
                "scaffold",
                "--inventory",
                inventory,
                "--output",
                output,
            )
            self.assertEqual(scaffold.returncode, 0, scaffold.stdout + scaffold.stderr)
            generated = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(generated["status"], "pending")
            self.assertEqual(generated["inventory_ids"], ["ACTION-SUBMIT"])
            self.assertEqual(len(generated["categories"]), 6)
            self.assertTrue(
                all(item["disposition"] == "unresolved" for item in generated["categories"])
            )


if __name__ == "__main__":
    unittest.main()
