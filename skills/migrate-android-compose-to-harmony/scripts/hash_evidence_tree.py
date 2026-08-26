#!/usr/bin/env python3
"""Generate or verify a portable manifest for frozen execution-plan evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "android-to-harmony.execution-plan-evidence-tree.v1"
PROJECTS = ("banking", "ekspensify", "buckwheat")
CENTRAL_MANIFEST = "skill-identities/bundled-skill-tree-manifest.json"
CENTRAL_BINDING = "skill-identities/repo-skill-binding.json"
PROJECT_REQUIRED_FILES = (
    "contract/migration-contract.json",
    "contract/migration-contract.json.owner.json",
    "capability-graph.json",
    "review-queue.json",
    "gate-report.json",
    "execution-plan.json",
    "frozen-task-state.json",
    "logs/01-start.stdout.txt",
    "logs/01-start.stderr.txt",
    "logs/01-start.command.log",
    "logs/02-status.stdout.txt",
    "logs/02-status.stderr.txt",
    "logs/02-status.command.log",
    "exit/01-start.exit.json",
    "exit/02-status.exit.json",
    "tests/start-status.test.log",
    "skill-identity-reference.json",
    "source-identity.json",
)
BUCKWHEAT_ACQUISITION_REQUIRED_FILES = (
    "logs/00-clone.stdout.txt",
    "logs/00-clone.stderr.txt",
    "logs/00-clone.command.log",
    "logs/00-revision-present.stdout.txt",
    "logs/00-revision-present.stderr.txt",
    "logs/00-revision-present.command.log",
    "logs/00-checkout.stdout.txt",
    "logs/00-checkout.stderr.txt",
    "logs/00-checkout.command.log",
    "logs/00-source-final-remote.stdout.txt",
    "logs/00-source-final-remote.stderr.txt",
    "logs/00-source-final-remote.command.log",
    "logs/00-source-final-head.stdout.txt",
    "logs/00-source-final-head.stderr.txt",
    "logs/00-source-final-head.command.log",
    "logs/00-source-final-detached.stdout.txt",
    "logs/00-source-final-detached.stderr.txt",
    "logs/00-source-final-detached.command.log",
    "exit/00-clone.exit.json",
    "exit/00-revision-present.exit.json",
    "exit/00-checkout.exit.json",
    "exit/00-source-final-remote.exit.json",
    "exit/00-source-final-head.exit.json",
    "exit/00-source-final-detached.exit.json",
)


class EvidenceManifestError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or verify relative-path SHA-256 evidence membership."
    )
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--change-dir", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path)
    destination.add_argument("--input", type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceManifestError(f"invalid {role}: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise EvidenceManifestError(f"{role} must be a JSON object: {path}")
    return payload


def normalize_paths(
    change_dir: Path,
    evidence_root: Path,
    manifest_path: Path,
) -> tuple[Path, Path, Path]:
    change_input = Path(os.path.abspath(os.path.expanduser(str(change_dir))))
    evidence_input = Path(os.path.abspath(os.path.expanduser(str(evidence_root))))
    manifest_input = Path(os.path.abspath(os.path.expanduser(str(manifest_path))))
    if change_input.is_symlink() or evidence_input.is_symlink() or manifest_input.is_symlink():
        raise EvidenceManifestError("manifest paths must not be symbolic links")
    change = change_input.resolve()
    evidence = evidence_input.resolve()
    manifest = manifest_input.resolve()
    if not change.is_dir():
        raise EvidenceManifestError(f"change directory is invalid: {change}")
    if not evidence.is_dir():
        raise EvidenceManifestError(f"evidence root is invalid: {evidence}")
    if evidence != change / "evidence":
        raise EvidenceManifestError("evidence root must be the change-local evidence directory")
    if evidence not in manifest.parents:
        raise EvidenceManifestError("manifest must be stored inside the evidence root")
    return change, evidence, manifest


def require_regular_file(path: Path, role: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise EvidenceManifestError(f"missing or unsafe {role}: {path}")


def validate_skill_identity(evidence_root: Path, project: str) -> None:
    central_manifest = evidence_root / CENTRAL_MANIFEST
    central_binding = evidence_root / CENTRAL_BINDING
    require_regular_file(central_manifest, "central Skill manifest")
    require_regular_file(central_binding, "central Skill binding")
    manifest = load_json(central_manifest, "central Skill manifest")
    binding = load_json(central_binding, "central Skill binding")
    if manifest.get("schema") != "android-to-harmony.skill-tree-manifest.v1":
        raise EvidenceManifestError("central Skill manifest schema is invalid")
    local_root = manifest.get("local_root")
    if (
        local_root != "skills/migrate-android-compose-to-harmony"
        or Path(local_root).is_absolute()
    ):
        raise EvidenceManifestError("central Skill manifest root is not portable")
    if binding.get("schema") != "android-to-harmony.repo-skill-binding.v1":
        raise EvidenceManifestError("central Skill binding schema is invalid")
    if binding.get("bundled_skill_path") != local_root:
        raise EvidenceManifestError("central Skill binding path does not match the manifest")
    if binding.get("manifest_path") != CENTRAL_MANIFEST:
        raise EvidenceManifestError("central Skill binding manifest path is not portable")
    if binding.get("bundled_tree_sha256") != manifest.get("tree_sha256"):
        raise EvidenceManifestError("central Skill binding digest does not match the manifest")
    if binding.get("file_count") != manifest.get("file_count"):
        raise EvidenceManifestError("central Skill binding file count does not match the manifest")

    reference_path = (
        evidence_root
        / "execution-plan-dag-v1"
        / project
        / "skill-identity-reference.json"
    )
    require_regular_file(reference_path, f"{project} Skill identity reference")
    reference = load_json(reference_path, f"{project} Skill identity reference")
    if (
        reference.get("schema")
        != "android-to-harmony.skill-identity-reference.v1"
        or reference.get("project") != project
        or reference.get("manifest_path") != CENTRAL_MANIFEST
        or reference.get("binding_path") != CENTRAL_BINDING
        or reference.get("manifest_sha256") != sha256_file(central_manifest)
        or reference.get("binding_sha256") != sha256_file(central_binding)
    ):
        raise EvidenceManifestError(
            f"{project} Skill identity reference is stale or tampered"
        )


def validate_project_evidence(evidence_root: Path, project: str) -> None:
    if project not in PROJECTS:
        raise EvidenceManifestError(f"unsupported evidence project: {project}")
    require_regular_file(evidence_root / CENTRAL_MANIFEST, "central Skill manifest")
    require_regular_file(evidence_root / CENTRAL_BINDING, "central Skill binding")
    project_root = evidence_root / "execution-plan-dag-v1"
    if not project_root.is_dir() or project_root.is_symlink():
        raise EvidenceManifestError("execution-plan-dag-v1 evidence root is missing")
    subtree = project_root / project
    for relative in PROJECT_REQUIRED_FILES:
        require_regular_file(subtree / relative, f"{project} artifact {relative}")
    if project == "buckwheat":
        for relative in BUCKWHEAT_ACQUISITION_REQUIRED_FILES:
            require_regular_file(subtree / relative, f"{project} artifact {relative}")
    fact_packs = subtree / "fact-packs"
    if fact_packs.is_symlink() or not fact_packs.is_dir():
        raise EvidenceManifestError(f"{project} fact-pack directory is missing")
    fact_files = sorted(fact_packs.glob("*-fact-pack.json"))
    if not fact_files or any(path.is_symlink() for path in fact_files):
        raise EvidenceManifestError(f"{project} fact-pack family is incomplete")
    validate_skill_identity(evidence_root, project)


def validate_evidence_layout(evidence_root: Path) -> None:
    project_root = evidence_root / "execution-plan-dag-v1"
    if not project_root.is_dir() or project_root.is_symlink():
        raise EvidenceManifestError("execution-plan-dag-v1 evidence root is missing")
    present_projects = sorted(
        path.name
        for path in project_root.iterdir()
        if path.is_dir() and not path.is_symlink()
    )
    if present_projects != sorted(PROJECTS):
        raise EvidenceManifestError(
            f"unexpected project evidence membership: {present_projects}"
        )
    for project in PROJECTS:
        validate_project_evidence(evidence_root, project)


def collect_files(evidence_root: Path, manifest_path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(evidence_root.rglob("*")):
        if path == manifest_path:
            continue
        relative = path.relative_to(evidence_root).as_posix()
        if path.is_symlink():
            raise EvidenceManifestError(f"symbolic links are forbidden in evidence: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise EvidenceManifestError(f"unsupported evidence artifact: {relative}")
        entries.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def create_manifest(evidence_root: Path, manifest_path: Path) -> dict[str, Any]:
    validate_evidence_layout(evidence_root)
    files = collect_files(evidence_root, manifest_path)
    digest_payload = "".join(
        f"{entry['path']}\0{entry['bytes']}\0{entry['sha256']}\n"
        for entry in files
    ).encode("utf-8")
    return {
        "schema": SCHEMA,
        "evidence_root": ".",
        "projects": list(PROJECTS),
        "file_count": len(files),
        "tree_sha256": hashlib.sha256(digest_payload).hexdigest(),
        "files": files,
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
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


def verify_manifest(
    evidence_root: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> None:
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("evidence_root") != "."
        or manifest.get("projects") != list(PROJECTS)
        or not isinstance(manifest.get("files"), list)
    ):
        raise EvidenceManifestError("evidence manifest envelope is invalid")
    validate_evidence_layout(evidence_root)
    current = collect_files(evidence_root, manifest_path)
    if current != manifest["files"]:
        expected_paths = {
            entry.get("path")
            for entry in manifest["files"]
            if isinstance(entry, dict)
        }
        current_paths = {entry["path"] for entry in current}
        missing = sorted(path for path in expected_paths - current_paths if isinstance(path, str))
        extra = sorted(current_paths - expected_paths)
        if missing or extra:
            raise EvidenceManifestError(
                f"evidence membership mismatch; missing={missing}; extra={extra}"
            )
        raise EvidenceManifestError("evidence content is stale or tampered")
    expected = create_manifest(evidence_root, manifest_path)
    if expected != manifest:
        raise EvidenceManifestError("evidence manifest identity is stale or tampered")


def main() -> int:
    args = parse_args()
    manifest_argument = args.input if args.verify else args.output
    if args.verify != (args.input is not None):
        print(json.dumps({"ok": False, "error": "--verify requires --input"}))
        return 2
    try:
        _, evidence_root, manifest_path = normalize_paths(
            args.change_dir,
            args.evidence_root,
            manifest_argument,
        )
        if args.verify:
            require_regular_file(manifest_path, "evidence manifest")
            manifest = load_json(manifest_path, "evidence manifest")
            verify_manifest(evidence_root, manifest_path, manifest)
        else:
            if manifest_path.exists() or manifest_path.is_symlink():
                raise EvidenceManifestError(f"manifest output already exists: {manifest_path}")
            manifest = create_manifest(evidence_root, manifest_path)
            write_json_atomic(manifest_path, manifest)
    except (EvidenceManifestError, OSError, UnicodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "verified": args.verify,
                "manifest": str(manifest_path),
                "file_count": manifest["file_count"],
                "tree_sha256": manifest["tree_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
