#!/usr/bin/env python3
"""Small, standalone source helpers used by the behavior-contract tools."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


MANIFEST_NAME = ".behavior-source-safe.json"


def lexical_code_mask(text: str, *, mask_strings: bool = True) -> str:
    """Mask comments and optionally string literals without changing offsets."""
    masked = list(text)
    state = "code"
    delimiter = ""
    block_depth = 0
    index = 0

    def blank(start: int, end: int) -> None:
        for position in range(start, min(end, len(masked))):
            if masked[position] not in {"\r", "\n"}:
                masked[position] = " "

    while index < len(text):
        if state == "line_comment":
            if text[index] in {"\r", "\n"}:
                state = "code"
            else:
                blank(index, index + 1)
            index += 1
            continue
        if state == "block_comment":
            if text.startswith("/*", index):
                blank(index, index + 2)
                block_depth += 1
                index += 2
            elif text.startswith("*/", index):
                blank(index, index + 2)
                block_depth -= 1
                index += 2
                if block_depth == 0:
                    state = "code"
            else:
                blank(index, index + 1)
                index += 1
            continue
        if state == "string":
            if text.startswith(delimiter, index):
                if mask_strings:
                    blank(index, index + len(delimiter))
                index += len(delimiter)
                state = "code"
            elif len(delimiter) == 1 and text[index] == "\\":
                if mask_strings:
                    blank(index, index + 2)
                index += 2
            else:
                if mask_strings:
                    blank(index, index + 1)
                index += 1
            continue
        if text.startswith("//", index):
            blank(index, index + 2)
            state = "line_comment"
            index += 2
        elif text.startswith("/*", index):
            blank(index, index + 2)
            state = "block_comment"
            block_depth = 1
            index += 2
        elif text.startswith('\"\"\"', index) or text.startswith("'''", index):
            delimiter = text[index:index + 3]
            if mask_strings:
                blank(index, index + 3)
            state = "string"
            index += 3
        elif text[index] in {'\"', "'"}:
            delimiter = text[index]
            if mask_strings:
                blank(index, index + 1)
            state = "string"
            index += 1
        else:
            index += 1
    return "".join(masked)


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("snapshot paths must be non-empty strings")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError(f"unsafe snapshot path: {value!r}")
    return value


def validate_safe_tree(root: Path, *, require_safe_manifest: bool = True) -> dict:
    """Verify the explicit Kotlin/Java snapshot manifest and every listed hash."""
    root = Path(root)
    violations: list[str] = []
    if root.is_symlink() or not root.is_dir():
        return {"ok": False, "violations": ["snapshot root must be a real directory"]}
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        message = f"missing regular {MANIFEST_NAME}"
        return {"ok": not require_safe_manifest, "violations": [message]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "behavior-source-snapshot.v1":
            violations.append("unsupported snapshot manifest schema_version")
        files = manifest.get("text_files")
        hashes = manifest.get("text_file_sha256")
        if not isinstance(files, list) or not files or not isinstance(hashes, dict):
            raise ValueError("manifest requires text_files and text_file_sha256")
        if len(files) != len(set(files)):
            violations.append("snapshot manifest contains duplicate paths")
        root_resolved = root.resolve(strict=True)
        for value in files:
            relative = _safe_relative_path(value)
            source = root / relative
            parents = [root.joinpath(*PurePosixPath(relative).parts[:index])
                       for index in range(1, len(PurePosixPath(relative).parts))]
            if any(parent.is_symlink() for parent in parents) or source.is_symlink() or not source.is_file():
                violations.append(f"listed source is missing or symbolic: {relative}")
                continue
            if root_resolved not in source.resolve(strict=True).parents:
                violations.append(f"listed source escapes snapshot: {relative}")
                continue
            expected = hashes.get(relative)
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
            if expected != actual:
                violations.append(f"listed source hash differs: {relative}")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        violations.append(str(error))
    return {"ok": not violations, "violations": violations}
