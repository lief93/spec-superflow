#!/usr/bin/env python3
"""Materialize manifest-approved static Android drawables into Harmony media resources."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


RESOURCE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
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


class MaterializeDrawablesError(RuntimeError):
    pass


def candidate_priority(asset_path: str, output_suffix: str) -> tuple[int, str]:
    source_suffix = PurePosixPath(asset_path).suffix.lower()
    if source_suffix == ".xml" and output_suffix == ".svg":
        return 0, asset_path
    if output_suffix == ".svg":
        return 1, asset_path
    return 2, asset_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy bitmap/SVG drawables and convert Android VectorDrawable XML assets "
            "from an AI-safe manifest into Harmony base/media resources."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--module", default="entry")
    parser.add_argument('--page-json', type=Path, help='Use the selected page asset SHA to disambiguate same-name module resources')
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        help="Optional Android drawable resource name to materialize. May be repeated.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    manifest_path = Path(os.path.abspath(os.path.expanduser(str(path)))).resolve()
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise MaterializeDrawablesError("safe-snapshot manifest is not a regular file")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MaterializeDrawablesError(f"safe-snapshot manifest is invalid: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != "android-to-harmony.safe-snapshot.v1":
        raise MaterializeDrawablesError("unsupported safe-snapshot manifest schema")
    assets = manifest.get("local_only_assets")
    if not isinstance(assets, list):
        raise MaterializeDrawablesError("safe-snapshot manifest local_only_assets must be a list")
    return manifest


def drawable_candidate(asset: dict[str, Any]) -> tuple[str, str, str] | None:
    path = asset.get("path")
    if not isinstance(path, str):
        return None
    parsed = PurePosixPath(path)
    parts = parsed.parts
    for index, part in enumerate(parts[:-2]):
        if part != "res":
            continue
        qualifier = parts[index + 1]
        if not qualifier.startswith(("drawable", "mipmap")):
            continue
        name = parsed.stem
        suffix = parsed.suffix.lower()
        if RESOURCE_NAME_PATTERN.fullmatch(name) is None:
            return None
        if suffix == ".xml":
            return path, name, ".svg"
        if suffix in IMAGE_SUFFIXES:
            return path, name, suffix
    return None


def run_tool(script: Path, arguments: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            payload.setdefault("ok", False)
            payload["exit_code"] = completed.returncode
            if completed.stderr.strip():
                payload["stderr"] = completed.stderr.strip()[:1000]
            return payload
        return {
            "ok": False,
            "exit_code": completed.returncode,
            "stderr": completed.stderr.strip()[:1000],
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return {
            "ok": False,
            "exit_code": completed.returncode,
            "stderr": f"tool did not return JSON: {error}",
        }
    return payload if isinstance(payload, dict) else {"ok": False, "stderr": "tool JSON was not an object"}


def page_asset_hashes(path: Path) -> dict[str, str]:
    result = {}
    def visit(node):
        asset = node.get('migration', {}).get('style', {}).get('asset', {})
        resource, digest = asset.get('resource'), asset.get('sha256')
        if isinstance(resource, str) and RESOURCE_NAME_PATTERN.fullmatch(resource) and digest:
            if resource in result and result[resource] != digest:
                raise MaterializeDrawablesError('same page uses different resources with the same name: ' + resource)
            result[resource] = digest
        for child in node.get('layers', []):
            visit(child)
    from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
    visit(unpack_lanhu_document(json.loads(path.read_text()))['artboard'])
    return result


def main() -> int:
    args = parse_args()
    try:
        manifest = load_manifest(args.manifest)
        selected_hashes = page_asset_hashes(args.page_json) if args.page_json else {}
        target = Path(os.path.abspath(os.path.expanduser(str(args.target)))).resolve()
        if target.is_symlink() or not target.is_dir():
            raise MaterializeDrawablesError("target must be an existing regular directory")
        selected_names = set(args.name)
        if any(RESOURCE_NAME_PATTERN.fullmatch(name) is None for name in selected_names):
            raise MaterializeDrawablesError("--name must be a valid lowercase Harmony resource name")

        script_root = Path(__file__).resolve().parent
        copy_script = script_root / "copy_local_asset.py"
        convert_script = script_root / "convert_android_vector.py"
        candidates_by_name: dict[str, list[tuple[str, str, str]]] = {}
        name_order: list[str] = []
        results: list[dict[str, Any]] = []
        skipped = 0
        for asset in manifest["local_only_assets"]:
            if not isinstance(asset, dict):
                skipped += 1
                continue
            candidate = drawable_candidate(asset)
            if candidate is None:
                skipped += 1
                continue
            asset_path, name, suffix = candidate
            if name in selected_hashes and asset.get('sha256') != selected_hashes[name]:
                continue
            if selected_names and name not in selected_names:
                skipped += 1
                continue
            if name not in candidates_by_name:
                candidates_by_name[name] = []
                name_order.append(name)
            candidates_by_name[name].append(candidate)

        for name in set(selected_hashes) & (selected_names or set(selected_hashes)):
            if name not in candidates_by_name:
                raise MaterializeDrawablesError('selected page asset SHA has no manifest candidate: ' + name)

        for name in name_order:
            name_candidates = sorted(
                candidates_by_name[name],
                key=lambda item: candidate_priority(item[0], item[2]),
            )
            materialized_name = False
            for asset_path, name, suffix in name_candidates:
                if materialized_name:
                    if suffix == ".svg" and PurePosixPath(asset_path).suffix.lower() == ".xml":
                        tool = convert_script
                    else:
                        tool = copy_script
                    results.append(
                        {
                            "name": name,
                            "asset_path": asset_path,
                            "destination": (
                                f"{args.module}/src/main/resources/base/media/{name}{suffix}"
                            ),
                            "tool": tool.name,
                            "ok": None,
                            "changed": None,
                            "skipped_as_alternative": True,
                            "reason": (
                                "another drawable or mipmap candidate with the same "
                                "resource name materialized successfully"
                            ),
                        }
                    )
                    continue
                destination = (
                    target / args.module / "src/main/resources/base/media" / f"{name}{suffix}"
                )
                if suffix == ".svg" and PurePosixPath(asset_path).suffix.lower() == ".xml":
                    tool = convert_script
                else:
                    tool = copy_script
                payload = run_tool(
                    tool,
                    [
                        "--manifest",
                        str(args.manifest),
                        "--asset-path",
                        asset_path,
                        "--target",
                        str(target),
                        "--destination",
                        str(destination),
                    ],
                )
                unsupported_xml = (
                    tool == convert_script
                    and payload.get("ok") is not True
                    and payload.get("error") == "approved XML asset is not an Android vector"
                )
                results.append(
                    {
                        "name": name,
                        "asset_path": asset_path,
                        "destination": (
                            f"{args.module}/src/main/resources/base/media/{name}{suffix}"
                        ),
                        "tool": tool.name,
                        "ok": None if unsupported_xml else payload.get("ok") is True,
                        "changed": payload.get("changed"),
                        "result": payload,
                        **(
                            {
                                "skipped_unsupported_xml": True,
                                "reason": (
                                    "approved XML drawable is not a VectorDrawable; "
                                    "no Harmony media resource was generated"
                                ),
                            }
                            if unsupported_xml
                            else {}
                        ),
                    }
                )
                if payload.get("ok") is True:
                    materialized_name = True

        successful_names = {item["name"] for item in results if item["ok"] is True}
        for item in results:
            if item["ok"] is True or item["name"] not in successful_names:
                continue
            if item.get("skipped_as_alternative") is True:
                continue
            item["accepted_as_alternative_failure"] = True
            item["reason"] = "another drawable or mipmap candidate with the same resource name materialized successfully"
        failures = [
            item
            for item in results
            if (
                item["ok"] is not True
                and item.get("accepted_as_alternative_failure") is not True
                and item.get("skipped_as_alternative") is not True
                and item.get("skipped_unsupported_xml") is not True
            )
        ]
        materialized_count = sum(1 for item in results if item["ok"] is True)
        alternative_failure_count = sum(
            1 for item in results if item.get("accepted_as_alternative_failure") is True
        )
        skipped_alternative_count = sum(
            1 for item in results if item.get("skipped_as_alternative") is True
        )
        skipped_unsupported_xml_count = sum(
            1 for item in results if item.get("skipped_unsupported_xml") is True
        )
        output = {
            "ok": not failures,
            "schema": "android-to-harmony.static-drawable-materialization.v1",
            "module": args.module,
            "materialized_count": materialized_count,
            "failed_count": len(failures),
            "skipped_count": (
                skipped
                + alternative_failure_count
                + skipped_alternative_count
                + skipped_unsupported_xml_count
            ),
            "results": results,
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 1 if failures else 0
    except MaterializeDrawablesError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
