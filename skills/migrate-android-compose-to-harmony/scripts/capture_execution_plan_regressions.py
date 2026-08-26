#!/usr/bin/env python3
"""Capture checked fixed-revision execution-plan evidence for public projects."""

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
from pathlib import Path
from typing import Any

from hash_evidence_tree import PROJECT_REQUIRED_FILES, validate_project_evidence


SCRIPTS = Path(__file__).resolve().parent
MIGRATION_AGENT = SCRIPTS / "migration_agent.py"
PROJECT_URLS = {
    "banking": "https://github.com/alexandr7035/Banking-App-Mock-Compose.git",
    "ekspensify": "https://github.com/dilipsuthar264/ekspensify-android.git",
    "buckwheat": "https://github.com/danilkinkin/buckwheat.git",
}
PROJECT_REVISIONS = {
    "ekspensify": "0292c62e267a8b9cbc0d9dc580d80c549701661c",
    "buckwheat": "4b60102db5293059aadb7be22bf6390ae4b345a7",
}
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,63}$")
BUNDLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$")


class CaptureError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze a checked public-project execution-plan regression."
    )
    parser.add_argument("--change-dir", required=True, type=Path)
    parser.add_argument("--project", required=True, choices=tuple(PROJECT_URLS))
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--reuse-candidate", type=Path)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--target-dir", required=True, type=Path)
    parser.add_argument("--evidence-subtree", required=True, type=Path)
    return parser.parse_args()


def absolute(path: Path) -> Path:
    normalized = Path(os.path.abspath(os.path.expanduser(str(path))))
    if normalized.is_symlink():
        raise CaptureError(f"capture path must not be a symbolic link: {normalized}")
    return normalized.resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


class CommandRecorder:
    def __init__(self, evidence_subtree: Path) -> None:
        self.logs = evidence_subtree / "logs"
        self.exits = evidence_subtree / "exit"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.exits.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        name: str,
        argv: list[str],
        *,
        allow_failure: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(argv, check=False, capture_output=True, text=True)
        (self.logs / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (self.logs / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        (self.logs / f"{name}.command.log").write_text(
            shlex.join(argv) + "\n",
            encoding="utf-8",
        )
        write_json_atomic(
            self.exits / f"{name}.exit.json",
            {"schema": "android-to-harmony.command-exit.v1", "exit_code": result.returncode},
        )
        if result.returncode != 0 and not allow_failure:
            raise CaptureError(
                f"command {name} failed with exit {result.returncode}: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result


def validate_arguments(args: argparse.Namespace) -> argparse.Namespace:
    change = absolute(args.change_dir)
    source = absolute(args.source_dir)
    reuse = absolute(args.reuse_candidate) if args.reuse_candidate else None
    run_root = absolute(args.run_root)
    target = absolute(args.target_dir)
    subtree = absolute(args.evidence_subtree)
    if not change.is_dir() or change.is_symlink():
        raise CaptureError(f"change directory is invalid: {change}")
    expected_subtree = change / "evidence/execution-plan-dag-v1" / args.project
    if subtree != expected_subtree:
        raise CaptureError("evidence subtree is not the fixed change-local project path")
    if run_root != subtree / "run-root" or target != subtree / "target":
        raise CaptureError("run and target paths must use the fixed evidence-subtree locations")
    if args.source_url != PROJECT_URLS[args.project]:
        raise CaptureError(f"source URL is not fixed for project {args.project}")
    if not SHA_PATTERN.fullmatch(args.expected_revision):
        raise CaptureError("expected revision must be a full lowercase Git SHA")
    fixed_revision = PROJECT_REVISIONS.get(args.project)
    if fixed_revision is not None and args.expected_revision != fixed_revision:
        raise CaptureError(f"expected revision is not fixed for project {args.project}")
    if not PROJECT_NAME_PATTERN.fullmatch(args.project_name):
        raise CaptureError("project name is invalid")
    if not BUNDLE_NAME_PATTERN.fullmatch(args.bundle_name):
        raise CaptureError("bundle name is invalid")
    if any(path.is_symlink() for path in (source, run_root, target, subtree)):
        raise CaptureError("capture paths must not be symbolic links")
    args.change_dir = change
    args.source_dir = source
    args.reuse_candidate = reuse
    args.run_root = run_root
    args.target_dir = target
    args.evidence_subtree = subtree
    return args


def git_value(recorder: CommandRecorder, name: str, repository: Path, *arguments: str) -> str:
    result = recorder.run(name, ["git", "-C", str(repository), *arguments])
    return result.stdout.strip()


def verify_repository(
    recorder: CommandRecorder,
    prefix: str,
    repository: Path,
    source_url: str,
    expected_revision: str,
    *,
    require_detached: bool = False,
) -> None:
    if not repository.is_dir() or repository.is_symlink():
        raise CaptureError(f"Git source is missing or unsafe: {repository}")
    remote = git_value(
        recorder,
        f"{prefix}-remote",
        repository,
        "config",
        "--get",
        "remote.origin.url",
    )
    if remote != source_url:
        raise CaptureError(f"source remote mismatch: expected {source_url}, got {remote}")
    revision = git_value(recorder, f"{prefix}-head", repository, "rev-parse", "HEAD")
    if revision != expected_revision:
        raise CaptureError(
            f"source revision mismatch: expected {expected_revision}, got {revision}"
        )
    if require_detached:
        detached = recorder.run(
            f"{prefix}-detached",
            ["git", "-C", str(repository), "symbolic-ref", "-q", "HEAD"],
            allow_failure=True,
        )
        if detached.returncode != 1:
            raise CaptureError("source checkout is not detached at the expected revision")


def acquire_source(args: argparse.Namespace, recorder: CommandRecorder) -> bool:
    source_created = False
    source_existed = args.source_dir.exists()
    if args.reuse_candidate is not None:
        verify_repository(
            recorder,
            "00-reuse",
            args.reuse_candidate,
            args.source_url,
            args.expected_revision,
        )
    if not args.source_dir.exists():
        args.source_dir.parent.mkdir(parents=True, exist_ok=True)
        if args.reuse_candidate is not None:
            recorder.run(
                "00-clone",
                ["git", "clone", "--no-local", str(args.reuse_candidate), str(args.source_dir)],
            )
            recorder.run(
                "00-set-origin",
                ["git", "-C", str(args.source_dir), "remote", "set-url", "origin", args.source_url],
            )
        else:
            recorder.run(
                "00-clone",
                ["git", "clone", "--no-checkout", args.source_url, str(args.source_dir)],
            )
        source_created = True
    else:
        remote = git_value(
            recorder,
            "00-source-remote-before",
            args.source_dir,
            "config",
            "--get",
            "remote.origin.url",
        )
        if remote != args.source_url:
            raise CaptureError(
                f"source remote mismatch: expected {args.source_url}, got {remote}"
            )

    source_head_before = None
    if source_existed:
        source_head_before = git_value(
            recorder,
            "00-source-head-before",
            args.source_dir,
            "rev-parse",
            "HEAD",
        )

    commit_present = recorder.run(
        "00-revision-present",
        ["git", "-C", str(args.source_dir), "cat-file", "-e", f"{args.expected_revision}^{{commit}}"],
        allow_failure=True,
    )
    if commit_present.returncode != 0 or (
        source_head_before is not None and source_head_before != args.expected_revision
    ):
        recorder.run(
            "00-fetch",
            ["git", "-C", str(args.source_dir), "fetch", "origin", args.expected_revision],
        )
    recorder.run(
        "00-checkout",
        ["git", "-C", str(args.source_dir), "checkout", "--detach", args.expected_revision],
    )
    verify_repository(
        recorder,
        "00-source-final",
        args.source_dir,
        args.source_url,
        args.expected_revision,
        require_detached=True,
    )
    return source_created


def copy_file(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise CaptureError(f"required workflow artifact is missing or unsafe: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def freeze_workflow_artifacts(args: argparse.Namespace) -> None:
    copies = {
        "migration-contract.json": args.evidence_subtree / "contract/migration-contract.json",
        "migration-contract.json.owner.json": args.evidence_subtree / "contract/migration-contract.json.owner.json",
        "capability-graph.json": args.evidence_subtree / "capability-graph.json",
        "review-queue.json": args.evidence_subtree / "review-queue.json",
        "gate-report.json": args.evidence_subtree / "gate-report.json",
        "execution-plan.json": args.evidence_subtree / "execution-plan.json",
        "execution-task-state.json": args.evidence_subtree / "frozen-task-state.json",
    }
    for filename, destination in copies.items():
        copy_file(args.run_root / filename, destination)
    source_fact_packs = args.run_root / "fact-packs"
    destination_fact_packs = args.evidence_subtree / "fact-packs"
    if source_fact_packs.is_symlink() or not source_fact_packs.is_dir():
        raise CaptureError("workflow fact-pack directory is missing or unsafe")
    shutil.copytree(source_fact_packs, destination_fact_packs)


def write_skill_reference(args: argparse.Namespace) -> None:
    evidence_root = args.change_dir / "evidence"
    manifest = evidence_root / "skill-identities/bundled-skill-tree-manifest.json"
    binding = evidence_root / "skill-identities/repo-skill-binding.json"
    for path, role in ((manifest, "Skill manifest"), (binding, "Skill binding")):
        if path.is_symlink() or not path.is_file():
            raise CaptureError(f"central {role} is missing or unsafe: {path}")
    write_json_atomic(
        args.evidence_subtree / "skill-identity-reference.json",
        {
            "schema": "android-to-harmony.skill-identity-reference.v1",
            "project": args.project,
            "manifest_path": "skill-identities/bundled-skill-tree-manifest.json",
            "manifest_sha256": sha256_file(manifest),
            "binding_path": "skill-identities/repo-skill-binding.json",
            "binding_sha256": sha256_file(binding),
        },
    )


def remove_owned_directory(path: Path) -> None:
    if path.is_symlink():
        raise CaptureError(f"refusing to remove symbolic-link work directory: {path}")
    if path.is_dir():
        shutil.rmtree(path)


def capture(args: argparse.Namespace) -> dict[str, Any]:
    args = validate_arguments(args)
    if args.evidence_subtree.exists() and any(args.evidence_subtree.iterdir()):
        raise CaptureError(f"evidence subtree is not empty: {args.evidence_subtree}")
    args.evidence_subtree.mkdir(parents=True, exist_ok=True)
    recorder = CommandRecorder(args.evidence_subtree)
    source_created = acquire_source(args, recorder)
    try:
        start = recorder.run(
            "01-start",
            [
                sys.executable,
                str(MIGRATION_AGENT),
                "start",
                "--source",
                str(args.source_dir),
                "--run-root",
                str(args.run_root),
                "--target",
                str(args.target_dir),
                "--project-name",
                args.project_name,
                "--bundle-name",
                args.bundle_name,
            ],
        )
        status = recorder.run(
            "02-status",
            [
                sys.executable,
                str(MIGRATION_AGENT),
                "status",
                "--run-root",
                str(args.run_root),
            ],
        )
        start_payload = json.loads(start.stdout)
        status_payload = json.loads(status.stdout)
        if (
            start_payload.get("ok") is not True
            or status_payload.get("ok") is not True
            or start_payload.get("plan_identity") != status_payload.get("plan_identity")
            or start_payload.get("execution_plan") != status_payload.get("execution_plan")
            or start_payload.get("execution_task_state") != status_payload.get("execution_task_state")
        ):
            raise CaptureError("workflow start/status identity verification failed")
        freeze_workflow_artifacts(args)
        write_json_atomic(
            args.evidence_subtree / "source-identity.json",
            {
                "schema": "android-to-harmony.public-source-identity.v1",
                "project": args.project,
                "remote_url": args.source_url,
                "revision": args.expected_revision,
            },
        )
        write_skill_reference(args)
        test_log = args.evidence_subtree / "tests/start-status.test.log"
        test_log.parent.mkdir(parents=True, exist_ok=True)
        test_log.write_text(
            "PASS source remote and revision verified\n"
            "PASS migration_agent start/status plan identity stable\n"
            "PASS immutable plan and frozen task state captured\n",
            encoding="utf-8",
        )
    finally:
        remove_owned_directory(args.run_root)
        remove_owned_directory(args.target_dir)
        remove_owned_directory(
            args.evidence_subtree / ".android-to-harmony-ownership"
        )
        if source_created:
            remove_owned_directory(args.source_dir)

    for relative in PROJECT_REQUIRED_FILES:
        path = args.evidence_subtree / relative
        if path.is_symlink() or not path.is_file():
            raise CaptureError(f"frozen {args.project} evidence is incomplete: {relative}")
    validate_project_evidence(args.change_dir / "evidence", args.project)
    return {
        "ok": True,
        "project": args.project,
        "source_url": args.source_url,
        "source_revision": args.expected_revision,
        "evidence_subtree": str(args.evidence_subtree),
        "plan_identity": start_payload["plan_identity"],
        "task_state_identity": start_payload["task_state_identity"],
    }


def main() -> int:
    try:
        result = capture(parse_args())
    except (CaptureError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
