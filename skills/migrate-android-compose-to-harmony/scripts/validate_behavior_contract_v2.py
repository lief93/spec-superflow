#!/usr/bin/env python3
"""Validate source collection and target parity for behavior-contract.v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from audit_behavior_source import validate_closure, validate_semantic_review
from collect_behavior_rules import validate_collection


CONTRACT_SCHEMA = "behavior-contract.v2"
INVENTORY_SCHEMA = "behavior-source-inventory.v1"
RESULTS_SCHEMA = "behavior-scenario-results.v1"
VALIDATION_SCHEMA = "android-to-harmony.behavior-contract-validation.v2"
REQUIRED_SECTIONS = {
    "schema_version",
    "identity",
    "scope",
    "screens",
    "states",
    "actions",
    "navigation",
    "domain",
    "data_flows",
    "async_states",
    "platform_effects",
    "lifecycle",
    "observables",
    "scenarios",
    "traceability",
    "unresolved",
}
ACTION_FIELDS = {
    "id",
    "trigger",
    "guard",
    "handler_chain",
    "transition",
    "effects",
    "observable_results",
    "scenario_ids",
    "source_inventory_ids",
}
TARGET_STATUSES = {"implemented", "partial", "missing"}


class ValidationInputError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a frontend behavior contract and its migration evidence."
    )
    parser.add_argument("--phase", required=True, choices=("source", "target"))
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--scenario-results", type=Path)
    parser.add_argument("--snapshot", type=Path, help="Approved safe source snapshot required in both phases")
    parser.add_argument("--source-scope", type=Path, help="Independently selected full page/flow/application source scope")
    parser.add_argument("--source-review", type=Path, help="Independent semantic review bound to the current source and contract")
    parser.add_argument("--target", type=Path, help="Owned Harmony target containing signed execution evidence")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def load_json(path: Path, role: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationInputError(f"cannot read {role}: {error}") from error
    if not isinstance(payload, dict):
        raise ValidationInputError(f"{role} must be a JSON object")
    return payload, hashlib.sha256(raw).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(nonempty_string(item) for item in value)
    )


def ids(items: Any, role: str, errors: list[str]) -> list[str]:
    if not isinstance(items, list):
        errors.append(f"{role} must be an array")
        return []
    result: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not nonempty_string(item.get("id")):
            errors.append(f"{role}[{index}] is missing id")
            continue
        result.append(item["id"])
    duplicates = sorted(item for item, count in Counter(result).items() if count > 1)
    if duplicates:
        errors.append(f"{role} contains duplicate ids: {', '.join(duplicates)}")
    return result


def collect_inventory_refs(value: Any, refs: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "collection":
                continue
            if key == "source_inventory_ids":
                if isinstance(child, list):
                    refs.update(item for item in child if isinstance(item, str))
            else:
                collect_inventory_refs(child, refs)
    elif isinstance(value, list):
        for child in value:
            collect_inventory_refs(child, refs)


def validate_runtime_evidence(contract, results, target, closure):
    """Reuse the normal runner's attestation/command/artifact checks, not path strings."""
    if target is None:
        return ['runtime execution evidence requires the owned --target'], set()
    from evidence_runner import current_target_revision
    from migration_agent import (validate_evidence_record, target_relative_path, OrchestrationError)
    errors, executed = [], set()
    scope = closure.get('scope', {})
    try:
        target = Path(target).absolute()
        if target.is_symlink():
            raise ValueError('target is a symbolic link')
        revision = current_target_revision(target)
        if results.get('target_revision') != revision:
            raise ValueError('scenario results target revision is stale')
        scenarios = {s['id']: s for s in contract.get('scenarios', [])}
        for item in results.get('scenarios', []):
            scenario = scenarios.get(item.get('id'), {})
            test_id = scenario.get('target_test')
            if not isinstance(test_id, str) or not re.fullmatch(r'[\w$]+\.[\w$]+', test_id):
                errors.append(f"runtime execution evidence has no reviewed target_test for {item.get('id')}")
                continue
            matched = False
            for name in item.get('evidence', []):
                path = target_relative_path(target, name, 'scenario execution evidence', 'read_evidence')
                record = validate_evidence_record(path, target)
                if record.get('source_revision') != 'snapshot-sha256:' + str(closure.get('snapshot_manifest_sha256')):
                    raise ValueError('scenario execution source identity differs from the reviewed snapshot')
                if (record.get('gate') not in {'ui_tests', 'device_test'}
                        or record.get('runner_mode') != 'run' or record.get('status') != 'passed'
                        or record.get('execution_status') != 'executed'
                        or record.get('target_revision') != revision
                        or record.get('tests', {}).get('skipped') != 0
                        or item['id'] not in record.get('demand_ids', [])
                        or scope.get('id') not in record.get('slice_ids', [])):
                    raise ValueError('scenario evidence is not current scoped device execution')
                report = target_relative_path(target, record['test_report']['path'],
                                              'captured scenario report', 'read_evidence')
                current_class, current_test = None, None
                for line in report.read_text(encoding='utf-8').splitlines():
                    if line.startswith('class='):
                        current_class = line[6:]
                    elif line.startswith('test='):
                        current_test = line[5:]
                    elif line == 'result=Success':
                        qualified = (current_test.replace('#', '.') if current_test and '#' in current_test
                                     else f'{current_class}.{current_test}')
                        if qualified == test_id:
                            matched = True
            if matched:
                executed.add(item['id'])
            else:
                errors.append(f"runtime execution evidence lacks passing test {test_id}")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, OrchestrationError) as error:
        errors.append('runtime execution evidence: ' + str(error))
    return errors, executed


def validate(
    contract: dict[str, Any],
    inventory: dict[str, Any],
    *,
    phase: str,
    scenario_results: dict[str, Any] | None = None,
    snapshot: Path | None = None,
    source_scope: dict[str, Any] | None = None,
    source_review: dict[str, Any] | None = None,
    target: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    owned_target = target
    try:
        collection_result = validate_collection(contract, inventory, snapshot)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        collection_result = {"verdict": "fail", "errors": [f"collection malformed: {error}"]}
    errors.extend(collection_result["errors"])
    closure_result = validate_closure(contract, inventory, snapshot, source_scope)
    errors.extend(closure_result['errors'])
    try:
        errors.extend(validate_semantic_review(contract, closure_result, source_review))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append('source semantic review malformed: ' + str(error))
    missing_sections = sorted(REQUIRED_SECTIONS - contract.keys())
    if missing_sections:
        errors.append("missing contract sections: " + ", ".join(missing_sections))
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        errors.append(f"contract schema_version must be {CONTRACT_SCHEMA}")
    if inventory.get("schema_version") != INVENTORY_SCHEMA:
        errors.append(f"inventory schema_version must be {INVENTORY_SCHEMA}")

    identity = contract.get("identity")
    if not isinstance(identity, dict):
        identity = {}
        errors.append("contract identity must be an object")
    contract_id = identity.get("contract_id")
    source_revision = identity.get("source_revision")
    if not nonempty_string(contract_id):
        errors.append("contract identity.contract_id is missing")
    if not nonempty_string(source_revision):
        errors.append("contract identity.source_revision is missing")
    if source_revision != inventory.get("source_revision"):
        errors.append("contract and inventory source revisions differ")

    scope = contract.get("scope")
    included_scopes = scope.get("included_scopes") if isinstance(scope, dict) else None
    scope_id = inventory.get("scope_id")
    if not nonempty_string_list(included_scopes):
        errors.append("contract scope.included_scopes must be a non-empty string array")
    elif scope_id not in included_scopes:
        errors.append("inventory scope_id is outside contract scope")

    inventory_items = inventory.get("items")
    inventory_ids = ids(inventory_items, "inventory items", errors)
    inventory_set = set(inventory_ids)
    if isinstance(inventory_items, list):
        for item in inventory_items:
            if not isinstance(item, dict) or not nonempty_string(item.get("id")):
                continue
            if not nonempty_string(item.get("category")):
                errors.append(f"inventory item {item['id']} is missing category")
            if not nonempty_string(item.get("summary")):
                errors.append(f"inventory item {item['id']} is missing summary")
            if not nonempty_string_list(item.get("source_evidence")):
                errors.append(f"inventory item {item['id']} lacks source evidence")

    mapped_inventory: set[str] = set()
    collect_inventory_refs(contract, mapped_inventory)
    unknown_inventory = sorted(mapped_inventory - inventory_set)
    missing_inventory = sorted(inventory_set - mapped_inventory)
    if unknown_inventory:
        errors.append("unknown source inventory ids: " + ", ".join(unknown_inventory))
    if missing_inventory:
        errors.append("unmapped source inventory ids: " + ", ".join(missing_inventory))

    actions = contract.get("actions")
    action_ids = ids(actions, "actions", errors)
    action_set = set(action_ids)
    scenarios = contract.get("scenarios")
    scenario_ids = ids(scenarios, "scenarios", errors)
    scenario_set = set(scenario_ids)
    scenarios_by_action: dict[str, list[str]] = defaultdict(list)
    if isinstance(scenarios, list):
        for scenario in scenarios:
            if not isinstance(scenario, dict) or not nonempty_string(scenario.get("id")):
                continue
            scenario_id = scenario["id"]
            if not nonempty_string_list(scenario.get("android_evidence")):
                errors.append(f"scenario {scenario_id} lacks Android evidence")
            linked_actions = scenario.get("action_ids")
            if not nonempty_string_list(linked_actions):
                errors.append(f"scenario {scenario_id} has no action_ids")
                continue
            for action_id in linked_actions:
                if action_id not in action_set:
                    errors.append(
                        f"scenario {scenario_id} references unknown action {action_id}"
                    )
                else:
                    scenarios_by_action[action_id].append(scenario_id)

    malformed_actions: list[str] = []
    if isinstance(actions, list):
        for action in actions:
            if not isinstance(action, dict) or not nonempty_string(action.get("id")):
                continue
            action_id = action["id"]
            absent = sorted(ACTION_FIELDS - action.keys())
            if absent:
                malformed_actions.append(action_id)
                errors.append(
                    f"action {action_id} is missing fields: {', '.join(absent)}"
                )
            if not nonempty_string_list(action.get("observable_results")):
                errors.append(f"action {action_id} has no observable results")
            if not scenarios_by_action[action_id]:
                errors.append(f"action {action_id} has no acceptance scenario")
            declared = action.get("scenario_ids")
            if isinstance(declared, list) and set(declared) != set(
                scenarios_by_action[action_id]
            ):
                errors.append(f"action {action_id} scenario declaration differs")

    traceability = contract.get("traceability")
    targets = (
        traceability.get("target_implementation")
        if isinstance(traceability, dict)
        else None
    )
    target_ids = ids(targets, "target implementation", errors)
    target_by_action: dict[str, dict[str, Any]] = {}
    if isinstance(targets, list):
        for target in targets:
            if not isinstance(target, dict):
                continue
            action_id = target.get("id")
            if nonempty_string(action_id):
                target_by_action[action_id] = target
    missing_targets = sorted(action_set - set(target_ids))
    unknown_targets = sorted(set(target_ids) - action_set)
    if missing_targets:
        errors.append("actions missing target mapping: " + ", ".join(missing_targets))
    if unknown_targets:
        errors.append("target mappings reference unknown actions: " + ", ".join(unknown_targets))

    status_counts: Counter[str] = Counter()
    for action_id, target in target_by_action.items():
        status = target.get("status")
        status_counts[str(status)] += 1
        if status not in TARGET_STATUSES:
            errors.append(f"target mapping {action_id} has invalid status {status!r}")
        if status == "implemented" and not nonempty_string(target.get("target")):
            errors.append(f"implemented target mapping {action_id} lacks target symbol")

    unresolved = contract.get("unresolved")
    if not isinstance(unresolved, list):
        errors.append("contract unresolved must be an array")
        unresolved_count = 0
    else:
        unresolved_count = len(unresolved)
        if unresolved:
            errors.append("contract has unresolved behavior facts")

    source_complete = not errors
    result_by_scenario: dict[str, dict[str, Any]] = {}
    executed_scenarios: set[str] = set()
    if phase == "target":
        for action_id, mapping in target_by_action.items():
            if mapping.get('status') != 'implemented':
                errors.append(f"target mapping {action_id} is not implemented")
        if scenario_results is None:
            errors.append("target phase requires scenario results")
        else:
            if scenario_results.get("schema_version") != RESULTS_SCHEMA:
                errors.append(f"scenario results schema_version must be {RESULTS_SCHEMA}")
            if scenario_results.get("contract_id") != contract_id:
                errors.append("scenario results contract_id differs")
            if scenario_results.get("source_revision") != source_revision:
                errors.append("scenario results source_revision differs")
            if not nonempty_string(scenario_results.get("target_revision")):
                errors.append("scenario results target_revision is missing")
            result_items = scenario_results.get("scenarios")
            result_ids = ids(result_items, "scenario results", errors)
            if isinstance(result_items, list):
                for item in result_items:
                    if isinstance(item, dict) and nonempty_string(item.get("id")):
                        result_by_scenario[item["id"]] = item
            missing_results = sorted(scenario_set - set(result_ids))
            extra_results = sorted(set(result_ids) - scenario_set)
            if missing_results:
                errors.append("scenarios missing target results: " + ", ".join(missing_results))
            if extra_results:
                errors.append("target results reference unknown scenarios: " + ", ".join(extra_results))
            for scenario_id, item in result_by_scenario.items():
                if item.get("verdict") != "pass":
                    errors.append(f"scenario {scenario_id} did not pass")
                if not nonempty_string_list(item.get("evidence")):
                    errors.append(f"scenario {scenario_id} lacks target evidence")
            runtime_errors, executed_scenarios = validate_runtime_evidence(
                contract, scenario_results, owned_target, closure_result)
            errors.extend(runtime_errors)

    category_totals = Counter(
        item.get("category")
        for item in inventory_items or []
        if isinstance(item, dict) and nonempty_string(item.get("category"))
    )
    category_covered = Counter(
        item.get("category")
        for item in inventory_items or []
        if isinstance(item, dict) and item.get("id") in mapped_inventory
    )
    category_coverage = {
        category: {
            "covered": category_covered[category],
            "total": total,
            "percent": round(100 * category_covered[category] / total, 2),
        }
        for category, total in sorted(category_totals.items())
    }
    inventory_total = len(inventory_set)
    inventory_covered = inventory_total - len(missing_inventory)
    implemented = status_counts["implemented"]
    reported_passed = sum(
        1 for item in result_by_scenario.values() if item.get("verdict") == "pass"
    )
    passed_scenarios = len(executed_scenarios)
    return {
        "schema": VALIDATION_SCHEMA,
        "artifact_type": "behavior_source_validation" if phase == 'source' else "behavior_contract_validation",
        "verdict": "pass" if not errors else "fail",
        "phase": phase,
        "collection": collection_result,
        "collection_valid": collection_result["verdict"] == "pass",
        "source_complete": source_complete,
        "runtime_complete": phase == 'target' and not errors and executed_scenarios == scenario_set,
        "application_complete": phase == 'target' and not errors and executed_scenarios == scenario_set
            and (source_scope or {}).get('kind') == 'application' and not contract.get('scope', {}).get('excluded'),
        "source_closure": closure_result,
        "contract_id": contract_id,
        "source_revision": source_revision,
        "source_inventory": {
            "covered": inventory_covered,
            "total": inventory_total,
            "percent": round(100 * inventory_covered / inventory_total, 2)
            if inventory_total
            else 0.0,
            "missing": missing_inventory,
            "category_coverage": category_coverage,
        },
        "contract": {
            "actions": len(action_set),
            "states": len(contract.get("states", []))
            if isinstance(contract.get("states"), list)
            else 0,
            "navigation": len(contract.get("navigation", []))
            if isinstance(contract.get("navigation"), list)
            else 0,
            "scenarios": len(scenario_set),
            "unresolved_count": unresolved_count,
            "malformed_actions": sorted(set(malformed_actions)),
        },
        "target": {
            "implemented": implemented,
            "partial": status_counts["partial"],
            "missing": status_counts["missing"],
            "action_coverage_percent": round(100 * implemented / len(action_set), 2)
            if action_set
            else 0.0,
        },
        "scenario_results": {
            "reported_passed": reported_passed,
            "passed": passed_scenarios,
            "total": len(scenario_set),
            "percent": round(100 * passed_scenarios / len(scenario_set), 2)
            if scenario_set
            else 0.0,
        },
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    try:
        contract, contract_sha256 = load_json(args.contract, "behavior contract")
        inventory, inventory_sha256 = load_json(args.inventory, "source inventory")
        scenario_results = None
        scenario_results_sha256 = None
        if args.scenario_results is not None:
            scenario_results, scenario_results_sha256 = load_json(
                args.scenario_results, "scenario results"
            )
        result = validate(
            contract,
            inventory,
            phase=args.phase,
            scenario_results=scenario_results,
            snapshot=args.snapshot,
            source_scope=load_json(args.source_scope, "source scope")[0] if args.source_scope else None,
            source_review=load_json(args.source_review, "source review")[0] if args.source_review else None,
            target=args.target,
        )
        result["artifacts"] = {
            "contract_sha256": contract_sha256,
            "inventory_sha256": inventory_sha256,
            "scenario_results_sha256": scenario_results_sha256,
        }
    except ValidationInputError as error:
        result = {
            "schema": VALIDATION_SCHEMA,
            "artifact_type": "behavior_source_validation" if args.phase == 'source' else "behavior_contract_validation",
            "verdict": "fail",
            "phase": args.phase,
            "errors": [str(error)],
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        write_json(args.output, result)
    print(rendered, end="")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
