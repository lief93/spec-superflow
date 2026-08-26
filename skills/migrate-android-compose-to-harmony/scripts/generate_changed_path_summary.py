#!/usr/bin/env python3
"""Validate that before/after exact-closure evidence actually exercises a target path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


CONFIG_SCHEMA = "android-to-harmony.changed-path-summary-config.v1"
SUMMARY_SCHEMA = "android-to-harmony.changed-path-summary.v1"
COMMAND_RESULT_SCHEMA = "android-to-harmony.command-result.v1"


class SummaryError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize before/after exact-closure evidence with changed-path coverage checks."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, expected_schema: str | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SummaryError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise SummaryError(f"JSON payload must be an object: {path}")
    if expected_schema is not None and payload.get("schema") != expected_schema:
        raise SummaryError(f"unexpected schema for {path}: {payload.get('schema')!r}")
    return payload


def resolve_path(path_like: str, base: Path) -> Path:
    path = Path(path_like)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
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


def load_generated_evidence(generate_result_path: Path, base: Path) -> dict[str, Any]:
    result = load_json(resolve_path(str(generate_result_path), base), COMMAND_RESULT_SCHEMA)
    target = Path(str(result.get("target", ""))).resolve()
    output_relative = result.get("output")
    manifest_relative = result.get("manifest")
    if not isinstance(output_relative, str) or not output_relative:
        raise SummaryError(f"generate result missing output: {generate_result_path}")
    if not isinstance(manifest_relative, str) or not manifest_relative:
        raise SummaryError(f"generate result missing manifest: {generate_result_path}")
    output_path = (target / output_relative).resolve()
    manifest_path = (target / manifest_relative).resolve()
    if not output_path.is_file():
        raise SummaryError(f"generated file does not exist: {output_path}")
    if not manifest_path.is_file():
        raise SummaryError(f"manifest file does not exist: {manifest_path}")
    manifest = load_json(manifest_path)
    unresolved = manifest.get("unresolved")
    if not isinstance(unresolved, list):
        raise SummaryError(f"manifest unresolved payload must be a list: {manifest_path}")
    return {
        "result": result,
        "output_path": output_path,
        "output_text": output_path.read_text(encoding="utf-8"),
        "output_sha256": sha256_file(output_path),
        "manifest_path": manifest_path,
        "manifest": manifest,
        "manifest_sha256": sha256_file(manifest_path),
        "unresolved": unresolved,
    }


def unresolved_reason_count(entries: list[dict[str, Any]], contains: str) -> int:
    needle = contains.lower()
    return sum(1 for entry in entries if needle in str(entry.get("reason", "")).lower())


def evaluate_check(
    check: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    kind = check.get("kind")
    if not isinstance(kind, str) or not kind:
        raise SummaryError("changed-path check is missing kind")
    if kind == "generated_substring_added":
        substring = check.get("substring")
        if not isinstance(substring, str) or not substring:
            raise SummaryError("generated_substring_added requires substring")
        before_present = substring in before["output_text"]
        after_present = substring in after["output_text"]
        return {
            "kind": kind,
            "substring": substring,
            "before": before_present,
            "after": after_present,
            "passed": (not before_present) and after_present,
        }
    if kind == "generated_substring_removed":
        substring = check.get("substring")
        if not isinstance(substring, str) or not substring:
            raise SummaryError("generated_substring_removed requires substring")
        before_present = substring in before["output_text"]
        after_present = substring in after["output_text"]
        return {
            "kind": kind,
            "substring": substring,
            "before": before_present,
            "after": after_present,
            "passed": before_present and (not after_present),
        }
    if kind == "manifest_reason_removed":
        contains = check.get("contains")
        if not isinstance(contains, str) or not contains:
            raise SummaryError("manifest_reason_removed requires contains")
        before_count = unresolved_reason_count(before["unresolved"], contains)
        after_count = unresolved_reason_count(after["unresolved"], contains)
        return {
            "kind": kind,
            "contains": contains,
            "before": before_count,
            "after": after_count,
            "passed": before_count > after_count,
        }
    raise SummaryError(f"unsupported changed-path check kind: {kind}")


def summarize_sample(sample: dict[str, Any], *, config_base: Path) -> dict[str, Any]:
    name = sample.get("name")
    if not isinstance(name, str) or not name:
        raise SummaryError("sample is missing name")
    before_result = sample.get("before_generate_result")
    after_result = sample.get("after_generate_result")
    if not isinstance(before_result, str) or not isinstance(after_result, str):
        raise SummaryError(f"sample {name} is missing before/after generate result paths")
    checks = sample.get("checks")
    if not isinstance(checks, list) or not checks:
        raise SummaryError(f"sample {name} must declare at least one changed-path check")
    before = load_generated_evidence(Path(before_result), config_base)
    after = load_generated_evidence(Path(after_result), config_base)
    results = [evaluate_check(check, before, after) for check in checks]
    passed_checks = [result for result in results if result["passed"]]
    if not passed_checks:
        raise SummaryError(
            f"sample {name} does not cover any declared changed path; before/after evidence is invalid"
        )
    if any(not result["passed"] for result in results):
        failing = next(result for result in results if not result["passed"])
        raise SummaryError(
            f"sample {name} failed changed-path check {failing['kind']}: {json.dumps(failing, ensure_ascii=False)}"
        )
    return {
        "name": name,
        "before_generated_path": str(before["output_path"]),
        "before_generated_sha256": before["output_sha256"],
        "before_manifest_path": str(before["manifest_path"]),
        "before_manifest_sha256": before["manifest_sha256"],
        "after_generated_path": str(after["output_path"]),
        "after_generated_sha256": after["output_sha256"],
        "after_manifest_path": str(after["manifest_path"]),
        "after_manifest_sha256": after["manifest_sha256"],
        "generated_changed": before["output_sha256"] != after["output_sha256"],
        "manifest_changed": before["manifest_sha256"] != after["manifest_sha256"],
        "checks": results,
        "changed_paths_covered": True,
    }


def main() -> int:
    args = parse_args()
    try:
        config_path = args.config.resolve()
        config = load_json(config_path, CONFIG_SCHEMA)
        samples = config.get("samples")
        if not isinstance(samples, list) or not samples:
            raise SummaryError("config must contain at least one sample")
        payload = {
            "schema": SUMMARY_SCHEMA,
            "config_path": str(config_path),
            "sample_count": len(samples),
            "samples": [
                summarize_sample(sample, config_base=config_path.parent)
                for sample in samples
            ],
        }
        write_json(args.output.resolve(), payload)
    except SummaryError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "output": str(args.output.resolve()), "sample_count": payload["sample_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
