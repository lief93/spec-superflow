#!/usr/bin/env python3
"""Build a deterministic execution-plan DAG from the capability graph."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from aggregate_gate_evidence import REPORT_SCHEMA as GATE_REPORT_SCHEMA
from aggregate_gate_evidence import REVIEW_QUEUE_SCHEMA, validate_review_queue
from build_capability_graph import (
    CONTRACT_SCHEMA,
    GraphError,
    load_json as load_graph_json,
    sha256_bytes,
    validate_contract,
)


PLAN_SCHEMA = "android-to-harmony.execution-plan.v1"
GRAPH_SCHEMA = "android-to-harmony.capability-graph.v1"
TASK_STATUSES = {"ready", "blocked", "pending", "completed"}
PRODUCTION_LAYERS = {
    "page",
    "control",
    "business",
    "network",
    "storage",
    "platform",
    "ui_system",
    "unclassified",
}
GENERIC_TOKENS = {
    "activity",
    "adapter",
    "api",
    "app",
    "button",
    "class",
    "component",
    "data",
    "database",
    "dialog",
    "entity",
    "flow",
    "form",
    "fragment",
    "helper",
    "impl",
    "interface",
    "item",
    "local",
    "manager",
    "model",
    "page",
    "remote",
    "repository",
    "screen",
    "service",
    "source",
    "state",
    "storage",
    "test",
    "theme",
    "ui",
    "use",
    "usecase",
    "util",
    "utils",
    "view",
    "viewmodel",
}
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


class PlannerError(RuntimeError):
    """Raised when execution-plan inputs are invalid."""


def canonical_sha256(payload: Any) -> str:
    return sha256_bytes(
        json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic Android-to-Harmony execution plan.",
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--gate-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: Path, expected_schema: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise PlannerError(f"unable to read JSON {path}: {error}") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise PlannerError(f"invalid JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise PlannerError(f"JSON payload must be an object: {path}")
    if payload.get("schema") != expected_schema:
        raise PlannerError(
            f"schema must be {expected_schema!r}; received {payload.get('schema')!r}"
        )
    return payload, raw


def validate_graph(path: Path, contract_sha256: str) -> dict[str, Any]:
    try:
        graph, _raw = load_graph_json(path)
    except GraphError as error:
        raise PlannerError(str(error)) from error
    if graph.get("schema") != GRAPH_SCHEMA:
        raise PlannerError(
            f"graph schema must be {GRAPH_SCHEMA!r}; received {graph.get('schema')!r}"
        )
    if graph.get("contract_sha256") != contract_sha256:
        raise PlannerError(
            "stale graph binding for contract_sha256: "
            f"graph={graph.get('contract_sha256')!r}, contract={contract_sha256!r}"
        )
    return graph


def validate_gate_report(path: Path, graph: dict[str, Any]) -> tuple[dict[str, Any], str]:
    report, raw = load_json(path, GATE_REPORT_SCHEMA)
    for field in ("source_revision", "contract_sha256", "skill_tree_digest"):
        if report.get(field) != graph.get(field):
            raise PlannerError(
                f"stale gate report binding for {field}: "
                f"report={report.get(field)!r}, graph={graph.get(field)!r}"
            )
    expected_graph_sha256 = report.get("graph_sha256")
    if expected_graph_sha256 is not None:
        current_graph_sha256 = sha256_bytes(
            json.dumps(graph, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        if expected_graph_sha256 != current_graph_sha256:
            raise PlannerError("gate report graph_sha256 does not match the current graph")
    expected_node_ids = report.get("graph_node_ids")
    if expected_node_ids is not None:
        current_node_ids = sorted(
            node["id"]
            for node in graph.get("nodes", [])
            if isinstance(node, dict) and isinstance(node.get("id"), str)
        )
        if expected_node_ids != current_node_ids:
            raise PlannerError("gate report graph_node_ids do not match the current graph")
    expected_review_queue = report.get("review_queue")
    current_review_queue = graph.get("review_queue", {})
    if expected_review_queue is not None:
        if not isinstance(expected_review_queue, dict):
            raise PlannerError("gate report review_queue must be an object")
        if expected_review_queue.get("sha256") != current_review_queue.get("sha256"):
            raise PlannerError("gate report review queue digest does not match the current graph")
    expected_node_statuses_sha256 = report.get("node_statuses_sha256")
    report_by_node = report.get("report_by_node")
    if expected_node_statuses_sha256 is not None:
        if not isinstance(report_by_node, dict):
            raise PlannerError("gate report report_by_node must be an object")
        current_node_statuses_sha256 = canonical_sha256(report_by_node)
        if expected_node_statuses_sha256 != current_node_statuses_sha256:
            raise PlannerError("gate report node statuses do not match report_by_node")
    return report, sha256_bytes(raw)


def tokens_for_value(value: str) -> set[str]:
    if not value:
        return set()
    prepared = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    prepared = prepared.replace("/", " ").replace(".", " ").replace("-", " ").replace("_", " ")
    tokens = {
        token.lower()
        for token in TOKEN_PATTERN.findall(prepared)
        if token and token.lower() not in GENERIC_TOKENS and len(token) > 1
    }
    return tokens


def node_tokens(node: dict[str, Any]) -> set[str]:
    values = [str(node.get("id", ""))]
    values.extend(str(path) for path in node.get("primary_source_files", []) if isinstance(path, str))
    values.extend(str(path) for path in node.get("source_evidence", []) if isinstance(path, str))
    return set().union(*(tokens_for_value(value) for value in values))


def batch_tokens(batch: dict[str, Any]) -> set[str]:
    values = [str(batch.get("id", "")), str(batch.get("goal", ""))]
    values.extend(str(path) for path in batch.get("source_files", []) if isinstance(path, str))
    return set().union(*(tokens_for_value(value) for value in values))


def route_tokens(route: dict[str, Any]) -> set[str]:
    values = [str(route.get("route", "")), str(route.get("source", ""))]
    return set().union(*(tokens_for_value(value) for value in values))


def production_source_files(node: dict[str, Any]) -> list[str]:
    return sorted(
        {
            path
            for path in node.get("primary_source_files", [])
            if isinstance(path, str) and path
        }
    )


def route_for_page(page_node: dict[str, Any], contract: dict[str, Any]) -> str | None:
    ui = contract.get("ui", {})
    routes = ui.get("routes", []) if isinstance(ui, dict) else []
    page_sources = set(production_source_files(page_node))
    for route in routes:
        if not isinstance(route, dict):
            continue
        source = route.get("source")
        route_value = route.get("route")
        if isinstance(source, str) and isinstance(route_value, str) and source in page_sources:
            return route_value
    return None


def score_node_for_page(
    node: dict[str, Any],
    page_node: dict[str, Any],
    page_anchor_tokens: set[str],
    page_batches: list[dict[str, Any]],
) -> tuple[int, int]:
    score = 0
    page_sources = set(production_source_files(page_node))
    node_sources = set(production_source_files(node))
    if page_sources & node_sources:
        score += 1000
    node_token_set = node_tokens(node)
    overlap = len(page_anchor_tokens & node_token_set)
    if overlap:
        score += overlap * 10
    batch_overlap = 0
    for batch in page_batches:
        batch_source_files = {
            path for path in batch.get("source_files", []) if isinstance(path, str)
        }
        if node_sources & batch_source_files:
            score += 200
            batch_overlap += 1
        token_overlap = len(batch_tokens(batch) & node_token_set)
        if token_overlap:
            score += token_overlap * 3
    return score, batch_overlap


def topological_sort(task_packets: list[dict[str, Any]]) -> list[str]:
    task_ids = {task["id"] for task in task_packets}
    dependency_map: dict[str, list[str]] = {}
    for task in task_packets:
        dependencies = task.get("dependent_task_ids", [])
        if not isinstance(dependencies, list):
            raise PlannerError(f"task {task['id']!r} dependent_task_ids must be a list")
        for dependency in dependencies:
            if dependency not in task_ids:
                raise PlannerError(
                    f"task {task['id']!r} depends on unknown task {dependency!r}"
                )
        dependency_map[task["id"]] = sorted(str(dependency) for dependency in dependencies)
    remaining = {task_id: set(dependencies) for task_id, dependencies in dependency_map.items()}
    ordered: list[str] = []
    ready = sorted(task_id for task_id, dependencies in remaining.items() if not dependencies)
    while ready:
        task_id = ready.pop(0)
        ordered.append(task_id)
        remaining.pop(task_id, None)
        for other_id in sorted(remaining):
            if task_id in remaining[other_id]:
                remaining[other_id].remove(task_id)
                if not remaining[other_id] and other_id not in ready:
                    ready.append(other_id)
                    ready.sort()
    if remaining:
        raise PlannerError(
            "execution plan dependencies contain a cycle: " + ", ".join(sorted(remaining))
        )
    return ordered


def foundation_task_id(node_id: str) -> str:
    return "foundation:" + node_id.split(":", 1)[-1].lower().replace("/", "-").replace("_", "-")


def consumer_task_id_for_page(page_id: str, contract: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]) -> str:
    route = route_for_page(nodes_by_id[page_id], contract)
    route_slug = route or page_id.split(":", 1)[-1]
    return f"slice:{route_slug.lower().replace('/', '-').replace('_', '-')}"


def seed_task_status(
    task_packet: dict[str, Any],
    report_by_node: dict[str, Any],
    blocked_definitions: list[dict[str, Any]],
) -> str:
    if blocked_definitions:
        return "blocked"
    if task_packet.get("dependent_task_ids"):
        return "pending"
    for node_id in task_packet.get("primary_owner_node_ids", []):
        report = report_by_node.get(node_id, {})
        if isinstance(report, dict) and report.get("status") == "completed":
            continue
    return "ready"


def gate_report_identity(gate_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "graph_sha256": gate_report.get("graph_sha256"),
        "node_statuses_sha256": gate_report.get("node_statuses_sha256"),
        "review_queue_sha256": (
            gate_report.get("review_queue", {}).get("sha256")
            if isinstance(gate_report.get("review_queue"), dict)
            else None
        ),
    }


def apply_task_state_view(
    plan: dict[str, Any],
    task_state: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    task_packets = plan.get("tasks", [])
    packet_by_id = {
        task["id"]: task
        for task in task_packets
        if isinstance(task, dict) and isinstance(task.get("id"), str)
    }
    task_states = {}
    if isinstance(task_state, dict):
        raw_states = task_state.get("tasks")
        if isinstance(raw_states, dict):
            task_states = raw_states
    resolved_tasks: list[dict[str, Any]] = []
    for task_id in sorted(packet_by_id):
        packet = packet_by_id[task_id]
        task_record = task_states.get(task_id, {}) if isinstance(task_states.get(task_id), dict) else {}
        completed = task_record.get("status") == "completed"
        blocked_definitions = list(packet.get("blocked_by", []))
        prerequisite_task_ids = list(packet.get("dependent_task_ids", []))
        prerequisites_complete = all(
            isinstance(task_states.get(prerequisite_id), dict)
            and task_states[prerequisite_id].get("status") == "completed"
            for prerequisite_id in prerequisite_task_ids
        )
        if completed:
            status = "completed"
        elif blocked_definitions:
            status = "blocked"
        elif prerequisite_task_ids and not prerequisites_complete:
            status = "pending"
        else:
            status = "ready"
        resolved_task = json.loads(json.dumps(packet))
        resolved_task["status"] = status
        resolved_tasks.append(resolved_task)
    ordered = topological_sort(resolved_tasks)
    resolved_by_id = {task["id"]: task for task in resolved_tasks}
    resolved_tasks = [resolved_by_id[task_id] for task_id in ordered]
    ready = [task_id for task_id in ordered if resolved_by_id[task_id]["status"] == "ready"]
    blocked = [task_id for task_id in ordered if resolved_by_id[task_id]["status"] == "blocked"]
    return resolved_tasks, ready, blocked, ordered


def build_batch1_execution_plan(
    contract: dict[str, Any],
    contract_sha256: str,
    graph: dict[str, Any],
    gate_report: dict[str, Any],
    *,
    gate_report_sha256: str,
) -> dict[str, Any]:
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise PlannerError("graph nodes must be a list")
    nodes_by_id = {
        node["id"]: node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    root_qualification = graph.get("root_qualification")
    resolved_edges = graph.get("resolved_edges")
    if not isinstance(root_qualification, list) or not isinstance(resolved_edges, list):
        raise PlannerError("graph is missing root_qualification or resolved_edges")
    roots = [
        item
        for item in root_qualification
        if isinstance(item, dict)
        and item.get("qualified_as_root") is True
        and isinstance(item.get("node_id"), str)
        and nodes_by_id.get(item["node_id"], {}).get("layer") == "page"
    ]
    if not roots:
        raise PlannerError("execution plan requires at least one qualified route/page root")
    qualified_root_node_ids = {item["node_id"] for item in roots}

    edges_from: dict[str, list[dict[str, Any]]] = {}
    for edge in resolved_edges:
        if not isinstance(edge, dict):
            continue
        from_node_id = edge.get("from_node_id")
        to_node_id = edge.get("to_node_id")
        if not isinstance(from_node_id, str) or not isinstance(to_node_id, str):
            continue
        edges_from.setdefault(from_node_id, []).append(edge)
    for edge_list in edges_from.values():
        edge_list.sort(key=lambda item: str(item.get("edge_id", "")))

    batch_sources_by_task: dict[str, set[str]] = {}
    batches = contract.get("migration_batches", [])
    if isinstance(batches, list):
        for root in roots:
            page_node = nodes_by_id[root["node_id"]]
            page_sources = set(production_source_files(page_node))
            task_route = route_for_page(page_node, contract) or root["node_id"].split(":", 1)[-1]
            task_id = f"slice:{task_route.lower().replace('/', '-').replace('_', '-')}"
            for batch in batches:
                if not isinstance(batch, dict):
                    continue
                source_files = {
                    path for path in batch.get("source_files", []) if isinstance(path, str)
                }
                if page_sources & source_files:
                    batch_sources_by_task.setdefault(task_id, set()).update(source_files)

    task_packets: list[dict[str, Any]] = []
    node_to_task_ids: dict[str, set[str]] = {}
    report_by_node = gate_report.get("report_by_node", {})
    if not isinstance(report_by_node, dict):
        report_by_node = {}
    prerequisite_edges: list[dict[str, Any]] = []
    shared_foundation_consumers: dict[str, set[str]] = {}

    page_root_ids = {item["node_id"] for item in roots}
    page_consumers_by_node: dict[str, set[str]] = {}
    for edge in resolved_edges:
        if not isinstance(edge, dict):
            continue
        if edge.get("consumed_by_planner") != "closure_and_assignment":
            continue
        from_node_id = edge.get("from_node_id")
        to_node_id = edge.get("to_node_id")
        if not isinstance(from_node_id, str) or not isinstance(to_node_id, str):
            continue
        target_node = nodes_by_id.get(to_node_id)
        if from_node_id in page_root_ids and target_node and target_node.get("layer") in {
            "business",
            "network",
            "storage",
            "platform",
            "ui_system",
        }:
            page_consumers_by_node.setdefault(to_node_id, set()).add(
                consumer_task_id_for_page(from_node_id, contract, nodes_by_id)
            )
    shared_foundation_targets = {
        edge["to_node_id"]
        for edge in resolved_edges
        if isinstance(edge, dict)
        and edge.get("kind") == "shared_foundation_member"
        and isinstance(edge.get("to_node_id"), str)
    }
    shared_foundation_targets.update(
        node_id
        for node_id, consumer_task_ids in page_consumers_by_node.items()
        if len(consumer_task_ids) > 1
    )
    foundation_task_by_node: dict[str, str] = {}

    for root in sorted(roots, key=lambda item: str(item["node_id"])):
        page_id = root["node_id"]
        page_node = nodes_by_id[page_id]
        route = route_for_page(page_node, contract)
        route_slug = route or page_id.split(":", 1)[-1]
        task_id = f"slice:{route_slug.lower().replace('/', '-').replace('_', '-')}"
        task_packet = {
            "id": task_id,
            "kind": "vertical_slice",
            "route": route,
            "page_node_ids": [page_id],
            "control_node_ids": [],
            "ui_system_node_ids": [],
            "business_node_ids": [],
            "network_node_ids": [],
            "storage_node_ids": [],
            "platform_node_ids": [],
            "unclassified_node_ids": [],
            "related_test_support_node_ids": [],
            "primary_owner_node_ids": [page_id],
            "dependent_task_ids": [],
            "prerequisite_edges": [],
            "blocked_by": [],
            "blocked_source_files": [],
            "required_skills": ["migrate-android-compose-to-harmony"],
            "required_gates": list(page_node.get("required_gates", [])),
            "required_tests": list(page_node.get("required_tests", [])),
            "source_files": production_source_files(page_node),
            "evidence_identity": {
                "source_revision": graph.get("source_revision"),
                "contract_sha256": contract_sha256,
                "skill_tree_digest": graph.get("skill_tree_digest"),
                "gate_report_identity": gate_report_identity(gate_report),
            },
            "foundation_owner_node_ids": [],
            "frozen_evidence_references": [
                {
                    "kind": "gate_report",
                    "identity": gate_report_identity(gate_report),
                }
            ],
            "closure_provenance": [],
        }
        visited = {page_id}
        queue = [page_id]
        while queue:
            current = queue.pop(0)
            for edge in edges_from.get(current, []):
                consumed = edge.get("consumed_by_planner")
                if consumed not in {"closure_and_assignment", "provenance_only"}:
                    continue
                target_id = edge["to_node_id"]
                target_node = nodes_by_id.get(target_id)
                if target_node is None:
                    continue
                if consumed == "provenance_only":
                    continue
                if target_id in shared_foundation_targets:
                    shared_foundation_consumers.setdefault(target_id, set()).add(task_id)
                    continue
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append(target_id)
                    task_packet["closure_provenance"].append(
                        {
                            "edge_id": edge.get("edge_id"),
                            "via_edge": edge.get("kind"),
                            "from_node_id": edge.get("from_node_id"),
                            "to_node_id": target_id,
                            "source_path": edge.get("source_path"),
                        }
                    )
                layer = target_node.get("layer")
                if layer == "test_support":
                    task_packet["related_test_support_node_ids"].append(target_id)
                    continue
                if layer == "control":
                    task_packet["control_node_ids"].append(target_id)
                elif layer == "ui_system":
                    task_packet["ui_system_node_ids"].append(target_id)
                elif layer == "business":
                    task_packet["business_node_ids"].append(target_id)
                elif layer == "network":
                    task_packet["network_node_ids"].append(target_id)
                elif layer == "storage":
                    task_packet["storage_node_ids"].append(target_id)
                elif layer == "platform":
                    task_packet["platform_node_ids"].append(target_id)
                elif layer == "unclassified":
                    task_packet["unclassified_node_ids"].append(target_id)
                else:
                    continue
                task_packet["primary_owner_node_ids"].append(target_id)
                task_packet["required_gates"] = sorted(
                    set(task_packet["required_gates"]) | set(target_node.get("required_gates", []))
                )
                task_packet["required_tests"] = sorted(
                    set(task_packet["required_tests"]) | set(target_node.get("required_tests", []))
                )
                task_packet["source_files"] = sorted(
                    set(task_packet["source_files"]) | set(production_source_files(target_node))
                )
                node_to_task_ids.setdefault(target_id, set()).add(task_id)
        if not task_packet["closure_provenance"]:
            raise PlannerError(
                f"semantic closure incomplete for {task_id}: no resolved cross-layer provenance"
            )
        for node_id in task_packet["primary_owner_node_ids"]:
            node_to_task_ids.setdefault(node_id, set()).add(task_id)
        for field in (
            "control_node_ids",
            "ui_system_node_ids",
            "business_node_ids",
            "network_node_ids",
            "storage_node_ids",
            "platform_node_ids",
            "unclassified_node_ids",
            "related_test_support_node_ids",
            "primary_owner_node_ids",
        ):
            task_packet[field] = sorted(set(task_packet[field]))
        task_packets.append(task_packet)

    assigned_production_node_ids = {
        node_id
        for task in task_packets
        for node_id in task["primary_owner_node_ids"]
        if nodes_by_id[node_id].get("layer") in PRODUCTION_LAYERS
    }
    for node_id, consumer_task_ids in sorted(shared_foundation_consumers.items()):
        foundation_node = nodes_by_id.get(node_id)
        if foundation_node is None:
            continue
        foundation_task = {
            "id": foundation_task_id(node_id),
            "kind": "shared_foundation",
            "route": None,
            "page_node_ids": [],
            "control_node_ids": [],
            "ui_system_node_ids": [node_id] if foundation_node.get("layer") == "ui_system" else [],
            "business_node_ids": [node_id] if foundation_node.get("layer") == "business" else [],
            "network_node_ids": [node_id] if foundation_node.get("layer") == "network" else [],
            "storage_node_ids": [node_id] if foundation_node.get("layer") == "storage" else [],
            "platform_node_ids": [node_id] if foundation_node.get("layer") == "platform" else [],
            "unclassified_node_ids": [node_id] if foundation_node.get("layer") == "unclassified" else [],
            "related_test_support_node_ids": [],
            "primary_owner_node_ids": [node_id],
            "dependent_task_ids": [],
            "prerequisite_edges": [],
            "blocked_by": [],
            "blocked_source_files": [],
            "required_skills": ["migrate-android-compose-to-harmony"],
            "required_gates": sorted(set(foundation_node.get("required_gates", []))),
            "required_tests": sorted(set(foundation_node.get("required_tests", []))),
            "source_files": production_source_files(foundation_node),
            "evidence_identity": {
                "source_revision": graph.get("source_revision"),
                "contract_sha256": contract_sha256,
                "skill_tree_digest": graph.get("skill_tree_digest"),
                "gate_report_identity": gate_report_identity(gate_report),
            },
            "foundation_owner_node_ids": [node_id],
            "frozen_evidence_references": [
                {
                    "kind": "gate_report",
                    "identity": gate_report_identity(gate_report),
                }
            ],
            "closure_provenance": [
                {
                    "edge_id": edge.get("edge_id"),
                    "via_edge": edge.get("kind"),
                    "from_node_id": edge.get("from_node_id"),
                    "to_node_id": node_id,
                    "source_path": edge.get("source_path"),
                }
                for edge in resolved_edges
                if isinstance(edge, dict)
                and edge.get("kind") == "shared_foundation_member"
                and edge.get("to_node_id") == node_id
            ],
        }
        task_packets.append(foundation_task)
        foundation_task_by_node[node_id] = foundation_task["id"]
        node_to_task_ids.setdefault(node_id, set()).add(foundation_task["id"])
        assigned_production_node_ids.add(node_id)
        for consumer_task_id in sorted(consumer_task_ids):
            consumer_task = next(
                task for task in task_packets if task["id"] == consumer_task_id
            )
            if foundation_task["id"] not in consumer_task["dependent_task_ids"]:
                consumer_task["dependent_task_ids"].append(foundation_task["id"])
            source_edges = [
                edge.get("edge_id")
                for edge in resolved_edges
                if isinstance(edge, dict)
                and edge.get("kind") == "shared_foundation_member"
                and edge.get("to_node_id") == node_id
                and consumer_task["page_node_ids"]
                and edge.get("from_node_id") == consumer_task["page_node_ids"][0]
                and isinstance(edge.get("edge_id"), str)
            ]
            prerequisite_edge = {
                "kind": "shared_foundation_prerequisite",
                "from_task_id": foundation_task["id"],
                "to_task_id": consumer_task_id,
                "owner_node_id": node_id,
                "source_edge_ids": sorted(source_edges),
            }
            consumer_task["prerequisite_edges"].append(prerequisite_edge)
            prerequisite_edges.append(prerequisite_edge)
    for node in sorted(
        (
            candidate
            for candidate in nodes
            if candidate.get("layer") in {"ui_system", "platform"}
            and candidate["id"] not in assigned_production_node_ids
            and production_source_files(candidate)
        ),
        key=lambda item: (str(item.get("layer")), item["id"]),
    ):
        task_id = foundation_task_id(node["id"])
        standalone_foundation = {
            "id": task_id,
            "kind": "shared_foundation",
            "route": None,
            "page_node_ids": [],
            "control_node_ids": [],
            "ui_system_node_ids": [node["id"]] if node.get("layer") == "ui_system" else [],
            "business_node_ids": [],
            "network_node_ids": [],
            "storage_node_ids": [],
            "platform_node_ids": [node["id"]] if node.get("layer") == "platform" else [],
            "unclassified_node_ids": [],
            "related_test_support_node_ids": [],
            "primary_owner_node_ids": [node["id"]],
            "dependent_task_ids": [],
            "prerequisite_edges": [],
            "blocked_by": [],
            "blocked_source_files": [],
            "required_skills": ["migrate-android-compose-to-harmony"],
            "required_gates": sorted(set(node.get("required_gates", []))),
            "required_tests": sorted(set(node.get("required_tests", []))),
            "source_files": production_source_files(node),
            "evidence_identity": {
                "source_revision": graph.get("source_revision"),
                "contract_sha256": contract_sha256,
                "skill_tree_digest": graph.get("skill_tree_digest"),
                "gate_report_identity": gate_report_identity(gate_report),
            },
            "foundation_owner_node_ids": [node["id"]],
            "frozen_evidence_references": [
                {
                    "kind": "gate_report",
                    "identity": gate_report_identity(gate_report),
                }
            ],
            "closure_provenance": [],
        }
        task_packets.append(standalone_foundation)
        node_to_task_ids.setdefault(node["id"], set()).add(task_id)
        assigned_production_node_ids.add(node["id"])
    for node in nodes:
        if not isinstance(node, dict):
            continue
        produced_contract_ids = node.get("produced_contract_ids", [])
        if not isinstance(produced_contract_ids, list) or not produced_contract_ids:
            continue
        producer_task_ids = sorted(node_to_task_ids.get(node.get("id"), set()))
        if len(producer_task_ids) != 1:
            raise PlannerError(
                f"produced contract owner must resolve to exactly one task: {node.get('id')!r}"
            )
        producer_task_id = producer_task_ids[0]
        for consumer in nodes:
            if not isinstance(consumer, dict):
                continue
            required_contract_ids = consumer.get("required_contract_ids", [])
            if not isinstance(required_contract_ids, list):
                continue
            shared_contracts = sorted(
                contract_id
                for contract_id in produced_contract_ids
                if isinstance(contract_id, str) and contract_id in required_contract_ids
            )
            if not shared_contracts:
                continue
            consumer_task_ids = sorted(node_to_task_ids.get(consumer.get("id"), set()))
            if len(consumer_task_ids) != 1:
                raise PlannerError(
                    f"produced contract consumer must resolve to exactly one task: {consumer.get('id')!r}"
                )
            consumer_task_id = consumer_task_ids[0]
            if consumer_task_id == producer_task_id:
                continue
            consumer_task = next(
                task for task in task_packets if task["id"] == consumer_task_id
            )
            if producer_task_id not in consumer_task["dependent_task_ids"]:
                consumer_task["dependent_task_ids"].append(producer_task_id)
            source_edge_ids = sorted(
                edge.get("edge_id")
                for edge in resolved_edges
                if isinstance(edge, dict)
                and edge.get("from_node_id") == consumer.get("id")
                and edge.get("to_node_id") == node.get("id")
                and isinstance(edge.get("edge_id"), str)
            )
            prerequisite_edge = {
                "kind": "produced_contract_prerequisite",
                "from_task_id": producer_task_id,
                "to_task_id": consumer_task_id,
                "owner_node_id": node.get("id"),
                "contract_ids": shared_contracts,
                "source_edge_ids": source_edge_ids,
            }
            consumer_task["prerequisite_edges"].append(prerequisite_edge)
            prerequisite_edges.append(prerequisite_edge)
    production_nodes = [
        node
        for node in nodes
        if node.get("layer") in PRODUCTION_LAYERS
        and production_source_files(node)
        and not (
            node.get("layer") == "page"
            and node.get("id") not in qualified_root_node_ids
        )
    ]
    unassigned = [
        node["id"]
        for node in production_nodes
        if node.get("layer") != "unclassified"
        if node["id"] not in assigned_production_node_ids
    ]
    if unassigned:
        raise PlannerError(
            "explicit unassigned blocker: production incomplete; empty executable fallback; "
            + ", ".join(sorted(unassigned))
        )

    review_queue_sources = []
    review_queue = graph.get("review_queue", {})
    if isinstance(review_queue, dict):
        review_queue_sources = [
            source
            for source in review_queue.get("unclassified_source_files", [])
            if isinstance(source, str)
        ]
    for source_path in sorted(set(review_queue_sources)):
        matched_tasks = [
            task
            for task in task_packets
            if source_path in task["source_files"]
        ]
        if not matched_tasks:
            matched_tasks = [
                task
                for task in task_packets
                if source_path in batch_sources_by_task.get(task["id"], set())
            ]
        if not matched_tasks:
            raise PlannerError(
                f"explicit unassigned blocker: production incomplete; empty executable fallback; {source_path}"
            )
        for task in matched_tasks:
            task["status"] = "blocked"
            task["blocked_source_files"].append(source_path)
            task["blocked_by"].append(
                {
                    "kind": "review_queue",
                    "source_path": source_path,
                    "blocking_parent_gate": "project.child_dispositions",
                }
            )

    for node_id, report in sorted(report_by_node.items()):
        if not isinstance(report, dict):
            continue
        status = report.get("status")
        failed_gates = report.get("failed_gates", [])
        if status not in {"failed", "blocked"} and not failed_gates:
            continue
        matched_task_ids = sorted(node_to_task_ids.get(node_id, set()))
        if not matched_task_ids:
            raise PlannerError(
                f"explicit unassigned blocker: failed gate without executable fallback; {node_id}"
            )
        for task in task_packets:
            if task["id"] not in matched_task_ids:
                continue
            task["blocked_by"].append(
                {
                    "kind": "failed_gate",
                    "node_id": node_id,
                    "failed_gates": list(failed_gates) if isinstance(failed_gates, list) else [],
                }
            )

    provenance_priority = {
        "page_declares_control": 0,
        "page_uses_business": 1,
        "business_uses_repository": 2,
        "repository_uses_storage": 3,
        "repository_uses_network": 4,
        "page_uses_platform": 5,
        "page_uses_ui_system": 6,
        "shared_foundation_member": 7,
        "test_obligation": 8,
    }
    for task in task_packets:
        task["closure_provenance"].sort(
            key=lambda item: (
                provenance_priority.get(str(item.get("via_edge")), 99),
                str(item.get("edge_id", "")),
            )
        )
        task["prerequisite_edges"] = sorted(
            task.get("prerequisite_edges", []),
            key=lambda item: (
                str(item.get("kind", "")),
                str(item.get("from_task_id", "")),
                str(item.get("to_task_id", "")),
            ),
        )
        task["dependent_task_ids"] = sorted(set(task.get("dependent_task_ids", [])))
        task["blocked_source_files"] = sorted(set(task.get("blocked_source_files", [])))
    ordered_task_ids = topological_sort(task_packets)
    task_packets_by_id = {task["id"]: task for task in task_packets}
    task_packets = [task_packets_by_id[task_id] for task_id in ordered_task_ids]
    production_node_ids = sorted(node["id"] for node in production_nodes)
    production_source_files_all = sorted(
        {
            source
            for node in production_nodes
            for source in production_source_files(node)
        }
    )
    covered_source_files = sorted(
        {
            source
            for task in task_packets
            for source in task["source_files"]
        }
    )
    seed_state = {
        task["id"]: {
            "status": seed_task_status(task, report_by_node, list(task.get("blocked_by", []))),
        }
        for task in task_packets
    }
    immutable_payload = {
        "schema": PLAN_SCHEMA,
        "source_revision": graph.get("source_revision"),
        "contract_sha256": contract_sha256,
        "skill_tree_digest": graph.get("skill_tree_digest"),
        "selected_skill": "migrate-android-compose-to-harmony",
        "prerequisite_edges": prerequisite_edges,
        "tasks": task_packets,
        "coverage": {
            "production_node_count": len(production_node_ids),
            "covered_production_node_count": len(assigned_production_node_ids),
            "uncovered_production_node_ids": [],
            "production_source_files": production_source_files_all,
            "covered_production_source_files": covered_source_files,
            "uncovered_production_source_files": [],
            "review_queue_unclassified_source_files": sorted(set(review_queue_sources)),
        },
    }
    plan_identity = canonical_sha256(immutable_payload)
    resolved_tasks, next_executable_tasks, blocked_tasks, topological_task_ids = apply_task_state_view(
        immutable_payload,
        {
            "tasks": seed_state,
        },
    )
    return {
        **immutable_payload,
        "contract_schema": CONTRACT_SCHEMA,
        "graph_schema": GRAPH_SCHEMA,
        "gate_report_schema": GATE_REPORT_SCHEMA,
        "review_queue_schema": REVIEW_QUEUE_SCHEMA,
        "plan_identity": plan_identity,
        "seed_task_states": seed_state,
        "next_executable_tasks": next_executable_tasks,
        "blocked_tasks": blocked_tasks,
        "topological_task_ids": topological_task_ids,
        "task_views": resolved_tasks,
    }


def build_execution_plan(
    contract: dict[str, Any],
    contract_sha256: str,
    graph: dict[str, Any],
    gate_report: dict[str, Any],
    *,
    graph_path: Path,
    gate_report_sha256: str,
) -> dict[str, Any]:
    if isinstance(graph.get("root_qualification"), list) and isinstance(
        graph.get("resolved_edges"), list
    ):
        return build_batch1_execution_plan(
            contract,
            contract_sha256,
            graph,
            gate_report,
            gate_report_sha256=gate_report_sha256,
        )
    validate_review_queue(graph, graph_path=str(graph_path))
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise PlannerError("graph nodes must be a list")
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise PlannerError("graph node entries must be objects")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise PlannerError("graph node is missing id")
        nodes_by_id[node_id] = node

    pages = [node for node in nodes if node.get("layer") == "page"]
    if not pages:
        raise PlannerError("execution plan requires at least one page node")
    pages.sort(key=lambda node: str(node["id"]))

    report_nodes = gate_report.get("nodes")
    if not isinstance(report_nodes, list):
        raise PlannerError("gate report nodes must be a list")
    report_by_node = {
        entry["id"]: entry
        for entry in report_nodes
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }

    batches = contract.get("migration_batches", [])
    if not isinstance(batches, list):
        raise PlannerError("contract migration_batches must be a list")
    batches = [batch for batch in batches if isinstance(batch, dict)]
    batches.sort(key=lambda batch: str(batch.get("id", "")))

    tasks: list[dict[str, Any]] = []
    page_task_ids: dict[str, str] = {}
    page_context: dict[str, dict[str, Any]] = {}
    assigned_node_to_task: dict[str, str] = {}
    ui_system_candidates: list[str] = []
    production_nodes = [
        node
        for node in nodes
        if node.get("layer") in PRODUCTION_LAYERS and production_source_files(node)
    ]
    test_support_nodes = [
        node for node in nodes if node.get("layer") == "test_support" and production_source_files(node)
    ]

    for page in pages:
        route = route_for_page(page, contract)
        route_slug = route or page["id"].split(":", 1)[-1]
        task_id = f"slice:{route_slug.lower().replace('/', '-').replace('_', '-')}"
        page_task_ids[page["id"]] = task_id
        route_entry = next(
            (
                candidate
                for candidate in contract.get("ui", {}).get("routes", [])
                if isinstance(candidate, dict)
                and candidate.get("route") == route
                and candidate.get("source") in set(production_source_files(page))
            ),
            None,
        )
        page_batches = [
            batch
            for batch in batches
            if set(production_source_files(page))
            & {path for path in batch.get("source_files", []) if isinstance(path, str)}
        ]
        anchor_tokens = node_tokens(page)
        if route_entry is not None:
            anchor_tokens.update(route_tokens(route_entry))
        for batch in page_batches:
            anchor_tokens.update(batch_tokens(batch))
        page_context[page["id"]] = {
            "task_id": task_id,
            "page": page,
            "route": route,
            "anchor_tokens": anchor_tokens,
            "batches": page_batches,
        }
        task = {
            "id": task_id,
            "kind": "vertical_slice",
            "route": route,
            "page_node_ids": [page["id"]],
            "control_node_ids": [],
            "ui_system_node_ids": [],
            "business_node_ids": [],
            "network_node_ids": [],
            "storage_node_ids": [],
            "platform_node_ids": [],
            "unclassified_node_ids": [],
            "related_test_support_node_ids": [],
            "primary_owner_node_ids": [page["id"]],
            "dependent_task_ids": [],
            "blocked_by": [],
            "blocked_source_files": [],
            "required_skills": ["migrate-android-compose-to-harmony"],
            "required_gates": list(page.get("required_gates", [])),
            "required_tests": list(page.get("required_tests", [])),
            "source_files": production_source_files(page),
            "evidence_identity": {
                "source_revision": graph.get("source_revision"),
                "contract_sha256": contract_sha256,
                "skill_tree_digest": graph.get("skill_tree_digest"),
                "gate_report_sha256": gate_report_sha256,
            },
            "status": "ready",
            "closure_provenance": [],
        }
        assigned_node_to_task[page["id"]] = task_id
        for child_id in page.get("child_ids", []):
            child = nodes_by_id.get(child_id)
            if not child or child.get("layer") != "control":
                continue
            task["control_node_ids"].append(child_id)
            task["primary_owner_node_ids"].append(child_id)
            task["required_gates"] = sorted(set(task["required_gates"]) | set(child.get("required_gates", [])))
            task["required_tests"] = sorted(set(task["required_tests"]) | set(child.get("required_tests", [])))
            task["source_files"] = sorted(set(task["source_files"]) | set(production_source_files(child)))
            assigned_node_to_task[child_id] = task_id
        tasks.append(task)

    tasks_by_id = {task["id"]: task for task in tasks}

    for node in production_nodes:
        node_id = str(node["id"])
        if node_id in assigned_node_to_task:
            continue
        layer = str(node.get("layer"))
        if layer == "ui_system":
            ui_system_candidates.append(node_id)
            continue
        best_page_id: str | None = None
        best_score = (-1, -1)
        for page_id, context in page_context.items():
            score = score_node_for_page(
                node,
                context["page"],
                context["anchor_tokens"],
                context["batches"],
            )
            if score > best_score:
                best_score = score
                best_page_id = page_id
        if best_page_id is None:
            raise PlannerError(
                f"unable to anchor production node {node_id!r} to any page slice"
            )
        if best_score[0] <= 0 and layer == "unclassified":
            raise PlannerError(
                f"unable to anchor production node {node_id!r} to any page slice"
            )
        task = tasks_by_id[page_task_ids[best_page_id]]
        field = f"{layer}_node_ids"
        if field not in task:
            raise PlannerError(f"unsupported production layer {layer!r}")
        task[field].append(node_id)
        task["primary_owner_node_ids"].append(node_id)
        task["required_gates"] = sorted(set(task["required_gates"]) | set(node.get("required_gates", [])))
        task["required_tests"] = sorted(set(task["required_tests"]) | set(node.get("required_tests", [])))
        task["source_files"] = sorted(set(task["source_files"]) | set(production_source_files(node)))
        assigned_node_to_task[node_id] = task["id"]

    for node_id in ui_system_candidates:
        node = nodes_by_id[node_id]
        best_task: dict[str, Any] | None = None
        best_score = (-1, -1)
        for page_id, context in page_context.items():
            score = score_node_for_page(
                node,
                context["page"],
                context["anchor_tokens"],
                context["batches"],
            )
            if score > best_score:
                best_score = score
                best_task = tasks_by_id[page_task_ids[page_id]]
        if best_task is None:
            best_task = tasks[0]
        best_task["ui_system_node_ids"].append(node_id)
        best_task["primary_owner_node_ids"].append(node_id)
        best_task["required_gates"] = sorted(
            set(best_task["required_gates"]) | set(node.get("required_gates", []))
        )
        best_task["required_tests"] = sorted(
            set(best_task["required_tests"]) | set(node.get("required_tests", []))
        )
        best_task["source_files"] = sorted(
            set(best_task["source_files"]) | set(production_source_files(node))
        )
        assigned_node_to_task[node_id] = best_task["id"]

    for node in test_support_nodes:
        node_id = str(node["id"])
        best_task: dict[str, Any] | None = None
        best_score = (-1, -1)
        for page_id, context in page_context.items():
            score = score_node_for_page(
                node,
                context["page"],
                context["anchor_tokens"],
                context["batches"],
            )
            if score > best_score:
                best_score = score
                best_task = tasks_by_id[page_task_ids[page_id]]
        if best_task is None:
            best_task = tasks[0]
        best_task["related_test_support_node_ids"].append(node_id)

    legacy_edges = graph.get("resolved_edges", [])
    if isinstance(legacy_edges, list):
        page_node_to_task = {
            page_id: page_task_ids[page_id] for page_id in page_task_ids
        }
        report_by_node_legacy = gate_report.get("report_by_node", {})
        if not isinstance(report_by_node_legacy, dict):
            report_by_node_legacy = {}
        changed = True
        while changed:
            changed = False
            for edge in legacy_edges:
                if not isinstance(edge, dict) or edge.get("kind") not in {"route_closure", "call"}:
                    continue
                from_node = edge.get("from")
                to_node = edge.get("to")
                if not isinstance(from_node, str) or not isinstance(to_node, str):
                    continue
                from_task_id = assigned_node_to_task.get(from_node)
                target_node = nodes_by_id.get(to_node)
                if not from_task_id or target_node is None:
                    continue
                if target_node.get("layer") == "test_support":
                    continue
                field = f"{target_node.get('layer')}_node_ids"
                if to_node in assigned_node_to_task:
                    current_task_id = assigned_node_to_task[to_node]
                    task = tasks_by_id[from_task_id]
                    if current_task_id != from_task_id and field in task:
                        previous_task = tasks_by_id[current_task_id]
                        if field in previous_task and to_node in previous_task[field]:
                            previous_task[field] = [
                                candidate for candidate in previous_task[field] if candidate != to_node
                            ]
                        previous_task["primary_owner_node_ids"] = [
                            candidate
                            for candidate in previous_task["primary_owner_node_ids"]
                            if candidate != to_node
                        ]
                        task[field].append(to_node)
                        task["primary_owner_node_ids"].append(to_node)
                        task["source_files"] = sorted(
                            set(task["source_files"]) | set(production_source_files(target_node))
                        )
                        assigned_node_to_task[to_node] = from_task_id
                    task["closure_provenance"].append(
                        {
                            "via_edge": edge.get("kind"),
                            "from_node_id": from_node,
                            "to_node_id": to_node,
                            "source_path": edge.get("source_path"),
                        }
                    )
                    continue
                task = tasks_by_id[from_task_id]
                if field in task:
                    task[field].append(to_node)
                    task["primary_owner_node_ids"].append(to_node)
                    task["required_gates"] = sorted(
                        set(task["required_gates"]) | set(target_node.get("required_gates", []))
                    )
                    task["required_tests"] = sorted(
                        set(task["required_tests"]) | set(target_node.get("required_tests", []))
                    )
                    task["source_files"] = sorted(
                        set(task["source_files"]) | set(production_source_files(target_node))
                    )
                    task["closure_provenance"].append(
                        {
                            "via_edge": edge.get("kind"),
                            "from_node_id": from_node,
                            "to_node_id": to_node,
                            "source_path": edge.get("source_path"),
                        }
                    )
                    assigned_node_to_task[to_node] = from_task_id
                    changed = True
        for edge in legacy_edges:
            if not isinstance(edge, dict) or edge.get("kind") != "navigation":
                continue
            from_node = edge.get("from")
            to_node = edge.get("to")
            if not isinstance(from_node, str) or not isinstance(to_node, str):
                continue
            from_task_id = page_node_to_task.get(from_node)
            to_task_id = page_node_to_task.get(to_node)
            if not from_task_id or not to_task_id or from_task_id == to_task_id:
                continue
            to_task = tasks_by_id[to_task_id]
            if from_task_id not in to_task["dependent_task_ids"]:
                to_task["dependent_task_ids"].append(from_task_id)
            to_task["status"] = "pending"

    unclassified_sources = set(
        graph.get("coverage", {}).get("unclassified_source_files", [])
        if isinstance(graph.get("coverage", {}), dict)
        else []
    )
    for task in tasks:
        for field in (
            "control_node_ids",
            "ui_system_node_ids",
            "business_node_ids",
            "network_node_ids",
            "storage_node_ids",
            "platform_node_ids",
            "unclassified_node_ids",
            "related_test_support_node_ids",
            "primary_owner_node_ids",
        ):
            task[field] = sorted(set(task[field]))
        task["source_files"] = sorted(set(task["source_files"]))
        task["required_gates"] = sorted(set(task["required_gates"]))
        task["required_tests"] = sorted(set(task["required_tests"]))
        blocked_sources = sorted(unclassified_sources & set(task["source_files"]))
        if blocked_sources:
            task["status"] = "blocked"
            task["blocked_source_files"] = blocked_sources
            task["blocked_by"] = [
                {
                    "kind": "review_queue",
                    "source_path": source_path,
                    "blocking_parent_gate": "project",
                }
                for source_path in blocked_sources
            ]
            for node_id in task["primary_owner_node_ids"]:
                if nodes_by_id[node_id].get("layer") == "unclassified":
                    task["unclassified_node_ids"].append(node_id)
        if task["status"] not in TASK_STATUSES:
            raise PlannerError(f"unsupported task status {task['status']!r}")

    ordered_task_ids = topological_sort(tasks)
    tasks.sort(key=lambda task: ordered_task_ids.index(task["id"]))

    production_node_ids = sorted(str(node["id"]) for node in production_nodes)
    covered_production_node_ids = sorted(
        {
            node_id
            for task in tasks
            for node_id in task["primary_owner_node_ids"]
            if nodes_by_id[node_id].get("layer") in PRODUCTION_LAYERS
        }
    )
    uncovered_production_node_ids = sorted(
        set(production_node_ids) - set(covered_production_node_ids)
    )
    if uncovered_production_node_ids:
        raise PlannerError(
            "execution plan left uncovered production nodes: "
            + ", ".join(uncovered_production_node_ids)
        )

    production_source_files_all = sorted(
        {
            source_path
            for node in production_nodes
            for source_path in production_source_files(node)
        }
    )
    covered_source_files = sorted(
        {
            source_path
            for task in tasks
            for node_id in task["primary_owner_node_ids"]
            for source_path in production_source_files(nodes_by_id[node_id])
            if nodes_by_id[node_id].get("layer") in PRODUCTION_LAYERS
        }
    )
    uncovered_source_files = sorted(
        set(production_source_files_all) - set(covered_source_files)
    )
    if uncovered_source_files:
        raise PlannerError(
            "execution plan left uncovered production source files: "
            + ", ".join(uncovered_source_files)
        )

    return {
        "schema": PLAN_SCHEMA,
        "contract_schema": CONTRACT_SCHEMA,
        "graph_schema": GRAPH_SCHEMA,
        "gate_report_schema": GATE_REPORT_SCHEMA,
        "review_queue_schema": REVIEW_QUEUE_SCHEMA,
        "source_revision": graph.get("source_revision"),
        "contract_sha256": contract_sha256,
        "skill_tree_digest": graph.get("skill_tree_digest"),
        "selected_skill": "migrate-android-compose-to-harmony",
        "next_executable_tasks": [task["id"] for task in tasks if task["status"] == "ready"],
        "blocked_tasks": [task["id"] for task in tasks if task["status"] == "blocked"],
        "topological_task_ids": ordered_task_ids,
        "coverage": {
            "production_node_count": len(production_node_ids),
            "covered_production_node_count": len(covered_production_node_ids),
            "uncovered_production_node_ids": uncovered_production_node_ids,
            "production_source_files": production_source_files_all,
            "covered_production_source_files": covered_source_files,
            "uncovered_production_source_files": uncovered_source_files,
            "review_queue_unclassified_source_files": sorted(unclassified_sources),
        },
        "tasks": tasks,
    }


def main() -> int:
    args = parse_args()
    try:
        contract, contract_sha256 = validate_contract(args.contract.resolve())
        graph = validate_graph(args.graph.resolve(), contract_sha256)
        gate_report, gate_report_sha256 = validate_gate_report(
            args.gate_report.resolve(),
            graph,
        )
        plan = build_execution_plan(
            contract,
            contract_sha256,
            graph,
            gate_report,
            graph_path=args.graph.resolve(),
            gate_report_sha256=gate_report_sha256,
        )
        write_json(args.output.resolve(), plan)
    except (PlannerError, GraphError, OSError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema": PLAN_SCHEMA,
                    "error": str(error),
                }
            )
        )
        return 1
    print(json.dumps({"ok": True, "schema": PLAN_SCHEMA, "output": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
