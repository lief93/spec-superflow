#!/usr/bin/env python3
"""Bind slot/container regression evidence to the current skill bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


CONFIG_SCHEMA = "android-to-harmony.slot-container-summary-config.v1"
SUMMARY_SCHEMA = "android-to-harmony.slot-container-summary.v1"
SKILL_MANIFEST_SCHEMA = "android-to-harmony.skill-tree-manifest.v1"
COMMAND_RESULT_SCHEMA = "android-to-harmony.command-result.v1"
HASH_SKILL_TREE = Path(__file__).resolve().with_name("hash_skill_tree.py")
BUTTON_WRAPPER_PATTERN = re.compile(
    r"(?:Button|TextButton|OutlinedButton|IconButton)\(\)\s*\{\s*Row\(\)\s*\{",
    re.MULTILINE,
)


class SummaryError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize slot/container regression evidence with stale-artifact checks."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--skill-manifest", required=True, type=Path)
    parser.add_argument("--generator", required=True, type=Path)
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
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SummaryError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(data, dict):
        raise SummaryError(f"JSON payload must be an object: {path}")
    if expected_schema is not None and data.get("schema") != expected_schema:
        raise SummaryError(
            f"unexpected schema for {path}: {data.get('schema')!r}"
        )
    return data


def resolve_path(path_like: str, base: Path) -> Path:
    path = Path(path_like)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def git_revision(source_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SummaryError(
            f"cannot resolve git revision for source root {source_root}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def write_json(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def compute_current_skill_tree_manifest(root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="slot-container-skill-manifest.") as temporary_dir:
        temporary = Path(temporary_dir) / "manifest.json"
        result = subprocess.run(
            [
                sys.executable,
                str(HASH_SKILL_TREE),
                "--root",
                str(root),
                "--output",
                str(temporary),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SummaryError(
                "cannot hash current skill tree: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return load_json(temporary, SKILL_MANIFEST_SCHEMA)


def validate_skill_binding(
    manifest: dict[str, Any],
    manifest_path: Path,
    generator_path: Path,
) -> dict[str, Any]:
    root = Path(str(manifest.get("local_root", ""))).resolve()
    if not root.is_dir():
        raise SummaryError(f"skill manifest root is not a directory: {root}")
    current_manifest = compute_current_skill_tree_manifest(root)
    if manifest.get("tree_sha256") != current_manifest.get("tree_sha256"):
        raise SummaryError("skill manifest does not bind the current skill tree bytes")
    try:
        relative_generator = generator_path.resolve().relative_to(root).as_posix()
    except ValueError as error:
        raise SummaryError(
            f"generator is not inside skill manifest root: {generator_path}"
        ) from error
    file_entries = manifest.get("files")
    if not isinstance(file_entries, list):
        raise SummaryError(f"skill manifest has invalid files payload: {manifest_path}")
    entry = next(
        (
            item
            for item in file_entries
            if isinstance(item, dict) and item.get("path") == relative_generator
        ),
        None,
    )
    if entry is None:
        raise SummaryError(
            f"skill manifest does not contain generator entry: {relative_generator}"
        )
    current_generator_sha = sha256_file(generator_path)
    if entry.get("sha256") != current_generator_sha:
        raise SummaryError(
            "skill manifest digest does not bind the current generator bytes"
        )
    return {
        "skill_tree_digest": manifest.get("tree_sha256"),
        "skill_manifest_path": str(manifest_path),
        "skill_manifest_root": str(root),
        "generator_path": str(generator_path),
        "generator_sha256": current_generator_sha,
        "generator_mtime_ns": generator_path.stat().st_mtime_ns,
    }


def summarize_sample(
    sample: dict[str, Any],
    *,
    config_base: Path,
    source_root: Path,
    generator_info: dict[str, Any],
    build_log: Path,
) -> dict[str, Any]:
    name = sample.get("name")
    source_file = sample.get("source_file")
    composable = sample.get("composable")
    generate_result_path = sample.get("generate_result")
    if not all(isinstance(value, str) and value for value in (name, source_file, composable, generate_result_path)):
        raise SummaryError("sample is missing required string fields")
    source_path = resolve_path(source_file, source_root)
    try:
        source_relative = source_path.relative_to(source_root).as_posix()
    except ValueError as error:
        raise SummaryError(f"source file is outside source root: {source_path}") from error
    if not source_path.is_file():
        raise SummaryError(f"source file does not exist: {source_path}")
    generate_result = load_json(
        resolve_path(generate_result_path, config_base),
        COMMAND_RESULT_SCHEMA,
    )
    root_info = generate_result.get("root")
    if not isinstance(root_info, dict):
        raise SummaryError(f"generate result missing root payload: {generate_result_path}")
    if root_info.get("source") != source_relative or root_info.get("composable") != composable:
        raise SummaryError(
            f"generate result root mismatch for sample {name}: "
            f"{root_info.get('source')!r} / {root_info.get('composable')!r}"
        )
    target = Path(str(generate_result.get("target", ""))).resolve()
    output_relative = generate_result.get("output")
    manifest_relative = generate_result.get("manifest")
    if not isinstance(output_relative, str) or not output_relative:
        raise SummaryError(f"generate result missing output for sample {name}")
    generated_file = (target / output_relative).resolve()
    if not generated_file.is_file():
        raise SummaryError(f"generated file does not exist: {generated_file}")
    if generated_file.stat().st_mtime_ns < int(generator_info["generator_mtime_ns"]):
        raise SummaryError(
            f"generated file is older than the current generator for sample {name}"
        )
    if build_log.stat().st_mtime_ns < generated_file.stat().st_mtime_ns:
        raise SummaryError(
            f"build log is older than generated file for sample {name}"
        )
    generated_text = generated_file.read_text(encoding="utf-8")
    for forbidden in sample.get("forbidden_substrings", []):
        if forbidden in generated_text:
            raise SummaryError(
                f"forbidden substring {forbidden!r} found in generated file for sample {name}"
            )
    expected_sequences = sample.get("expected_sequences", [])
    if not isinstance(expected_sequences, list):
        raise SummaryError(f"expected_sequences must be a list for sample {name}")
    for sequence in expected_sequences:
        if not isinstance(sequence, list) or not sequence:
            raise SummaryError(f"each expected sequence must be a non-empty list for sample {name}")
        position = -1
        for token in sequence:
            if not isinstance(token, str) or not token:
                raise SummaryError(f"expected sequence tokens must be non-empty strings for sample {name}")
            next_position = generated_text.find(token, position + 1)
            if next_position < 0:
                raise SummaryError(
                    f"sequence token {token!r} missing or out of order in sample {name}"
                )
            position = next_position
    required_click_substrings = sample.get("required_click_substrings", [])
    if not isinstance(required_click_substrings, list):
        raise SummaryError(
            f"required_click_substrings must be a list for sample {name}"
        )
    for token in required_click_substrings:
        if not isinstance(token, str) or token not in generated_text:
            raise SummaryError(
                f"required click substring {token!r} missing in sample {name}"
            )
    minimum_wrapper_count = sample.get("minimum_wrapper_count", 0)
    if not isinstance(minimum_wrapper_count, int) or minimum_wrapper_count < 0:
        raise SummaryError(
            f"minimum_wrapper_count must be a non-negative integer for sample {name}"
        )
    button_wrapper_count = len(BUTTON_WRAPPER_PATTERN.findall(generated_text))
    if button_wrapper_count < minimum_wrapper_count:
        raise SummaryError(
            f"sample {name} has {button_wrapper_count} button wrappers; "
            f"expected at least {minimum_wrapper_count}"
        )
    manifest_sha256 = None
    if isinstance(manifest_relative, str) and manifest_relative:
        manifest_path = (target / manifest_relative).resolve()
        if manifest_path.is_file():
            manifest_sha256 = sha256_file(manifest_path)
    return {
        "name": name,
        "source_file": source_relative,
        "composable": composable,
        "target": str(target),
        "generate_result_path": str(resolve_path(generate_result_path, config_base)),
        "generated_file": str(generated_file),
        "generated_file_sha256": sha256_file(generated_file),
        "generated_file_mtime_ns": generated_file.stat().st_mtime_ns,
        "generate_manifest_path": str((target / manifest_relative).resolve()) if isinstance(manifest_relative, str) else None,
        "generate_manifest_sha256": manifest_sha256,
        "button_wrapper_count": button_wrapper_count,
        "blank_count": generated_text.count("Blank()"),
        "stack_count": generated_text.count("Stack() {"),
        "expected_sequences": expected_sequences,
        "required_click_substrings": required_click_substrings,
        "unresolved_count": generate_result.get("unresolved_count"),
    }


def main() -> int:
    args = parse_args()
    try:
        config_path = args.config.resolve()
        skill_manifest_path = args.skill_manifest.resolve()
        generator_path = args.generator.resolve()
        output_path = args.output.resolve()
        config = load_json(config_path, CONFIG_SCHEMA)
        skill_manifest = load_json(skill_manifest_path, SKILL_MANIFEST_SCHEMA)
        generator_info = validate_skill_binding(
            skill_manifest,
            skill_manifest_path,
            generator_path,
        )
        config_base = config_path.parent
        source_root = resolve_path(str(config.get("source_root", "")), config_base)
        expected_revision = config.get("source_revision")
        if not isinstance(expected_revision, str) or not expected_revision:
            raise SummaryError("config is missing source_revision")
        current_revision = git_revision(source_root)
        if current_revision != expected_revision:
            raise SummaryError(
                f"source revision mismatch: expected {expected_revision}, got {current_revision}"
            )
        build_log = resolve_path(str(config.get("build_log", "")), config_base)
        if not build_log.is_file():
            raise SummaryError(f"build log does not exist: {build_log}")
        build_text = build_log.read_text(encoding="utf-8", errors="ignore")
        samples_payload = config.get("samples")
        if not isinstance(samples_payload, list) or not samples_payload:
            raise SummaryError("config must contain at least one sample")
        samples = [
            summarize_sample(
                sample,
                config_base=config_base,
                source_root=source_root,
                generator_info=generator_info,
                build_log=build_log,
            )
            for sample in samples_payload
        ]
        summary = {
            "schema": SUMMARY_SCHEMA,
            "skill_tree_digest": generator_info["skill_tree_digest"],
            "generator_path": generator_info["generator_path"],
            "generator_sha256": generator_info["generator_sha256"],
            "source_root": str(source_root),
            "source_revision": current_revision,
            "build_log": str(build_log),
            "build_log_sha256": sha256_file(build_log),
            "build_log_mtime_ns": build_log.stat().st_mtime_ns,
            "button_child_error_count": build_text.count(
                "The 'Button' component can have only one child component"
            ),
            "blank_parent_error_count": build_text.count(
                "Blank component can only be nested in Row,Column,Flex"
            ),
            "build_success": "BUILD SUCCESSFUL" in build_text or "BUILD SUCCESS" in build_text,
            "samples": samples,
        }
        write_json(output_path, summary)
    except (SummaryError, OSError, UnicodeError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
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
                "output": str(output_path),
                "sample_count": len(summary["samples"]),
                "skill_tree_digest": summary["skill_tree_digest"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
