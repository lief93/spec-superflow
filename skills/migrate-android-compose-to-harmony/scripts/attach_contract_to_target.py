#!/usr/bin/env python3
"""Attach a validated contract to a target without exporting local paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from init_harmony_project import load_contract


STATE_SCHEMA = "android-to-harmony.project-state.v1"


class AttachContractError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach a migration contract to an initialized target."
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_directory(path: Path, role: str) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise AttachContractError(f"{role} must not be a symbolic link: {absolute}")
    resolved = absolute.resolve()
    if not resolved.is_dir():
        raise AttachContractError(f"{role} does not exist: {resolved}")
    return resolved


def load_target_state(target: Path) -> tuple[Path, dict[str, Any]]:
    migration_directory = target / ".migration"
    if migration_directory.is_symlink():
        raise AttachContractError(
            "target mutation path must not contain a symbolic link: .migration"
        )
    state_path = migration_directory / "state.json"
    if not state_path.is_file() or state_path.is_symlink():
        raise AttachContractError("target project marker is missing")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise AttachContractError(f"invalid target project marker: {error}") from error
    if (
        not isinstance(state, dict)
        or state.get("schema") != STATE_SCHEMA
        or state.get("generator") != "migrate-android-compose-to-harmony"
    ):
        raise AttachContractError("target project marker is invalid")
    return state_path, state


def require_separate_target(
    target: Path,
    contract: dict[str, Any],
) -> None:
    source = contract["source"]
    for key in ("safe_snapshot_root", "original_root"):
        protected = Path(
            os.path.abspath(os.path.expanduser(source[key]))
        ).resolve()
        if (
            target == protected
            or protected in target.parents
            or target in protected.parents
        ):
            raise AttachContractError(
                "target must be separate from Android source and safe snapshot"
            )


def write_temporary(path: Path, payload: dict[str, Any]) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.attach-",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return temporary


def attach(
    contract_path: Path,
    target_path: Path,
    force: bool,
) -> dict[str, Any]:
    target = normalize_directory(target_path, "target")
    contract, resolved_contract = load_contract(contract_path)
    if contract is None or resolved_contract is None:
        raise AttachContractError("migration contract is required")
    require_separate_target(target, contract)
    state_path, state = load_target_state(target)
    destination = target / ".migration" / "source-contract.json"
    if destination.is_symlink():
        raise AttachContractError(
            "target mutation path must not contain a symbolic link: "
            ".migration/source-contract.json"
        )

    if destination.exists():
        if not force:
            raise AttachContractError(
                "target contract already exists; pass --force to replace it"
            )
        recorded = state.get("contract")
        if (
            not isinstance(recorded, dict)
            or recorded.get("copied_path") != ".migration/source-contract.json"
            or recorded.get("sha256") != sha256_file(destination)
        ):
            raise AttachContractError(
                "refusing to replace a target contract that changed "
                "after its recorded copy"
            )

    exported_contract = json.loads(json.dumps(contract))
    exported_contract["source"]["safe_snapshot_root"] = "<local-safe-snapshot>"
    exported_contract["source"]["original_root"] = "<local-android-source>"
    source = contract["source"]
    git = source.get("git")
    source_revision = git.get("revision") if isinstance(git, dict) else None

    contract_temporary = write_temporary(destination, exported_contract)
    contract_hash = sha256_file(contract_temporary)
    state["output_root"] = "."
    state["contract"] = {
        "original_path": "<local-contract-not-exported>",
        "copied_path": ".migration/source-contract.json",
        "sha256": contract_hash,
        "source_revision": source_revision,
    }
    state_temporary = write_temporary(state_path, state)
    contract_backup = destination.with_name(f".{destination.name}.backup")
    state_backup = state_path.with_name(f".{state_path.name}.backup")
    if contract_backup.exists() or state_backup.exists():
        contract_temporary.unlink(missing_ok=True)
        state_temporary.unlink(missing_ok=True)
        raise AttachContractError("refusing while attach backup files exist")
    try:
        if destination.exists():
            os.replace(destination, contract_backup)
        os.replace(state_path, state_backup)
        os.replace(contract_temporary, destination)
        os.replace(state_temporary, state_path)
        contract_backup.unlink(missing_ok=True)
        state_backup.unlink(missing_ok=True)
    except OSError:
        if contract_backup.exists():
            destination.unlink(missing_ok=True)
            os.replace(contract_backup, destination)
        if state_backup.exists():
            state_path.unlink(missing_ok=True)
            os.replace(state_backup, state_path)
        raise
    finally:
        contract_temporary.unlink(missing_ok=True)
        state_temporary.unlink(missing_ok=True)

    return {
        "target": str(target),
        "copied_path": ".migration/source-contract.json",
        "sha256": contract_hash,
        "source_revision": source_revision,
    }


def main() -> int:
    args = parse_args()
    try:
        result = attach(args.contract, args.target, args.force)
    except (AttachContractError, OSError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema": "android-to-harmony.command-result.v1",
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema": "android-to-harmony.command-result.v1",
                **result,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
