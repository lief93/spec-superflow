#!/usr/bin/env python3
"""Execute or record a verification gate with tamper-evident evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evidence_attestation import (
    EVIDENCE_GATES,
    NON_HUMAN_PROVIDER_PATTERN,
    RUNNER_TYPES,
    attach_attestation,
    classify_argv,
    classify_probe_argv,
    derive_trusted_tool_origin,
    has_external_ownership_proof,
    load_ownership_secret,
)
from hash_target_source import create_manifest


EVIDENCE_SCHEMA = "android-to-harmony.evidence.v2"
RESULT_SCHEMA = "android-to-harmony.evidence-runner-result.v1"
GENERATOR = "migrate-android-compose-to-harmony"
RUN_STATE_SCHEMA = "android-to-harmony.agent-state.v1"
RUN_OWNERSHIP_SCHEMA = "android-to-harmony.run-ownership.v1"
NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$"
DEVICE_GATES = {"ui_tests", "device_test"}
COMMAND_GATES = {"build", "unit_tests", "ui_tests", "device_test"}
TEST_GATES = {"unit_tests", "ui_tests", "device_test"}
ANSI_CSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
HDC_FAILURE_PATTERN = re.compile(
    r"(?m)^[ \t]*\[Fail\]\[(E[0-9]{6})\][ \t]*(.+?)\r?$"
)


class RunnerError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    raw_arguments = sys.argv[1:]
    try:
        separator = raw_arguments.index("--")
    except ValueError:
        parser_arguments = raw_arguments
        command_argv: list[str] = []
    else:
        parser_arguments = raw_arguments[:separator]
        command_argv = raw_arguments[separator + 1 :]
    parser = argparse.ArgumentParser(
        description="Run or record migration verification without a shell."
    )
    parser.add_argument("mode", choices=("run", "probe", "record"))
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--gate", required=True, choices=EVIDENCE_GATES)
    parser.add_argument("--name", required=True)
    parser.add_argument("--slice-id", action="append", required=True)
    parser.add_argument("--demand-id", action="append", required=True)
    parser.add_argument("--test-report", type=Path)
    parser.add_argument("--test-report-from-stdout", action="store_true")
    parser.add_argument("--ui-main-hap", type=Path)
    parser.add_argument("--ui-test-hap", type=Path)
    parser.add_argument(
        "--test-report-format",
        choices=("junit", "hypium-text"),
    )
    parser.add_argument("--output-artifact", action="append", type=Path)
    parser.add_argument("--device-kind")
    parser.add_argument("--device-id")
    parser.add_argument("--os-version")
    parser.add_argument("--api-version")
    parser.add_argument("--scenario-step", action="append")
    parser.add_argument("--expected")
    parser.add_argument("--actual")
    parser.add_argument("--provider")
    parser.add_argument("--provider-kind", choices=("human",))
    parser.add_argument("--evidence-owner")
    parser.add_argument("--notes")
    parser.add_argument("--record-status", choices=("passed", "failed"))
    parser.add_argument("--blocker")
    parser.add_argument("--next-action")
    args = parser.parse_args(parser_arguments)
    args.argv = command_argv
    return args


def absolute_path(path: Path, base: Path | None = None) -> Path:
    expanded = Path(os.path.expanduser(str(path)))
    if base is not None and not expanded.is_absolute():
        expanded = base / expanded
    return Path(os.path.abspath(expanded))


def assert_safe_components(
    path: Path,
    role: str,
    *,
    allow_missing: bool,
) -> None:
    """Reject a symlink or non-directory in every existing path component."""
    absolute = absolute_path(path)
    current = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            current_status = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                return
            raise RunnerError(f"{role} does not exist: {current}") from None
        except OSError as error:
            raise RunnerError(f"cannot inspect {role}: {error}") from error
        if stat.S_ISLNK(current_status.st_mode):
            raise RunnerError(f"{role} contains a symbolic link: {current}")
        if (
            index < len(parts) - 1
            and not stat.S_ISDIR(current_status.st_mode)
        ):
            raise RunnerError(
                f"{role} contains a non-directory component: {current}"
            )


def normalized_directory(path: Path, role: str) -> Path:
    absolute = absolute_path(path)
    assert_safe_components(absolute, role, allow_missing=False)
    try:
        mode = absolute.lstat().st_mode
    except OSError as error:
        raise RunnerError(f"cannot inspect {role}: {error}") from error
    if not stat.S_ISDIR(mode):
        raise RunnerError(f"{role} must be an existing non-symlink directory")
    return absolute


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def safe_target_path(target: Path, path: Path, role: str) -> Path:
    absolute = absolute_path(path, target)
    if not is_within(absolute, target):
        raise RunnerError(f"{role} must be inside the target")
    assert_safe_components(absolute, role, allow_missing=True)
    return absolute


def ensure_directory(
    path: Path,
    role: str,
    created_directories: list[Path],
) -> None:
    absolute = absolute_path(path)
    assert_safe_components(absolute, role, allow_missing=True)
    missing: list[Path] = []
    current = absolute
    while not os.path.lexists(current):
        missing.append(current)
        if current.parent == current:
            raise RunnerError(f"cannot create {role}")
        current = current.parent
    assert_safe_components(current, role, allow_missing=False)
    if not stat.S_ISDIR(current.lstat().st_mode):
        raise RunnerError(f"{role} parent is not a directory")
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except OSError as error:
            raise RunnerError(f"cannot create {role}: {error}") from error
        created_directories.append(directory)
    assert_safe_components(absolute, role, allow_missing=False)
    if not stat.S_ISDIR(absolute.lstat().st_mode):
        raise RunnerError(f"{role} is not a directory")


def file_snapshot(path: Path, role: str) -> dict[str, Any] | None:
    assert_safe_components(path, role, allow_missing=True)
    if not os.path.lexists(path):
        return None
    try:
        before = path.lstat()
    except OSError as error:
        raise RunnerError(f"cannot inspect {role}: {error}") from error
    if not stat.S_ISREG(before.st_mode):
        raise RunnerError(f"{role} must be a regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RunnerError(f"cannot open {role}: {error}") from error
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino)
                != (before.st_dev, before.st_ino)
            ):
                raise RunnerError(f"{role} changed while it was opened")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise RunnerError(f"cannot read {role}: {error}") from error
    assert_safe_components(path, role, allow_missing=False)
    after = path.lstat()
    if (
        not stat.S_ISREG(after.st_mode)
        or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    ):
        raise RunnerError(f"{role} changed while it was read")
    return {
        "sha256": digest.hexdigest(),
        "size": opened.st_size,
        "device": opened.st_dev,
        "inode": opened.st_ino,
        "mtime_ns": opened.st_mtime_ns,
        "ctime_ns": opened.st_ctime_ns,
    }


def resolve_executable(
    requested: str,
    target: Path,
    run_root: Path,
) -> tuple[Path, dict[str, Any]]:
    if not requested:
        raise RunnerError("command has no executable")
    has_separator = os.sep in requested or (
        os.altsep is not None and os.altsep in requested
    )
    if has_separator or Path(requested).is_absolute():
        candidate = absolute_path(Path(requested), target)
    else:
        found = shutil.which(requested)
        if found is None:
            raise RunnerError(f"executable was not found on PATH: {requested}")
        candidate = absolute_path(Path(found))
    assert_safe_components(candidate, "executable", allow_missing=False)
    executable = file_snapshot(candidate, "executable")
    if executable is None:
        raise RunnerError("executable does not exist")
    if is_within(candidate, target) or is_within(candidate, run_root):
        raise RunnerError("executable must be outside target and run root")
    if not os.access(candidate, os.X_OK):
        raise RunnerError("executable is not executable")
    return candidate, {
        "requested": requested,
        "resolved_path": str(candidate),
        "sha256": executable["sha256"],
        "size": executable["size"],
    }


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    )


def load_json_regular(path: Path, role: str) -> dict[str, Any]:
    snapshot = file_snapshot(path, role)
    if snapshot is None:
        raise RunnerError(f"{role} is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise RunnerError(f"invalid {role}: {error}") from error
    if not isinstance(payload, dict):
        raise RunnerError(f"{role} must be a JSON object")
    return payload


def require_recorded_hash(path: Path, expected: Any, role: str) -> str:
    snapshot = file_snapshot(path, role)
    if (
        snapshot is None
        or not is_sha256(expected)
        or snapshot["sha256"] != expected
    ):
        raise RunnerError(f"{role} is missing or changed")
    return expected


def recorded_absolute_path(
    mapping: dict[str, Any],
    key: str,
    role: str,
) -> Path:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise RunnerError(f"run state has no valid {role} path")
    path = absolute_path(Path(value))
    if str(path) != value:
        raise RunnerError(f"run state {role} path is not normalized")
    return path


def load_run_identity(run_root: Path, target: Path, secret: str) -> str:
    state_path = run_root / "agent-state.json"
    state = load_json_regular(state_path, "owned agent state")
    paths = state.get("paths") if isinstance(state, dict) else None
    ownership = state.get("ownership") if isinstance(state, dict) else None
    artifacts = state.get("artifacts") if isinstance(state, dict) else None
    project = state.get("project") if isinstance(state, dict) else None
    if (
        state.get("schema") != RUN_STATE_SCHEMA
        or state.get("generator") != GENERATOR
        or not isinstance(ownership, dict)
        or ownership.get("schema") != RUN_OWNERSHIP_SCHEMA
        or ownership.get("run_root") != str(run_root)
        or not is_nonempty(ownership.get("run_id"))
        or not isinstance(paths, dict)
        or not isinstance(artifacts, dict)
        or not isinstance(project, dict)
        or not is_nonempty(project.get("name"))
        or not is_nonempty(project.get("bundle_name"))
    ):
        raise RunnerError("run state does not own this target")

    recorded_target = recorded_absolute_path(paths, "target", "target")
    snapshot = recorded_absolute_path(paths, "snapshot", "snapshot")
    contract = recorded_absolute_path(paths, "contract", "contract")
    contract_owner = recorded_absolute_path(
        paths,
        "contract_owner",
        "contract owner",
    )
    source = recorded_absolute_path(paths, "source", "source")
    if (
        recorded_target != target
        or snapshot != run_root / "snapshot"
        or contract != run_root / "migration-contract.json"
        or contract_owner
        != contract.with_name(f"{contract.name}.owner.json")
    ):
        raise RunnerError("run paths do not belong to the recorded run root")
    normalized_directory(snapshot, "safe snapshot")

    manifest_path = snapshot / ".android-to-harmony-safe.json"
    snapshot_hash = artifacts.get("snapshot_manifest_sha256")
    require_recorded_hash(
        manifest_path,
        snapshot_hash,
        "safe snapshot manifest",
    )
    manifest = load_json_regular(manifest_path, "safe snapshot manifest")
    if (
        manifest.get("schema") != "android-to-harmony.safe-snapshot.v1"
        or manifest.get("snapshot_root") != str(snapshot)
        or manifest.get("source_root") != str(source)
    ):
        raise RunnerError("safe snapshot does not belong to this run")

    contract_hash = require_recorded_hash(
        contract,
        artifacts.get("contract_sha256"),
        "migration contract",
    )
    require_recorded_hash(
        contract_owner,
        artifacts.get("contract_owner_sha256"),
        "migration contract owner",
    )
    contract_payload = load_json_regular(contract, "migration contract")
    contract_owner_payload = load_json_regular(
        contract_owner,
        "migration contract owner",
    )
    contract_source = contract_payload.get("source")
    if (
        contract_payload.get("schema")
        != "android-to-harmony.migration-contract.v1"
        or contract_payload.get("generator") != GENERATOR
        or not isinstance(contract_source, dict)
        or contract_source.get("safe_snapshot_root") != str(snapshot)
        or contract_source.get("original_root") != str(source)
        or contract_owner_payload.get("schema")
        != "android-to-harmony.contract-owner.v1"
        or contract_owner_payload.get("generator") != GENERATOR
        or contract_owner_payload.get("output_name") != contract.name
        or contract_owner_payload.get("contract_sha256") != contract_hash
    ):
        raise RunnerError("migration contract does not belong to this run")

    target_state_path = target / ".migration/state.json"
    if artifacts.get("target_state_path") != str(target_state_path):
        raise RunnerError("run state does not reference the target project marker")
    target_state = load_json_regular(
        target_state_path,
        "target project marker",
    )
    if (
        target_state.get("schema")
        != "android-to-harmony.project-state.v1"
        or target_state.get("generator") != GENERATOR
        or target_state.get("output_root") not in {".", str(target)}
        or target_state.get("project_name") != project["name"]
        or target_state.get("bundle_name") != project["bundle_name"]
        or not has_external_ownership_proof(target, target_state, secret)
    ):
        raise RunnerError("target project ownership proof is invalid")

    target_contract_state = target_state.get("contract")
    if (
        not isinstance(target_contract_state, dict)
        or target_contract_state.get("copied_path")
        != ".migration/source-contract.json"
    ):
        raise RunnerError("target project is not bound to the migration contract")
    target_contract_path = target / ".migration/source-contract.json"
    require_recorded_hash(
        target_contract_path,
        target_contract_state.get("sha256"),
        "target contract copy",
    )
    target_contract = load_json_regular(
        target_contract_path,
        "target contract copy",
    )
    expected_target_contract = json.loads(json.dumps(contract_payload))
    expected_target_source = expected_target_contract.get("source")
    if not isinstance(expected_target_source, dict):
        raise RunnerError("migration contract source is invalid")
    expected_target_source["safe_snapshot_root"] = "<local-safe-snapshot>"
    expected_target_source["original_root"] = "<local-android-source>"
    if target_contract != expected_target_contract:
        raise RunnerError("target contract copy does not match the owned contract")

    batches = contract_payload.get("migration_batches")
    if (
        not isinstance(batches, list)
        or not all(isinstance(batch, dict) for batch in batches)
    ):
        raise RunnerError("migration contract has an invalid batch inventory")
    batch_ids = [batch.get("id") for batch in batches]
    if (
        any(not is_nonempty(batch_id) for batch_id in batch_ids)
        or len(batch_ids) != len(set(batch_ids))
        or state.get("batch_ids") != batch_ids
    ):
        raise RunnerError("recorded batch inventory does not match the contract")
    return f"snapshot-sha256:{snapshot_hash}"


def current_target_revision(target: Path) -> str:
    try:
        _manifest, revision = create_manifest(target)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise RunnerError(f"cannot hash target source: {error}") from error
    return revision


def find_hdc_failure_marker(output: str) -> re.Match[str] | None:
    return HDC_FAILURE_PATTERN.search(ANSI_CSI_PATTERN.sub("", output))


def parse_junit_report(path: Path) -> dict[str, int]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as error:
        raise RunnerError(f"invalid JUnit XML report: {error}") from error
    suites = [root] if root.tag.endswith("testsuite") else [
        child for child in root.iter() if child.tag.endswith("testsuite")
    ]
    if not suites:
        raise RunnerError("JUnit XML report contains no test suite")
    totals = {"passed": 0, "failed": 0, "skipped": 0}
    tests = failures = skipped = 0
    for suite in suites:
        if any(
            child is not root and child.tag.endswith("testsuite")
            for child in suite
        ):
            continue
        try:
            suite_tests = int(suite.attrib.get("tests", "0"))
            suite_failures = int(suite.attrib.get("failures", "0"))
            suite_errors = int(suite.attrib.get("errors", "0"))
            suite_skipped = int(
                suite.attrib.get("skipped", suite.attrib.get("disabled", "0"))
            )
        except ValueError as error:
            raise RunnerError("JUnit XML report has invalid counts") from error
        if min(suite_tests, suite_failures, suite_errors, suite_skipped) < 0:
            raise RunnerError("JUnit XML report has negative counts")
        tests += suite_tests
        failures += suite_failures + suite_errors
        skipped += suite_skipped
    totals["failed"] = failures
    totals["skipped"] = skipped
    totals["passed"] = tests - failures - skipped
    if min(totals.values()) < 0:
        raise RunnerError("JUnit XML report has inconsistent counts")
    return totals


def parse_hypium_text_report(path: Path) -> dict[str, int]:
    try:
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeDecodeError) as error:
        raise RunnerError(f"invalid Hypium text report: {error}") from error
    if not lines:
        raise RunnerError("Hypium text report is empty")
    summary_pattern = re.compile(
        r"^Tests run: ([0-9]+), Failure: ([0-9]+), Error: ([0-9]+), "
        r"Pass: ([0-9]+), Ignore: ([0-9]+)$"
    )
    summary = summary_pattern.fullmatch(lines[-1])
    if summary is None:
        raise RunnerError("Hypium text report has no strict final summary")
    run, failure, error, passed, ignored = (
        int(value) for value in summary.groups()
    )
    if run != failure + error + passed + ignored:
        raise RunnerError("Hypium text report summary counts are inconsistent")
    test_names = [
        line.removeprefix("test=")
        for line in lines[:-1]
        if line.startswith("test=")
    ]
    results = [
        line.removeprefix("result=")
        for line in lines[:-1]
        if line.startswith("result=")
    ]
    if (
        len(test_names) != run
        or len(results) != run
        or any(not value for value in (*test_names, *results))
    ):
        raise RunnerError(
            "Hypium text report test/result pairs do not match its summary"
        )
    result_counts = {
        "failure": 0,
        "error": 0,
        "pass": 0,
        "ignore": 0,
    }
    result_aliases = {
        "failure": "failure",
        "fail": "failure",
        "failed": "failure",
        "error": "error",
        "success": "pass",
        "pass": "pass",
        "passed": "pass",
        "ignore": "ignore",
        "ignored": "ignore",
        "skipped": "ignore",
    }
    for result in results:
        category = result_aliases.get(result.casefold())
        if category is None:
            raise RunnerError(f"Hypium text report has unknown result: {result}")
        result_counts[category] += 1
    if result_counts != {
        "failure": failure,
        "error": error,
        "pass": passed,
        "ignore": ignored,
    }:
        raise RunnerError(
            "Hypium text report result pairs disagree with its summary"
        )
    return {
        "passed": passed,
        "failed": failure + error,
        "skipped": ignored,
    }


def extract_hypium_report_from_aa_stdout(stdout: str) -> bytes:
    """Convert one complete ``hdc shell aa test`` transcript to Hypium text."""
    if not isinstance(stdout, str) or not stdout:
        raise RunnerError("HDC aa test stdout is empty")
    if "\ufffd" in stdout or "\x00" in stdout:
        raise RunnerError("HDC aa test stdout is not valid text")
    if len(stdout.encode("utf-8")) > 5 * 1024 * 1024:
        raise RunnerError("HDC aa test stdout is too large")
    if find_hdc_failure_marker(stdout) is not None:
        raise RunnerError("HDC aa test stdout contains a device failure marker")

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    summary_pattern = re.compile(
        r"^OHOS_REPORT_RESULT: stream=(Tests run: ([0-9]+), "
        r"Failure: ([0-9]+), Error: ([0-9]+), Pass: ([0-9]+), "
        r"Ignore: ([0-9]+))(?:, SkipSpec: ([0-9]+))?$"
    )
    summaries = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := summary_pattern.fullmatch(line)) is not None
    ]
    if len(summaries) != 1:
        raise RunnerError("HDC aa test stdout has no unique strict final summary")
    summary_index, summary_match = summaries[0]
    summary_text = summary_match.group(1)
    run, failure, error, passed, ignored = (
        int(value) for value in summary_match.groups()[1:6]
    )
    if run != failure + error + passed + ignored:
        raise RunnerError("HDC aa test stdout summary counts are inconsistent")
    skip_spec_value = summary_match.group(7)
    if skip_spec_value is not None:
        skip_spec = int(skip_spec_value)
        if skip_spec < 1 or skip_spec > ignored:
            raise RunnerError(
                "HDC aa test stdout SkipSpec count is inconsistent"
            )

    start_indexes = [
        index
        for index, line in enumerate(lines)
        if line == "start ability successfully."
    ]
    if len(start_indexes) != 1:
        raise RunnerError("HDC aa test stdout has no unique start marker")
    start_index = start_indexes[0]
    suite_sums = [
        (index, int(match.group(1)))
        for index, line in enumerate(lines)
        if (match := re.fullmatch(r"OHOS_REPORT_SUM: ([0-9]+)", line))
        is not None
    ]
    if not suite_sums:
        raise RunnerError("HDC aa test stdout suite count disagrees with summary")
    if any(
        not start_index < index < summary_index
        for index, _value in suite_sums
    ):
        raise RunnerError(
            "HDC aa test stdout has protocol events outside the execution "
            "window"
        )
    if sum(value for _index, value in suite_sums) != run:
        raise RunnerError("HDC aa test stdout suite count disagrees with summary")
    report_codes = [
        (index, int(match.group(1)))
        for index, line in enumerate(lines)
        if (match := re.fullmatch(r"OHOS_REPORT_CODE: (-?[0-9]+)", line))
        is not None
    ]
    expected_report_code = 0 if failure == 0 else -1
    if (
        len(report_codes) != 1
        or report_codes[0][0] <= summary_index
        or report_codes[0][1] != expected_report_code
    ):
        raise RunnerError("HDC aa test stdout has an invalid final report code")
    task_durations = [
        (index, int(match.group(1)))
        for index, line in enumerate(lines)
        if (
            match := re.fullmatch(
                r"OHOS_REPORT_STATUS: taskconsuming=([0-9]+)",
                line,
            )
        )
        is not None
    ]
    if len(task_durations) != 1 or task_durations[0][0] <= summary_index:
        raise RunnerError("HDC aa test stdout has no final task duration")
    finished_codes = [
        (index, int(match.group(1)))
        for index, line in enumerate(lines)
        if (
            match := re.fullmatch(
                r"TestFinished-ResultCode: (-?[0-9]+)",
                line,
            )
        )
        is not None
    ]
    if len(finished_codes) != 1 or finished_codes[0][1] != 0:
        raise RunnerError("HDC aa test stdout has no successful finish marker")
    completion_indexes = [
        index
        for index, line in enumerate(lines)
        if line == "user test finished."
    ]
    if len(completion_indexes) != 1:
        raise RunnerError("HDC aa test stdout has no unique completion marker")
    if not (
        start_index
        < summary_index
        < report_codes[0][0]
        < task_durations[0][0]
        < finished_codes[0][0]
        < completion_indexes[0]
    ):
        raise RunnerError(
            "HDC aa test stdout completion markers are out of order"
        )
    allowed_tail_protocol = {
        report_codes[0][0],
        task_durations[0][0],
    }
    if any(
        line.startswith("OHOS_REPORT_")
        and index not in allowed_tail_protocol
        for index, line in enumerate(lines)
        if index > summary_index
    ):
        raise RunnerError(
            "HDC aa test stdout has protocol events outside the execution "
            "window"
        )

    numtests_values = [
        int(match.group(1))
        for line in lines[:summary_index]
        if (
            match := re.fullmatch(
                r"OHOS_REPORT_STATUS: numtests=([0-9]+)",
                line,
            )
        )
        is not None
    ]
    if not numtests_values or any(value != run for value in numtests_values):
        raise RunnerError("HDC aa test stdout test counts disagree with summary")

    current_class: str | None = None
    pending_case: str | None = None
    last_event_case: str | None = None
    case_order: list[str] = []
    started_cases: set[str] = set()
    terminal_codes: dict[str, int] = {}
    skipped_cases: set[str] = set()
    for index, line in enumerate(lines):
        if index < start_index and line.startswith("OHOS_REPORT_"):
            raise RunnerError(
                "HDC aa test stdout has protocol events outside the "
                "execution window"
            )
        class_match = re.fullmatch(r"OHOS_REPORT_STATUS: class=(.+)", line)
        if class_match is not None:
            if not start_index < index < summary_index:
                raise RunnerError(
                    "HDC aa test stdout has protocol events outside the "
                    "execution window"
                )
            current_class = class_match.group(1).strip()
            if not current_class:
                raise RunnerError("HDC aa test stdout contains an empty class")
            continue
        test_match = re.fullmatch(r"OHOS_REPORT_STATUS: test=(.+)", line)
        if test_match is not None:
            if not start_index < index < summary_index:
                raise RunnerError(
                    "HDC aa test stdout has case events outside the "
                    "execution window"
                )
            if pending_case is not None or not current_class:
                raise RunnerError(
                    "HDC aa test stdout has an unpaired test event"
                )
            test_name = test_match.group(1).strip()
            if not test_name:
                raise RunnerError("HDC aa test stdout contains an empty test")
            pending_case = f"{current_class}#{test_name}"
            continue
        code_match = re.fullmatch(r"OHOS_REPORT_STATUS_CODE: (-?[0-9]+)", line)
        if code_match is not None:
            if not start_index < index < summary_index:
                raise RunnerError(
                    "HDC aa test stdout has case events outside the "
                    "execution window"
                )
            if pending_case is None:
                raise RunnerError(
                    "HDC aa test stdout has an unpaired status code"
                )
            code = int(code_match.group(1))
            if code == 1:
                if (
                    pending_case in started_cases
                    or pending_case in terminal_codes
                ):
                    raise RunnerError(
                        "HDC aa test stdout contains duplicate test starts"
                    )
                started_cases.add(pending_case)
                case_order.append(pending_case)
            elif code in {-2, -1, 0}:
                if (
                    pending_case not in started_cases
                    or pending_case in terminal_codes
                ):
                    raise RunnerError(
                        "HDC aa test stdout contains an invalid test finish"
                    )
                terminal_codes[pending_case] = code
            else:
                raise RunnerError(
                    f"HDC aa test stdout has unknown status code: {code}"
                )
            last_event_case = pending_case
            pending_case = None
            continue
        if line.startswith("OHOS_REPORT_STATUS: skipReason="):
            if not start_index < index < summary_index:
                raise RunnerError(
                    "HDC aa test stdout has case events outside the "
                    "execution window"
                )
            if last_event_case is None:
                raise RunnerError(
                    "HDC aa test stdout has an unpaired skip reason"
                )
            skipped_cases.add(last_event_case)

    if pending_case is not None:
        raise RunnerError("HDC aa test stdout ends with an unpaired test event")
    if (
        len(case_order) != run
        or len(terminal_codes) != run
        or len(set(case_order)) != run
    ):
        raise RunnerError(
            "HDC aa test stdout test/result pairs do not match its summary"
        )

    result_lines: list[str] = []
    result_counts = {
        "failure": 0,
        "error": 0,
        "pass": 0,
        "ignore": 0,
    }
    for case in case_order:
        code = terminal_codes[case]
        if code == -2:
            result = "Failure"
            result_counts["failure"] += 1
        elif code == -1:
            result = "Error"
            result_counts["error"] += 1
        elif case in skipped_cases:
            result = "Ignore"
            result_counts["ignore"] += 1
        else:
            result = "Success"
            result_counts["pass"] += 1
        result_lines.extend((f"test={case}", f"result={result}"))
    if result_counts != {
        "failure": failure,
        "error": error,
        "pass": passed,
        "ignore": ignored,
    }:
        raise RunnerError(
            "HDC aa test stdout result pairs disagree with its summary"
        )
    return ("\n".join((*result_lines, summary_text)) + "\n").encode("utf-8")


def parse_test_report(path: Path, report_format: str) -> dict[str, int]:
    if report_format == "junit":
        return parse_junit_report(path)
    if report_format == "hypium-text":
        return parse_hypium_text_report(path)
    raise RunnerError(f"unsupported test report format: {report_format}")


def write_exclusive(path: Path, data: bytes, role: str) -> None:
    assert_safe_components(path.parent, role, allow_missing=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise RunnerError(f"refusing to replace existing {role}: {path.name}") from None
    except OSError as error:
        raise RunnerError(f"cannot write {role}: {error}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def write_atomic_new(path: Path, payload: dict[str, Any]) -> None:
    serialized = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    write_exclusive(path, serialized, "evidence")


def relative_record(
    target: Path,
    path: Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "path": path.relative_to(target).as_posix(),
        "sha256": snapshot["sha256"],
        "size": snapshot["size"],
    }


def cleanup_path(path: Path) -> None:
    try:
        if path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def cleanup_directories(created_directories: list[Path]) -> None:
    for directory in reversed(created_directories):
        try:
            directory.rmdir()
        except OSError:
            pass


def quarantine_existing_files(
    paths: list[Path],
    stage: Path,
    backups: dict[Path, Path],
) -> None:
    """Move old artifacts aside so only command-created files can be accepted."""
    for index, path in enumerate(paths):
        snapshot = file_snapshot(path, "pre-existing result artifact")
        if snapshot is None:
            continue
        backup = stage / f"pre-existing-{index}.backup"
        assert_safe_components(backup, "result backup", allow_missing=True)
        try:
            os.replace(path, backup)
        except OSError as error:
            raise RunnerError(
                f"cannot quarantine pre-existing result artifact: {error}"
            ) from error
        backups[path] = backup
        backup_snapshot = file_snapshot(backup, "result backup")
        if (
            backup_snapshot is None
            or backup_snapshot["sha256"] != snapshot["sha256"]
            or backup_snapshot["size"] != snapshot["size"]
        ):
            raise RunnerError("result artifact changed while it was quarantined")


def restore_missing_backups(backups: dict[Path, Path]) -> None:
    """Restore an old artifact only when the command did not recreate it."""
    for original, backup in backups.items():
        if not os.path.lexists(backup) or os.path.lexists(original):
            continue
        assert_safe_components(
            original.parent,
            "result artifact parent",
            allow_missing=False,
        )
        assert_safe_components(backup, "result backup", allow_missing=False)
        try:
            os.replace(backup, original)
        except OSError as error:
            raise RunnerError(
                f"cannot restore pre-existing result artifact: {error}"
            ) from error


def validate_scope(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    if re.fullmatch(NAME_PATTERN, args.name) is None:
        raise RunnerError(
            "name must contain only letters, digits, dot, dash, underscore"
        )
    slice_ids = list(dict.fromkeys(args.slice_id))
    demand_ids = list(dict.fromkeys(args.demand_id))
    if (
        not slice_ids
        or not demand_ids
        or any(not value.strip() for value in (*slice_ids, *demand_ids))
    ):
        raise RunnerError("slice-id and demand-id must be non-empty")
    return slice_ids, demand_ids


def device_identity(args: argparse.Namespace, *, required: bool) -> Any:
    values = (
        args.device_kind,
        args.device_id,
        args.os_version,
        args.api_version,
    )
    if all(value is None for value in values):
        if required:
            raise RunnerError("device evidence requires complete device identity")
        return "unavailable"
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise RunnerError("device identity must be complete or entirely omitted")
    return {
        "kind": args.device_kind,
        "id": args.device_id,
        "os_version": args.os_version,
        "api_version": args.api_version,
    }


def reject_values(args: argparse.Namespace, names: tuple[str, ...], message: str) -> None:
    if any(getattr(args, name) not in (None, [], False) for name in names):
        raise RunnerError(message)


def is_nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_hdc_aa_test_argv(
    argv: list[str],
    device_id: str,
) -> dict[str, Any]:
    if Path(argv[0]).name.casefold() not in {"hdc", "hdc.exe"}:
        raise RunnerError(
            "stdout test reports are only supported for direct HDC aa test"
        )
    arguments = argv[1:]
    if (
        len(arguments) < 8
        or arguments[0] != "-t"
        or arguments[1] != device_id
        or arguments[2:5] != ["shell", "aa", "test"]
    ):
        raise RunnerError(
            "HDC aa test target must match the declared device id"
        )
    unsafe = re.compile(r"[\s;&|><`$()]")
    if any(not value or unsafe.search(value) for value in arguments):
        raise RunnerError("HDC aa test argv contains an unsafe value")

    required: dict[str, str] = {}
    settings: dict[str, str] = {}
    index = 5
    while index < len(arguments):
        option = arguments[index]
        if option in {"-b", "-m"}:
            if option in required or index + 1 >= len(arguments):
                raise RunnerError(
                    "HDC aa test argv has a missing or duplicate option"
                )
            required[option] = arguments[index + 1]
            index += 2
            continue
        if option == "-s":
            if index + 2 >= len(arguments):
                raise RunnerError("HDC aa test argv has an incomplete setting")
            key = arguments[index + 1]
            value = arguments[index + 2]
            if key in settings:
                raise RunnerError("HDC aa test argv has a duplicate setting")
            settings[key] = value
            index += 3
            continue
        raise RunnerError(f"HDC aa test argv has unsupported option: {option}")
    if set(required) != {"-b", "-m"}:
        raise RunnerError("HDC aa test argv must declare bundle and module")
    if settings.get("unittest") not in {
        "OpenHarmonyTestRunner",
        "/ets/testrunner/OpenHarmonyTestRunner",
    }:
        raise RunnerError("HDC aa test argv has an unsupported test runner")
    timeout = settings.get("timeout")
    if timeout is not None and (
        not timeout.isdecimal() or int(timeout) < 1
    ):
        raise RunnerError("HDC aa test argv has an invalid timeout")
    return {
        "device_id": device_id,
        "bundle": required["-b"],
        "module": required["-m"],
        "runner": settings["unittest"],
        "class": settings.get("class"),
        "timeout_ms": int(timeout) if timeout is not None else None,
    }


def validate_mode(
    args: argparse.Namespace,
) -> tuple[str | None, Any]:
    """Validate mode-specific fields and return runner type and device."""
    device_fields = ("device_kind", "device_id", "os_version", "api_version")
    ui_hap_fields = ("ui_main_hap", "ui_test_hap")
    record_fields = (
        "record_status",
        "scenario_step",
        "expected",
        "actual",
        "provider",
        "provider_kind",
        "evidence_owner",
        "notes",
    )
    if args.mode == "run":
        if args.gate not in COMMAND_GATES:
            raise RunnerError(f"{args.gate} passed evidence requires record mode")
        if not args.argv:
            raise RunnerError("run mode requires command argv after --")
        reject_values(
            args,
            ("blocker", "next_action", *record_fields),
            "run mode does not accept probe or record fields",
        )
        if args.gate == "build":
            if not args.output_artifact:
                raise RunnerError(
                    "passed build evidence requires at least one output-artifact"
                )
            if args.test_report is not None or args.test_report_from_stdout:
                raise RunnerError("build does not accept test-report")
            reject_values(
                args,
                ui_hap_fields,
                "build does not accept UI HAP artifacts",
            )
        elif args.gate in TEST_GATES:
            if args.gate in DEVICE_GATES and not args.test_report_from_stdout:
                raise RunnerError(
                    "UI test runs require controlled HDC stdout reports"
                )
            if args.test_report_from_stdout:
                if (
                    args.gate not in DEVICE_GATES
                    or args.test_report is not None
                    or args.test_report_format != "hypium-text"
                    or args.ui_main_hap is None
                    or args.ui_test_hap is None
                ):
                    raise RunnerError(
                        "stdout reports require device test gates, no test-report path, "
                        "hypium-text format, and main/test HAP artifacts"
                    )
            else:
                if args.test_report is None:
                    raise RunnerError("test gate requires a test report")
                reject_values(
                    args,
                    ui_hap_fields,
                    "file test reports do not accept UI HAP artifacts",
                )
            if args.output_artifact:
                raise RunnerError("test gates do not accept output-artifact")
        if args.gate not in TEST_GATES and args.test_report_format is not None:
            raise RunnerError(
                "test-report-format is only valid for test gates"
            )
        if args.gate in DEVICE_GATES:
            device = device_identity(args, required=True)
        else:
            reject_values(
                args,
                device_fields,
                "non-device command gates must not declare device identity",
            )
            device = "not_applicable"
        return None, device

    if args.mode == "probe":
        if args.gate not in DEVICE_GATES:
            raise RunnerError("probe mode is only valid for UI or device gates")
        if not args.argv:
            raise RunnerError("probe mode requires command argv after --")
        if not is_nonempty(args.blocker) or not is_nonempty(args.next_action):
            raise RunnerError("blocked probe requires blocker and next-action")
        reject_values(
            args,
            (
                "test_report",
                "test_report_from_stdout",
                "test_report_format",
                *ui_hap_fields,
                "output_artifact",
                *record_fields,
            ),
            "probe mode does not accept result artifacts or record fields",
        )
        return None, device_identity(args, required=False)

    if args.argv:
        raise RunnerError("record mode must not contain command argv")
    if args.gate not in {"device_test", "visual_review"}:
        raise RunnerError("record mode is only valid for device or visual evidence")
    if args.record_status not in {"passed", "failed"}:
        raise RunnerError("record mode requires record-status")
    reject_values(
        args,
        (
            "test_report",
            "test_report_from_stdout",
            "test_report_format",
            *ui_hap_fields,
            "output_artifact",
            "blocker",
            "next_action",
        ),
        "record mode does not accept command or probe fields",
    )
    if args.gate == "device_test":
        if (
            not args.scenario_step
            or any(not is_nonempty(step) for step in args.scenario_step)
            or not is_nonempty(args.expected)
            or not is_nonempty(args.actual)
            or not is_nonempty(args.provider)
            or args.provider_kind != "human"
        ):
            raise RunnerError(
                "device record requires a human provider, scenario, expected, "
                "and actual"
            )
        if NON_HUMAN_PROVIDER_PATTERN.search(args.provider):
            raise RunnerError("device record provider must identify a human")
        reject_values(
            args,
            ("evidence_owner", "notes"),
            "device record does not accept visual-review fields",
        )
        return RUNNER_TYPES[args.gate], device_identity(args, required=True)

    reject_values(
        args,
        (
            *device_fields,
            "scenario_step",
            "expected",
            "provider",
            "provider_kind",
        ),
        "visual review must not contain device or scenario fields",
    )
    if (
        not is_nonempty(args.actual)
        or not is_nonempty(args.notes)
        or not is_nonempty(args.evidence_owner)
    ):
        raise RunnerError(
            "visual review requires actual, notes, and a human evidence-owner"
        )
    if NON_HUMAN_PROVIDER_PATTERN.search(args.evidence_owner):
        raise RunnerError("visual review evidence-owner must identify a human")
    return RUNNER_TYPES[args.gate], None


def unique_target_files(
    target: Path,
    values: list[Path],
    role: str,
) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        path = safe_target_path(target, value, role)
        if path in seen:
            raise RunnerError(f"duplicate {role}: {value}")
        seen.add(path)
        paths.append(path)
    return paths


def run_hdc_hap_install(
    executable_path: Path,
    target: Path,
    device_id: str,
    role: str,
    hap_path: Path,
    before: dict[str, Any],
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], str | None]:
    relative_path = hap_path.relative_to(target).as_posix()
    argv = [
        str(executable_path),
        "-t",
        device_id,
        "install",
        "-r",
        relative_path,
    ]
    completed = subprocess.run(
        argv,
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
        shell=False,
    )
    validation_error: str | None = None
    try:
        after = file_snapshot(hap_path, f"{role} HAP after install")
    except RunnerError as error:
        after = None
        validation_error = str(error)
    if completed.returncode != 0:
        validation_error = f"{role} HAP install exited with {completed.returncode}"
    elif find_hdc_failure_marker(
        f"{completed.stdout}\n{completed.stderr}"
    ) is not None:
        validation_error = f"{role} HAP install reported an HDC failure"
    else:
        success_lines = [
            line.strip()
            for line in completed.stdout.splitlines()
            if re.fullmatch(
                r"(?:install bundle successfully\.|\[Info\]App install "
                r"path:.+ msg:install bundle successfully\.)",
                line.strip(),
            )
        ]
        if len(success_lines) != 1:
            validation_error = (
                f"{role} HAP install has no unique success marker"
            )
        elif (
            after is None
            or after["sha256"] != before["sha256"]
            or after["size"] != before["size"]
        ):
            validation_error = f"{role} HAP changed while it was installed"
    record: dict[str, Any] = {
        "role": role,
        "path": relative_path,
        "sha256": before["sha256"],
        "size": before["size"],
        "argv": argv,
        "command": shlex.join(argv),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "failed" if validation_error is not None else "passed",
    }
    if after is not None:
        record["post_install_sha256"] = after["sha256"]
        record["post_install_size"] = after["size"]
    if validation_error is not None:
        record["validation_error"] = validation_error
    return completed, record, validation_error


def build_log(
    runner_type: str,
    requested_argv: list[str],
    executed_argv: list[str],
    completed: subprocess.CompletedProcess[str],
    installed_haps: list[dict[str, Any]] | None = None,
    test_command_executed: bool = True,
) -> bytes:
    lines = [
        f"runner_type={runner_type}",
        f"requested_argv={shlex.join(requested_argv)}",
        f"executed_argv={shlex.join(executed_argv)}",
        f"test_command_executed={str(test_command_executed).lower()}",
        f"exit_code={completed.returncode}",
    ]
    for installation in installed_haps or []:
        lines.extend(
            (
                f"[install:{installation['role']}]",
                f"path={installation['path']}",
                f"sha256={installation['sha256']}",
                f"size={installation['size']}",
                f"argv={shlex.join(installation['argv'])}",
                f"exit_code={installation['exit_code']}",
                "[install stdout]",
                installation["stdout"],
                "[install stderr]",
                installation["stderr"],
            )
        )
    if test_command_executed:
        lines.extend(
            (
                "[stdout]",
                completed.stdout,
                "[stderr]",
                completed.stderr,
            )
        )
    return "\n".join(lines).encode("utf-8")


def probe_failure(
    executable_path: Path,
    completed: subprocess.CompletedProcess[str],
) -> dict[str, Any] | None:
    if completed.returncode != 0:
        return {
            "kind": "nonzero_exit",
            "exit_code": completed.returncode,
        }
    if executable_path.name.casefold() not in {"hdc", "hdc.exe"}:
        return None
    output = f"{completed.stdout}\n{completed.stderr}"
    match = find_hdc_failure_marker(output)
    if match is None:
        return None
    return {
        "kind": "hdc_failure_marker",
        "code": match.group(1),
        "message": match.group(2).strip(),
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    target = normalized_directory(args.target, "target")
    run_root = normalized_directory(args.run_root, "run root")
    slice_ids, demand_ids = validate_scope(args)
    record_runner_type, device = validate_mode(args)
    secret = load_ownership_secret(target)
    if secret is None:
        raise RunnerError("target has no valid external ownership secret")
    source_revision = load_run_identity(run_root, target, secret)

    evidence_root = safe_target_path(
        target,
        Path(".migration/evidence"),
        "evidence directory",
    )
    artifact_root = safe_target_path(
        target,
        Path(".migration/evidence/artifacts"),
        "artifact directory",
    )
    evidence_path = evidence_root / f"{args.name}.json"
    log_path = artifact_root / f"{args.name}.log"
    report_format = args.test_report_format or "junit"
    report_suffix = ".junit.xml" if report_format == "junit" else ".hypium.txt"
    report_copy_path = artifact_root / f"{args.name}{report_suffix}"
    record_path = artifact_root / f"{args.name}.record.txt"
    for candidate in (evidence_path, log_path, report_copy_path, record_path):
        assert_safe_components(candidate, "evidence output", allow_missing=True)
        if os.path.lexists(candidate):
            raise RunnerError("evidence name already exists")

    ui_hap_inputs: list[tuple[str, Path, dict[str, Any]]] = []
    if args.test_report_from_stdout:
        main_hap = safe_target_path(target, args.ui_main_hap, "main HAP")
        test_hap = safe_target_path(target, args.ui_test_hap, "test HAP")
        if main_hap == test_hap:
            raise RunnerError("main and test HAP artifacts must be different")
        for role, path in (("main", main_hap), ("test", test_hap)):
            if path.suffix.casefold() != ".hap":
                raise RunnerError(f"{role} UI artifact must be a HAP")
            snapshot = file_snapshot(path, f"{role} HAP")
            if snapshot is None or snapshot["size"] == 0:
                raise RunnerError(
                    f"{role} HAP must be an existing non-empty regular file"
                )
            ui_hap_inputs.append((role, path, snapshot))

    report_path: Path | None = None
    output_paths: list[Path] = []
    if (
        args.mode == "run"
        and args.gate in TEST_GATES
        and not args.test_report_from_stdout
    ):
        report_path = safe_target_path(target, args.test_report, "test report")
        if is_within(report_path, evidence_root):
            raise RunnerError("test report must be outside runner-owned evidence")
        file_snapshot(report_path, "test report")
    if args.mode == "run" and args.gate == "build":
        output_paths = unique_target_files(
            target,
            args.output_artifact or [],
            "output artifact",
        )
        for path in output_paths:
            if is_within(path, evidence_root):
                raise RunnerError(
                    "output artifact must be outside runner-owned evidence"
                )
            if path.suffix.casefold() not in {".hap", ".app"}:
                raise RunnerError("build output-artifact must be a HAP or APP")
            file_snapshot(path, "output artifact")

    created_directories: list[Path] = []
    created_outputs: list[Path] = []
    backups: dict[Path, Path] = {}
    stage: Path | None = None
    success = False
    started = datetime.now(timezone.utc)
    monotonic_start = time.monotonic()
    try:
        ensure_directory(evidence_root, "evidence directory", created_directories)
        ensure_directory(artifact_root, "artifact directory", created_directories)
        stage = Path(
            tempfile.mkdtemp(prefix=f".{args.name}.run-", dir=artifact_root)
        )
        assert_safe_components(stage, "runner staging directory", allow_missing=False)

        if args.mode == "record":
            duration = time.monotonic() - monotonic_start
            status = args.record_status
            runner_type = record_runner_type
            tests = {
                "passed": 1 if status == "passed" else 0,
                "failed": 1 if status == "failed" else 0,
                "skipped": 0,
            }
            record_lines = [
                f"gate={args.gate}",
                f"status={status}",
                f"recorded_at={started.isoformat()}",
            ]
            if args.gate == "device_test":
                record_lines.extend(
                    (
                        f"provider_kind={args.provider_kind}",
                        f"provider={args.provider}",
                        f"expected={args.expected}",
                        f"actual={args.actual}",
                        *(f"scenario_step={step}" for step in args.scenario_step),
                    )
                )
            else:
                record_lines.extend(
                    (
                        f"evidence_owner={args.evidence_owner}",
                        f"actual={args.actual}",
                        f"notes={args.notes}",
                    )
                )
            staged_artifact = stage / record_path.name
            staged_artifact.write_text(
                "\n".join(record_lines) + "\n",
                encoding="utf-8",
            )
            write_exclusive(
                record_path,
                staged_artifact.read_bytes(),
                "record artifact",
            )
            created_outputs.append(record_path)
            artifact_snapshot = file_snapshot(record_path, "record artifact")
            if artifact_snapshot is None:
                raise RunnerError("record artifact was not created")
            target_revision = current_target_revision(target)
            evidence: dict[str, Any] = {
                "schema": EVIDENCE_SCHEMA,
                "gate": args.gate,
                "scope": "slices:" + ",".join(slice_ids),
                "slice_ids": slice_ids,
                "demand_ids": demand_ids,
                "runner_type": runner_type,
                "runner_mode": "record",
                "started_at": started.isoformat(),
                "duration_seconds": duration,
                "exit_code": None,
                "artifact": record_path.relative_to(target).as_posix(),
                "artifact_sha256": artifact_snapshot["sha256"],
                "artifact_size": artifact_snapshot["size"],
                "tests": tests,
                "source_revision": source_revision,
                "target_revision": target_revision,
                "status": status,
            }
            if args.gate == "device_test":
                evidence.update(
                    {
                        "device": device,
                        "provider_kind": args.provider_kind,
                        "provider": args.provider,
                        "scenario_steps": args.scenario_step,
                        "expected": args.expected,
                        "actual": args.actual,
                    }
                )
            else:
                evidence.update(
                    {
                        "evidence_owner": args.evidence_owner,
                        "provider_kind": "human",
                        "actual": args.actual,
                        "notes": args.notes,
                    }
                )
        else:
            test_invocation: dict[str, Any] | None = None
            executable_path, executable = resolve_executable(
                args.argv[0],
                target,
                run_root,
            )
            tool_origin = derive_trusted_tool_origin(executable_path)
            if tool_origin is None:
                raise RunnerError(
                    "executable is not under a configured trusted Harmony "
                    "toolchain root"
                )
            executed_argv = [str(executable_path), *args.argv[1:]]
            if args.mode == "probe":
                runner_type = classify_probe_argv(args.gate, executed_argv)
            else:
                runner_type = classify_argv(args.gate, executed_argv)
            if runner_type is None:
                raise RunnerError(
                    "command argv does not match the selected gate category"
                )
            if args.test_report_from_stdout:
                test_invocation = validate_hdc_aa_test_argv(
                    executed_argv,
                    device["id"],
                )
            result_paths = (
                [report_path]
                if report_path is not None
                else output_paths
            )
            quarantine_existing_files(
                [path for path in result_paths if path is not None],
                stage,
                backups,
            )
            installed_haps: list[dict[str, Any]] = []
            installation_errors: list[str] = []
            test_command_executed = not args.test_report_from_stdout
            if args.test_report_from_stdout:
                for role, hap_path, hap_before in ui_hap_inputs:
                    completed, installation, install_error = (
                        run_hdc_hap_install(
                            executable_path,
                            target,
                            device["id"],
                            role,
                            hap_path,
                            hap_before,
                        )
                    )
                    installed_haps.append(installation)
                    if install_error is not None:
                        installation_errors.append(install_error)
                        break
                if not installation_errors:
                    test_command_executed = True
            if test_command_executed:
                completed = subprocess.run(
                    executed_argv,
                    cwd=target,
                    check=False,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    shell=False,
                )
            duration = time.monotonic() - monotonic_start
            executable_after = file_snapshot(executable_path, "executable")
            if (
                executable_after is None
                or executable_after["sha256"] != executable["sha256"]
                or executable_after["size"] != executable["size"]
            ):
                raise RunnerError("executable changed while the command ran")

            staged_log = stage / log_path.name
            staged_log.write_bytes(
                build_log(
                    runner_type,
                    args.argv,
                    executed_argv,
                    completed,
                    installed_haps,
                    test_command_executed,
                )
            )
            write_exclusive(log_path, staged_log.read_bytes(), "command log")
            created_outputs.append(log_path)
            log_snapshot = file_snapshot(log_path, "command log")
            if log_snapshot is None:
                raise RunnerError("command log was not created")

            validation_errors: list[str] = list(installation_errors)
            tests = {"passed": 0, "failed": 0, "skipped": 0}
            test_report: dict[str, Any] | None = None
            output_artifacts: list[dict[str, Any]] = []
            detected_probe_failure: dict[str, Any] | None = None

            if args.mode == "probe":
                detected_probe_failure = probe_failure(
                    executable_path,
                    completed,
                )
                if detected_probe_failure is None:
                    raise RunnerError("blocked probe unexpectedly succeeded")
                status = "blocked"
            elif args.gate == "build":
                for path in output_paths:
                    try:
                        after = file_snapshot(path, "output artifact")
                    except RunnerError as error:
                        validation_errors.append(str(error))
                        continue
                    if after is None:
                        validation_errors.append(
                            f"output artifact was not generated: "
                            f"{path.relative_to(target).as_posix()}"
                        )
                        continue
                    if after["size"] == 0:
                        validation_errors.append(
                            f"output artifact is empty: "
                            f"{path.relative_to(target).as_posix()}"
                        )
                        continue
                    output_artifacts.append(relative_record(target, path, after))
                status = (
                    "passed"
                    if completed.returncode == 0 and not validation_errors
                    else "failed"
                )
            else:
                if args.test_report_from_stdout:
                    report_state = "invalid"
                    staged_report = stage / report_copy_path.name
                    if test_command_executed:
                        try:
                            if find_hdc_failure_marker(
                                f"{completed.stdout}\n{completed.stderr}"
                            ) is not None:
                                raise RunnerError(
                                    "HDC aa test output contains a device "
                                    "failure marker"
                                )
                            staged_report.write_bytes(
                                extract_hypium_report_from_aa_stdout(
                                    completed.stdout
                                )
                            )
                            tests = parse_test_report(
                                staged_report,
                                report_format,
                            )
                        except (OSError, RunnerError) as error:
                            validation_errors.append(str(error))
                        else:
                            report_state = "captured"
                            write_exclusive(
                                report_copy_path,
                                staged_report.read_bytes(),
                                "Hypium report artifact",
                            )
                            created_outputs.append(report_copy_path)
                            owned_report = file_snapshot(
                                report_copy_path,
                                "Hypium report artifact",
                            )
                            if owned_report is None:
                                raise RunnerError(
                                    "Hypium report artifact was not created"
                                )
                            test_report = {
                                "status": report_state,
                                "format": report_format,
                                **relative_record(
                                    target,
                                    report_copy_path,
                                    owned_report,
                                ),
                                "source": log_path.relative_to(
                                    target
                                ).as_posix(),
                                "source_kind": "command_stdout",
                                "stream": "stdout",
                            }
                else:
                    assert report_path is not None
                    try:
                        report_after = file_snapshot(
                            report_path,
                            "test report",
                        )
                    except RunnerError as error:
                        report_after = None
                        report_state = "invalid"
                        validation_errors.append(str(error))
                    else:
                        if report_after is None:
                            report_state = "missing"
                            validation_errors.append(
                                "test report was not generated"
                            )
                        else:
                            try:
                                tests = parse_test_report(
                                    report_path,
                                    report_format,
                                )
                            except RunnerError as error:
                                report_state = "invalid"
                                validation_errors.append(str(error))
                            else:
                                report_state = "captured"
                                staged_report = stage / report_copy_path.name
                                shutil.copyfile(report_path, staged_report)
                                staged_snapshot = file_snapshot(
                                    staged_report,
                                    "staged test report",
                                )
                                if (
                                    staged_snapshot is None
                                    or staged_snapshot["sha256"]
                                    != report_after["sha256"]
                                    or staged_snapshot["size"]
                                    != report_after["size"]
                                ):
                                    raise RunnerError(
                                        "test report changed while it was copied"
                                    )
                                write_exclusive(
                                    report_copy_path,
                                    staged_report.read_bytes(),
                                    "test report artifact",
                                )
                                created_outputs.append(report_copy_path)
                                owned_report = file_snapshot(
                                    report_copy_path,
                                    "test report artifact",
                                )
                                if owned_report is None:
                                    raise RunnerError(
                                        "test report artifact was not created"
                                    )
                                test_report = {
                                    "status": report_state,
                                    "format": report_format,
                                    **relative_record(
                                        target,
                                        report_copy_path,
                                        owned_report,
                                    ),
                                    "source": report_path.relative_to(
                                        target
                                    ).as_posix(),
                                }
                if tests["failed"] != 0:
                    validation_errors.append(
                        "test report contains failed tests"
                    )
                if tests["passed"] < 1:
                    validation_errors.append(
                        "test report contains no passing tests"
                    )
                if test_report is None:
                    report_source = (
                        log_path.relative_to(target).as_posix()
                        if args.test_report_from_stdout
                        else report_path.relative_to(target).as_posix()
                    )
                    test_report = {
                        "status": report_state,
                        "format": report_format,
                        "source": report_source,
                    }
                    if args.test_report_from_stdout:
                        test_report.update(
                            {
                                "source_kind": "command_stdout",
                                "stream": "stdout",
                            }
                        )
                status = (
                    "passed"
                    if completed.returncode == 0 and not validation_errors
                    else "failed"
                )

            restore_missing_backups(backups)
            target_revision = current_target_revision(target)
            evidence = {
                "schema": EVIDENCE_SCHEMA,
                "gate": args.gate,
                "scope": "slices:" + ",".join(slice_ids),
                "slice_ids": slice_ids,
                "demand_ids": demand_ids,
                "runner_type": runner_type,
                "runner_mode": args.mode,
                "argv": executed_argv,
                "requested_argv": args.argv,
                "command": shlex.join(executed_argv),
                "executable": executable,
                "tool_origin": tool_origin,
                "started_at": started.isoformat(),
                "duration_seconds": duration,
                "exit_code": (
                    None if args.mode == "probe" else completed.returncode
                ),
                "artifact": log_path.relative_to(target).as_posix(),
                "artifact_sha256": log_snapshot["sha256"],
                "artifact_size": log_snapshot["size"],
                "tests": tests,
                "device": device,
                "source_revision": source_revision,
                "target_revision": target_revision,
                "status": status,
            }
            if validation_errors:
                evidence["validation_errors"] = validation_errors
            if args.mode == "probe":
                evidence.update(
                    {
                        "probe_exit_code": completed.returncode,
                        "probe_failure": detected_probe_failure,
                        "blocker": args.blocker,
                        "next_action": args.next_action,
                    }
                )
            elif args.gate == "build":
                evidence["output_artifacts"] = output_artifacts
            else:
                evidence["test_report"] = test_report
                if test_invocation is not None:
                    evidence["test_invocation"] = test_invocation
                    evidence["installed_haps"] = installed_haps
                    evidence["test_command_executed"] = (
                        test_command_executed
                    )
                if (
                    args.gate in DEVICE_GATES
                    and status == "passed"
                    and test_command_executed
                ):
                    evidence["execution_status"] = "executed"

        attach_attestation(evidence, target, secret)
        write_atomic_new(evidence_path, evidence)
        created_outputs.append(evidence_path)
        success = True
        return {
            "ok": True,
            "schema": RESULT_SCHEMA,
            "evidence": evidence_path.relative_to(target).as_posix(),
            "artifact": evidence["artifact"],
            "status": evidence["status"],
            "exit_code": (
                evidence.get("probe_exit_code")
                if evidence["status"] == "blocked"
                else evidence.get("exit_code")
            ),
        }
    finally:
        restore_missing_backups(backups)
        if stage is not None:
            cleanup_path(stage)
        if not success:
            for output in reversed(created_outputs):
                cleanup_path(output)
            cleanup_directories(created_directories)


def main() -> int:
    args = parse_args()
    try:
        result = execute(args)
    except (RunnerError, OSError, RuntimeError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {"ok": False, "schema": RESULT_SCHEMA, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
