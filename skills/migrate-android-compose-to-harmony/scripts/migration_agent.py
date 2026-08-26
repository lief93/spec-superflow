#!/usr/bin/env python3
"""Orchestrate a resumable Android Compose to HarmonyOS migration run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aggregate_gate_evidence import (
    BUNDLE_SCHEMA as GATE_EVIDENCE_BUNDLE_SCHEMA,
    REPORT_SCHEMA as GATE_REPORT_SCHEMA,
    aggregate_report,
)
from build_capability_graph import (
    DEFAULT_REGISTRY as DEFAULT_GATE_PROFILE_REGISTRY,
    GRAPH_SCHEMA as CAPABILITY_GRAPH_SCHEMA,
    GraphError,
    materialize_graph_outputs,
    validate_registry as validate_gate_profile_registry,
)
from evidence_attestation import (
    EVIDENCE_GATES,
    NON_HUMAN_PROVIDER_PATTERN,
    PROBE_RUNNER_TYPES,
    REQUIRED_GATES,
    RUNNER_TYPES,
    classify_argv,
    classify_probe_argv,
    has_valid_tool_origin,
    has_valid_attestation,
    repair_ownership_record_permissions,
)
from evidence_runner import (
    RunnerError,
    build_log,
    extract_hypium_report_from_aa_stdout,
    parse_hypium_text_report,
)
from build_execution_plan import (
    PLAN_SCHEMA as EXECUTION_PLAN_SCHEMA,
    PlannerError,
    apply_task_state_view,
    build_execution_plan,
    canonical_sha256,
)
from init_harmony_project import (
    attach_ownership_proof,
    claim_external_ownership,
    has_external_ownership_proof,
)
from hash_skill_tree import create_manifest

SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS.parent
GENERATOR = "migrate-android-compose-to-harmony"
STATE_SCHEMA = "android-to-harmony.agent-state.v1"
OWNERSHIP_SCHEMA = "android-to-harmony.run-ownership.v1"
RESULT_SCHEMA = "android-to-harmony.agent-command-result.v1"
SNAPSHOT_NAME = "snapshot"
CONTRACT_NAME = "migration-contract.json"
STATE_NAME = "agent-state.json"
SKILL_TREE_MANIFEST_NAME = "skill-tree-manifest.json"
CAPABILITY_GRAPH_NAME = "capability-graph.json"
FACT_PACK_DIR_NAME = "fact-packs"
REVIEW_QUEUE_NAME = "review-queue.json"
GATE_EVIDENCE_BUNDLE_NAME = "gate-evidence-bundle.json"
GATE_REPORT_NAME = "gate-report.json"
EXECUTION_PLAN_NAME = "execution-plan.json"
EXECUTION_TASK_STATE_NAME = "execution-task-state.json"
EXECUTION_TASK_STATE_SCHEMA = "android-to-harmony.execution-task-state.v1"
EVIDENCE_SCHEMA = "android-to-harmony.evidence.v2"
RECONCILIATION_SCHEMA = "android-to-harmony.inventory-reconciliation.v1"
ANSI_CSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
HDC_FAILURE_PATTERN = re.compile(
    r"(?m)^[ \t]*\[Fail\]\[(E[0-9]{6})\][ \t]*(.+?)\r?$"
)
HDC_INSTALL_SUCCESS_PATTERN = re.compile(
    r"(?:install bundle successfully\.|\[Info\]App install "
    r"path:.+ msg:install bundle successfully\.)"
)
FINAL_SLICE_STATUSES = {
    "implemented",
    "verified",
    "intentionally_excluded",
    "unsupported",
}


class OrchestrationError(RuntimeError):
    def __init__(self, message: str, stage: str = "preflight") -> None:
        super().__init__(message)
        self.stage = stage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start, resume, or inspect an Android Compose to HarmonyOS "
            "migration run."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser(
        "start",
        help="Create a new isolated intake run and HarmonyOS scaffold.",
    )
    start.add_argument("--source", required=True, type=Path)
    start.add_argument("--run-root", required=True, type=Path)
    start.add_argument("--target", required=True, type=Path)
    start.add_argument("--project-name", required=True)
    start.add_argument("--bundle-name", required=True)
    start.add_argument(
        "--sdk-version",
        default="6.0.1(21)",
        help=(
            "HarmonyOS SDK version for the generated target, "
            "for example 6.1.1(24)"
        ),
    )
    resume = subparsers.add_parser(
        "resume",
        help="Revalidate an owned run and report the next unfinished work.",
    )
    resume.add_argument("--run-root", required=True, type=Path)
    status = subparsers.add_parser(
        "status",
        help="Read and report an owned run without changing it.",
    )
    status.add_argument("--run-root", required=True, type=Path)
    claim = subparsers.add_parser(
        "claim-target-ownership",
        help=(
            "Upgrade a validated legacy target with external ownership "
            "needed for evidence attestations."
        ),
    )
    claim.add_argument("--run-root", required=True, type=Path)
    return parser.parse_args()


def normalize_path(path: Path, role: str) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise OrchestrationError(f"{role} must not be a symbolic link: {absolute}")
    return absolute.resolve()


def paths_overlap(left: Path, right: Path) -> bool:
    return (
        left == right
        or left in right.parents
        or right in left.parents
    )


def require_isolated_paths(
    source: Path,
    run_root: Path,
    target: Path,
) -> None:
    paths = (
        ("source", source),
        ("run root", run_root),
        ("target", target),
    )
    for index, (left_role, left) in enumerate(paths):
        for right_role, right in paths[index + 1 :]:
            if paths_overlap(left, right):
                raise OrchestrationError(
                    f"{left_role} and {right_role} must be separate "
                    "directories that do not contain one another"
                )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_safe_descendant(
    root: Path,
    path: Path,
    role: str,
    stage: str,
) -> Path:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise OrchestrationError(
            f"{role} is outside the owned target: {path}",
            stage,
        ) from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise OrchestrationError(
                f"{role} contains a symbolic link: {current}",
                stage,
            )
    return path


def target_relative_path(
    target: Path,
    value: Any,
    role: str,
    stage: str,
) -> Path:
    if not isinstance(value, str) or not value:
        raise OrchestrationError(f"{role} must be a target-relative path", stage)
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise OrchestrationError(f"{role} must be a target-relative path", stage)
    return require_safe_descendant(target, target / relative, role, stage)


def parse_timestamp(value: Any, role: str, stage: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise OrchestrationError(f"{role} must be an RFC3339 timestamp", stage)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise OrchestrationError(
            f"{role} must be an RFC3339 timestamp",
            stage,
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OrchestrationError(
            f"{role} must include a timezone",
            stage,
        )
    return parsed


def load_json_object(
    path: Path,
    role: str,
    stage: str = "preflight",
) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise OrchestrationError(f"{role} is missing or unsafe: {path}", stage)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise OrchestrationError(f"invalid {role}: {error}", stage) from error
    if not isinstance(payload, dict):
        raise OrchestrationError(f"{role} must be a JSON object", stage)
    return payload


def run_tool(stage: str, script_name: str, *arguments: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script_name), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise OrchestrationError(
            f"{stage} tool returned invalid JSON: {detail}",
            stage,
        ) from error
    if (
        result.returncode != 0
        or not isinstance(payload, dict)
        or payload.get("ok") is not True
    ):
        if isinstance(payload, dict):
            detail = payload.get("error")
        else:
            detail = None
        raise OrchestrationError(
            f"{stage} failed: {detail or 'unknown tool failure'}",
            stage,
        )
    return payload


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
    replace: bool = False,
) -> None:
    if path.exists() and not replace:
        raise OrchestrationError(f"refusing to replace existing state: {path}")
    if replace and (not path.is_file() or path.is_symlink()):
        raise OrchestrationError(f"refusing to replace unsafe state: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.write-",
        dir=path.parent,
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


def require_hash(
    path: Path,
    expected: Any,
    role: str,
    stage: str,
) -> None:
    if (
        not isinstance(expected, str)
        or not path.is_file()
        or path.is_symlink()
        or sha256_file(path) != expected
    ):
        raise OrchestrationError(
            f"{role} is missing or changed after the run was recorded",
            stage,
        )


def require_string_path(
    paths: dict[str, Any],
    key: str,
    role: str,
) -> Path:
    value = paths.get(key)
    if not isinstance(value, str) or not value:
        raise OrchestrationError(f"run state has no valid {role} path")
    return normalize_path(Path(value), role)


def validate_run(
    run_root_argument: Path,
    *,
    allow_invalid_target_ownership: bool = False,
) -> dict[str, Any]:
    run_root = normalize_path(run_root_argument, "run root")
    if not run_root.is_dir():
        raise OrchestrationError(f"run root does not exist: {run_root}")
    state_path = run_root / STATE_NAME
    state = load_json_object(state_path, "agent state", "validate_state")
    ownership = state.get("ownership")
    if (
        state.get("schema") != STATE_SCHEMA
        or state.get("generator") != GENERATOR
        or not isinstance(ownership, dict)
        or ownership.get("schema") != OWNERSHIP_SCHEMA
        or ownership.get("run_root") != str(run_root)
        or not isinstance(ownership.get("run_id"), str)
        or not ownership.get("run_id")
    ):
        raise OrchestrationError(
            "run root is not owned by this migration agent",
            "validate_state",
        )

    paths = state.get("paths")
    artifacts = state.get("artifacts")
    project = state.get("project")
    if (
        not isinstance(paths, dict)
        or not isinstance(artifacts, dict)
        or not isinstance(project, dict)
    ):
        raise OrchestrationError(
            "agent state is missing paths, artifacts, or project identity",
            "validate_state",
        )
    source = require_string_path(paths, "source", "source")
    snapshot = require_string_path(paths, "snapshot", "snapshot")
    contract = require_string_path(paths, "contract", "contract")
    contract_owner = require_string_path(
        paths,
        "contract_owner",
        "contract owner",
    )
    target = require_string_path(paths, "target", "target")
    require_isolated_paths(source, run_root, target)
    if snapshot != run_root / SNAPSHOT_NAME:
        raise OrchestrationError(
            "snapshot path does not belong to the recorded run root",
            "validate_state",
        )
    if contract != run_root / CONTRACT_NAME:
        raise OrchestrationError(
            "contract path does not belong to the recorded run root",
            "validate_state",
        )
    if contract_owner != contract.with_name(f"{contract.name}.owner.json"):
        raise OrchestrationError(
            "contract owner path does not match the contract",
            "validate_state",
        )
    if not source.is_dir():
        raise OrchestrationError(
            f"recorded source directory is missing: {source}",
            "validate_source",
        )

    manifest_path = snapshot / ".android-to-harmony-safe.json"
    require_hash(
        manifest_path,
        artifacts.get("snapshot_manifest_sha256"),
        "safe snapshot manifest",
        "validate_snapshot",
    )
    run_tool(
        "validate_snapshot",
        "validate_ai_safe_tree.py",
        "--require-safe-manifest",
        str(snapshot),
    )
    manifest = load_json_object(
        manifest_path,
        "safe snapshot manifest",
        "validate_snapshot",
    )
    if (
        manifest.get("schema") != "android-to-harmony.safe-snapshot.v1"
        or manifest.get("snapshot_root") != str(snapshot)
        or manifest.get("source_root") != str(source)
    ):
        raise OrchestrationError(
            "safe snapshot ownership does not match this run",
            "validate_snapshot",
        )

    require_hash(
        contract,
        artifacts.get("contract_sha256"),
        "migration contract",
        "validate_contract",
    )
    require_hash(
        contract_owner,
        artifacts.get("contract_owner_sha256"),
        "migration contract owner",
        "validate_contract",
    )
    contract_payload = load_json_object(
        contract,
        "migration contract",
        "validate_contract",
    )
    owner_payload = load_json_object(
        contract_owner,
        "migration contract owner",
        "validate_contract",
    )
    contract_source = contract_payload.get("source")
    if (
        contract_payload.get("schema")
        != "android-to-harmony.migration-contract.v1"
        or contract_payload.get("generator") != GENERATOR
        or not isinstance(contract_source, dict)
        or contract_source.get("safe_snapshot_root") != str(snapshot)
        or contract_source.get("original_root") != str(source)
        or owner_payload.get("schema")
        != "android-to-harmony.contract-owner.v1"
        or owner_payload.get("generator") != GENERATOR
        or owner_payload.get("output_name") != contract.name
        or owner_payload.get("contract_sha256") != sha256_file(contract)
    ):
        raise OrchestrationError(
            "migration contract ownership does not match this run",
            "validate_contract",
        )

    if not target.is_dir():
        raise OrchestrationError(
            f"recorded target directory is missing: {target}",
            "validate_target",
        )
    target_state_path = target / ".migration" / "state.json"
    require_safe_descendant(
        target,
        target_state_path,
        "target project marker",
        "validate_target",
    )
    if artifacts.get("target_state_path") != str(target_state_path):
        raise OrchestrationError(
            "target state path does not match this run",
            "validate_target",
        )
    target_state = load_json_object(
        target_state_path,
        "target project marker",
        "validate_target",
    )
    output_root = target_state.get("output_root")
    if output_root == ".":
        recorded_target = target
    elif isinstance(output_root, str) and output_root:
        recorded_target = normalize_path(Path(output_root), "recorded target")
    else:
        recorded_target = None
    if (
        target_state.get("schema") != "android-to-harmony.project-state.v1"
        or target_state.get("generator") != GENERATOR
        or recorded_target != target
        or target_state.get("project_name") != project.get("name")
        or target_state.get("bundle_name") != project.get("bundle_name")
    ):
        raise OrchestrationError(
            "target project marker does not belong to this run",
            "validate_target",
        )
    ownership_reference = target_state.get("ownership")
    if (
        ownership_reference is not None
        and not has_external_ownership_proof(target, target_state)
        and not allow_invalid_target_ownership
    ):
        raise OrchestrationError(
            "target project ownership proof is invalid",
            "validate_target",
        )
    target_contract_state = target_state.get("contract")
    if (
        not isinstance(target_contract_state, dict)
        or target_contract_state.get("copied_path")
        != ".migration/source-contract.json"
    ):
        raise OrchestrationError(
            "target project is not bound to the migration contract",
            "validate_target",
        )
    target_contract_path = target / ".migration" / "source-contract.json"
    require_safe_descendant(
        target,
        target_contract_path,
        "target contract copy",
        "validate_target",
    )
    require_hash(
        target_contract_path,
        target_contract_state.get("sha256"),
        "target contract copy",
        "validate_target",
    )
    target_contract = load_json_object(
        target_contract_path,
        "target contract copy",
        "validate_target",
    )
    expected_target_contract = json.loads(json.dumps(contract_payload))
    expected_target_contract["source"]["safe_snapshot_root"] = (
        "<local-safe-snapshot>"
    )
    expected_target_contract["source"]["original_root"] = (
        "<local-android-source>"
    )
    if target_contract != expected_target_contract:
        raise OrchestrationError(
            "target contract copy does not match the owned contract",
            "validate_target",
        )

    batches = contract_payload.get("migration_batches")
    if (
        not isinstance(batches, list)
        or not all(isinstance(batch, dict) for batch in batches)
    ):
        raise OrchestrationError(
            "migration contract has an invalid batch inventory",
            "validate_contract",
        )
    contract_batch_ids = [
        batch.get("id")
        for batch in batches
        if isinstance(batch.get("id"), str)
    ]
    if (
        len(contract_batch_ids) != len(batches)
        or len(contract_batch_ids) != len(set(contract_batch_ids))
        or state.get("batch_ids") != contract_batch_ids
    ):
        raise OrchestrationError(
            "recorded batch inventory does not match the contract",
            "validate_contract",
        )
    inventory = contract_payload.get("inventory")
    if (
        not isinstance(inventory, dict)
        or inventory.get("status") != "candidate_requires_review"
        or inventory.get("authoritative") is not False
    ):
        raise OrchestrationError(
            "migration inventory is not the required non-authoritative candidate",
            "validate_contract",
        )
    return {
        "run_root": run_root,
        "state": state,
        "contract": contract_payload,
        "contract_path": contract,
        "snapshot_manifest": manifest,
        "target": target,
        "target_state": target_state,
    }


def capability_artifact_paths(run_root: Path) -> dict[str, Path]:
    return {
        "skill_tree_manifest": run_root / SKILL_TREE_MANIFEST_NAME,
        "capability_graph": run_root / CAPABILITY_GRAPH_NAME,
        "fact_pack_dir": run_root / FACT_PACK_DIR_NAME,
        "review_queue": run_root / REVIEW_QUEUE_NAME,
        "gate_evidence_bundle": run_root / GATE_EVIDENCE_BUNDLE_NAME,
        "gate_report": run_root / GATE_REPORT_NAME,
        "execution_plan": run_root / EXECUTION_PLAN_NAME,
        "execution_task_state": run_root / EXECUTION_TASK_STATE_NAME,
    }


def task_state_identity_payload(task_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": EXECUTION_TASK_STATE_SCHEMA,
        "plan_identity": task_state["plan_identity"],
        "tasks": task_state["tasks"],
    }


def canonical_execution_plan_identity_payload(plan: dict[str, Any]) -> dict[str, Any]:
    immutable_plan = json.loads(json.dumps(plan))
    immutable_plan.pop("plan_identity", None)
    immutable_plan.pop("seed_task_states", None)
    immutable_plan.pop("next_executable_tasks", None)
    immutable_plan.pop("blocked_tasks", None)
    immutable_plan.pop("task_views", None)
    for task in immutable_plan.get("tasks", []):
        if isinstance(task, dict):
            task.pop("status", None)
    return immutable_plan


def project_immutable_execution_plan(plan: dict[str, Any]) -> dict[str, Any]:
    immutable_plan = canonical_execution_plan_identity_payload(plan)
    immutable_plan["plan_identity"] = canonical_sha256(immutable_plan)
    return immutable_plan


def validate_execution_plan(plan: dict[str, Any]) -> dict[str, Any]:
    projected = project_immutable_execution_plan(plan)
    if plan != projected:
        raise OrchestrationError(
            "execution plan identity does not match canonical immutable payload",
            "execution_plan",
        )
    return plan


def build_execution_task_state(
    plan: dict[str, Any],
    *,
    seed_task_states: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed_states = seed_task_states
    if seed_states is None:
        seed_states = plan.get("seed_task_states", {})
    task_state = {
        "schema": EXECUTION_TASK_STATE_SCHEMA,
        "plan_identity": plan["plan_identity"],
        "tasks": {
            task_id: {"status": state["status"]}
            for task_id, state in seed_states.items()
        },
    }
    task_state["task_state_identity"] = sha256_bytes(
        (
            json.dumps(
                task_state_identity_payload(task_state),
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
    )
    return task_state


def validate_execution_task_state(
    task_state: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    if task_state.get("schema") != EXECUTION_TASK_STATE_SCHEMA:
        raise OrchestrationError("execution task state schema is invalid", "execution_plan")
    if task_state.get("plan_identity") != plan.get("plan_identity"):
        raise OrchestrationError("execution task state plan identity does not match current plan", "execution_plan")
    expected_identity = sha256_bytes(
        (
            json.dumps(
                task_state_identity_payload(task_state),
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
    )
    if task_state.get("task_state_identity") != expected_identity:
        raise OrchestrationError("execution task state identity does not match current state payload", "execution_plan")
    task_packets = plan.get("tasks", [])
    task_ids = {
        task["id"]
        for task in task_packets
        if isinstance(task, dict) and isinstance(task.get("id"), str)
    }
    task_records = task_state.get("tasks")
    if not isinstance(task_records, dict):
        raise OrchestrationError("execution task state tasks must be an object", "execution_plan")
    if set(task_records) != task_ids:
        raise OrchestrationError("execution task state tasks do not match current plan task set", "execution_plan")
    for task_id, record in task_records.items():
        if not isinstance(record, dict) or record.get("status") not in {"ready", "pending", "blocked", "completed"}:
            raise OrchestrationError(
                f"execution task state for {task_id!r} is invalid",
                "execution_plan",
            )
    return task_state


def join_execution_plan_state(
    plan: dict[str, Any],
    task_state: dict[str, Any],
) -> dict[str, Any]:
    tasks, next_executable_tasks, blocked_tasks, topological_task_ids = apply_task_state_view(
        plan,
        task_state,
    )
    return {
        "tasks": tasks,
        "next_executable_tasks": next_executable_tasks,
        "blocked_tasks": blocked_tasks,
        "topological_task_ids": topological_task_ids,
        "plan_identity": plan["plan_identity"],
        "task_state_identity": task_state["task_state_identity"],
    }


def load_gate_registry() -> dict[str, Any]:
    try:
        return validate_gate_profile_registry(DEFAULT_GATE_PROFILE_REGISTRY.resolve())
    except (GraphError, OSError) as error:
        raise OrchestrationError(
            f"gate profile registry is invalid: {error}",
            "capability_graph",
        ) from error


def skill_tree_manifest_payload() -> dict[str, Any]:
    try:
        return create_manifest(SKILL_ROOT.resolve())
    except Exception as error:  # pragma: no cover - defensive bridge
        raise OrchestrationError(
            f"unable to hash current skill tree: {error}",
            "capability_graph",
        ) from error


def build_capability_artifact_payloads(
    contract_payload: dict[str, Any],
    contract_path: Path,
    run_root: Path,
    *,
    fallback_source_revision: str,
) -> dict[str, dict[str, Any]]:
    contract_sha256 = sha256_file(contract_path)
    skill_manifest = skill_tree_manifest_payload()
    registry = load_gate_registry()
    graph_contract = json.loads(json.dumps(contract_payload))
    source = graph_contract.get("source")
    if not isinstance(source, dict):
        source = {}
        graph_contract["source"] = source
    git = source.get("git")
    if not isinstance(git, dict):
        git = {}
        source["git"] = git
    if not isinstance(git.get("revision"), str) or not git.get("revision"):
        git["revision"] = fallback_source_revision
    try:
        graph, fact_packs, review_queue = materialize_graph_outputs(
            graph_contract,
            contract_sha256,
            registry,
            skill_manifest["tree_sha256"],
        )
    except GraphError as error:
        raise OrchestrationError(str(error), "capability_graph") from error
    bundle = {
        "schema": GATE_EVIDENCE_BUNDLE_SCHEMA,
        "graph_schema": CAPABILITY_GRAPH_SCHEMA,
        "source_revision": graph.get("source_revision"),
        "contract_sha256": graph.get("contract_sha256"),
        "skill_tree_digest": graph.get("skill_tree_digest"),
        "nodes": [
            {
                "node_id": node["id"],
                "status": node.get("status", "candidate"),
                "evidence_ids": [],
            }
            for node in graph.get("nodes", [])
            if isinstance(node, dict) and isinstance(node.get("id"), str)
        ],
        "evidence": [],
    }
    try:
        with tempfile.TemporaryDirectory(prefix="android-harmony-capability-") as temporary:
            temp_root = Path(temporary)
            temp_review_queue = temp_root / REVIEW_QUEUE_NAME
            temp_graph = temp_root / CAPABILITY_GRAPH_NAME
            temp_bundle = temp_root / GATE_EVIDENCE_BUNDLE_NAME
            write_json_atomic(temp_review_queue, review_queue)
            graph_for_aggregation = json.loads(json.dumps(graph))
            graph_for_aggregation["review_queue"]["path"] = REVIEW_QUEUE_NAME
            write_json_atomic(temp_graph, graph_for_aggregation)
            write_json_atomic(temp_bundle, bundle)
            report = aggregate_report(
                graph_for_aggregation,
                bundle,
                graph_path=str(temp_graph.resolve()),
                evidence_path=str(temp_bundle.resolve()),
            )
    except Exception as error:
        raise OrchestrationError(
            f"gate report aggregation failed: {error}",
            "gate_report",
        ) from error
    artifact_paths = capability_artifact_paths(run_root)
    try:
        raw_execution_plan = build_execution_plan(
            graph_contract,
            contract_sha256,
            graph,
            report,
            graph_path=artifact_paths["capability_graph"].resolve(),
            gate_report_sha256=sha256_bytes(
                (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            ),
        )
    except PlannerError as error:
        raise OrchestrationError(
            f"execution plan generation failed: {error}",
            "execution_plan",
        ) from error
    execution_plan = project_immutable_execution_plan(raw_execution_plan)
    validate_execution_plan(execution_plan)
    execution_task_state = build_execution_task_state(
        execution_plan,
        seed_task_states=raw_execution_plan.get("seed_task_states", {}),
    )
    return {
        "skill_tree_manifest": skill_manifest,
        "capability_graph": graph,
        "review_queue": review_queue,
        "gate_evidence_bundle": bundle,
        "gate_report": report,
        "execution_plan": execution_plan,
        "execution_task_state": execution_task_state,
        "fact_packs": fact_packs,
    }


def materialize_capability_artifacts(
    contract_payload: dict[str, Any],
    contract_path: Path,
    run_root: Path,
    *,
    fallback_source_revision: str,
) -> dict[str, Any]:
    artifacts = capability_artifact_paths(run_root)
    payloads = build_capability_artifact_payloads(
        contract_payload,
        contract_path,
        run_root,
        fallback_source_revision=fallback_source_revision,
    )
    task_state = payloads["execution_task_state"]
    joined = join_execution_plan_state(payloads["execution_plan"], task_state)
    fact_pack_dir = artifacts["fact_pack_dir"]
    fact_pack_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        artifacts["skill_tree_manifest"],
        payloads["skill_tree_manifest"],
    )
    write_json_atomic(
        artifacts["capability_graph"],
        payloads["capability_graph"],
    )
    write_json_atomic(
        artifacts["review_queue"],
        payloads["review_queue"],
    )
    write_json_atomic(
        artifacts["gate_evidence_bundle"],
        payloads["gate_evidence_bundle"],
    )
    write_json_atomic(
        artifacts["gate_report"],
        payloads["gate_report"],
    )
    write_json_atomic(
        artifacts["execution_plan"],
        payloads["execution_plan"],
    )
    write_json_atomic(
        artifacts["execution_task_state"],
        task_state,
    )
    for filename, fact_pack in payloads["fact_packs"].items():
        write_json_atomic(fact_pack_dir / filename, fact_pack)
    return {
        "status": "current",
        "current": True,
        "paths": {name: str(path) for name, path in artifacts.items()},
        "skill_tree_digest": payloads["skill_tree_manifest"]["tree_sha256"],
        "graph_schema": payloads["capability_graph"]["schema"],
        "gate_report_schema": payloads["gate_report"]["schema"],
        "execution_plan_schema": payloads["execution_plan"]["schema"],
        "fact_pack_count": len(payloads["fact_packs"]),
        "node_count": len(payloads["capability_graph"]["nodes"]),
        "plan_task_count": len(payloads["execution_plan"]["tasks"]),
        "plan_identity": payloads["execution_plan"]["plan_identity"],
        "task_state_identity": task_state["task_state_identity"],
        "execution_plan": payloads["execution_plan"],
        "execution_task_state": task_state,
        "next_executable_tasks": joined["next_executable_tasks"],
        "blocked_tasks": joined["blocked_tasks"],
    }


def assess_capability_artifacts(
    contract_payload: dict[str, Any],
    contract_path: Path,
    run_root: Path,
    *,
    fallback_source_revision: str,
) -> dict[str, Any]:
    artifacts = capability_artifact_paths(run_root)
    payloads = build_capability_artifact_payloads(
        contract_payload,
        contract_path,
        run_root,
        fallback_source_revision=fallback_source_revision,
    )
    fact_pack_names = sorted(payloads["fact_packs"])
    expected_task_state = payloads["execution_task_state"]
    current = all(path.exists() and not path.is_symlink() for path in artifacts.values())
    details: list[str] = []
    stored_execution_plan: dict[str, Any] | None = None
    stored_task_state: dict[str, Any] | None = None
    if current:
        try:
            stored_skill_manifest = load_json_object(
                artifacts["skill_tree_manifest"],
                "skill tree manifest",
                "capability_graph",
            )
            stored_graph = load_json_object(
                artifacts["capability_graph"],
                "capability graph",
                "capability_graph",
            )
            stored_bundle = load_json_object(
                artifacts["gate_evidence_bundle"],
                "gate evidence bundle",
                "gate_report",
            )
            stored_report = load_json_object(
                artifacts["gate_report"],
                "gate report",
                "gate_report",
            )
            stored_execution_plan = load_json_object(
                artifacts["execution_plan"],
                "execution plan",
                "execution_plan",
            )
            validate_execution_plan(stored_execution_plan)
            stored_task_state = load_json_object(
                artifacts["execution_task_state"],
                "execution task state",
                "execution_plan",
            )
            current = (
                stored_skill_manifest == payloads["skill_tree_manifest"]
                and stored_graph == payloads["capability_graph"]
                and stored_bundle == payloads["gate_evidence_bundle"]
                and stored_report == payloads["gate_report"]
                and stored_execution_plan == payloads["execution_plan"]
            )
            if current:
                validate_execution_task_state(stored_task_state, stored_execution_plan)
                for filename in fact_pack_names:
                    stored_fact_pack = load_json_object(
                        artifacts["fact_pack_dir"] / filename,
                        f"fact pack {filename}",
                        "capability_graph",
                    )
                    if stored_fact_pack != payloads["fact_packs"][filename]:
                        current = False
                        details.append(f"fact pack drift: {filename}")
                        break
            elif stored_report != payloads["gate_report"]:
                details.append("gate report drift")
            elif stored_execution_plan != payloads["execution_plan"]:
                details.append("execution plan drift")
        except OrchestrationError as error:
            current = False
            details.append(str(error))
    else:
        missing = [
            name
            for name, path in artifacts.items()
            if not path.exists() or path.is_symlink()
        ]
        details.append(
            "missing persisted internal artifacts: " + ", ".join(sorted(missing))
        )
    if current and stored_execution_plan is not None and stored_task_state is not None:
        joined = join_execution_plan_state(stored_execution_plan, stored_task_state)
        plan_identity = stored_execution_plan["plan_identity"]
        task_state_identity = stored_task_state["task_state_identity"]
        execution_plan = stored_execution_plan
        execution_task_state = stored_task_state
    else:
        joined = join_execution_plan_state(payloads["execution_plan"], expected_task_state)
        plan_identity = payloads["execution_plan"]["plan_identity"]
        task_state_identity = expected_task_state["task_state_identity"]
        execution_plan = payloads["execution_plan"]
        execution_task_state = expected_task_state
    return {
        "status": "current" if current else "stale",
        "current": current,
        "paths": {name: str(path) for name, path in artifacts.items()},
        "skill_tree_digest": payloads["skill_tree_manifest"]["tree_sha256"],
        "graph_schema": payloads["capability_graph"]["schema"],
        "gate_report_schema": payloads["gate_report"]["schema"],
        "execution_plan_schema": payloads["execution_plan"]["schema"],
        "fact_pack_count": len(fact_pack_names),
        "node_count": len(payloads["capability_graph"]["nodes"]),
        "plan_task_count": len(payloads["execution_plan"]["tasks"]),
        "plan_identity": plan_identity,
        "task_state_identity": task_state_identity,
        "execution_plan": execution_plan,
        "execution_task_state": execution_task_state,
        "next_executable_tasks": joined["next_executable_tasks"],
        "blocked_tasks": joined["blocked_tasks"],
        "details": details,
    }


def expected_source_revision(state: dict[str, Any]) -> str:
    artifacts = state["artifacts"]
    return (
        "snapshot-sha256:"
        f"{artifacts['snapshot_manifest_sha256']}"
    )


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    )


def validate_target_artifact(
    target: Path,
    path_value: Any,
    sha256_value: Any,
    size_value: Any,
    role: str,
) -> Path:
    artifact = target_relative_path(
        target,
        path_value,
        role,
        "read_evidence",
    )
    if (
        not artifact.is_file()
        or artifact.is_symlink()
        or not is_sha256(sha256_value)
        or isinstance(size_value, bool)
        or not isinstance(size_value, int)
        or size_value < 0
        or artifact.stat().st_size != size_value
        or sha256_file(artifact) != sha256_value
    ):
        raise OrchestrationError(
            f"{role} is missing or changed: {path_value}",
            "read_evidence",
        )
    return artifact


def validate_nested_artifact(
    target: Path,
    record: Any,
    role: str,
) -> Path:
    if not isinstance(record, dict):
        raise OrchestrationError(
            f"{role} has an invalid schema",
            "read_evidence",
        )
    return validate_target_artifact(
        target,
        record.get("path"),
        record.get("sha256"),
        record.get("size"),
        role,
    )


def valid_probe_failure_record(
    evidence: dict[str, Any],
    argv: list[str],
) -> bool:
    probe_exit_code = evidence.get("probe_exit_code")
    failure = evidence.get("probe_failure")
    if (
        isinstance(probe_exit_code, bool)
        or not isinstance(probe_exit_code, int)
        or not isinstance(failure, dict)
    ):
        return False
    if failure.get("kind") == "nonzero_exit":
        return (
            probe_exit_code != 0
            and failure.get("exit_code") == probe_exit_code
        )
    return (
        failure.get("kind") == "hdc_failure_marker"
        and probe_exit_code == 0
        and Path(argv[0]).name.casefold() in {"hdc", "hdc.exe"}
        and isinstance(failure.get("code"), str)
        and re.fullmatch(r"E[0-9]{6}", failure["code"]) is not None
        and isinstance(failure.get("message"), str)
        and bool(failure["message"])
    )


def parse_hdc_ui_test_invocation(
    argv: list[str],
    device_id: str,
) -> dict[str, Any] | None:
    if (
        Path(argv[0]).name.casefold() not in {"hdc", "hdc.exe"}
        or len(argv) < 9
        or argv[1:6] != ["-t", device_id, "shell", "aa", "test"]
    ):
        return None
    unsafe = re.compile(r"[\s;&|><`$()]")
    if any(not value or unsafe.search(value) for value in argv[1:]):
        return None

    required: dict[str, str] = {}
    settings: dict[str, str] = {}
    index = 6
    while index < len(argv):
        option = argv[index]
        if option in {"-b", "-m"}:
            if option in required or index + 1 >= len(argv):
                return None
            required[option] = argv[index + 1]
            index += 2
            continue
        if option == "-s":
            if index + 2 >= len(argv):
                return None
            key = argv[index + 1]
            if key in settings:
                return None
            settings[key] = argv[index + 2]
            index += 3
            continue
        return None
    if (
        set(required) != {"-b", "-m"}
        or settings.get("unittest")
        not in {
            "OpenHarmonyTestRunner",
            "/ets/testrunner/OpenHarmonyTestRunner",
        }
    ):
        return None
    timeout = settings.get("timeout")
    if timeout is not None and (
        not timeout.isdecimal() or int(timeout) < 1
    ):
        return None
    return {
        "device_id": device_id,
        "bundle": required["-b"],
        "module": required["-m"],
        "runner": settings["unittest"],
        "class": settings.get("class"),
        "timeout_ms": int(timeout) if timeout is not None else None,
    }


def validate_ui_install_record(
    target: Path,
    record: Any,
    role: str,
    hdc_path: str,
    device_id: str,
    relative: str,
) -> Path:
    if not isinstance(record, dict):
        raise OrchestrationError(
            f"{role} UI HAP install record is invalid: {relative}",
            "read_evidence",
        )
    path = target_relative_path(
        target,
        record.get("path"),
        f"{role} UI HAP in {relative}",
        "read_evidence",
    )
    initial_sha256 = record.get("sha256")
    initial_size = record.get("size")
    if (
        path.suffix.casefold() != ".hap"
        or not is_sha256(initial_sha256)
        or isinstance(initial_size, bool)
        or not isinstance(initial_size, int)
        or initial_size < 1
    ):
        raise OrchestrationError(
            f"{role} UI artifact is not a non-empty HAP: {relative}",
            "read_evidence",
        )
    expected_argv = [
        hdc_path,
        "-t",
        device_id,
        "install",
        "-r",
        record["path"],
    ]
    exit_code = record.get("exit_code")
    stdout = record.get("stdout")
    stderr = record.get("stderr")
    post_sha256 = record.get("post_install_sha256")
    post_size = record.get("post_install_size")
    has_post_sha256 = "post_install_sha256" in record
    has_post_size = "post_install_size" in record
    if (
        record.get("role") != role
        or record.get("argv") != expected_argv
        or record.get("command") != shlex.join(expected_argv)
        or isinstance(exit_code, bool)
        or not isinstance(exit_code, int)
        or not isinstance(stdout, str)
        or not isinstance(stderr, str)
        or has_post_sha256 != has_post_size
        or (
            has_post_sha256
            and (
                not is_sha256(post_sha256)
                or isinstance(post_size, bool)
                or not isinstance(post_size, int)
                or post_size < 0
            )
        )
    ):
        raise OrchestrationError(
            f"{role} UI HAP install record is inconsistent: {relative}",
            "read_evidence",
        )
    if has_post_sha256:
        validate_target_artifact(
            target,
            record["path"],
            post_sha256,
            post_size,
            f"{role} UI HAP after install in {relative}",
        )

    output = ANSI_CSI_PATTERN.sub("", f"{stdout}\n{stderr}")
    success_lines = [
        line.strip()
        for line in stdout.splitlines()
        if HDC_INSTALL_SUCCESS_PATTERN.fullmatch(line.strip())
    ]
    succeeded = (
        exit_code == 0
        and HDC_FAILURE_PATTERN.search(output) is None
        and len(success_lines) == 1
        and has_post_sha256
        and post_sha256 == initial_sha256
        and post_size == initial_size
    )
    status = record.get("status")
    validation_error = record.get("validation_error")
    if (
        status != ("passed" if succeeded else "failed")
        or (
            status == "passed"
            and "validation_error" in record
        )
        or (
            status == "failed"
            and (
                not isinstance(validation_error, str)
                or not validation_error
            )
        )
    ):
        raise OrchestrationError(
            f"{role} UI HAP install result is inconsistent: {relative}",
            "read_evidence",
        )
    return path


def validate_ui_command_log_and_report(
    evidence: dict[str, Any],
    target: Path,
    argv: list[str],
    installed_haps: list[dict[str, Any]],
    test_command_executed: bool,
    report: dict[str, Any],
    relative: str,
) -> None:
    artifact_path = target_relative_path(
        target,
        evidence.get("artifact"),
        f"UITest command log in {relative}",
        "read_evidence",
    )
    try:
        artifact_bytes = artifact_path.read_bytes()
    except OSError as error:
        raise OrchestrationError(
            f"cannot read UITest command log in {relative}: {error}",
            "read_evidence",
        ) from error

    completed = subprocess.CompletedProcess(
        argv,
        evidence["exit_code"],
        stdout="",
        stderr="",
    )
    if not test_command_executed:
        expected = build_log(
            evidence["runner_type"],
            evidence["requested_argv"],
            argv,
            completed,
            installed_haps,
            False,
        )
        if (
            artifact_bytes != expected
            or report.get("status") != "invalid"
            or evidence["tests"]
            != {"passed": 0, "failed": 0, "skipped": 0}
        ):
            raise OrchestrationError(
                f"UITest pre-execution log is inconsistent: {relative}",
                "read_evidence",
            )
        return

    stdout_token = f"__UI_STDOUT_{uuid.uuid4().hex}__"
    template = build_log(
        evidence["runner_type"],
        evidence["requested_argv"],
        argv,
        subprocess.CompletedProcess(
            argv,
            evidence["exit_code"],
            stdout=stdout_token,
            stderr="",
        ),
        installed_haps,
        True,
    )
    prefix, separator, _suffix = template.partition(
        stdout_token.encode("utf-8")
    )
    stderr_separator = b"\n[stderr]\n"
    remainder = artifact_bytes[len(prefix):]
    if (
        not separator
        or not artifact_bytes.startswith(prefix)
        or remainder.count(stderr_separator) != 1
    ):
        raise OrchestrationError(
            f"UITest command log structure is inconsistent: {relative}",
            "read_evidence",
        )
    stdout_bytes, stderr_bytes = remainder.split(stderr_separator)
    try:
        stdout = stdout_bytes.decode("utf-8")
        stderr = stderr_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OrchestrationError(
            f"UITest command log is not valid UTF-8: {relative}",
            "read_evidence",
        ) from error
    completed = subprocess.CompletedProcess(
        argv,
        evidence["exit_code"],
        stdout=stdout,
        stderr=stderr,
    )
    if build_log(
        evidence["runner_type"],
        evidence["requested_argv"],
        argv,
        completed,
        installed_haps,
        True,
    ) != artifact_bytes:
        raise OrchestrationError(
            f"UITest command log does not match its evidence: {relative}",
            "read_evidence",
        )

    extracted_report: bytes | None = None
    combined_output = ANSI_CSI_PATTERN.sub("", f"{stdout}\n{stderr}")
    if HDC_FAILURE_PATTERN.search(combined_output) is None:
        try:
            extracted_report = extract_hypium_report_from_aa_stdout(stdout)
        except RunnerError:
            pass
    if extracted_report is None:
        if (
            report.get("status") != "invalid"
            or evidence["tests"]
            != {"passed": 0, "failed": 0, "skipped": 0}
        ):
            raise OrchestrationError(
                f"UITest output and report status disagree: {relative}",
                "read_evidence",
            )
        return
    if report.get("status") != "captured":
        raise OrchestrationError(
            f"UITest output report was not captured: {relative}",
            "read_evidence",
        )
    report_path = validate_nested_artifact(
        target,
        report,
        f"UITest Hypium report in {relative}",
    )
    try:
        parsed_tests = parse_hypium_text_report(report_path)
        report_bytes = report_path.read_bytes()
    except (OSError, RunnerError) as error:
        raise OrchestrationError(
            f"UITest Hypium report is invalid: {relative}",
            "read_evidence",
        ) from error
    if (
        report_bytes != extracted_report
        or parsed_tests != evidence["tests"]
    ):
        raise OrchestrationError(
            f"UITest Hypium report does not match command stdout: {relative}",
            "read_evidence",
        )


def validate_ui_run_evidence(
    evidence: dict[str, Any],
    target: Path,
    argv: list[str],
    device: dict[str, Any],
    report: dict[str, Any],
    relative: str,
) -> None:
    invocation = parse_hdc_ui_test_invocation(argv, device["id"])
    test_command_executed = evidence.get("test_command_executed")
    installed_haps = evidence.get("installed_haps")
    if (
        invocation is None
        or evidence.get("test_invocation") != invocation
        or not isinstance(test_command_executed, bool)
        or not isinstance(installed_haps, list)
        or len(installed_haps) not in {1, 2}
        or report.get("format") != "hypium-text"
        or report.get("source_kind") != "command_stdout"
        or report.get("stream") != "stdout"
        or report.get("source") != evidence.get("artifact")
    ):
        raise OrchestrationError(
            f"UITest evidence has no controlled HDC execution: {relative}",
            "read_evidence",
        )

    roles = ["main", "test"][: len(installed_haps)]
    installed_paths = [
        validate_ui_install_record(
            target,
            record,
            role,
            argv[0],
            device["id"],
            relative,
        )
        for role, record in zip(roles, installed_haps, strict=True)
    ]
    if len(set(installed_paths)) != len(installed_paths):
        raise OrchestrationError(
            f"UITest main and test HAP artifacts are not distinct: {relative}",
            "read_evidence",
        )

    install_statuses = [
        record["status"]
        for record in installed_haps
    ]
    all_installed = (
        len(installed_haps) == 2
        and install_statuses == ["passed", "passed"]
    )
    if (
        (len(installed_haps) == 1 and install_statuses != ["failed"])
        or (
            len(installed_haps) == 2
            and install_statuses[0] != "passed"
        )
        or test_command_executed != all_installed
        or (
            not test_command_executed
            and evidence.get("exit_code")
            != installed_haps[-1]["exit_code"]
        )
        or any(
            record.get("validation_error")
            not in evidence.get("validation_errors", [])
            for record in installed_haps
            if record["status"] == "failed"
        )
    ):
        raise OrchestrationError(
            f"UITest install sequence is inconsistent: {relative}",
            "read_evidence",
        )

    validate_ui_command_log_and_report(
        evidence,
        target,
        argv,
        installed_haps,
        test_command_executed,
        report,
        relative,
    )

    if evidence["status"] == "passed" and (
        not all_installed
        or not test_command_executed
        or evidence.get("execution_status") != "executed"
        or report.get("status") != "captured"
        or report.get("path") == evidence.get("artifact")
    ):
        raise OrchestrationError(
            f"UITest evidence is not a completed device run: {relative}",
            "read_evidence",
        )
    if (
        evidence["status"] != "passed"
        and "execution_status" in evidence
    ):
        raise OrchestrationError(
            f"failed UITest evidence claims execution success: {relative}",
            "read_evidence",
        )


def validate_evidence_record(
    path: Path,
    target: Path,
) -> dict[str, Any]:
    relative = path.relative_to(target).as_posix()
    evidence = load_json_object(
        path,
        f"evidence record {relative}",
        "read_evidence",
    )
    gate = evidence.get("gate")
    status = evidence.get("status")
    runner_mode = evidence.get("runner_mode")
    duration = evidence.get("duration_seconds")
    tests = evidence.get("tests")
    slice_ids = evidence.get("slice_ids")
    demand_ids = evidence.get("demand_ids")
    if (
        evidence.get("schema") != EVIDENCE_SCHEMA
        or gate not in EVIDENCE_GATES
        or status not in {"passed", "failed", "blocked"}
        or not isinstance(evidence.get("scope"), str)
        or not evidence.get("scope")
        or not isinstance(slice_ids, list)
        or not slice_ids
        or len(slice_ids) != len(set(slice_ids))
        or not all(isinstance(value, str) and value for value in slice_ids)
        or not isinstance(demand_ids, list)
        or not demand_ids
        or len(demand_ids) != len(set(demand_ids))
        or not all(isinstance(value, str) and value for value in demand_ids)
        or runner_mode not in {"run", "probe", "record"}
        or isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or duration < 0
        or not isinstance(tests, dict)
        or any(
            isinstance(tests.get(key), bool)
            or not isinstance(tests.get(key), int)
            or tests[key] < 0
            for key in ("passed", "failed", "skipped")
        )
        or not isinstance(evidence.get("source_revision"), str)
        or not evidence["source_revision"]
        or not isinstance(evidence.get("target_revision"), str)
        or not evidence["target_revision"]
        or not has_valid_attestation(evidence, target)
    ):
        raise OrchestrationError(
            f"evidence record has an invalid schema: {relative}",
            "read_evidence",
        )
    parse_timestamp(
        evidence.get("started_at"),
        f"evidence started_at in {relative}",
        "read_evidence",
    )
    artifact = validate_target_artifact(
        target,
        evidence.get("artifact"),
        evidence.get("artifact_sha256"),
        evidence.get("artifact_size"),
        f"evidence artifact in {relative}",
    )
    if not artifact.relative_to(target).as_posix().startswith(
        ".migration/evidence/artifacts/"
    ):
        raise OrchestrationError(
            f"evidence artifact is outside the owned artifact directory: {relative}",
            "read_evidence",
        )

    validation_errors = evidence.get("validation_errors")
    if validation_errors is not None and (
        not isinstance(validation_errors, list)
        or not validation_errors
        or not all(
            isinstance(value, str) and value
            for value in validation_errors
        )
    ):
        raise OrchestrationError(
            f"evidence validation errors are invalid: {relative}",
            "read_evidence",
        )

    if runner_mode in {"run", "probe"}:
        argv = evidence.get("argv")
        requested_argv = evidence.get("requested_argv")
        executable = evidence.get("executable")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(value, str) and value for value in argv)
            or not isinstance(requested_argv, list)
            or not requested_argv
            or not all(
                isinstance(value, str) and value
                for value in requested_argv
            )
            or not isinstance(executable, dict)
            or executable.get("requested") != requested_argv[0]
            or executable.get("resolved_path") != argv[0]
            or argv[1:] != requested_argv[1:]
            or not is_sha256(executable.get("sha256"))
            or isinstance(executable.get("size"), bool)
            or not isinstance(executable.get("size"), int)
            or executable["size"] < 0
            or evidence.get("command") != shlex.join(argv)
            or not has_valid_tool_origin(
                executable["resolved_path"],
                evidence.get("tool_origin"),
            )
        ):
            raise OrchestrationError(
                f"command evidence has an invalid executable identity: {relative}",
                "read_evidence",
            )
        expected_runner_type = (
            classify_probe_argv(gate, argv)
            if runner_mode == "probe"
            else classify_argv(gate, argv)
        )
        if expected_runner_type != evidence.get("runner_type"):
            raise OrchestrationError(
                f"command category does not match evidence gate: {relative}",
                "read_evidence",
            )
    else:
        if (
            gate not in {"device_test", "visual_review"}
            or evidence.get("runner_type") != RUNNER_TYPES[gate]
            or any(
                key in evidence
                for key in (
                    "argv",
                    "requested_argv",
                    "command",
                    "executable",
                    "tool_origin",
                    "validation_errors",
                )
            )
        ):
            raise OrchestrationError(
                f"recorded evidence has an invalid command shape: {relative}",
                "read_evidence",
            )

    device = evidence.get("device")
    if gate in {"ui_tests", "device_test"}:
        if runner_mode == "probe" and device == "unavailable":
            pass
        elif (
            not isinstance(device, dict)
            or any(
                not isinstance(device.get(key), str) or not device[key]
                for key in ("kind", "id", "os_version", "api_version")
            )
        ):
            raise OrchestrationError(
                f"device evidence has no concrete device identity: {relative}",
                "read_evidence",
            )
    elif gate == "visual_review":
        if "device" in evidence:
            raise OrchestrationError(
                f"visual review must not declare a device: {relative}",
                "read_evidence",
            )
    elif device != "not_applicable":
        raise OrchestrationError(
            f"non-device evidence must use device=not_applicable: {relative}",
            "read_evidence",
        )

    if runner_mode == "run":
        if gate not in {"build", "unit_tests", "ui_tests", "device_test"}:
            raise OrchestrationError(
                f"gate does not support command execution: {relative}",
                "read_evidence",
            )
        if (
            isinstance(evidence.get("exit_code"), bool)
            or not isinstance(evidence.get("exit_code"), int)
            or status == "blocked"
            or (status == "passed" and evidence["exit_code"] != 0)
            or (status == "passed" and validation_errors is not None)
            or (
                status == "failed"
                and evidence["exit_code"] == 0
                and validation_errors is None
            )
        ):
            raise OrchestrationError(
                f"command result does not match evidence status: {relative}",
                "read_evidence",
            )
        if gate == "build":
            output_artifacts = evidence.get("output_artifacts")
            if (
                not isinstance(output_artifacts, list)
                or (
                    status == "passed"
                    and not output_artifacts
                )
            ):
                raise OrchestrationError(
                    f"build evidence has no output artifacts: {relative}",
                    "read_evidence",
                )
            for index, output in enumerate(output_artifacts):
                validate_nested_artifact(
                    target,
                    output,
                    f"build output {index} in {relative}",
                )
            if "test_report" in evidence:
                raise OrchestrationError(
                    f"build evidence must not contain a test report: {relative}",
                    "read_evidence",
                )
        else:
            report = evidence.get("test_report")
            if (
                not isinstance(report, dict)
                or report.get("status")
                not in {"captured", "missing", "stale", "invalid"}
                or report.get("format") not in {"junit", "hypium-text"}
                or not isinstance(report.get("source"), str)
                or not report["source"]
            ):
                raise OrchestrationError(
                    f"test evidence has an invalid report record: {relative}",
                    "read_evidence",
                )
            target_relative_path(
                target,
                report["source"],
                f"test report source in {relative}",
                "read_evidence",
            )
            if report["status"] == "captured":
                report_path = validate_nested_artifact(
                    target,
                    report,
                    f"captured test report in {relative}",
                )
                if not report_path.relative_to(target).as_posix().startswith(
                    ".migration/evidence/artifacts/"
                ):
                    raise OrchestrationError(
                        f"captured test report is outside artifacts: {relative}",
                        "read_evidence",
                    )
            elif any(key in report for key in ("path", "sha256", "size")):
                raise OrchestrationError(
                    f"uncaptured test report must not name an artifact: {relative}",
                    "read_evidence",
                )
            if status == "passed" and (
                report["status"] != "captured"
                or tests["passed"] < 1
                or tests["failed"] != 0
            ):
                raise OrchestrationError(
                    f"passed test evidence has no clean executed report: {relative}",
                    "read_evidence",
                )
            if gate in {"ui_tests", "device_test"}:
                validate_ui_run_evidence(
                    evidence,
                    target,
                    argv,
                    device,
                    report,
                    relative,
                )
    elif runner_mode == "probe":
        if (
            gate not in PROBE_RUNNER_TYPES
            or status != "blocked"
            or evidence.get("exit_code") is not None
            or not valid_probe_failure_record(evidence, argv)
            or any(
                not isinstance(evidence.get(key), str) or not evidence[key]
                for key in ("blocker", "next_action")
            )
        ):
            raise OrchestrationError(
                f"blocked evidence lacks a failed controlled probe: {relative}",
                "read_evidence",
            )
    else:
        expected_counts = (
            {"passed": 1, "failed": 0, "skipped": 0}
            if status == "passed"
            else {"passed": 0, "failed": 1, "skipped": 0}
        )
        if (
            status == "blocked"
            or evidence.get("exit_code") is not None
            or tests != expected_counts
        ):
            raise OrchestrationError(
                f"recorded result does not match its status: {relative}",
                "read_evidence",
            )
        if gate == "device_test":
            if (
                evidence.get("provider_kind") != "human"
                or not isinstance(evidence.get("provider"), str)
                or not evidence["provider"]
                or NON_HUMAN_PROVIDER_PATTERN.search(evidence["provider"])
                or not isinstance(evidence.get("scenario_steps"), list)
                or not evidence["scenario_steps"]
                or not all(
                    isinstance(value, str) and value
                    for value in evidence["scenario_steps"]
                )
                or not isinstance(evidence.get("expected"), str)
                or not evidence["expected"]
                or not isinstance(evidence.get("actual"), str)
                or not evidence["actual"]
            ):
                raise OrchestrationError(
                    f"device evidence is missing scenario details: {relative}",
                    "read_evidence",
                )
        elif (
            evidence.get("provider_kind") != "human"
            or not isinstance(evidence.get("evidence_owner"), str)
            or not evidence["evidence_owner"]
            or not isinstance(evidence.get("actual"), str)
            or not evidence["actual"]
            or not isinstance(evidence.get("notes"), str)
            or not evidence["notes"]
        ):
            raise OrchestrationError(
                f"visual review is missing its human provider: {relative}",
                "read_evidence",
            )
    return evidence


def collect_evidence(
    target: Path,
    target_revision: str,
    source_revision: str,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    evidence_root = target / ".migration" / "evidence"
    by_path: dict[str, dict[str, Any]] = {}
    by_gate_candidates: dict[
        str,
        list[tuple[datetime, str, dict[str, Any]]],
    ] = {gate: [] for gate in EVIDENCE_GATES}
    blocked: list[dict[str, Any]] = []
    if evidence_root.exists():
        try:
            require_safe_descendant(
                target,
                evidence_root,
                "evidence directory",
                "read_evidence",
            )
            if not evidence_root.is_dir():
                raise OrchestrationError(
                    "evidence path is not a directory",
                    "read_evidence",
                )
        except OrchestrationError as error:
            blocked.append(
                {
                    "gate": "evidence",
                    "scope": ".migration/evidence",
                    "status": "blocked",
                    "reason": str(error),
                }
            )
        else:
            for path in sorted(evidence_root.glob("*.json")):
                relative = path.relative_to(target).as_posix()
                try:
                    require_safe_descendant(
                        target,
                        path,
                        f"evidence record {relative}",
                        "read_evidence",
                    )
                    evidence = validate_evidence_record(
                        path,
                        target,
                    )
                    started_at = parse_timestamp(
                        evidence["started_at"],
                        f"evidence started_at in {relative}",
                        "read_evidence",
                    )
                except OrchestrationError as error:
                    blocked.append(
                        {
                            "gate": "evidence",
                            "scope": relative,
                            "status": "blocked",
                            "reason": str(error),
                        }
                    )
                    continue
                if (
                    evidence.get("source_revision") == source_revision
                    and evidence.get("target_revision") == target_revision
                ):
                    by_path[relative] = evidence
                by_gate_candidates[evidence["gate"]].append(
                    (started_at, relative, evidence)
                )

    latest_by_gate: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    for gate in EVIDENCE_GATES:
        candidates = by_gate_candidates[gate]
        if not candidates:
            pending.append(
                {
                    "gate": gate,
                    "scope": "target",
                    "status": "pending",
                }
            )
            continue
        _, relative, latest = max(candidates, key=lambda item: (item[0], item[1]))
        latest_by_gate[gate] = latest
        if (
            latest.get("source_revision") != source_revision
            or latest.get("target_revision") != target_revision
        ):
            blocked.append(
                {
                    "gate": gate,
                    "scope": latest["scope"],
                    "status": "blocked",
                    "reason": f"latest {gate} evidence is stale",
                    "evidence": relative,
                }
            )
            continue
        if latest["status"] in {"blocked", "failed"}:
            blocked.append(
                {
                    "gate": gate,
                    "scope": latest["scope"],
                    "status": latest["status"],
                    "reason": latest.get("blocker")
                    or f"latest {gate} evidence reports {latest['status']}",
                    "evidence": relative,
                }
            )
    return by_path, latest_by_gate, pending, blocked


def collect_slice_progress(
    target: Path,
    batches: list[dict[str, Any]],
    evidence_by_path: dict[str, dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, set[str]],
]:
    batch_sources = {
        batch["id"]: set(batch.get("source_files", []))
        for batch in batches
    }
    verified_slices: list[dict[str, Any]] = []
    implemented_slices: list[dict[str, Any]] = []
    resolved_slices: list[dict[str, Any]] = []
    blocked_gates: list[dict[str, Any]] = []
    covered: dict[str, set[str]] = {
        batch_id: set() for batch_id in batch_sources
    }
    seen_slice_ids: set[str] = set()
    source_owners: dict[tuple[str, str], str] = {}
    slices_root = target / ".migration" / "slices"
    if slices_root.exists() and (
        not slices_root.is_dir() or slices_root.is_symlink()
    ):
        blocked_gates.append(
            {
                "gate": "slice_ledger",
                "scope": ".migration/slices",
                "status": "blocked",
                "reason": "slice ledger path is not a safe directory",
            }
        )
    elif slices_root.is_dir():
        try:
            require_safe_descendant(
                target,
                slices_root,
                "slice ledger directory",
                "read_slice_ledger",
            )
        except OrchestrationError as error:
            blocked_gates.append(
                {
                    "gate": "slice_ledger",
                    "scope": ".migration/slices",
                    "status": "blocked",
                    "reason": str(error),
                }
            )
            return (
                verified_slices,
                implemented_slices,
                resolved_slices,
                [],
                blocked_gates,
                covered,
            )
        for path in sorted(slices_root.iterdir()):
            if path.suffix != ".json":
                continue
            relative = path.relative_to(target).as_posix()
            try:
                require_safe_descendant(
                    target,
                    path,
                    f"slice ledger {relative}",
                    "read_slice_ledger",
                )
                ledger = load_json_object(
                    path,
                    f"slice ledger {relative}",
                    "read_slice_ledger",
                )
                slice_id = ledger.get("id")
                batch_id = ledger.get("batch_id")
                status = ledger.get("status")
                source_files = ledger.get("source_files")
                demand_ids = ledger.get("demand_ids")
                required_gates = ledger.get("required_gates")
                visual_check_required = ledger.get(
                    "human_visual_check_required",
                    False,
                )
                if (
                    ledger.get("schema")
                    != "android-to-harmony.slice-ledger.v1"
                    or not isinstance(slice_id, str)
                    or not slice_id
                    or batch_id not in batch_sources
                    or status
                    not in {
                        "pending",
                        "in_progress",
                        "blocked",
                        *FINAL_SLICE_STATUSES,
                    }
                    or not isinstance(source_files, list)
                    or not all(
                        isinstance(source_file, str)
                        for source_file in source_files
                    )
                    or len(source_files) != len(set(source_files))
                    or not set(source_files).issubset(batch_sources[batch_id])
                    or not isinstance(visual_check_required, bool)
                    or (
                        status in {"implemented", "verified"}
                        and (
                            not isinstance(demand_ids, list)
                            or not demand_ids
                            or len(demand_ids) != len(set(demand_ids))
                            or not all(
                                isinstance(value, str) and value
                                for value in demand_ids
                            )
                            or not isinstance(required_gates, list)
                            or set(required_gates) != set(REQUIRED_GATES)
                            or len(required_gates) != len(REQUIRED_GATES)
                        )
                    )
                ):
                    raise OrchestrationError(
                        "ledger schema, batch, status, or source coverage is invalid",
                        "read_slice_ledger",
                    )
                if slice_id in seen_slice_ids:
                    raise OrchestrationError(
                        f"duplicate slice id: {slice_id}",
                        "read_slice_ledger",
                    )
                seen_slice_ids.add(slice_id)
                for source_file in source_files:
                    owner_key = (batch_id, source_file)
                    if owner_key in source_owners:
                        raise OrchestrationError(
                            "source file is claimed by multiple slice ledgers: "
                            f"{source_file}",
                            "read_slice_ledger",
                        )
                    source_owners[owner_key] = slice_id
                evidence_refs = ledger.get("evidence")
                if status == "verified":
                    if (
                        not isinstance(evidence_refs, list)
                        or len(evidence_refs) != len(set(evidence_refs))
                        or not all(
                            isinstance(reference, str) and reference
                            for reference in evidence_refs
                        )
                    ):
                        raise OrchestrationError(
                            "verified slice must reference evidence records",
                            "read_slice_ledger",
                        )
                    referenced = [
                        evidence_by_path.get(reference)
                        for reference in evidence_refs
                    ]
                    if any(record is None for record in referenced):
                        raise OrchestrationError(
                            "verified slice references missing or stale evidence",
                            "read_slice_ledger",
                        )
                    referenced_gates = {
                        record["gate"]
                        for record in referenced
                        if record is not None and record["status"] == "passed"
                    }
                    if not set(required_gates).issubset(referenced_gates):
                        raise OrchestrationError(
                            "verified slice is missing passed required gate evidence",
                            "read_slice_ledger",
                        )
                    for required_gate in required_gates:
                        covered_demands = {
                            demand_id
                            for record in referenced
                            if record is not None
                            and record["gate"] == required_gate
                            and record["status"] == "passed"
                            and slice_id in record["slice_ids"]
                            for demand_id in record["demand_ids"]
                        }
                        if not set(demand_ids).issubset(covered_demands):
                            raise OrchestrationError(
                                "verified slice evidence scope does not cover "
                                f"every demand in {slice_id} for gate "
                                f"{required_gate}",
                                "read_slice_ledger",
                            )
                elif status == "intentionally_excluded":
                    if (
                        not isinstance(ledger.get("rationale"), str)
                        or not ledger["rationale"]
                    ):
                        raise OrchestrationError(
                            "excluded slice requires a rationale",
                            "read_slice_ledger",
                        )
                elif status == "unsupported":
                    if any(
                        not isinstance(ledger.get(key), str) or not ledger[key]
                        for key in ("rationale", "decision_owner")
                    ):
                        raise OrchestrationError(
                            "unsupported slice requires rationale and decision owner",
                            "read_slice_ledger",
                        )
            except OrchestrationError as error:
                blocked_gates.append(
                    {
                        "gate": "slice_ledger",
                        "scope": relative,
                        "status": "blocked",
                        "reason": str(error),
                    }
                )
                continue
            summary = {
                "id": slice_id,
                "batch_id": batch_id,
                "status": status,
                "source_files": source_files,
                "ledger": relative,
            }
            if status == "verified":
                summary["evidence"] = ledger["evidence"]
                summary["required_gates"] = required_gates
                summary["demand_ids"] = demand_ids
                summary["human_visual_check_required"] = (
                    visual_check_required
                )
                verified_slices.append(summary)
                resolved_slices.append(summary)
                covered[batch_id].update(source_files)
            elif status == "implemented":
                summary["required_gates"] = required_gates
                summary["demand_ids"] = demand_ids
                summary["human_visual_check_required"] = (
                    visual_check_required
                )
                implemented_slices.append(summary)
                resolved_slices.append(summary)
                covered[batch_id].update(source_files)
            elif status in {"intentionally_excluded", "unsupported"}:
                summary["rationale"] = ledger["rationale"]
                resolved_slices.append(summary)
                covered[batch_id].update(source_files)
            elif status == "blocked":
                blocked_gates.append(
                    {
                        "gate": "slice",
                        "scope": slice_id,
                        "status": "blocked",
                        "reason": ledger.get("blocker")
                        or "slice ledger reports a blocker",
                    }
                )

    pending_batches: list[dict[str, Any]] = []
    for batch in batches:
        batch_id = batch["id"]
        source_files = batch.get("source_files", [])
        remaining = sorted(set(source_files) - covered[batch_id])
        if remaining:
            pending_batches.append(
                {
                    "id": batch_id,
                    "goal": batch.get("goal"),
                    "source_file_count": len(source_files),
                    "remaining_source_file_count": len(remaining),
                    "remaining_source_files": remaining,
                }
            )
    return (
        verified_slices,
        implemented_slices,
        resolved_slices,
        pending_batches,
        blocked_gates,
        covered,
    )


def reconcile_inventory(
    validated: dict[str, Any],
    covered: dict[str, set[str]],
    pending_batches: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    target = validated["target"]
    state = validated["state"]
    contract = validated["contract"]
    snapshot_manifest = validated["snapshot_manifest"]
    pending: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    contract_sources = {
        source_file
        for batch in contract["migration_batches"]
        for source_file in batch.get("source_files", [])
    }
    snapshot_sources = set(snapshot_manifest.get("text_files", []))
    if contract_sources != snapshot_sources:
        blocked.append(
            {
                "gate": "inventory_reconciliation",
                "scope": "target",
                "status": "blocked",
                "reason": (
                    "contract batch inventory does not exactly cover the "
                    "validated safe snapshot"
                ),
            }
        )
    reconciliation_path = target / ".migration/inventory-reconciliation.json"
    if not reconciliation_path.exists():
        pending.append(
            {
                "gate": "inventory_reconciliation",
                "scope": "target",
                "status": "pending",
            }
        )
        valid_reconciliation = False
    else:
        try:
            require_safe_descendant(
                target,
                reconciliation_path,
                "inventory reconciliation",
                "reconcile_inventory",
            )
            reconciliation = load_json_object(
                reconciliation_path,
                "inventory reconciliation",
                "reconcile_inventory",
            )
            if (
                reconciliation.get("schema") != RECONCILIATION_SCHEMA
                or reconciliation.get("status") != "authoritative"
                or reconciliation.get("all_snapshot_files_reviewed") is not True
                or reconciliation.get("snapshot_manifest_sha256")
                != state["artifacts"]["snapshot_manifest_sha256"]
                or reconciliation.get("contract_sha256")
                != state["artifacts"]["contract_sha256"]
                or not isinstance(reconciliation.get("reviewer"), str)
                or not reconciliation["reviewer"]
            ):
                raise OrchestrationError(
                    "inventory reconciliation is incomplete or stale",
                    "reconcile_inventory",
                )
            parse_timestamp(
                reconciliation.get("reviewed_at"),
                "inventory reconciliation reviewed_at",
                "reconcile_inventory",
            )
            valid_reconciliation = True
        except OrchestrationError as error:
            valid_reconciliation = False
            blocked.append(
                {
                    "gate": "inventory_reconciliation",
                    "scope": ".migration/inventory-reconciliation.json",
                    "status": "blocked",
                    "reason": str(error),
                }
            )
    authoritative = (
        valid_reconciliation
        and not pending_batches
        and not blocked
        and all(
            set(batch.get("source_files", [])).issubset(covered[batch["id"]])
            for batch in contract["migration_batches"]
        )
    )
    return (
        {
            "status": (
                "authoritative"
                if authoritative
                else contract["inventory"].get("status")
            ),
            "quality": contract.get("inventory_quality"),
            "candidate": not authoritative,
            "authoritative": authoritative,
        },
        pending,
        blocked,
    )


def target_is_scaffold_only(
    target: Path,
    target_state: dict[str, Any],
) -> bool:
    generated_hashes = target_state.get("generated_file_sha256")
    if not isinstance(generated_hashes, dict):
        return False
    for relative, expected in generated_hashes.items():
        if not isinstance(relative, str) or relative.startswith(".migration/"):
            continue
        path = target / relative
        if (
            not isinstance(expected, str)
            or not path.is_file()
            or path.is_symlink()
            or sha256_file(path) != expected
        ):
            return False
    generated_product_files = {
        relative
        for relative in generated_hashes
        if isinstance(relative, str) and not relative.startswith(".migration/")
    }
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(target)
        parts = relative.parts
        if not parts:
            continue
        if parts[0] == ".migration":
            continue
        if any(part in {".hvigor", ".test", "oh_modules"} for part in parts):
            continue
        if parts[0] in {"build", ".idea"}:
            continue
        if len(parts) >= 2 and parts[1] == "build":
            continue
        if relative.as_posix() not in generated_product_files:
            return False
    return True


def claim_target_ownership(run_root_argument: Path) -> dict[str, Any]:
    validated = validate_run(
        run_root_argument,
        allow_invalid_target_ownership=True,
    )
    target = validated["target"]
    target_state = validated["target_state"]
    state_path = target / ".migration/state.json"
    if has_external_ownership_proof(target, target_state):
        return {
            "ok": True,
            "schema": RESULT_SCHEMA,
            "command": "claim-target-ownership",
            "target": str(target),
            "ownership_ready": True,
            "changed": False,
        }
    if target_state.get("ownership") is not None:
        if repair_ownership_record_permissions(target, target_state):
            return {
                "ok": True,
                "schema": RESULT_SCHEMA,
                "command": "claim-target-ownership",
                "target": str(target),
                "ownership_ready": True,
                "changed": True,
            }
        raise OrchestrationError(
            "refusing to replace an invalid target ownership proof",
            "claim_target_ownership",
        )
    current_state = load_json_object(
        state_path,
        "target project marker",
        "claim_target_ownership",
    )
    if current_state != target_state:
        raise OrchestrationError(
            "target project marker changed during ownership upgrade",
            "claim_target_ownership",
        )
    secret = claim_external_ownership(target)
    attach_ownership_proof(current_state, target, secret)
    write_json_atomic(state_path, current_state, replace=True)
    written = load_json_object(
        state_path,
        "target project marker",
        "claim_target_ownership",
    )
    if not has_external_ownership_proof(target, written):
        raise OrchestrationError(
            "target ownership upgrade could not be verified",
            "claim_target_ownership",
        )
    return {
        "ok": True,
        "schema": RESULT_SCHEMA,
        "command": "claim-target-ownership",
        "target": str(target),
        "ownership_ready": True,
        "changed": True,
    }


def report_run(
    run_root_argument: Path,
    command: str,
) -> dict[str, Any]:
    validated = validate_run(run_root_argument)
    capability_artifacts = assess_capability_artifacts(
        validated["contract"],
        validated["contract_path"],
        validated["run_root"],
        fallback_source_revision=expected_source_revision(validated["state"]),
    )
    if not capability_artifacts["current"]:
        details = capability_artifacts.get("details") or ["execution plan drift"]
        raise OrchestrationError(
            "; ".join(str(detail) for detail in details),
            "execution_plan",
        )
    contract = validated["contract"]
    target = validated["target"]
    target_state = validated["target_state"]
    batches = contract["migration_batches"]
    revision_result = run_tool(
        "validate_target_revision",
        "hash_target_source.py",
        "--target",
        str(target),
    )
    target_revision = revision_result["manifest_hash"]
    (
        evidence_by_path,
        latest_evidence,
        pending_gates,
        evidence_blocked,
    ) = collect_evidence(
        target,
        target_revision,
        expected_source_revision(validated["state"]),
    )
    (
        verified_slices,
        implemented_slices,
        resolved_slices,
        pending_batches,
        slice_blocked,
        covered,
    ) = collect_slice_progress(target, batches, evidence_by_path)
    visual_required_slices = [
        item
        for item in (*verified_slices, *implemented_slices)
        if item.get("human_visual_check_required") is True
    ]
    pending_gates = [
        item
        for item in pending_gates
        if item.get("gate") != "visual_review"
    ]
    if not visual_required_slices:
        evidence_blocked = [
            item
            for item in evidence_blocked
            if item.get("gate") != "visual_review"
        ]
    else:
        visual_blocked = any(
            item.get("gate") == "visual_review"
            for item in evidence_blocked
        )
        current_visual_records = [
            record
            for record in evidence_by_path.values()
            if record["gate"] == "visual_review"
            and record["status"] == "passed"
        ]
        if not current_visual_records and not visual_blocked:
            pending_gates.append(
                {
                    "gate": "visual_review",
                    "scope": "human_visual_check_required",
                    "status": "pending",
                }
            )
        elif current_visual_records:
            uncovered_visual_slices: list[str] = []
            for item in visual_required_slices:
                covered_demands = {
                    demand_id
                    for record in current_visual_records
                    if item["id"] in record["slice_ids"]
                    for demand_id in record["demand_ids"]
                }
                if not set(item["demand_ids"]).issubset(covered_demands):
                    uncovered_visual_slices.append(item["id"])
            if uncovered_visual_slices:
                evidence_blocked.append(
                    {
                        "gate": "visual_review",
                        "scope": "human_visual_check_required",
                        "status": "blocked",
                        "reason": (
                            "current passed visual review does not cover: "
                            + ", ".join(uncovered_visual_slices)
                        ),
                    }
                )
    inventory, inventory_pending, inventory_blocked = reconcile_inventory(
        validated,
        covered,
        pending_batches,
    )
    pending_gates.extend(inventory_pending)
    pending_gates.extend(
        {
            "gate": "slice_verification",
            "scope": item["id"],
            "status": "pending",
            "required_gates": item["required_gates"],
        }
        for item in implemented_slices
    )
    ownership_ready = has_external_ownership_proof(target, target_state)
    if not ownership_ready:
        pending_gates.append(
            {
                "gate": "target_ownership",
                "scope": ".migration/state.json",
                "status": "pending",
                "next_action": (
                    "Run claim-target-ownership for this validated legacy run"
                ),
            }
        )
    blocked_gates = [
        *evidence_blocked,
        *slice_blocked,
        *inventory_blocked,
    ]

    if blocked_gates:
        next_phase = "resolve_blocked_gate"
    elif pending_batches:
        next_phase = "implement_and_verify_slice"
    elif not ownership_ready:
        next_phase = "claim_target_ownership"
    elif pending_gates:
        next_phase = "run_verification_gates"
    elif target_is_scaffold_only(target, target_state):
        next_phase = "implement_and_verify_slice"
    else:
        next_phase = "complete"

    scaffold_only = target_is_scaffold_only(target, target_state)
    complete = (
        inventory["authoritative"] is True
        and not scaffold_only
        and not pending_batches
        and not pending_gates
        and not blocked_gates
    )
    return {
        "ok": True,
        "schema": RESULT_SCHEMA,
        "command": command,
        "run_root": str(validated["run_root"]),
        "target": {
            "path": str(target),
            "scaffold_only": scaffold_only,
            "ownership_ready": ownership_ready,
        },
        "inventory": {
            **inventory,
        },
        "target_revision": target_revision,
        "verified_slices": verified_slices,
        "implemented_slices": implemented_slices,
        "resolved_slices": resolved_slices,
        "pending_batches": pending_batches,
        "blocked_gates": blocked_gates,
        "pending_gates": pending_gates,
        "latest_evidence": {
            gate: evidence.get("status")
            for gate, evidence in latest_evidence.items()
        },
        "visual_review_required_slices": [
            item["id"] for item in visual_required_slices
        ],
        "capability_artifacts": capability_artifacts,
        "plan_identity": capability_artifacts["plan_identity"],
        "task_state_identity": capability_artifacts["task_state_identity"],
        "execution_plan": capability_artifacts["execution_plan"],
        "execution_task_state": capability_artifacts["execution_task_state"],
        "next_executable_tasks": capability_artifacts["next_executable_tasks"],
        "blocked_tasks": capability_artifacts["blocked_tasks"],
        "next_phase": next_phase,
        "next_batch": (
            pending_batches[0]["id"] if pending_batches else None
        ),
        "complete": complete,
    }


def start_run(args: argparse.Namespace) -> dict[str, Any]:
    source = normalize_path(args.source, "source")
    run_root = normalize_path(args.run_root, "run root")
    target = normalize_path(args.target, "target")
    require_isolated_paths(source, run_root, target)
    if not source.is_dir():
        raise OrchestrationError(f"source directory does not exist: {source}")
    if run_root.exists():
        raise OrchestrationError(
            "run root already exists and is not owned by this new run; "
            "choose a new path or use resume for an existing owned run"
        )
    if target.exists():
        raise OrchestrationError(
            "target already exists; choose a new target directory"
        )

    run_root.parent.mkdir(parents=True, exist_ok=True)
    run_root.mkdir()
    snapshot = run_root / SNAPSHOT_NAME
    contract = run_root / CONTRACT_NAME
    contract_owner = contract.with_name(f"{contract.name}.owner.json")

    try:
        run_tool(
            "prepare_snapshot",
            "prepare_safe_snapshot.py",
            "--source",
            str(source),
            "--snapshot",
            str(snapshot),
        )
        run_tool(
            "validate_snapshot",
            "validate_ai_safe_tree.py",
            "--require-safe-manifest",
            str(snapshot),
        )
        run_tool(
            "analyze_contract",
            "analyze_compose_project.py",
            "--snapshot",
            str(snapshot),
            "--output",
            str(contract),
        )
        run_tool(
            "initialize_target",
            "init_harmony_project.py",
            "--output",
            str(target),
            "--project-name",
            args.project_name,
            "--bundle-name",
            args.bundle_name,
            "--sdk-version",
            args.sdk_version,
            "--contract",
            str(contract),
        )
    except (OSError, OrchestrationError):
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        if run_root.is_symlink():
            run_root.unlink()
        elif run_root.is_dir():
            shutil.rmtree(run_root)
        raise

    manifest_path = snapshot / ".android-to-harmony-safe.json"
    target_state_path = target / ".migration" / "state.json"
    contract_payload = load_json_object(contract, "migration contract")
    batches = contract_payload.get("migration_batches")
    if not isinstance(batches, list):
        raise OrchestrationError(
            "migration contract has no batch inventory",
            "record_state",
        )
    batch_ids = [
        batch.get("id")
        for batch in batches
        if isinstance(batch, dict) and isinstance(batch.get("id"), str)
    ]
    next_phase = (
        "implement_and_verify_slice"
        if batch_ids
        else "reconcile_inventory_and_completion_gates"
    )
    try:
        state = {
            "schema": STATE_SCHEMA,
            "generator": GENERATOR,
            "ownership": {
                "schema": OWNERSHIP_SCHEMA,
                "run_id": str(uuid.uuid4()),
                "run_root": str(run_root),
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "phase": "implementation",
            "paths": {
                "source": str(source),
                "snapshot": str(snapshot),
                "contract": str(contract),
                "contract_owner": str(contract_owner),
                "target": str(target),
            },
            "project": {
                "name": args.project_name,
                "bundle_name": args.bundle_name,
                "sdk_version": args.sdk_version,
            },
            "artifacts": {
                "snapshot_manifest_sha256": sha256_file(manifest_path),
                "contract_sha256": sha256_file(contract),
                "contract_owner_sha256": sha256_file(contract_owner),
                "target_state_path": str(target_state_path),
            },
            "inventory": {
                "status": contract_payload.get("inventory", {}).get("status"),
                "authoritative": contract_payload.get("inventory", {}).get(
                    "authoritative"
                ),
                "quality": contract_payload.get("inventory_quality"),
            },
            "batch_ids": batch_ids,
        }
        capability_artifacts = materialize_capability_artifacts(
            contract_payload,
            contract,
            run_root,
            fallback_source_revision=(
                "snapshot-sha256:" f"{sha256_file(manifest_path)}"
            ),
        )
        write_json_atomic(run_root / STATE_NAME, state)
    except (OSError, OrchestrationError):
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        if run_root.is_symlink():
            run_root.unlink()
        elif run_root.is_dir():
            shutil.rmtree(run_root)
        raise
    return {
        "ok": True,
        "schema": RESULT_SCHEMA,
        "command": "start",
        "run_root": str(run_root),
        "target": str(target),
        "state": str(run_root / STATE_NAME),
        "capability_artifacts": capability_artifacts,
        "plan_identity": capability_artifacts["plan_identity"],
        "task_state_identity": capability_artifacts["task_state_identity"],
        "execution_plan": capability_artifacts["execution_plan"],
        "execution_task_state": capability_artifacts["execution_task_state"],
        "next_executable_tasks": capability_artifacts["next_executable_tasks"],
        "blocked_tasks": capability_artifacts["blocked_tasks"],
        "next_phase": next_phase,
        "next_batch": batch_ids[0] if batch_ids else None,
        "pending_batches": batch_ids,
    }


def main() -> int:
    args = parse_args()
    try:
        if args.command == "start":
            result = start_run(args)
        elif args.command in {"resume", "status"}:
            result = report_run(args.run_root, args.command)
        elif args.command == "claim-target-ownership":
            result = claim_target_ownership(args.run_root)
        else:
            raise OrchestrationError(f"unsupported command: {args.command}")
    except (
        OrchestrationError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema": RESULT_SCHEMA,
                    "command": getattr(args, "command", None),
                    "failed_stage": getattr(error, "stage", "orchestrator"),
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
