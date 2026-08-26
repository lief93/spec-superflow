#!/usr/bin/env python3
"""Copy one manifest-approved opaque asset locally without printing its bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


class AssetCopyError(RuntimeError):
    pass


IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".psd",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}
FONT_SUFFIXES = {
    ".otf",
    ".ttf",
}
TARGET_STATE_SCHEMA = "android-to-harmony.project-state.v1"
ASSET_LEDGER_SCHEMA = "android-to-harmony.asset-ledger.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hash-check and copy one opaque source asset into a target project."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--asset-path", required=True)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def absolute_without_final_symlink(path: Path, role: str) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise AssetCopyError(f"{role} must not be a symbolic link: {absolute}")
    return absolute.resolve()


def is_local_only_asset_path(path: Path) -> bool:
    if path.suffix.lower() in IMAGE_SUFFIXES | FONT_SUFFIXES:
        return True
    if path.suffix.lower() != ".xml":
        return False
    return any(
        part.startswith(("drawable", "mipmap"))
        for part in path.parts
    )


def load_asset(
    manifest_path: Path,
    requested_asset: str,
    *,
    allow_vector_xml: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    manifest_path = absolute_without_final_symlink(manifest_path, "manifest")
    if not manifest_path.is_file():
        raise AssetCopyError(f"safe-snapshot manifest does not exist: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AssetCopyError(f"invalid safe-snapshot manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise AssetCopyError("safe-snapshot manifest must be a JSON object")
    if manifest.get("schema") != "android-to-harmony.safe-snapshot.v1":
        raise AssetCopyError("unsupported safe-snapshot schema")

    snapshot_root_value = manifest.get("snapshot_root")
    source_root_value = manifest.get("source_root")
    assets = manifest.get("local_only_assets")
    if not isinstance(snapshot_root_value, str) or not isinstance(source_root_value, str):
        raise AssetCopyError("manifest source/snapshot roots are invalid")
    if not isinstance(assets, list):
        raise AssetCopyError("manifest local_only_assets must be a list")

    snapshot_root = Path(snapshot_root_value).expanduser().resolve()
    expected_manifest = snapshot_root / ".android-to-harmony-safe.json"
    if expected_manifest != manifest_path:
        raise AssetCopyError("manifest is not located at its recorded snapshot root")

    matches = [
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("path") == requested_asset
    ]
    if len(matches) != 1:
        raise AssetCopyError("asset path is not uniquely approved by the manifest")
    asset = matches[0]
    if not isinstance(asset.get("bytes"), int) or not isinstance(
        asset.get("sha256"), str
    ):
        raise AssetCopyError("approved asset metadata is invalid")

    relative = Path(requested_asset)
    if relative.is_absolute() or ".." in relative.parts:
        raise AssetCopyError("asset path must be a safe relative path")
    if not is_local_only_asset_path(relative):
        raise AssetCopyError("manifest entry is not an approved opaque asset path")
    if relative.suffix.lower() == ".xml" and not allow_vector_xml:
        raise AssetCopyError(
            "Android drawable/mipmap XML requires explicit HarmonyOS "
            "conversion and cannot be copied as an opaque media asset"
        )
    source_root = absolute_without_final_symlink(Path(source_root_value), "source root")
    source = source_root / relative
    if source.is_symlink() or not source.is_file():
        raise AssetCopyError("approved source asset is missing or is a symbolic link")
    resolved_source = source.resolve()
    if source_root not in resolved_source.parents:
        raise AssetCopyError("approved asset escapes the source root")
    if resolved_source.stat().st_size != asset["bytes"]:
        raise AssetCopyError("source asset size changed after snapshot creation")
    if sha256_file(resolved_source) != asset["sha256"]:
        raise AssetCopyError("source asset hash changed after snapshot creation")
    return resolved_source, source_root, asset


def validate_target_and_destination(
    target_path: Path,
    destination_path: Path,
    source_suffix: str = "",
) -> tuple[Path, Path, str]:
    target = absolute_without_final_symlink(target_path, "target")
    if not target.is_dir():
        raise AssetCopyError(f"target project does not exist: {target}")
    state_path = target / ".migration" / "state.json"
    if not state_path.is_file() or state_path.is_symlink():
        raise AssetCopyError("target project marker is missing")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise AssetCopyError(f"invalid target project marker: {error}") from error
    if (
        not isinstance(state, dict)
        or state.get("schema") != TARGET_STATE_SCHEMA
        or state.get("generator") != "migrate-android-compose-to-harmony"
    ):
        raise AssetCopyError("target project marker is invalid")
    recorded_output = state.get("output_root")
    if recorded_output != ".":
        if not isinstance(recorded_output, str):
            raise AssetCopyError("target project output marker is invalid")
        if absolute_without_final_symlink(
            Path(recorded_output),
            "recorded target",
        ) != target:
            raise AssetCopyError("target project output marker does not match")

    raw_destination = Path(
        os.path.abspath(os.path.expanduser(str(destination_path)))
    )
    if raw_destination.is_symlink():
        raise AssetCopyError(
            f"destination must not be a symbolic link: {raw_destination}"
        )
    current = raw_destination.parent
    while current != target and target in current.parents:
        if current.is_symlink():
            raise AssetCopyError(
                f"destination ancestor must not be a symbolic link: {current}"
            )
        current = current.parent
    destination = raw_destination.resolve()
    if target not in destination.parents:
        raise AssetCopyError("destination must be inside the target project")
    relative = destination.relative_to(target)
    is_font = source_suffix in FONT_SUFFIXES
    is_supported_resource_directory = (
        "resources" in relative.parts
        and (
            (is_font and "rawfile" in relative.parts)
            or (not is_font and destination.parent.name == "media")
        )
    )
    if not is_supported_resource_directory:
        raise AssetCopyError(
            "font destinations must be inside HarmonyOS resources/rawfile; "
            "other opaque assets must be inside a resources media directory"
        )
    return target, destination, relative.as_posix()


def load_asset_ledger(target: Path) -> tuple[Path, dict[str, Any]]:
    ledger_path = target / ".migration" / "assets.json"
    if not ledger_path.exists():
        return ledger_path, {
            "schema": ASSET_LEDGER_SCHEMA,
            "assets": {},
        }
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise AssetCopyError("asset ledger is not a regular file")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise AssetCopyError(f"invalid asset ledger: {error}") from error
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema") != ASSET_LEDGER_SCHEMA
        or not isinstance(ledger.get("assets"), dict)
    ):
        raise AssetCopyError("asset ledger has an unsupported schema")
    return ledger_path, ledger


def write_asset_ledger(path: Path, ledger: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.write-",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def copy_asset(
    source: Path,
    source_root: Path,
    asset: dict[str, Any],
    destination: Path,
    destination_relative: str,
    ledger: dict[str, Any],
    force: bool,
) -> tuple[Path, bool]:
    if destination.exists() and destination.is_dir():
        raise AssetCopyError(f"destination is a directory: {destination}")
    assets = ledger["assets"]
    previous = assets.get(destination_relative)
    if previous is not None and not isinstance(previous, dict):
        raise AssetCopyError("asset ledger entry is invalid")
    if destination.exists():
        if not destination.is_file() or previous is None:
            raise AssetCopyError("refusing to replace an unowned destination")
        previous_hash = previous.get("destination_sha256")
        if (
            not isinstance(previous_hash, str)
            or sha256_file(destination) != previous_hash
        ):
            raise AssetCopyError(
                "refusing to replace a destination changed after its recorded copy"
            )
        if (
            previous.get("asset_path") == asset.get("path")
            and previous_hash == asset.get("sha256")
            and destination.stat().st_size == asset.get("bytes")
        ):
            return destination, False
        if not force:
            raise AssetCopyError(
                "destination contains a different owned asset; "
                "pass --force to replace it"
            )
    if source.suffix.lower() != destination.suffix.lower():
        raise AssetCopyError("destination must preserve the approved asset extension")
    if source.parent == destination.parent and source.name == destination.name:
        raise AssetCopyError("source and destination must be different files")
    if (
        destination == source_root or source_root in destination.parents
    ):
        raise AssetCopyError("destination must be outside the Android source")

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.copy-",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        if temporary.stat().st_size != asset["bytes"]:
            raise AssetCopyError("copied asset size does not match the manifest")
        if sha256_file(temporary) != asset["sha256"]:
            raise AssetCopyError("copied asset hash does not match the manifest")
        os.replace(temporary, destination)
        assets[destination_relative] = {
            "asset_path": asset["path"],
            "bytes": asset["bytes"],
            "destination_sha256": asset["sha256"],
        }
        return destination, True
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    args = parse_args()
    try:
        source, source_root, asset = load_asset(args.manifest, args.asset_path)
        target, destination_path, destination_relative = (
            validate_target_and_destination(
                args.target,
                args.destination,
                source.suffix.lower(),
            )
        )
        ledger_path, ledger = load_asset_ledger(target)
        destination, changed = copy_asset(
            source,
            source_root,
            asset,
            destination_path,
            destination_relative,
            ledger,
            args.force,
        )
        if changed:
            write_asset_ledger(ledger_path, ledger)
    except (AssetCopyError, OSError) as error:
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
                "asset_path": args.asset_path,
                "destination": destination_relative,
                "bytes": asset["bytes"],
                "sha256": asset["sha256"],
                "changed": changed,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
