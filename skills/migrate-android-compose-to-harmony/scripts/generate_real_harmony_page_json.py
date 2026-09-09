#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from init_harmony_project import load_contract, sha256_file
from page_snapshot import png_dimensions
from real_page_pipeline import (
    RealPageError,
    apply_screenshot_visual_facts,
    build_runtime_page_snapshot,
    build_source_page_spec,
    load_runtime_source_map_file,
    parse_harmony_layout_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a real OpenHarmony page and generate source, runtime, and coverage JSON artifacts."
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--root-source", required=True)
    parser.add_argument("--root-composable", required=True)
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--state-id", required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--runtime-source-map", type=Path)
    parser.add_argument("--bundle")
    parser.add_argument("--serial")
    parser.add_argument("--hdc", default="hdc")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--uitest-layout", type=Path)
    parser.add_argument("--density", required=True, type=float)
    parser.add_argument("--font-scale", type=float, default=1.0)
    parser.add_argument("--insets-px")
    parser.add_argument("--device-model")
    parser.add_argument("--os-version")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def run(command: list[str], binary: bool = False) -> bytes | str:
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip() or completed.stdout.decode("utf-8", "replace").strip()
        raise RealPageError(f"command failed ({completed.returncode}): {' '.join(command)}: {detail}")
    return completed.stdout if binary else completed.stdout.decode("utf-8", "replace").strip()


def hdc_command(hdc: str, serial: str, *arguments: str) -> list[str]:
    return [hdc, "-t", serial, *arguments]


def harmony_capture_commands(
    hdc: str,
    serial: str,
    remote_screenshot: str,
    remote_layout: str,
    screenshot_path: Path,
    layout_path: Path,
) -> list[list[str]]:
    return [
        hdc_command(hdc, serial, "shell", "rm", "-f", remote_screenshot, remote_layout),
        hdc_command(hdc, serial, "shell", "uitest", "dumpLayout", "-p", remote_layout),
        hdc_command(hdc, serial, "shell", "uitest", "screenCap", "-p", remote_screenshot),
        hdc_command(hdc, serial, "file", "recv", remote_screenshot, str(screenshot_path)),
        hdc_command(hdc, serial, "file", "recv", remote_layout, str(layout_path)),
    ]


def parse_insets(value: str | None) -> dict[str, int]:
    if value is None:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0}
    try:
        numbers = [int(item) for item in value.split(",")]
    except ValueError as error:
        raise RealPageError("--insets-px must contain left,top,right,bottom integers") from error
    if len(numbers) != 4 or any(item < 0 for item in numbers):
        raise RealPageError("--insets-px must contain four non-negative integers")
    return dict(zip(("left", "top", "right", "bottom"), numbers, strict=True))


def atomic_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def query_device(hdc: str, serial: str, argument: str, fallback: str) -> str:
    try:
        value = str(run(hdc_command(hdc, serial, "shell", "param", "get", argument))).strip()
    except RealPageError:
        return fallback
    return value if value and value != "null" else fallback


def main() -> int:
    args = parse_args()
    output = Path(os.path.abspath(os.path.expanduser(str(args.output_dir))))
    try:
        if output.exists() or output.is_symlink():
            raise RealPageError("output directory must not already exist")
        if args.density <= 0 or args.font_scale <= 0:
            raise RealPageError("density and font scale must be greater than zero")
        if bool(args.serial) == bool(args.screenshot or args.uitest_layout):
            raise RealPageError("use either --serial capture or both --screenshot and --uitest-layout")
        if not args.serial and (args.screenshot is None or args.uitest_layout is None):
            raise RealPageError("offline mode requires both --screenshot and --uitest-layout")
        contract, contract_path = load_contract(args.contract)
        if contract is None or contract_path is None:
            raise RealPageError("migration contract is required")
        output.mkdir(parents=True)
        screenshot_path = output / "screenshot.png"
        layout_path = output / "uitest-layout.json"
        capture_start = time.perf_counter()
        device: dict[str, str] = {}
        if args.serial:
            targets = str(run([args.hdc, "list", "targets"])).splitlines()
            if args.serial not in {line.strip() for line in targets}:
                raise RealPageError(f"OpenHarmony target is not ready: {args.serial}")
            remote_screenshot = "/data/local/tmp/android-to-harmony-screen.png"
            remote_layout = "/data/local/tmp/android-to-harmony-layout.json"
            for command in harmony_capture_commands(
                args.hdc,
                args.serial,
                remote_screenshot,
                remote_layout,
                screenshot_path,
                layout_path,
            ):
                run(command)
            device = {
                "id": args.serial,
                "model": args.device_model or query_device(args.hdc, args.serial, "const.product.model", "unknown"),
                "os_version": args.os_version or query_device(args.hdc, args.serial, "const.ohos.fullname", "OpenHarmony"),
            }
        else:
            source_screenshot = Path(os.path.abspath(os.path.expanduser(str(args.screenshot))))
            source_layout = Path(os.path.abspath(os.path.expanduser(str(args.uitest_layout))))
            if not source_screenshot.is_file() or not source_layout.is_file():
                raise RealPageError("offline screenshot and uitest layout must exist")
            shutil.copyfile(source_screenshot, screenshot_path)
            shutil.copyfile(source_layout, layout_path)
            device = {
                key: value
                for key, value in {
                    "id": args.serial,
                    "model": args.device_model,
                    "os_version": args.os_version,
                }.items()
                if value
            }
        capture_ms = (time.perf_counter() - capture_start) * 1000
        dimensions = png_dimensions(screenshot_path)
        insets = parse_insets(args.insets_px)
        source_start = time.perf_counter()
        source_spec = build_source_page_spec(
            contract,
            args.root_source,
            args.root_composable,
            args.page_id,
            args.state_id,
            sha256_file(contract_path),
            Path(os.path.abspath(os.path.expanduser(str(args.source_root)))) if args.source_root else None,
        )
        source_ms = (time.perf_counter() - source_start) * 1000
        runtime_start = time.perf_counter()
        runtime_tree_bytes = layout_path.read_bytes()
        runtime_tree_sha256 = hashlib.sha256(runtime_tree_bytes).hexdigest()
        runtime_components = parse_harmony_layout_json(runtime_tree_bytes, dimensions, args.bundle)
        runtime_ms = (time.perf_counter() - runtime_start) * 1000
        if not runtime_components:
            raise RealPageError("OpenHarmony uitest layout contains no visible runtime nodes")
        runtime_source_map, runtime_source_map_sha256 = load_runtime_source_map_file(args.runtime_source_map)
        pixel_sampling = apply_screenshot_visual_facts(
            screenshot_path, runtime_components, float(args.density), float(args.font_scale)
        )
        merge_start = time.perf_counter()
        snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source_spec,
            runtime_components=runtime_components,
            screenshot_path=screenshot_path,
            screenshot_sha256=hashlib.sha256(screenshot_path.read_bytes()).hexdigest(),
            screenshot_byte_count=screenshot_path.stat().st_size,
            dimensions=dimensions,
            density=float(args.density),
            font_scale=float(args.font_scale),
            insets_px=insets,
            device=device,
            timings_ms={
                "capture": capture_ms,
                "source": source_ms,
                "runtime_tree": runtime_ms,
                "merge": (time.perf_counter() - merge_start) * 1000,
            },
            platform="harmony",
            runtime_origin="OpenHarmony uitest dumpLayout from bound capture",
            runtime_source_map=runtime_source_map,
            runtime_source_map_sha256=runtime_source_map_sha256,
            runtime_tree_sha256=runtime_tree_sha256,
        )
        metrics["pixel_sampling"] = pixel_sampling
        metrics["capture_binding"] = {
            "screenshot_sha256": snapshot["capture"]["screenshot"]["sha256"],
            "uitest_layout_sha256": hashlib.sha256(layout_path.read_bytes()).hexdigest(),
        }
        from ui_migration.contracts.source_storage import pack_source_page
        atomic_json(output / "source-page.json", pack_source_page(source_spec))
        atomic_json(output / "runtime-tree.json", {
            "schema": "android-to-harmony.runtime-tree.v1",
            "platform": "harmony",
            "screenshot_sha256": snapshot["capture"]["screenshot"]["sha256"],
            "uitest_layout_sha256": metrics["capture_binding"]["uitest_layout_sha256"],
            "runtime_tree_sha256": runtime_tree_sha256,
            "components": runtime_components,
        })
        atomic_json(output / "page.json", snapshot)
        atomic_json(output / "metrics.json", metrics)
        print(json.dumps({
            "ok": True,
            "verdict": metrics["verdict"],
            "output_dir": str(output),
            "source_call_count": metrics["source"]["call_count"],
            "runtime_component_count": metrics["runtime"]["component_count"],
            "visible_primitive_mapping_ratio": metrics["source"]["primitive_mapping_ratio"],
            "runtime_semantic_mapping_ratio": metrics["runtime"]["semantic_mapping_ratio"],
            "total_ms": metrics["timings_ms"]["total"],
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, RealPageError) as error:
        if output.is_dir() and not any(output.iterdir()):
            output.rmdir()
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
