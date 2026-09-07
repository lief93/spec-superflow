#!/usr/bin/env python3

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from aggregate_gate_evidence import artifact_satisfies_gate
from scan_android_behavior_symbols import scan
from validate_behavior_contract_v2 import validate


def inventory() -> dict:
    return {
        "schema_version": "behavior-source-inventory.v1",
        "source_revision": "source-rev",
        "scope_id": "tasks",
        "items": [
            {
                "id": "INV-ACTION-REFRESH",
                "category": "action",
                "summary": "Refresh tasks",
                "source_evidence": ["TasksScreen.kt:42"],
            },
            {
                "id": "INV-STATE-LOADING",
                "category": "state",
                "summary": "Loading state",
                "source_evidence": ["TasksViewModel.kt:30"],
            },
        ],
    }


def contract(status: str = "missing", target: str | None = None) -> dict:
    return {
        "schema_version": "behavior-contract.v2",
        "identity": {
            "contract_id": "tasks-contract",
            "source_revision": "source-rev",
        },
        "scope": {"included_scopes": ["tasks"], "excluded": []},
        "screens": [{"id": "tasks"}],
        "states": [
            {
                "id": "STATE-LOADING",
                "source_inventory_ids": ["INV-STATE-LOADING"],
            }
        ],
        "actions": [
            {
                "id": "ACTION-REFRESH",
                "trigger": "tap refresh",
                "guard": "screen visible",
                "handler_chain": ["TasksViewModel.refresh"],
                "transition": "content -> loading -> content",
                "effects": ["reload repository"],
                "observable_results": ["loading toggles", "items rendered"],
                "scenario_ids": ["SCN-REFRESH"],
                "source_inventory_ids": ["INV-ACTION-REFRESH"],
            }
        ],
        "navigation": [],
        "domain": {},
        "data_flows": [],
        "async_states": [],
        "platform_effects": {"items": [], "none_reason": "not applicable"},
        "lifecycle": [],
        "observables": [{"id": "OBS-ITEMS"}],
        "scenarios": [
            {
                "id": "SCN-REFRESH",
                "action_ids": ["ACTION-REFRESH"],
                "given": "tasks screen",
                "when": "refresh",
                "then": ["loading toggles", "items rendered"],
                "android_evidence": ["TasksViewModelTest.refresh"],
            }
        ],
        "traceability": {
            "source_inventory": "tasks.inventory.json",
            "target_implementation": [
                {
                    "id": "ACTION-REFRESH",
                    "status": status,
                    "target": target,
                }
            ],
        },
        "unresolved": [],
    }


def scenario_results(verdict: str = "pass") -> dict:
    return {
        "schema_version": "behavior-scenario-results.v1",
        "contract_id": "tasks-contract",
        "source_revision": "source-rev",
        "target_revision": "target-rev",
        "scenarios": [
            {
                "id": "SCN-REFRESH",
                "verdict": verdict,
                "evidence": ["tasks-refresh-uitest.json"],
            }
        ],
    }


class BehaviorContractV2Tests(unittest.TestCase):
    def checked_validate(self, c, i, **kwargs):
        # Existing behavior tests retain a valid collection prerequisite so their
        # original action/scenario assertions remain independently sensitive.
        from test_behavior_collection import fixture
        from test_behavior_source_closure import bind_source_closure, reviewed_fixture
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _ = fixture(root / 'snapshot')
            c['collection'] = proof['collection']
            c['collection']['facts'][0]['source_expressions'].extend([
                'fun refresh() { loading = true; repository.refresh(); loading = false }',
                'loading = true', 'loading = false'])
            for item in i['items']:
                item['source_evidence'] = ['source']
            for scenario in c['scenarios']:
                if scenario.get('android_evidence'):
                    scenario['android_evidence'] = ['source']
            current = bind_source_closure(root, c, i)
            review = reviewed_fixture(root, c, current)
            return validate(c, i, snapshot=root / 'snapshot', source_scope=current['scope'],
                            source_review=review, **kwargs)

    def test_normal_source_and_target_gate_require_collection_proof(self) -> None:
        for phase in ("source", "target"):
            with self.subTest(phase=phase):
                result = validate(
                    contract("implemented", "Index.ets#refresh"), inventory(),
                    phase=phase, scenario_results=scenario_results(),
                )
                self.assertEqual("fail", result["verdict"])
                self.assertTrue(any("collection" in e for e in result["errors"]))

    def test_source_phase_accepts_complete_inventory_before_target_implementation(self) -> None:
        result = self.checked_validate(contract(), inventory(), phase="source")
        self.assertEqual("pass", result["verdict"])
        self.assertEqual(100.0, result["source_inventory"]["percent"])
        self.assertEqual(0.0, result["target"]["action_coverage_percent"])

    def test_source_phase_fails_when_inventory_fact_is_unmapped(self) -> None:
        changed = contract()
        changed["states"][0]["source_inventory_ids"] = []
        result = self.checked_validate(changed, inventory(), phase="source")
        self.assertEqual("fail", result["verdict"])
        self.assertIn("INV-STATE-LOADING", result["source_inventory"]["missing"])

    def test_source_phase_fails_without_android_scenario_evidence(self) -> None:
        changed = contract()
        changed["scenarios"][0]["android_evidence"] = []
        result = self.checked_validate(changed, inventory(), phase="source")
        self.assertEqual("fail", result["verdict"])
        self.assertTrue(any("lacks Android evidence" in item for item in result["errors"]))

    def test_source_phase_fails_when_action_has_no_scenario(self) -> None:
        changed = contract()
        changed["scenarios"] = []
        result = self.checked_validate(changed, inventory(), phase="source")
        self.assertEqual("fail", result["verdict"])
        self.assertTrue(any("no acceptance scenario" in item for item in result["errors"]))

    def test_source_phase_fails_closed_on_unresolved_fact(self) -> None:
        changed = contract()
        changed["unresolved"] = [{"id": "UNKNOWN", "question": "retry semantics"}]
        result = self.checked_validate(changed, inventory(), phase="source")
        self.assertEqual("fail", result["verdict"])
        self.assertEqual(1, result["contract"]["unresolved_count"])

    def test_target_phase_requires_concrete_implementation(self) -> None:
        result = self.checked_validate(
            contract(), inventory(), phase="target", scenario_results=scenario_results()
        )
        self.assertEqual("fail", result["verdict"])
        self.assertTrue(result['source_complete'], result['errors'])
        self.assertFalse(result['runtime_complete'])
        self.assertTrue(any("is not implemented" in item for item in result["errors"]))

    def test_target_phase_requires_passing_scenario_evidence(self) -> None:
        result = self.checked_validate(
            contract("implemented", "Index.ets#refresh"),
            inventory(),
            phase="target",
            scenario_results=scenario_results("fail"),
        )
        self.assertEqual("fail", result["verdict"])
        self.assertEqual(0.0, result["scenario_results"]["percent"])

    def test_target_phase_does_not_treat_implementation_and_claimed_results_as_execution(self) -> None:
        result = self.checked_validate(
            contract("implemented", "Index.ets#refresh"),
            inventory(),
            phase="target",
            scenario_results=scenario_results(),
        )
        self.assertEqual("fail", result["verdict"])
        self.assertEqual(100.0, result["target"]["action_coverage_percent"])
        self.assertEqual(0.0, result["scenario_results"]["percent"])
        self.assertTrue(result['source_complete'])
        self.assertFalse(result['runtime_complete'])

    def test_behavior_contract_gate_rejects_plain_unit_tests(self) -> None:
        self.assertFalse(artifact_satisfies_gate("behavior_contract", "unit_tests"))
        self.assertTrue(
            artifact_satisfies_gate(
                "behavior_contract", "behavior_contract_validation"
            )
        )
        self.assertTrue(artifact_satisfies_gate("state_transition_tests", "unit_tests"))

    def test_optional_symbol_scan_detects_unmapped_kotlin_callback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Tasks.kt"
            source.write_text(
                "fun TasksScreen(\n"
                "  onRefresh: () -> Unit,\n"
                "  onAddTask: () -> Unit,\n"
                ") { }\n",
                encoding="utf-8",
            )
            config = {
                "groups": [
                    {
                        "id": "callbacks",
                        "kind": "function_parameters",
                        "file": "Tasks.kt",
                        "symbol": "TasksScreen",
                        "name_pattern": "^on[A-Z]",
                    }
                ],
                "mapping": {"callbacks:onRefresh": ["INV-ACTION-REFRESH"]},
            }
            result = scan(config, root, inventory())
            self.assertEqual("fail", result["verdict"])
            self.assertEqual(["callbacks:onAddTask"], result["unmapped_symbols"])


if __name__ == "__main__":
    unittest.main()
