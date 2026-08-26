#!/usr/bin/env python3
"""Create a deterministic manifest for migration-relevant target sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = "android-to-harmony.target-source-manifest.v1"
GENERATOR = "migrate-android-compose-to-harmony"
ROOT_FILES = {
    "build-profile.json5",
    "hvigorfile.ts",
    "oh-package.json5",
    "oh-package-lock.json5",
    "hvigor/hvigor-config.json5",
    "AppScope/app.json5",
    "AppScope/resources/base/element/string.json",
}
MODULE_FILES = (
    "build-profile.json5",
    "hvigorfile.ts",
    "oh-package.json5",
)
MODULE_SOURCE_DIRECTORIES = (
    "src/main",
    "src/test",
    "src/ohosTest",
)
APP_RESOURCE_PREFIX = "AppScope/resources/"
MIGRATION_SOURCE_PREFIX = ".migration/slices/"
SLICE_LEDGER_SCHEMA = "android-to-harmony.slice-ledger.v1"
SLICE_PROJECTION = "android-to-harmony.slice-definition.v1"
SLICE_LIFECYCLE_FIELDS = {
    "status",
    "evidence",
    "blocker",
}
ASSET_LEDGER_PATH = ".migration/assets.json"
ASSET_LEDGER_SCHEMA = "android-to-harmony.asset-ledger.v1"
FONT_SUFFIXES = {".ttf", ".otf"}
EXCLUDED_PATH_PARTS = {
    ".hvigor",
    ".idea",
    ".test",
    "oh_modules",
}


class TargetHashError(RuntimeError):
    pass


def is_excluded_path(relative: Path) -> bool:
    if any(part in EXCLUDED_PATH_PARTS for part in relative.parts):
        return True
    for index, part in enumerate(relative.parts):
        if part != "build":
            continue
        ancestors = relative.parts[:index]
        in_source_set = any(
            ancestors[offset : offset + 2] == ("src", source_set)
            for offset in range(max(0, len(ancestors) - 1))
            for source_set in ("main", "test", "ohosTest")
        )
        if not in_source_set:
            return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hash migration-relevant HarmonyOS target source files."
    )
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_target(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise TargetHashError(f"target must not be a symbolic link: {absolute}")
    resolved = absolute.resolve()
    if not resolved.is_dir():
        raise TargetHashError(f"target does not exist: {resolved}")
    return resolved


def discover_modules(target: Path) -> tuple[str, ...]:
    modules: list[str] = []
    for current_root, directories, filenames in os.walk(target):
        current = Path(current_root)
        kept_directories: list[str] = []
        for directory in directories:
            child = current / directory
            relative_child = child.relative_to(target)
            if is_excluded_path(relative_child):
                continue
            if child.is_symlink():
                raise TargetHashError(
                    "non-excluded target path is a symbolic link: "
                    f"{relative_child.as_posix()}"
                )
            kept_directories.append(directory)
        directories[:] = kept_directories
        if current == target:
            continue
        relative = current.relative_to(target)
        if is_excluded_path(relative):
            continue
        present_descriptors = set(filenames).intersection(MODULE_FILES)
        if not present_descriptors:
            continue
        missing_descriptors = [
            filename
            for filename in MODULE_FILES
            if filename not in present_descriptors
        ]
        if missing_descriptors:
            raise TargetHashError(
                "incomplete HarmonyOS module: "
                f"{relative.as_posix()}; missing {missing_descriptors[0]}"
            )
        modules.append(relative.as_posix())
    return tuple(sorted(modules, key=lambda value: value.encode("utf-8")))


def is_resource_path(relative: str, modules: tuple[str, ...]) -> bool:
    if relative.startswith(APP_RESOURCE_PREFIX):
        return True
    return any(
        relative.startswith(
            f"{module}/{source_directory}/resources/"
        )
        for module in modules
        for source_directory in MODULE_SOURCE_DIRECTORIES
    )


def should_include(relative: str, modules: tuple[str, ...]) -> bool:
    path = Path(relative)
    if is_resource_path(relative, modules):
        return True
    if is_excluded_path(path):
        return False
    if relative in ROOT_FILES or relative == ASSET_LEDGER_PATH:
        return True
    included = relative.startswith(MIGRATION_SOURCE_PREFIX)
    for module in modules:
        if relative in {
            f"{module}/{filename}"
            for filename in MODULE_FILES
        } or any(
            relative.startswith(f"{module}/{source_directory}/")
            for source_directory in MODULE_SOURCE_DIRECTORIES
        ):
            included = True
            break
    if not included:
        return False
    return True


def monitored_roots(target: Path, modules: tuple[str, ...]) -> tuple[Path, ...]:
    relative_roots = {
        Path(APP_RESOURCE_PREFIX.removesuffix("/")),
        Path(MIGRATION_SOURCE_PREFIX.removesuffix("/")),
        *(
            Path(module) / source_directory
            for module in modules
            for source_directory in MODULE_SOURCE_DIRECTORIES
        ),
    }
    return tuple(
        target / relative
        for relative in sorted(
            relative_roots,
            key=lambda path: path.as_posix().encode("utf-8"),
        )
    )


def validate_monitored_roots(
    target: Path,
    modules: tuple[str, ...],
) -> None:
    pending = [
        root
        for root in monitored_roots(target, modules)
        if os.path.lexists(root)
    ]
    while pending:
        current = pending.pop()
        relative = current.relative_to(target).as_posix()
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise TargetHashError(
                f"monitored target path is a symbolic link: {relative}"
            )
        if stat.S_ISREG(mode):
            raise TargetHashError(
                f"monitored target root is not a directory: {relative}"
            )
        if not stat.S_ISDIR(mode):
            raise TargetHashError(
                f"monitored target path is not a regular file or directory: "
                f"{relative}"
            )
        with os.scandir(current) as entries:
            for entry in entries:
                child = Path(entry.path)
                child_relative = child.relative_to(target).as_posix()
                child_mode = child.lstat().st_mode
                if stat.S_ISLNK(child_mode):
                    raise TargetHashError(
                        "monitored target path is a symbolic link: "
                        f"{child_relative}"
                    )
                if stat.S_ISDIR(child_mode):
                    pending.append(child)
                elif not stat.S_ISREG(child_mode):
                    raise TargetHashError(
                        "monitored target path is not a regular file or "
                        f"directory: {child_relative}"
                    )


def validate_asset_ledger(target: Path) -> None:
    ledger_path = target / ASSET_LEDGER_PATH
    if not os.path.lexists(ledger_path):
        return
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise TargetHashError("asset ledger is not a regular file")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise TargetHashError(f"invalid asset ledger: {error}") from error
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema") != ASSET_LEDGER_SCHEMA
        or not isinstance(ledger.get("assets"), dict)
    ):
        raise TargetHashError("asset ledger has an unsupported schema")

    for destination, record in ledger["assets"].items():
        if not isinstance(destination, str) or not destination:
            raise TargetHashError("asset ledger destination is invalid")
        relative = Path(destination)
        if relative.is_absolute() or ".." in relative.parts:
            raise TargetHashError(
                f"asset ledger destination is unsafe: {destination}"
            )
        is_font = relative.suffix.lower() in FONT_SUFFIXES
        is_supported_resource_directory = (
            "resources" in relative.parts
            and (
                (is_font and "rawfile" in relative.parts)
                or (not is_font and relative.parent.name == "media")
            )
        )
        if not is_supported_resource_directory:
            raise TargetHashError(
                "asset ledger destination is not a supported HarmonyOS "
                f"resource: {destination}"
            )
        if not isinstance(record, dict):
            raise TargetHashError(
                f"asset ledger entry is invalid: {destination}"
            )
        expected_size = record.get("bytes")
        expected_hash = record.get("destination_sha256")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or expected_hash != expected_hash.lower()
            or any(
                character not in "0123456789abcdef"
                for character in expected_hash
            )
        ):
            raise TargetHashError(
                f"asset ledger entry is invalid: {destination}"
            )

        asset_path = target / relative
        current = target
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise TargetHashError(
                    f"asset ledger destination contains a symbolic link: "
                    f"{destination}"
                )
        if not asset_path.is_file():
            raise TargetHashError(
                f"asset ledger destination is missing or unsafe: {destination}"
            )
        if asset_path.stat().st_size != expected_size:
            raise TargetHashError(
                f"asset ledger size does not match target: {destination}"
            )
        if sha256_file(asset_path) != expected_hash:
            raise TargetHashError(
                f"asset ledger hash does not match target: {destination}"
            )


def collect_files(target: Path, modules: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for current_root, directories, filenames in os.walk(target):
        current = Path(current_root)
        kept_directories: list[str] = []
        for directory in directories:
            child = current / directory
            relative = child.relative_to(target)
            if child.is_symlink() and should_include(relative.as_posix(), modules):
                raise TargetHashError(
                    f"included target path is a symbolic link: {relative.as_posix()}"
                )
            if (
                not is_excluded_path(relative)
                or is_resource_path(f"{relative.as_posix()}/", modules)
            ):
                kept_directories.append(directory)
        directories[:] = kept_directories
        for filename in filenames:
            child = current / filename
            relative = child.relative_to(target).as_posix()
            if not should_include(relative, modules):
                continue
            if child.is_symlink() or not child.is_file():
                raise TargetHashError(
                    f"included target path is not a regular file: {relative}"
                )
            files.append(child)
    return sorted(
        files,
        key=lambda path: path.relative_to(target).as_posix().encode("utf-8"),
    )


def manifest_file_entry(target: Path, path: Path) -> dict[str, Any]:
    relative = path.relative_to(target).as_posix()
    if not relative.startswith(MIGRATION_SOURCE_PREFIX):
        return {
            "path": relative,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise TargetHashError(
            f"invalid slice ledger while hashing target: {relative}: {error}"
        ) from error
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema") != SLICE_LEDGER_SCHEMA
    ):
        raise TargetHashError(
            f"invalid slice ledger while hashing target: {relative}"
        )
    definition = {
        key: value
        for key, value in ledger.items()
        if key not in SLICE_LIFECYCLE_FIELDS
    }
    canonical = json.dumps(
        {
            "schema": SLICE_PROJECTION,
            "definition": definition,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "path": relative,
        "size": len(canonical),
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "hash_mode": "slice_definition_projection",
    }


def create_manifest(target: Path) -> tuple[dict[str, Any], str]:
    modules = discover_modules(target)
    if not modules:
        raise TargetHashError(
            "target must contain at least one complete HarmonyOS module"
        )
    validate_monitored_roots(target, modules)
    validate_asset_ledger(target)
    files = collect_files(target, modules)
    module_files = {
        f"{module}/{filename}"
        for module in modules
        for filename in MODULE_FILES
    }
    missing = sorted(
        relative
        for relative in ROOT_FILES | module_files
        if not (target / relative).is_file()
    )
    if missing:
        raise TargetHashError(f"required target source is missing: {missing[0]}")
    portable_manifest = {
        "schema": MANIFEST_SCHEMA,
        "algorithm": "sha256",
        "files": [
            manifest_file_entry(target, path)
            for path in files
        ],
    }
    manifest = {
        **portable_manifest,
        "generator": GENERATOR,
        "local_target_root": str(target),
    }
    canonical = json.dumps(
        portable_manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return manifest, f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def normalize_output(target: Path, path: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    lexical_target: Path | None = None
    for candidate in (absolute, *absolute.parents):
        if not candidate.is_symlink() and candidate.resolve() == target:
            lexical_target = candidate
            break
    if lexical_target is None:
        raise TargetHashError(f"output must be inside target: {absolute}")
    try:
        absolute.resolve().relative_to(target)
    except ValueError as error:
        raise TargetHashError(
            f"output must be inside target: {absolute}"
        ) from error
    relative = absolute.relative_to(lexical_target)
    if not relative.parts:
        raise TargetHashError(f"output must be inside target: {absolute}")
    current = lexical_target
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise TargetHashError(
                f"output path must not contain a symbolic link: {current}"
            )
    return absolute


def write_manifest(
    target: Path,
    path: Path,
    manifest: dict[str, Any],
    force: bool,
) -> Path:
    output = normalize_output(target, path)
    if output.exists():
        if not force:
            raise TargetHashError(
                "target source manifest exists; pass --force to replace it"
            )
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            existing = None
        if (
            not isinstance(existing, dict)
            or existing.get("schema") != MANIFEST_SCHEMA
            or existing.get("generator") != GENERATOR
        ):
            raise TargetHashError(
                "refusing to replace an unowned target source manifest"
            )
        if existing.get("local_target_root") != str(target):
            raise TargetHashError(
                "refusing to replace a manifest owned by a different local target"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.hash-",
        dir=output.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def main() -> int:
    args = parse_args()
    try:
        target = normalize_target(args.target)
        requested_output = (
            normalize_output(target, args.output)
            if args.output is not None
            else None
        )
        manifest, manifest_hash = create_manifest(target)
        output = (
            write_manifest(target, requested_output, manifest, args.force)
            if requested_output is not None
            else None
        )
    except (OSError, TargetHashError) as error:
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
                "target": str(target),
                "file_count": len(manifest["files"]),
                "manifest_hash": manifest_hash,
                "output": str(output) if output is not None else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
