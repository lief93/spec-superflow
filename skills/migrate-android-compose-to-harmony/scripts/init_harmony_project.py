#!/usr/bin/env python3
"""Initialize an isolated HarmonyOS Stage project from the bundled template."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from evidence_attestation import (
    has_external_ownership_proof as validate_external_ownership_proof,
    load_ownership_secret,
)


SCHEMA = "android-to-harmony.project-state.v1"
OWNERSHIP_SCHEMA = "android-to-harmony.external-ownership.v1"
OWNERSHIP_REFERENCE_SCHEMA = "android-to-harmony.ownership-reference.v1"
STRING_RESOURCE_SCHEMA = "android-to-harmony.android-string-resources.v1"
OWNERSHIP_DIRECTORY = ".android-to-harmony-ownership"
OWNERSHIP_KIND = "harmony-project"
TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "harmony-stage-template"
)
BUNDLE_NAME_PATTERN = re.compile(
    r"^[A-Za-z](?:[A-Za-z0-9_]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9_]*[A-Za-z0-9])?){2,}$"
)
PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$")
SDK_VERSION_PATTERN = re.compile(
    r"^[1-9][0-9]*\.[0-9]+\.[0-9]+\([1-9][0-9]*\)$"
)
DEFAULT_SDK_VERSION = "6.0.1(21)"
PLACEHOLDERS = {
    "__PROJECT_NAME__": "project_name",
    "__BUNDLE_NAME__": "bundle_name",
    "__SDK_VERSION__": "sdk_version",
}
TEMPLATED_FILES = {
    "build-profile.json5",
    "AppScope/app.json5",
    "AppScope/resources/base/element/string.json",
    "entry/src/main/ets/pages/Index.ets",
    "entry/src/ohosTest/ets/test/Ability.test.ets",
}
PROTECTED_OUTPUTS = {
    Path("/"),
    Path.home().resolve(),
    Path.home().resolve().parent,
}
REQUIRED_CONTRACT_FIELDS = {
    "source": dict,
    "privacy": dict,
    "inventory": dict,
    "dependencies": list,
    "ui": dict,
    "business": dict,
    "platform_capabilities": list,
    "migration_batches": list,
    "risks": list,
    "completion_gates": list,
}


class InitializationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a standalone HarmonyOS project for a migration run."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument(
        "--sdk-version",
        default=DEFAULT_SDK_VERSION,
        help=(
            "HarmonyOS SDK version written to targetSdkVersion and "
            "compatibleSdkVersion, for example 6.1.1(24)"
        ),
    )
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def validate_identity(project_name: str, bundle_name: str) -> None:
    if (
        project_name != project_name.strip()
        or PROJECT_NAME_PATTERN.fullmatch(project_name) is None
    ):
        raise InitializationError(
            "project name must be 1-64 letters, digits, spaces, underscores, or hyphens"
        )
    if (
        len(bundle_name.encode("utf-8")) < 7
        or len(bundle_name.encode("utf-8")) > 128
        or BUNDLE_NAME_PATTERN.fullmatch(bundle_name) is None
    ):
        raise InitializationError(
            "bundle name must be 7-128 bytes, contain at least three identifier "
            "segments, and end every segment with a letter or digit"
        )


def validate_sdk_version(sdk_version: str) -> None:
    if (
        sdk_version != sdk_version.strip()
        or SDK_VERSION_PATTERN.fullmatch(sdk_version) is None
    ):
        raise InitializationError(
            "sdk version must use the HarmonyOS release format, "
            "for example 6.1.1(24)"
        )


def normalized_output(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise InitializationError(f"output directory must not be a symbolic link: {absolute}")
    return absolute.resolve()


def ownership_record_path(target: Path) -> Path:
    target_key = hashlib.sha256(str(target).encode("utf-8")).hexdigest()
    return target.parent / OWNERSHIP_DIRECTORY / f"{target_key}.json"


def load_external_ownership(target: Path) -> str | None:
    return load_ownership_secret(target)


def claim_external_ownership(target: Path) -> str:
    existing = load_external_ownership(target)
    if existing is not None:
        return existing
    record_path = ownership_record_path(target)
    ownership_directory = record_path.parent
    if ownership_directory.is_symlink():
        raise InitializationError(
            f"external ownership directory must not be a symbolic link: "
            f"{ownership_directory}"
        )
    if ownership_directory.exists() and not ownership_directory.is_dir():
        raise InitializationError(
            f"external ownership path is not a directory: "
            f"{ownership_directory}"
        )
    ownership_directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    if record_path.exists() or record_path.is_symlink():
        raise InitializationError(
            "external ownership record is invalid; refusing to replace it"
        )
    secret = secrets.token_hex(32)
    record = {
        "schema": OWNERSHIP_SCHEMA,
        "kind": OWNERSHIP_KIND,
        "target_root": str(target),
        "secret": secret,
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{record_path.name}.initialize-",
        dir=ownership_directory,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, record_path)
        except FileExistsError as error:
            raced = load_external_ownership(target)
            if raced is not None:
                return raced
            raise InitializationError(
                "external ownership record changed while it was being created"
            ) from error
    finally:
        temporary.unlink(missing_ok=True)
    return secret


def ownership_signature(
    payload: dict[str, Any],
    target: Path,
    secret: str,
) -> str:
    unsigned_payload = {
        key: value
        for key, value in payload.items()
        if key != "ownership"
    }
    message = json.dumps(
        {
            "kind": OWNERSHIP_KIND,
            "target_root": str(target),
            "payload": unsigned_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(
        bytes.fromhex(secret),
        message,
        hashlib.sha256,
    ).hexdigest()


def attach_ownership_proof(
    payload: dict[str, Any],
    target: Path,
    secret: str,
) -> None:
    payload["ownership"] = {
        "schema": OWNERSHIP_REFERENCE_SCHEMA,
        "signature": ownership_signature(payload, target, secret),
    }


def has_external_ownership_proof(
    target: Path,
    payload: dict[str, Any],
) -> bool:
    return validate_external_ownership_proof(target, payload)


def ensure_safe_output(output: Path) -> None:
    if output in PROTECTED_OUTPUTS or output.parent == output:
        raise InitializationError(f"refusing unsafe output directory: {output}")
    if TEMPLATE == output or TEMPLATE in output.parents or output in TEMPLATE.parents:
        raise InitializationError("output must be separate from the bundled template")
    if output.name == OWNERSHIP_DIRECTORY:
        raise InitializationError(
            "output must not use the reserved external ownership "
            f"directory name: {OWNERSHIP_DIRECTORY}"
        )


def contains_git_repository(output: Path) -> bool:
    for current_root, directories, _filenames in os.walk(output):
        if ".git" in directories or Path(current_root, ".git").is_file():
            return True
        directories[:] = [
            directory
            for directory in directories
            if not Path(current_root, directory).is_symlink()
        ]
    return False


def owns_existing_output(output: Path) -> bool:
    state_path = output / ".migration" / "state.json"
    if not state_path.is_file() or state_path.is_symlink():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        recorded_output_value = state.get("output_root")
        if recorded_output_value == ".":
            recorded_output = output
        else:
            recorded_output = normalized_output(Path(recorded_output_value))
    except (
        AttributeError,
        InitializationError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return False
    if (
        state.get("schema") != SCHEMA
        or state.get("generator") != "migrate-android-compose-to-harmony"
        or recorded_output != output
        or not has_external_ownership_proof(output, state)
    ):
        return False

    generated_files = state.get("generated_files")
    generated_directories = state.get("generated_directories")
    generated_hashes = state.get("generated_file_sha256")
    if (
        not isinstance(generated_files, list)
        or not all(isinstance(path, str) for path in generated_files)
        or not isinstance(generated_directories, list)
        or not all(isinstance(path, str) for path in generated_directories)
        or not isinstance(generated_hashes, dict)
    ):
        return False
    expected_files = set(generated_files)
    expected_hashed_files = expected_files - {".migration/state.json"}
    if (
        len(expected_files) != len(generated_files)
        or set(generated_hashes) != expected_hashed_files
        or not all(isinstance(value, str) for value in generated_hashes.values())
    ):
        return False

    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for current_root, directories, filenames in os.walk(output):
        current = Path(current_root)
        for directory in directories:
            child = current / directory
            if child.is_symlink():
                return False
            actual_directories.add(child.relative_to(output).as_posix())
        for filename in filenames:
            child = current / filename
            if child.is_symlink() or not child.is_file():
                return False
            actual_files.add(child.relative_to(output).as_posix())
    if actual_files != expected_files:
        return False
    if (
        len(generated_directories) != len(set(generated_directories))
        or actual_directories != set(generated_directories)
    ):
        return False
    return all(
        sha256_file(output / relative) == expected_hash
        for relative, expected_hash in generated_hashes.items()
    )


def validate_output(output: Path, force: bool) -> None:
    ensure_safe_output(output)
    if output.exists() and not output.is_dir():
        raise InitializationError(f"output exists and is not a directory: {output}")
    if output.exists():
        if not force:
            raise InitializationError(
                "output directory already exists; pass --force to replace it"
            )
        if not owns_existing_output(output):
            raise InitializationError(
                "refusing to replace a directory without a valid "
                "generated-project marker and matching external ownership "
                "proof; legacy outputs without an external ownership record "
                "must be recreated at a new path"
            )
        if contains_git_repository(output):
            raise InitializationError("refusing to replace a Git repository")
    output.parent.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract(path: Path | None) -> tuple[dict[str, Any] | None, Path | None]:
    if path is None:
        return None, None
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise InitializationError(f"migration contract does not exist: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InitializationError(f"invalid migration contract: {error}") from error
    if not isinstance(payload, dict):
        raise InitializationError("migration contract must be a JSON object")
    if payload.get("schema") != "android-to-harmony.migration-contract.v1":
        raise InitializationError("unsupported migration contract schema")
    for key, expected_type in REQUIRED_CONTRACT_FIELDS.items():
        if not isinstance(payload.get(key), expected_type):
            raise InitializationError(
                f"migration contract {key} must be a "
                f"{expected_type.__name__}"
            )
    source = payload.get("source")
    safe_snapshot_root = source.get("safe_snapshot_root")
    original_root = source.get("original_root")
    if not isinstance(safe_snapshot_root, str) or not safe_snapshot_root:
        raise InitializationError(
            "migration contract source.safe_snapshot_root must be a path"
        )
    if not isinstance(original_root, str) or not original_root:
        raise InitializationError(
            "migration contract source.original_root must be a path"
        )
    git = source.get("git")
    if git is not None and not isinstance(git, dict):
        raise InitializationError("migration contract source.git must be an object")
    inventory = payload["inventory"]
    if (
        inventory.get("status") != "candidate_requires_review"
        or inventory.get("authoritative") is not False
        or not isinstance(inventory.get("text_file_count"), int)
        or not isinstance(inventory.get("gradle_modules"), list)
    ):
        raise InitializationError(
            "migration contract inventory must be a non-authoritative candidate"
        )
    privacy = payload["privacy"]
    if (
        privacy.get("absolute_image_absence_proven") is not False
        or not isinstance(privacy.get("embedded_image_scan"), dict)
        or not isinstance(privacy.get("credential_literal_scan"), dict)
    ):
        raise InitializationError(
            "migration contract privacy policy is incomplete"
        )
    if (
        not payload["completion_gates"]
        or not all(
            isinstance(gate, str) and bool(gate.strip())
            for gate in payload["completion_gates"]
        )
    ):
        raise InitializationError(
            "migration contract completion_gates must be non-empty strings"
        )
    return payload, resolved


def ensure_contract_separation(
    output: Path,
    contract: dict[str, Any] | None,
) -> None:
    if contract is None:
        return
    source = contract["source"]
    for key in ("safe_snapshot_root", "original_root"):
        protected = Path(
            os.path.abspath(os.path.expanduser(source[key]))
        ).resolve()
        if (
            output == protected
            or protected in output.parents
            or output in protected.parents
        ):
            raise InitializationError(
                "target output must be separate from Android source and safe snapshot"
            )


def copy_template(output: Path, replacements: dict[str, str]) -> list[str]:
    if not TEMPLATE.is_dir():
        raise InitializationError(f"bundled template is missing: {TEMPLATE}")

    generated_files: list[str] = []
    for source in sorted(TEMPLATE.rglob("*")):
        relative = source.relative_to(TEMPLATE)
        destination = output / relative
        if source.is_symlink():
            raise InitializationError(f"template contains a symbolic link: {relative}")
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        relative_text = relative.as_posix()
        if relative_text in TEMPLATED_FILES:
            try:
                text = source.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                raise InitializationError(
                    f"templated file is not UTF-8: {relative}"
                ) from error
            for placeholder, value in replacements.items():
                text = text.replace(placeholder, value)
            destination.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(source, destination)
        generated_files.append(relative.as_posix())
    return generated_files


def merge_android_string_resources(
    output: Path,
    contract: dict[str, Any] | None,
) -> str | None:
    if contract is None:
        return None
    inventory = contract.get("ui", {}).get("android_value_resource_inventory", {})
    resources = inventory.get("resources") if isinstance(inventory, dict) else None
    if not isinstance(resources, list):
        return None
    accepted: dict[str, dict[str, str]] = {}
    skipped: list[dict[str, str]] = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        if resource.get("qualifier") != "values" or resource.get("type") != "string":
            continue
        name = resource.get("name")
        value = resource.get("value")
        source = resource.get("source")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
            or not isinstance(value, str)
            or not isinstance(source, str)
        ):
            skipped.append(
                {
                    "name": str(name),
                    "reason": "invalid string resource name, value, or source",
                }
            )
            continue
        existing = accepted.get(name)
        if existing is not None and existing["value"] != value:
            skipped.append(
                {
                    "name": name,
                    "reason": "conflicting default string resource values",
                }
            )
            accepted.pop(name, None)
            continue
        if existing is None:
            accepted[name] = {"name": name, "value": value, "source": source}
    if not accepted and not skipped:
        return None

    string_json_path = output / "AppScope/resources/base/element/string.json"
    try:
        payload = json.loads(string_json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InitializationError(f"invalid Harmony string resource template: {error}") from error
    strings = payload.get("string")
    if not isinstance(strings, list):
        raise InitializationError("Harmony string resource template must contain a string array")
    merged: dict[str, dict[str, str]] = {}
    for item in strings:
        if (
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("value"), str)
        ):
            merged[item["name"]] = {"name": item["name"], "value": item["value"]}
    for name, item in accepted.items():
        merged[name] = {"name": name, "value": item["value"]}
    payload["string"] = [merged[name] for name in sorted(merged)]
    string_json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = {
        "schema": STRING_RESOURCE_SCHEMA,
        "source": "ui.android_value_resource_inventory",
        "default_string_count": len(accepted),
        "output": "AppScope/resources/base/element/string.json",
        "names": sorted(accepted),
        "skipped": skipped,
    }
    summary_path = output / ".migration" / "android-string-resources.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ".migration/android-string-resources.json"


def assert_no_placeholders(output: Path, generated_files: list[str]) -> None:
    unresolved: list[str] = []
    for relative in sorted(TEMPLATED_FILES.intersection(generated_files)):
        text = (output / relative).read_text(encoding="utf-8")
        if any(placeholder in text for placeholder in PLACEHOLDERS):
            unresolved.append(relative)
    if unresolved:
        raise InitializationError(
            f"generated files contain unresolved placeholders: {', '.join(unresolved)}"
        )


def commit_generated_tree(temporary: Path, output: Path) -> None:
    if not output.exists():
        os.replace(temporary, output)
        return

    backup = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.backup-", dir=output.parent)
    )
    backup.rmdir()
    os.replace(output, backup)
    try:
        os.replace(temporary, output)
    except OSError:
        os.replace(backup, output)
        raise
    shutil.rmtree(backup)


def initialize(
    output: Path,
    project_name: str,
    bundle_name: str,
    sdk_version: str,
    contract_path: Path | None,
    force: bool,
) -> dict[str, Any]:
    output = normalized_output(output)
    validate_identity(project_name, bundle_name)
    validate_sdk_version(sdk_version)
    contract, resolved_contract = load_contract(contract_path)
    ensure_contract_separation(output, contract)
    validate_output(output, force)
    ownership_secret = claim_external_ownership(output)

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.generate-", dir=output.parent)
    )
    try:
        generated_files = copy_template(
            temporary,
            {
                "__PROJECT_NAME__": project_name,
                "__BUNDLE_NAME__": bundle_name,
                "__SDK_VERSION__": sdk_version,
            },
        )
        assert_no_placeholders(temporary, generated_files)

        migration_directory = temporary / ".migration"
        migration_directory.mkdir()
        string_resource_summary = merge_android_string_resources(temporary, contract)
        if string_resource_summary is not None:
            generated_files.append(string_resource_summary)
        contract_state: dict[str, Any] | None = None
        if contract is not None and resolved_contract is not None:
            copied_contract = migration_directory / "source-contract.json"
            exported_contract = json.loads(json.dumps(contract))
            exported_contract["source"]["safe_snapshot_root"] = (
                "<local-safe-snapshot>"
            )
            exported_contract["source"]["original_root"] = (
                "<local-android-source>"
            )
            copied_contract.write_text(
                json.dumps(exported_contract, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            generated_files.append(".migration/source-contract.json")
            source = contract.get("source")
            git = source.get("git") if isinstance(source, dict) else None
            source_revision = (
                git.get("revision") if isinstance(git, dict) else None
            )
            contract_state = {
                "original_path": "<local-contract-not-exported>",
                "copied_path": ".migration/source-contract.json",
                "sha256": sha256_file(copied_contract),
                "source_revision": source_revision,
            }

        state_generated_files = sorted(
            generated_files + [".migration/state.json"]
        )
        generated_directories = sorted(
            path.relative_to(temporary).as_posix()
            for path in temporary.rglob("*")
            if path.is_dir()
        )
        generated_file_hashes = {
            relative: sha256_file(temporary / relative)
            for relative in state_generated_files
            if relative != ".migration/state.json"
        }
        state = {
            "schema": SCHEMA,
            "generator": "migrate-android-compose-to-harmony",
            "project_name": project_name,
            "bundle_name": bundle_name,
            "sdk_version": sdk_version,
            "output_root": ".",
            "template": "assets/harmony-stage-template",
            "contract": contract_state,
            "generated_files": state_generated_files,
            "generated_directories": generated_directories,
            "generated_file_sha256": generated_file_hashes,
            "verification": {
                "build": "pending",
                "unit_tests": "pending",
                "ui_tests": "pending",
                "device_test": "pending",
            },
        }
        attach_ownership_proof(state, output, ownership_secret)
        state_path = migration_directory / "state.json"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        commit_generated_tree(temporary, output)
        return state
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> int:
    args = parse_args()
    try:
        state = initialize(
            args.output,
            args.project_name,
            args.bundle_name,
            args.sdk_version,
            args.contract,
            args.force,
        )
    except (InitializationError, OSError) as error:
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
                "output": str(normalized_output(args.output)),
                "project_name": state["project_name"],
                "bundle_name": state["bundle_name"],
                "generated_file_count": len(state["generated_files"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
