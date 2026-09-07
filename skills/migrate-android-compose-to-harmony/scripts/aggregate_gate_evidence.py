#!/usr/bin/env python3
"""Aggregate existing gate evidence for an Android-to-Harmony capability graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


GRAPH_SCHEMA = "android-to-harmony.capability-graph.v1"
BUNDLE_SCHEMA = "android-to-harmony.gate-evidence-bundle.v1"
REPORT_SCHEMA = "android-to-harmony.gate-report.v1"
REVIEW_QUEUE_SCHEMA = "android-to-harmony.review-queue.v1"
FINAL_STATUSES = {"verified", "unsupported", "intentionally_excluded"}
ALLOWED_STATUSES = {"candidate", "implemented", "verified", "unsupported", "intentionally_excluded"}
DEVICE_ARTIFACTS = {"device_ui_test", "family_device_ui_test", "page_ui_test"}
VISUAL_ARTIFACTS = {"visual_review"}
MANUAL_ARTIFACTS = {"manual_review"}


class AggregationError(RuntimeError):
    """Raised when aggregation inputs are invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate existing Android-to-Harmony gate evidence."
    )
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path, expected_schema: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AggregationError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise AggregationError(f"JSON payload must be an object: {path}")
    if payload.get("schema") != expected_schema:
        raise AggregationError(
            f"schema must be {expected_schema!r}; received {payload.get('schema')!r}"
        )
    return payload


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


def artifact_satisfies_gate(gate: str, artifact_type: str) -> bool:
    if gate == "behavior_contract":
        return artifact_type == "behavior_contract_validation"
    if gate in {"mapping_semantics", "capability_mapping", "exact_closure", "state_matrix", "navigation_callbacks", "resource_mapping", "endpoint_contract", "request_response_contract", "auth_error_retry_cache", "schema_contract", "default_values", "migration_semantics", "child_dispositions"}:
        return artifact_type in {
            "mapping_review",
            "contract_tests",
            "unit_tests",
            "repository_tests",
            "report",
            "review",
        }
    if gate in {"synthetic_tests", "state_transition_tests", "contract_tests", "repository_tests", "unit_tests"}:
        return artifact_type in {"synthetic_tests", "unit_tests", "contract_tests", "repository_tests"}
    if gate in {"sdk_compile", "build"}:
        return artifact_type in {"build", "sdk_compile"}
    if gate in {"family_runtime_ui_test", "page_ui_test", "device_test", "adapter_device_evidence", "ui_tests"}:
        return artifact_type in DEVICE_ARTIFACTS
    if gate == "visual_review":
        return artifact_type in VISUAL_ARTIFACTS
    if gate == "manual_review":
        return artifact_type in MANUAL_ARTIFACTS
    if gate == "production_adapter":
        return artifact_type in {"contract_tests", "integration_tests", "adapter_tests"}
    if gate == "permission_lifecycle":
        return artifact_type in {"device_ui_test", "integration_tests", "review"}
    return True


def evidence_covers_node(evidence: dict[str, Any], node: dict[str, Any]) -> bool:
    node_ids = evidence.get("node_ids")
    if isinstance(node_ids, list) and node["id"] in node_ids:
        return True
    mapping_ids = evidence.get("mapping_ids")
    if isinstance(mapping_ids, list) and node.get("mapping_id") in mapping_ids:
        return True
    families = evidence.get("control_families")
    if isinstance(families, list) and node.get("control_family") in families:
        return True
    profiles = evidence.get("gate_profiles")
    if isinstance(profiles, list) and node.get("gate_profile") in profiles:
        return True
    return False


def validate_bindings(graph: dict[str, Any], bundle: dict[str, Any]) -> None:
    if bundle.get("graph_schema") != GRAPH_SCHEMA:
        raise AggregationError(
            f"evidence bundle graph_schema must be {GRAPH_SCHEMA!r}; "
            f"received {bundle.get('graph_schema')!r}"
        )
    for field in ("source_revision", "contract_sha256", "skill_tree_digest"):
        graph_value = graph.get(field)
        bundle_value = bundle.get(field)
        if graph_value != bundle_value:
            raise AggregationError(
                f"stale evidence bundle binding for {field}: "
                f"graph={graph_value!r}, evidence={bundle_value!r}"
            )


def validate_review_queue(graph: dict[str, Any], *, graph_path: str) -> dict[str, Any]:
    coverage = graph.get("coverage", {})
    unclassified = coverage.get("unclassified_source_files", [])
    if not isinstance(unclassified, list):
        raise AggregationError("graph coverage.unclassified_source_files must be a list")
    summary = graph.get("review_queue")
    if not unclassified:
        return summary if isinstance(summary, dict) else {}
    if not isinstance(summary, dict):
        raise AggregationError("review queue metadata is missing for unclassified sources")
    if summary.get("schema") != REVIEW_QUEUE_SCHEMA:
        raise AggregationError("review queue metadata schema is invalid")
    relative = summary.get("path")
    expected_sha256 = summary.get("sha256")
    if not isinstance(relative, str) or not relative:
        raise AggregationError("review queue path is missing")
    queue_path = Path(relative)
    if not queue_path.is_absolute():
        queue_path = Path(graph_path).resolve().parent / queue_path
    try:
        queue_bytes = queue_path.read_bytes()
    except OSError as error:
        raise AggregationError(f"review queue is missing: {error}") from error
    if not isinstance(expected_sha256, str) or hashlib.sha256(queue_bytes).hexdigest() != expected_sha256:
        raise AggregationError("review queue digest does not match the current graph")
    try:
        payload = json.loads(queue_bytes)
    except json.JSONDecodeError as error:
        raise AggregationError(f"review queue is invalid JSON: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema") != REVIEW_QUEUE_SCHEMA:
        raise AggregationError("review queue schema is invalid")
    queue_sources = payload.get("unclassified_source_files")
    if not isinstance(queue_sources, list):
        raise AggregationError("review queue unclassified_source_files must be a list")
    if sorted(queue_sources) != sorted(unclassified):
        raise AggregationError("review queue does not match graph unclassified_source_files")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise AggregationError("review queue entries must be a list")
    if payload.get("entry_count") != len(entries):
        raise AggregationError("review queue entry_count does not match entries")
    entry_sources = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("source_path"), str):
            raise AggregationError("review queue entry is missing source_path")
        entry_sources.append(entry["source_path"])
    if sorted(entry_sources) != sorted(unclassified):
        raise AggregationError("review queue entries do not exactly cover unclassified sources")
    return payload


def aggregate_report(
    graph: dict[str, Any],
    bundle: dict[str, Any],
    *,
    graph_path: str,
    evidence_path: str,
) -> dict[str, Any]:
    validate_bindings(graph, bundle)
    review_queue_payload = validate_review_queue(graph, graph_path=graph_path)
    graph_bytes = Path(graph_path).read_bytes()
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise AggregationError("graph nodes must be a list")
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise AggregationError("graph node entries must be objects")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise AggregationError("graph node is missing id")
        if node_id in nodes_by_id:
            raise AggregationError(f"duplicate graph node id: {node_id}")
        nodes_by_id[node_id] = node
    evidence_entries = bundle.get("evidence")
    if not isinstance(evidence_entries, list):
        raise AggregationError("evidence bundle evidence must be a list")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for entry in evidence_entries:
        if not isinstance(entry, dict):
            raise AggregationError("evidence entries must be objects")
        evidence_id = entry.get("id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise AggregationError("evidence entry is missing id")
        if evidence_id in evidence_by_id:
            raise AggregationError(f"duplicate evidence id: {evidence_id}")
        for field in ("source_revision", "contract_sha256", "skill_tree_digest"):
            if entry.get(field) != graph.get(field):
                raise AggregationError(
                    f"stale evidence {evidence_id!r}: {field} does not match current graph"
                )
        evidence_by_id[evidence_id] = entry

    bundle_nodes = bundle.get("nodes")
    if not isinstance(bundle_nodes, list):
        raise AggregationError("evidence bundle nodes must be a list")
    bundle_node_map: dict[str, dict[str, Any]] = {}
    for entry in bundle_nodes:
        if not isinstance(entry, dict):
            raise AggregationError("evidence bundle node entries must be objects")
        node_id = entry.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            raise AggregationError("evidence bundle node is missing node_id")
        if node_id in bundle_node_map:
            raise AggregationError(f"duplicate evidence node override: {node_id}")
        if node_id not in nodes_by_id:
            raise AggregationError(f"evidence references unknown node: {node_id}")
        bundle_node_map[node_id] = entry

    report_nodes: list[dict[str, Any]] = []
    report_by_node: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    pending_lookup = {
        node_id: bundle_node_map.get(node_id, {}).get(
            "status",
            nodes_by_id[node_id].get("status", "candidate"),
        )
        for node_id in nodes_by_id
    }
    if graph.get("coverage", {}).get("unassigned_source_files") and any(
        override.get("status") == "verified"
        and nodes_by_id[override["node_id"]].get("layer") == "project"
        for override in bundle_node_map.values()
    ):
        raise AggregationError(
            "unassigned source files remain; project cannot be verified"
        )
    if graph.get("coverage", {}).get("unclassified_source_files") and any(
        override.get("status") == "verified"
        and nodes_by_id[override["node_id"]].get("layer") == "project"
        for override in bundle_node_map.values()
    ):
        raise AggregationError(
            "unclassified production source files remain; project cannot be verified"
        )

    for node in sorted(nodes_by_id.values(), key=lambda item: item["id"]):
        override = bundle_node_map.get(node["id"], {})
        status = override.get("status", node.get("status", "candidate"))
        if status not in ALLOWED_STATUSES:
            raise AggregationError(
                f"unsupported node status {status!r} for {node['id']}"
            )
        if status == "unsupported":
            rationale = override.get("rationale", node.get("rationale"))
            decision_owner = override.get("decision_owner", node.get("decision_owner"))
            if not rationale or not decision_owner:
                raise AggregationError(
                    f"unsupported node {node['id']!r} requires rationale and decision_owner"
                )
        if status == "intentionally_excluded" and not override.get(
            "rationale", node.get("rationale")
        ):
            raise AggregationError(
                f"intentionally_excluded node {node['id']!r} requires rationale"
            )
        if status == "verified":
            node_failures: list[str] = []
            unresolved = node.get("unresolved", [])
            if isinstance(unresolved, list) and unresolved:
                node_failures.append(
                    f"node {node['id']!r} has unresolved items prevent verified status"
                )
            for child_id in node.get("child_ids", []):
                child_status = pending_lookup.get(child_id, "candidate")
                if child_status not in FINAL_STATUSES:
                    node_failures.append(
                        f"child node {child_id!r} is not in a final passing disposition"
                    )
            if node_failures:
                failures.extend(node_failures)
                continue
            required_gates = node.get("required_gates", [])
            evidence_ids = override.get("evidence_ids", [])
            if not isinstance(required_gates, list):
                raise AggregationError(
                    f"node {node['id']!r} required_gates must be a list"
                )
            if not isinstance(evidence_ids, list):
                raise AggregationError(
                    f"node {node['id']!r} evidence_ids must be a list"
                )
            for gate in required_gates:
                matches = [
                    evidence_by_id[evidence_id]
                    for evidence_id in evidence_ids
                    if evidence_id in evidence_by_id
                    and evidence_by_id[evidence_id].get("gate") == gate
                    and evidence_by_id[evidence_id].get("passed") is True
                    and evidence_covers_node(evidence_by_id[evidence_id], node)
                ]
                if not matches:
                    node_failures.append(
                        f"node {node['id']!r} is missing required gate evidence for {gate}"
                    )
                    continue
                for match in matches:
                    artifact_type = str(match.get("artifact_type", ""))
                    if not artifact_satisfies_gate(gate, artifact_type):
                        node_failures.append(
                            f"evidence {match['id']!r} cannot satisfy gate {gate!r} "
                            f"with artifact_type {artifact_type!r}"
                        )
            failures.extend(node_failures)
        report_nodes.append(
            {
                "id": node["id"],
                "layer": node.get("layer"),
                "status": status,
                "gate_profile": node.get("gate_profile"),
                "required_gates": node.get("required_gates", []),
            }
        )
        report_by_node[node["id"]] = {
            "status": status,
            "failed_gates": [],
            "evidence_ids": list(override.get("evidence_ids", []))
            if isinstance(override.get("evidence_ids"), list)
            else [],
        }
    if failures:
        raise AggregationError("; ".join(failures))

    node_statuses_bytes = (
        json.dumps(report_by_node, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    )

    return {
        "schema": REPORT_SCHEMA,
        "source_revision": graph.get("source_revision"),
        "contract_sha256": graph.get("contract_sha256"),
        "skill_tree_digest": graph.get("skill_tree_digest"),
        "graph_sha256": hashlib.sha256(graph_bytes).hexdigest(),
        "graph_node_ids": sorted(nodes_by_id),
        "graph_path": Path(graph_path).name,
        "evidence_path": Path(evidence_path).name,
        "review_queue": {
            "sha256": graph.get("review_queue", {}).get("sha256"),
            "entry_count": review_queue_payload.get("entry_count", 0),
            "unclassified_source_files": review_queue_payload.get(
                "unclassified_source_files",
                [],
            ),
        },
        "review_queue_sha256": graph.get("review_queue", {}).get("sha256"),
        "node_statuses_sha256": hashlib.sha256(node_statuses_bytes).hexdigest(),
        "nodes": report_nodes,
        "report_by_node": report_by_node,
    }


def main() -> int:
    args = parse_args()
    try:
        graph = load_json(args.graph.resolve(), GRAPH_SCHEMA)
        bundle = load_json(args.evidence.resolve(), BUNDLE_SCHEMA)
        report = aggregate_report(
            graph,
            bundle,
            graph_path=str(args.graph.resolve()),
            evidence_path=str(args.evidence.resolve()),
        )
        write_json(args.output.resolve(), report)
    except AggregationError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "node_count": len(report["nodes"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
