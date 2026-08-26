#!/usr/bin/env python3
"""Create a path-independent SHA-256 manifest for an installed skill tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "android-to-harmony.skill-tree-manifest.v1"


class ManifestError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hash deliverable files and symbolic links in a skill/plugin tree."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize_paths(root: Path, output: Path) -> tuple[Path, Path]:
    normalized_root = Path(
        os.path.abspath(os.path.expanduser(str(root)))
    ).resolve()
    normalized_output = Path(
        os.path.abspath(os.path.expanduser(str(output)))
    ).resolve()
    if not normalized_root.is_dir():
        raise ManifestError(f"hashed root is not a directory: {normalized_root}")
    if (
        normalized_output == normalized_root
        or normalized_root in normalized_output.parents
    ):
        raise ManifestError("manifest output must be outside the hashed root")
    if normalized_output.exists() or normalized_output.is_symlink():
        raise ManifestError(f"manifest output already exists: {normalized_output}")
    return normalized_root, normalized_output


def create_manifest(root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    digest_lines: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        relative_parts = path.relative_to(root).parts
        if "__pycache__" in relative_parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            target = os.readlink(path)
            payload = target.encode("utf-8", errors="surrogateescape")
            entry = {
                "path": relative,
                "type": "symlink",
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "target": target,
            }
        elif path.is_file():
            payload = path.read_bytes()
            entry = {
                "path": relative,
                "type": "file",
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            }
        elif path.is_dir():
            continue
        else:
            raise ManifestError(f"unsupported tree entry: {path}")
        entries.append(entry)
        digest_lines.append(
            f"{entry['type']}\\0{entry['path']}\\0{entry['bytes']}\\0"
            f"{entry['sha256']}\\0{entry.get('target', '')}\n"
        )
    tree_digest = sha256_bytes("".join(digest_lines).encode("utf-8"))
    return {
        "schema": SCHEMA,
        "local_root": str(root),
        "file_count": len(entries),
        "tree_sha256": tree_digest,
        "files": entries,
    }


def write_manifest(output: Path, manifest: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    try:
        root, output = normalize_paths(args.root, args.output)
        manifest = create_manifest(root)
        write_manifest(output, manifest)
    except (ManifestError, OSError, UnicodeError) as error:
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
                "output": str(output),
                "file_count": manifest["file_count"],
                "tree_sha256": manifest["tree_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
