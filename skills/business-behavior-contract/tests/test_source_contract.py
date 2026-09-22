from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_behavior_source import census, digest  # noqa: E402
from validate_behavior_contract_v2 import validate  # noqa: E402


SOURCE = "package sample\n\nfun submit() = save()\n"
FAMILIES = [
    "ownership",
    "events_state_navigation",
    "data",
    "async_lifecycle",
    "validation_security",
    "scenarios_evidence",
]


def write_snapshot(root: Path) -> tuple[dict, dict]:
    root.mkdir(exist_ok=True)
    source = root / "Checkout.kt"
    source.write_text(SOURCE, encoding="utf-8")
    source_hash = hashlib.sha256(SOURCE.encode()).hexdigest()
    manifest = {
        "schema_version": "behavior-source-snapshot.v1",
        "source_revision": "rev-1",
        "text_files": ["Checkout.kt"],
        "text_file_sha256": {"Checkout.kt": source_hash},
        "blocked_files": [],
    }
    (root / ".behavior-source-safe.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    scope = {
        "schema_version": "behavior-source-scope.v1",
        "id": "checkout",
        "kind": "page",
        "source_revision": "rev-1",
        "entry_paths": ["Checkout.kt"],
    }
    return manifest, scope


def complete_fixture(root: Path) -> tuple[dict, dict, dict, dict]:
    snapshot = root / "snapshot"
    _, scope = write_snapshot(snapshot)
    current = census(snapshot, scope)
    source_hash = hashlib.sha256(SOURCE.encode()).hexdigest()
    inventory = {
        "schema_version": "behavior-source-inventory.v1",
        "source_revision": "rev-1",
        "scope_id": "checkout",
        "items": [
            {
                "id": "ACTION-SUBMIT",
                "category": "action",
                "record_kind": "action",
                "summary": "Submit checkout",
                "source_evidence": ["source"],
            }
        ],
    }
    collection = {
        "schema_version": "behavior-collection.v1",
        "status": "reviewed",
        "source_revision": "rev-1",
        "inventory_ids": ["ACTION-SUBMIT"],
        "anchors": [
            {
                "id": "source",
                "kind": "source",
                "path": "Checkout.kt",
                "start_line": 1,
                "end_line": 3,
                "file_sha256": source_hash,
                "span_sha256": source_hash,
            }
        ],
        "entities": [
            {
                "id": "page",
                "kind": "page",
                "owner_id": None,
                "anchor_ids": ["source"],
                "source_inventory_ids": ["ACTION-SUBMIT"],
            }
        ],
        "relationships": [],
        "facts": [
            {
                "id": "submit",
                "kind": "action",
                "owner_id": "page",
                "contract_ids": ["ACTION-SUBMIT"],
                "anchor_ids": ["source"],
                "source_inventory_ids": ["ACTION-SUBMIT"],
                "trigger": "submit request",
                "handler": "submit",
                "outcomes": ["save is invoked"],
                "source_expressions": ["fun submit() = save()"],
            },
            {
                "id": "submit-scenario",
                "kind": "scenario",
                "owner_id": "page",
                "contract_ids": ["SCN-SUBMIT"],
                "anchor_ids": ["source"],
                "source_inventory_ids": ["ACTION-SUBMIT"],
                "action_ids": ["submit"],
                "given": "checkout is visible",
                "when": "submit is requested",
                "then": ["save is invoked"],
                "evidence_kind": "source",
            },
        ],
        "categories": [],
    }
    records = {
        "ownership": ["page"],
        "events_state_navigation": ["submit"],
        "scenarios_evidence": ["submit-scenario"],
    }
    for family in FAMILIES:
        ids = records.get(family, [])
        collection["categories"].append(
            {
                "family": family,
                "disposition": "applicable" if ids else "not_applicable",
                "rationale": "Reviewed against the fixed checkout source scope",
                "anchor_ids": ["source"],
                "record_ids": ids,
            }
        )
    contract = {
        "schema_version": "behavior-contract.v2",
        "identity": {"contract_id": "checkout", "source_revision": "rev-1"},
        "scope": {"included_scopes": ["checkout"], "excluded": []},
        "screens": [{"id": "checkout"}],
        "states": [],
        "actions": [
            {
                "id": "ACTION-SUBMIT",
                "trigger": "submit request",
                "guard": "checkout visible",
                "handler_chain": ["submit"],
                "transition": "save",
                "effects": ["save"],
                "observable_results": ["save invoked"],
                "scenario_ids": ["SCN-SUBMIT"],
                "source_inventory_ids": ["ACTION-SUBMIT"],
            }
        ],
        "navigation": [],
        "domain": {},
        "data_flows": [],
        "async_states": [],
        "platform_effects": {"items": [], "none_reason": "not applicable"},
        "lifecycle": [],
        "observables": [{"id": "SAVE-INVOKED"}],
        "scenarios": [
            {
                "id": "SCN-SUBMIT",
                "action_ids": ["ACTION-SUBMIT"],
                "given": "checkout visible",
                "when": "submit requested",
                "then": ["save invoked"],
                "android_evidence": ["source"],
            }
        ],
        "traceability": {
            "source_inventory": "inventory.json",
            "target_implementation": [
                {"id": "ACTION-SUBMIT", "status": "missing", "target": None}
            ],
        },
        "unresolved": [],
        "collection": collection,
        "source_closure": {
            "schema_version": "behavior-source-closure.v1",
            "census_sha256": current["census_sha256"],
            "inventory_sha256": digest(inventory),
            "bindings": [
                {
                    "obligation_id": obligation["id"],
                    "record_ids": ["page"]
                    if obligation["kind"] == "declaration"
                    else ["submit"],
                    "scenario_ids": ["SCN-SUBMIT"],
                }
                for obligation in current["obligations"]
            ],
        },
    }
    review = {
        "schema_version": "behavior-source-review.v1",
        "verdict": "pass",
        "reviewer": "independent-reviewer",
        "scope_sha256": current["scope_sha256"],
        "census_sha256": current["census_sha256"],
        "contract_sha256": digest(contract),
        "unresolved": [],
        "dependency_edges": current["dependency_edges"],
        "external_dependencies": current["external_dependencies"],
        "expectations": [
            {
                "id": f"EXPECT-{index}",
                "summary": "Source behavior is represented",
                "obligation_ids": [obligation["id"]],
                "record_ids": ["page"]
                if obligation["kind"] == "declaration"
                else ["submit"],
                "scenario_ids": ["SCN-SUBMIT"],
            }
            for index, obligation in enumerate(current["obligations"], 1)
        ],
    }
    return contract, inventory, scope, review


class SourceContractTests(unittest.TestCase):
    def test_census_rejects_stale_or_symbolic_snapshot_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, scope = write_snapshot(root)
            self.assertTrue(census(root, scope)["obligations"])
            (root / "Checkout.kt").write_text(SOURCE + "// changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash differs"):
                census(root, scope)

        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            external = Path(outside) / "Checkout.kt"
            external.write_text(SOURCE, encoding="utf-8")
            (root / "linked").symlink_to(Path(outside), target_is_directory=True)
            (root / ".behavior-source-safe.json").write_text(
                json.dumps(
                    {
                        "schema_version": "behavior-source-snapshot.v1",
                        "source_revision": "rev-1",
                        "text_files": ["linked/Checkout.kt"],
                        "text_file_sha256": {
                            "linked/Checkout.kt": hashlib.sha256(SOURCE.encode()).hexdigest()
                        },
                    }
                ),
                encoding="utf-8",
            )
            scope = {
                "schema_version": "behavior-source-scope.v1",
                "id": "checkout",
                "kind": "page",
                "source_revision": "rev-1",
                "entry_paths": ["linked/Checkout.kt"],
            }
            with self.assertRaisesRegex(ValueError, "symbolic|escapes"):
                census(root, scope)

    def test_source_validation_requires_full_current_closure_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract, inventory, scope, review = complete_fixture(root)
            for name, payload in (
                ("contract.json", contract),
                ("inventory.json", inventory),
                ("scope.json", scope),
                ("review.json", review),
            ):
                (root / name).write_text(json.dumps(payload), encoding="utf-8")
            command = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "validate_behavior_contract_v2.py"),
                    "--phase",
                    "source",
                    "--contract",
                    str(root / "contract.json"),
                    "--inventory",
                    str(root / "inventory.json"),
                    "--snapshot",
                    str(root / "snapshot"),
                    "--source-scope",
                    str(root / "scope.json"),
                    "--source-review",
                    str(root / "review.json"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, command.returncode, command.stdout + command.stderr)
            result = json.loads(command.stdout)
            self.assertEqual("pass", result["verdict"], result["errors"])
            changed = copy.deepcopy(contract)
            changed["source_closure"]["bindings"].pop()
            rejected = validate(
                changed,
                inventory,
                phase="source",
                snapshot=root / "snapshot",
                source_scope=scope,
                source_review=review,
            )
            self.assertEqual("fail", rejected["verdict"])
            self.assertTrue(rejected["source_closure"]["missing"])

    def test_target_validation_accepts_only_matching_executed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract, inventory, scope, review = complete_fixture(root)
            contract["traceability"]["target_implementation"][0] = {
                "id": "ACTION-SUBMIT",
                "status": "implemented",
                "target": "Checkout.submit",
            }
            review["contract_sha256"] = digest(contract)
            target = root / "target"
            target.mkdir()
            evidence = {
                "schema_version": "behavior-scenario-evidence.v1",
                "scenario_id": "SCN-SUBMIT",
                "source_revision": "rev-1",
                "target_revision": "target-1",
                "scope_id": "checkout",
                "execution_status": "executed",
                "verdict": "pass",
            }
            (target / "submit.json").write_text(json.dumps(evidence), encoding="utf-8")
            results = {
                "schema_version": "behavior-scenario-results.v1",
                "contract_id": "checkout",
                "source_revision": "rev-1",
                "target_revision": "target-1",
                "scenarios": [
                    {"id": "SCN-SUBMIT", "verdict": "pass", "evidence": ["submit.json"]}
                ],
            }
            accepted = validate(
                contract,
                inventory,
                phase="target",
                scenario_results=results,
                snapshot=root / "snapshot",
                source_scope=scope,
                source_review=review,
                target=target,
            )
            self.assertEqual("pass", accepted["verdict"], accepted["errors"])
            evidence["target_revision"] = "stale"
            (target / "submit.json").write_text(json.dumps(evidence), encoding="utf-8")
            rejected = validate(
                contract,
                inventory,
                phase="target",
                scenario_results=results,
                snapshot=root / "snapshot",
                source_scope=scope,
                source_review=review,
                target=target,
            )
            self.assertEqual("fail", rejected["verdict"])
            self.assertIn("mismatched", " ".join(rejected["errors"]))

    def test_symbol_scan_fails_closed_for_unmapped_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Screen.kt"
            source.write_text(
                "fun Screen(\n  onSubmit: () -> Unit,\n  title: String\n) {}\n",
                encoding="utf-8",
            )
            config = root / "config.json"
            inventory = root / "inventory.json"
            config.write_text(
                json.dumps(
                    {
                        "groups": [
                            {
                                "id": "screen",
                                "file": "Screen.kt",
                                "kind": "function_parameters",
                                "symbol": "Screen",
                                "name_pattern": "^on[A-Z]",
                            }
                        ],
                        "mapping": {},
                    }
                ),
                encoding="utf-8",
            )
            inventory.write_text(
                json.dumps(
                    {
                        "source_revision": "rev-1",
                        "scope_id": "screen",
                        "items": [{"id": "ACTION-SUBMIT"}],
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "scan_android_behavior_symbols.py"),
                    "--config",
                    str(config),
                    "--source-root",
                    str(root),
                    "--inventory",
                    str(inventory),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(1, result.returncode)
            self.assertEqual(["screen:onSubmit"], json.loads(result.stdout)["unmapped_symbols"])

            escaped = json.loads(config.read_text(encoding="utf-8"))
            escaped["groups"][0]["file"] = "../Screen.kt"
            config.write_text(json.dumps(escaped), encoding="utf-8")
            traversal = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "scan_android_behavior_symbols.py"),
                    "--config",
                    str(config),
                    "--source-root",
                    str(root),
                    "--inventory",
                    str(inventory),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(1, traversal.returncode)
            self.assertIn("unsafe source path", traversal.stdout)


if __name__ == "__main__":
    unittest.main()
