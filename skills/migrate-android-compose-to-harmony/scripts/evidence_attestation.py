#!/usr/bin/env python3
"""Shared evidence attestation and command classification helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping


ATTESTATION_SCHEMA = "android-to-harmony.evidence-attestation.v1"
RUNNER_ID = "android-to-harmony-evidence-runner-v1"
TOOL_ORIGIN_SCHEMA = "android-to-harmony.tool-origin.v1"
SLICE_GATES = ("build", "unit_tests", "ui_tests", "device_test")
EVIDENCE_GATES = SLICE_GATES + ("visual_review",)
# Compatibility for slice-ledger callers. Visual review is an evidence gate, not
# a gate that every slice must declare in its required_gates array.
REQUIRED_GATES = SLICE_GATES
RUNNER_TYPES = {
    "build": "harmony_build_runner",
    "unit_tests": "harmony_unit_runner",
    "ui_tests": "harmony_ui_device_runner",
    "device_test": "harmony_device_scenario_record",
    "visual_review": "harmony_human_visual_review_record",
}
PROBE_RUNNER_TYPES = {
    "ui_tests": "harmony_ui_device_preflight_runner",
    "device_test": "harmony_device_preflight_runner",
}
OWNERSHIP_SCHEMA = "android-to-harmony.external-ownership.v1"
OWNERSHIP_REFERENCE_SCHEMA = "android-to-harmony.ownership-reference.v1"
OWNERSHIP_DIRECTORY = ".android-to-harmony-ownership"
OWNERSHIP_KIND = "harmony-project"
TOOL_ROOT_ENVIRONMENTS = (
    "DEVECO_HOME",
    "DEVECO_SDK_HOME",
    "OHOS_SDK_HOME",
    "HOS_SDK_HOME",
)
NON_HUMAN_PROVIDER_PATTERN = re.compile(
    r"(?:^|[\s._-])"
    r"(automation|automated|bot|agent|codex|pipeline|ci|test)"
    r"(?:$|[\s._-])",
    re.IGNORECASE,
)


def ownership_record_path(target: Path) -> Path:
    target_key = hashlib.sha256(str(target).encode("utf-8")).hexdigest()
    return target.parent / OWNERSHIP_DIRECTORY / f"{target_key}.json"


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _is_safe_regular_file(path: Path) -> bool:
    """Return False when any existing component is a symlink or non-directory."""
    absolute = _absolute_path(path)
    current = Path(absolute.anchor)
    try:
        parts = absolute.parts[1:] if absolute.anchor else absolute.parts
        for index, part in enumerate(parts):
            current = current / part
            file_status = current.lstat()
            if stat.S_ISLNK(file_status.st_mode):
                return False
            if index < len(parts) - 1 and not stat.S_ISDIR(file_status.st_mode):
                return False
        return stat.S_ISREG(absolute.lstat().st_mode)
    except OSError:
        return False


def load_ownership_secret(target: Path) -> str | None:
    target = _absolute_path(target)
    if not target.is_dir() or target.is_symlink():
        return None
    record_path = ownership_record_path(target)
    if not _is_safe_regular_file(record_path):
        return None
    try:
        record_mode = record_path.lstat().st_mode
    except OSError:
        return None
    if os.name != "nt" and record_mode & 0o077:
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    secret = record.get("secret") if isinstance(record, dict) else None
    if (
        not isinstance(record, dict)
        or record.get("schema") != OWNERSHIP_SCHEMA
        or record.get("kind") != OWNERSHIP_KIND
        or record.get("target_root") != str(target)
        or not isinstance(secret, str)
        or re.fullmatch(r"[0-9a-f]{64}", secret) is None
    ):
        return None
    return secret


def has_external_ownership_proof(
    target: Path,
    payload: dict[str, Any],
    secret: str | None = None,
) -> bool:
    """Validate the in-target project marker against the external secret."""
    reference = payload.get("ownership")
    if secret is None:
        secret = load_ownership_secret(target)
    if (
        not isinstance(reference, dict)
        or not isinstance(secret, str)
        or re.fullmatch(r"[0-9a-f]{64}", secret) is None
    ):
        return False
    signature = reference.get("signature")
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
    expected = hmac.new(
        bytes.fromhex(secret),
        message,
        hashlib.sha256,
    ).hexdigest()
    return (
        reference.get("schema") == OWNERSHIP_REFERENCE_SCHEMA
        and isinstance(signature, str)
        and re.fullmatch(r"[0-9a-f]{64}", signature) is not None
        and hmac.compare_digest(signature, expected)
    )


def repair_ownership_record_permissions(
    target: Path,
    payload: dict[str, Any],
) -> bool:
    """Repair only POSIX mode bits on an otherwise valid ownership record."""
    target = _absolute_path(target)
    record_path = ownership_record_path(target)
    if not _is_safe_regular_file(record_path):
        return False
    try:
        before = record_path.lstat()
        record = json.loads(record_path.read_text(encoding="utf-8"))
        after_read = record_path.lstat()
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False
    secret = record.get("secret") if isinstance(record, dict) else None
    if (
        not isinstance(record, dict)
        or record.get("schema") != OWNERSHIP_SCHEMA
        or record.get("kind") != OWNERSHIP_KIND
        or record.get("target_root") != str(target)
        or not isinstance(secret, str)
        or re.fullmatch(r"[0-9a-f]{64}", secret) is None
        or (before.st_dev, before.st_ino)
        != (after_read.st_dev, after_read.st_ino)
        or not has_external_ownership_proof(target, payload, secret)
    ):
        return False
    if os.name != "nt":
        try:
            os.chmod(record_path, 0o600, follow_symlinks=False)
        except (NotImplementedError, OSError):
            return False
    return (
        load_ownership_secret(target) == secret
        and has_external_ownership_proof(target, payload, secret)
    )


def evidence_signature(
    evidence: dict[str, Any],
    target: Path,
    secret: str,
) -> str:
    unsigned = {
        key: value
        for key, value in evidence.items()
        if key != "attestation"
    }
    message = json.dumps(
        {
            "runner": RUNNER_ID,
            "target_root": str(target.resolve()),
            "evidence": unsigned,
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


def attach_attestation(
    evidence: dict[str, Any],
    target: Path,
    secret: str,
) -> None:
    evidence["attestation"] = {
        "schema": ATTESTATION_SCHEMA,
        "runner": RUNNER_ID,
        "signature": evidence_signature(evidence, target, secret),
    }


def has_valid_attestation(evidence: dict[str, Any], target: Path) -> bool:
    attestation = evidence.get("attestation")
    secret = load_ownership_secret(target)
    if not isinstance(attestation, dict) or secret is None:
        return False
    signature = attestation.get("signature")
    return (
        attestation.get("schema") == ATTESTATION_SCHEMA
        and attestation.get("runner") == RUNNER_ID
        and isinstance(signature, str)
        and re.fullmatch(r"[0-9a-f]{64}", signature) is not None
        and hmac.compare_digest(
            signature,
            evidence_signature(evidence, target, secret),
        )
    )


def _tool_layout_is_valid(
    source_environment: str,
    relative_path: Path,
) -> bool:
    parts = tuple(part.casefold() for part in relative_path.parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    executable = parts[-1]
    if executable in {"hvigorw", "hvigorw.bat", "hvigorw.cmd"}:
        return (
            source_environment == "DEVECO_HOME"
            and len(parts) >= 4
            and parts[-4:-1] == ("tools", "hvigor", "bin")
        )
    if executable in {"hdc", "hdc.exe"}:
        return (
            source_environment in TOOL_ROOT_ENVIRONMENTS
            and "toolchains" in parts[:-1]
            and (
                source_environment != "DEVECO_HOME"
                or "sdk" in parts[:-1]
            )
        )
    if executable in {"xdevice", "xdevice.exe"}:
        return (
            source_environment == "DEVECO_HOME"
            and "tools" in parts[:-1]
            and any("xdevice" in part for part in parts[:-1])
        )
    return False


def has_valid_tool_origin(
    executable: Path | str,
    origin: Any,
) -> bool:
    if not isinstance(origin, dict):
        return False
    source_environment = origin.get("source_environment")
    root_value = origin.get("root")
    relative_value = origin.get("relative_path")
    if (
        origin.get("schema") != TOOL_ORIGIN_SCHEMA
        or source_environment not in TOOL_ROOT_ENVIRONMENTS
        or not isinstance(root_value, str)
        or not root_value
        or not isinstance(relative_value, str)
        or not relative_value
    ):
        return False
    root = _absolute_path(Path(root_value))
    if str(root) != root_value:
        return False
    relative = Path(relative_value)
    if relative.is_absolute() or relative.as_posix() != relative_value:
        return False
    if not _tool_layout_is_valid(source_environment, relative):
        return False
    return _absolute_path(root / relative) == _absolute_path(Path(executable))


def derive_trusted_tool_origin(
    executable: Path,
    environment: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    values = os.environ if environment is None else environment
    executable = _absolute_path(executable)
    for source_environment in TOOL_ROOT_ENVIRONMENTS:
        raw_root = values.get(source_environment)
        if not isinstance(raw_root, str) or not raw_root:
            continue
        root = _absolute_path(Path(raw_root))
        try:
            relative = executable.relative_to(root)
        except ValueError:
            continue
        origin = {
            "schema": TOOL_ORIGIN_SCHEMA,
            "source_environment": source_environment,
            "root": str(root),
            "relative_path": relative.as_posix(),
        }
        if has_valid_tool_origin(executable, origin):
            return origin
    return None


def classify_argv(gate: str, argv: list[str]) -> str | None:
    """Classify executable/task pairs used for successful command evidence.

    Task tokens deliberately have fixed positions. Searching the whole argv
    would allow an unrelated command or option value to masquerade as a gate.
    """
    if not argv or not all(isinstance(value, str) and value for value in argv):
        return None
    executable = Path(argv[0]).name.lower()
    arguments = [value.casefold() for value in argv[1:]]
    task = arguments[0] if arguments else None
    if gate == "build":
        if (
            executable in {"hvigorw", "hvigorw.bat", "hvigorw.cmd"}
            and task in {"assemblehap", "assembleapp"}
        ):
            return RUNNER_TYPES[gate]
    elif gate == "unit_tests":
        if (
            executable in {"hvigorw", "hvigorw.bat", "hvigorw.cmd"}
            and task == "test"
        ):
            return RUNNER_TYPES[gate]
    elif gate in {"ui_tests", "device_test"}:
        is_hvigor_device = executable in {
            "hvigorw",
            "hvigorw.bat",
            "hvigorw.cmd",
        } and task == "ondevicetest"
        is_xdevice = executable in {"xdevice", "xdevice.exe"} and task == "run"
        hdc_arguments = arguments
        if len(hdc_arguments) >= 2 and hdc_arguments[0] == "-t":
            if not hdc_arguments[1]:
                return None
            hdc_arguments = hdc_arguments[2:]
        is_aa_test = (
            executable in {"hdc", "hdc.exe"}
            and hdc_arguments[:3] == ["shell", "aa", "test"]
        )
        if is_hvigor_device or is_xdevice or is_aa_test:
            return RUNNER_TYPES[gate]
    return None


def classify_probe_argv(gate: str, argv: list[str]) -> str | None:
    """Classify failed, device-related preflight commands.

    Probes cannot attest build or unit gates. They accept either an actual UI
    device runner that failed before execution, or a narrowly defined
    device-discovery command. In particular, ``assembleHap`` is never a UI
    preflight.
    """
    if gate not in PROBE_RUNNER_TYPES:
        return None
    if not argv or not all(isinstance(value, str) and value for value in argv):
        return None
    if classify_argv("ui_tests", argv) is not None:
        return PROBE_RUNNER_TYPES[gate]
    executable = Path(argv[0]).name.lower()
    arguments = [value.casefold() for value in argv[1:]]
    is_hdc_discovery = (
        executable in {"hdc", "hdc.exe"}
        and arguments[:2] == ["list", "targets"]
    )
    is_xdevice_discovery = (
        executable in {"xdevice", "xdevice.exe"}
        and arguments[:1] == ["list"]
    )
    if is_hdc_discovery or is_xdevice_discovery:
        return PROBE_RUNNER_TYPES[gate]
    return None
