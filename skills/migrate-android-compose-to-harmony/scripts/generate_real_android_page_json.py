#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from init_harmony_project import load_contract, sha256_file
from page_snapshot import png_dimensions
from real_page_pipeline import (
    RealPageError,
    build_runtime_page_snapshot,
    build_source_page_spec,
    apply_screenshot_visual_facts,
    load_runtime_source_map_file,
    parse_uiautomator_xml,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a real Android page and generate source, runtime, and coverage JSON artifacts."
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--root-source", required=True)
    parser.add_argument("--root-composable", required=True)
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--state-id", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--runtime-source-map", type=Path)
    parser.add_argument("--serial")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--uiautomator-xml", type=Path)
    parser.add_argument("--density", type=float)
    parser.add_argument("--font-scale", type=float)
    parser.add_argument("--insets-px")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def run(command: list[str], binary: bool = False) -> bytes | str:
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip() or completed.stdout.decode("utf-8", "replace").strip()
        raise RealPageError(f"command failed ({completed.returncode}): {' '.join(command)}: {detail}")
    return completed.stdout if binary else completed.stdout.decode("utf-8", "replace").strip()


def adb_command(adb: str, serial: str, *arguments: str) -> list[str]:
    return [adb, "-s", serial, *arguments]


def android_capture_commands(adb: str, serial: str, remote_layout: str) -> list[list[str]]:
    return [
        adb_command(adb, serial, "shell", "rm", "-f", remote_layout),
        adb_command(adb, serial, "shell", "uiautomator", "dump", remote_layout),
        adb_command(adb, serial, "exec-out", "screencap", "-p"),
        adb_command(adb, serial, "exec-out", "cat", remote_layout),
    ]


def parse_insets(value: str) -> dict[str, int]:
    try:
        numbers = [int(item) for item in value.split(",")]
    except ValueError as error:
        raise RealPageError("--insets-px must contain left,top,right,bottom integers") from error
    if len(numbers) != 4 or any(item < 0 for item in numbers):
        raise RealPageError("--insets-px must contain four non-negative integers")
    return dict(zip(("left", "top", "right", "bottom"), numbers, strict=True))


def device_insets(adb: str, serial: str, dimensions: tuple[int, int]) -> dict[str, int]:
    output = str(run(adb_command(adb, serial, "shell", "dumpsys", "window")))
    result = {"left": 0, "top": 0, "right": 0, "bottom": 0}
    for kind, left, top, right, bottom in re.findall(
        r"InsetsSource type=(?:ITYPE_|TYPE_)(STATUS_BAR|NAVIGATION_BAR|TOP_BAR|SIDE_BAR_1) frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\] visible=true",
        output,
    ):
        x1, y1, x2, y2 = map(int, (left, top, right, bottom))
        if kind in {"STATUS_BAR", "TOP_BAR"} and y1 == 0 and x1 == 0 and x2 == dimensions[0]:
            result["top"] = max(result["top"], y2)
        elif kind in {"NAVIGATION_BAR", "SIDE_BAR_1"} and y2 == dimensions[1] and x1 == 0 and x2 == dimensions[0]:
            result["bottom"] = max(result["bottom"], dimensions[1] - y1)
        elif kind == "NAVIGATION_BAR" and x1 == 0 and y1 == 0 and y2 == dimensions[1]:
            result["left"] = max(result["left"], x2)
        elif kind == "NAVIGATION_BAR" and x2 == dimensions[0] and y1 == 0 and y2 == dimensions[1]:
            result["right"] = max(result["right"], dimensions[0] - x1)
    return result


def atomic_json(path: Path, value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(encoded, encoding="utf-8")


def main() -> int:
    args = parse_args()
    output = Path(os.path.abspath(os.path.expanduser(str(args.output_dir))))
    try:
        if output.exists() or output.is_symlink():
            raise RealPageError("output directory must not already exist")
        if bool(args.serial) == bool(args.screenshot or args.uiautomator_xml):
            raise RealPageError("use either --serial capture or both --screenshot and --uiautomator-xml")
        if not args.serial and (args.screenshot is None or args.uiautomator_xml is None):
            raise RealPageError("offline mode requires both --screenshot and --uiautomator-xml")
        contract, contract_path = load_contract(args.contract)
        if contract is None or contract_path is None:
            raise RealPageError("migration contract is required")
        output.mkdir(parents=True)
        screenshot_path = output / "screenshot.png"
        xml_path = output / "uiautomator.xml"
        device: dict[str, str] = {}
        capture_start = time.perf_counter()
        density = args.density
        font_scale = args.font_scale
        if args.serial:
            serial = args.serial
            state = run(adb_command(args.adb, serial, "get-state"))
            if state != "device":
                raise RealPageError(f"Android target is not ready: {state}")
            capture_commands = android_capture_commands(
                args.adb, serial, "/sdcard/android-to-harmony-window.xml"
            )
            run(capture_commands[0])
            run(capture_commands[1])
            screenshot_path.write_bytes(run(capture_commands[2], binary=True))
            xml_path.write_bytes(run(capture_commands[3], binary=True))
            model = str(run(adb_command(args.adb, serial, "shell", "getprop", "ro.product.model")))
            sdk = str(run(adb_command(args.adb, serial, "shell", "getprop", "ro.build.version.sdk")))
            device = {"id": serial, "model": model, "os_version": sdk}
            if density is None:
                density_text = str(run(adb_command(args.adb, serial, "shell", "wm", "density")))
                density_value = next(
                    (line.rsplit(":", 1)[-1].strip() for line in reversed(density_text.splitlines()) if ":" in line),
                    "",
                )
                density = float(density_value) / 160.0
            if font_scale is None:
                raw_font_scale = str(run(adb_command(args.adb, serial, "shell", "settings", "get", "system", "font_scale")))
                font_scale = float(raw_font_scale) if raw_font_scale not in {"", "null"} else 1.0
        else:
            source_screenshot = Path(os.path.abspath(os.path.expanduser(str(args.screenshot))))
            source_xml = Path(os.path.abspath(os.path.expanduser(str(args.uiautomator_xml))))
            if not source_screenshot.is_file() or not source_xml.is_file():
                raise RealPageError("offline screenshot and UIAutomator XML must exist")
            shutil.copyfile(source_screenshot, screenshot_path)
            shutil.copyfile(source_xml, xml_path)
            if density is None:
                raise RealPageError("offline mode requires --density")
            font_scale = font_scale or 1.0
        capture_ms = (time.perf_counter() - capture_start) * 1000
        dimensions = png_dimensions(screenshot_path)
        insets = (
            parse_insets(args.insets_px)
            if args.insets_px is not None
            else device_insets(args.adb, args.serial, dimensions)
            if args.serial
            else {"left": 0, "top": 0, "right": 0, "bottom": 0}
        )
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
        runtime_tree_bytes = xml_path.read_bytes()
        runtime_tree_sha256 = hashlib.sha256(runtime_tree_bytes).hexdigest()
        runtime_components = parse_uiautomator_xml(runtime_tree_bytes, dimensions, args.package)
        runtime_ms = (time.perf_counter() - runtime_start) * 1000
        if not runtime_components:
            raise RealPageError("UIAutomator tree contains no visible nodes for the requested package")
        runtime_source_map, runtime_source_map_sha256 = load_runtime_source_map_file(args.runtime_source_map)
        pixel_sampling = apply_screenshot_visual_facts(
            screenshot_path, runtime_components, float(density), float(font_scale)
        )
        merge_start = time.perf_counter()
        snapshot, metrics = build_runtime_page_snapshot(
            source_spec=source_spec,
            runtime_components=runtime_components,
            screenshot_path=screenshot_path,
            screenshot_sha256=hashlib.sha256(screenshot_path.read_bytes()).hexdigest(),
            screenshot_byte_count=screenshot_path.stat().st_size,
            dimensions=dimensions,
            density=float(density),
            font_scale=float(font_scale),
            insets_px=insets,
            device=device,
            timings_ms={
                "capture": capture_ms,
                "source": source_ms,
                "runtime_tree": runtime_ms,
                "merge": (time.perf_counter() - merge_start) * 1000,
            },
            runtime_source_map=runtime_source_map,
            runtime_source_map_sha256=runtime_source_map_sha256,
            runtime_tree_sha256=runtime_tree_sha256,
        )
        atomic_json(output / "source-page.json", source_spec)
        atomic_json(output / "page.json", snapshot)
        metrics["pixel_sampling"] = pixel_sampling
        atomic_json(output / "metrics.json", metrics)
        atomic_json(
            output / "runtime-tree.json",
            {
                "schema": "android-to-harmony.runtime-tree.v1",
                "platform": "android",
                "screenshot_sha256": snapshot["capture"]["screenshot"]["sha256"],
                "runtime_tree_sha256": runtime_tree_sha256,
                "components": runtime_components,
            },
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "verdict": metrics["verdict"],
                    "output_dir": str(output),
                    "source_call_count": metrics["source"]["call_count"],
                    "runtime_component_count": metrics["runtime"]["component_count"],
                    "visible_primitive_mapping_ratio": metrics["source"]["primitive_mapping_ratio"],
                    "total_ms": metrics["timings_ms"]["total"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, TypeError, RealPageError) as error:
        if output.is_dir() and not any(output.iterdir()):
            output.rmdir()
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
