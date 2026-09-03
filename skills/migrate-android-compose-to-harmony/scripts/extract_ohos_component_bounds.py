#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


MARKER = "OHOS_COMPONENT_BOUNDS:"
COMPONENT_SCHEMA = "android-to-harmony.component-bounds.v1"
COMPONENT_SCHEMA_V2 = "android-to-harmony.component-bounds.v2"
COMMAND_SCHEMA = "android-to-harmony.command-result.v1"
MAX_INPUT_BYTES = 5 * 1024 * 1024
SAFE_TOKEN = re.compile(r"[A-Za-z0-9._:/#@-]{1,120}")


class ExtractionError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one sanitized HarmonyOS UITest component-bounds inventory from stdin."
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def require_token(value: Any, field: str) -> str:
    if not isinstance(value, str) or SAFE_TOKEN.fullmatch(value) is None:
        raise ExtractionError(
            f"component {field} must use 1 to 120 non-sensitive identifier characters"
        )
    return value


def validate_inventory(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ExtractionError("component inventory has unsupported root fields")
    schema = payload.get("schema")
    expected_fields = {"schema", "screenshot_dimensions", "components"}
    if schema == COMPONENT_SCHEMA_V2:
        expected_fields.add("content_insets_px")
    elif schema != COMPONENT_SCHEMA:
        raise ExtractionError("component inventory schema is unsupported")
    if set(payload) != expected_fields:
        raise ExtractionError("component inventory has unsupported root fields")
    dimensions = payload["screenshot_dimensions"]
    if not isinstance(dimensions, dict) or set(dimensions) != {"width", "height"}:
        raise ExtractionError("component inventory dimensions are malformed")
    if (
        type(dimensions["width"]) is not int
        or type(dimensions["height"]) is not int
        or dimensions["width"] <= 0
        or dimensions["height"] <= 0
    ):
        raise ExtractionError("component inventory dimensions must be positive integers")
    if schema == COMPONENT_SCHEMA_V2:
        insets = payload["content_insets_px"]
        fields = {"left", "top", "right", "bottom"}
        if (
            not isinstance(insets, dict)
            or set(insets) != fields
            or any(type(insets[field]) is not int or insets[field] < 0 for field in fields)
            or insets["left"] + insets["right"] >= dimensions["width"]
            or insets["top"] + insets["bottom"] >= dimensions["height"]
        ):
            raise ExtractionError("component inventory content insets are malformed")
    components = payload["components"]
    if not isinstance(components, list) or len(components) > 10000:
        raise ExtractionError("component inventory must contain at most 10000 components")
    component_ids: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise ExtractionError("component inventory contains a non-object component")
        if not {"id", "type", "bounds"}.issubset(component) or not set(component).issubset(
            {"id", "type", "semantic_key", "bounds"}
        ):
            raise ExtractionError("component inventory contains unsupported component fields")
        component_id = require_token(component["id"], "id")
        require_token(component["type"], "type")
        if "semantic_key" in component:
            require_token(component["semantic_key"], "semantic_key")
        if component_id in component_ids:
            raise ExtractionError("component inventory contains a duplicate component id")
        component_ids.add(component_id)
        bounds = component["bounds"]
        if not isinstance(bounds, dict) or set(bounds) != {"x", "y", "width", "height"}:
            raise ExtractionError("component bounds are malformed")
        if any(type(bounds[field]) is not int for field in ("x", "y", "width", "height")):
            raise ExtractionError("component bounds must be integers")
        if bounds["x"] < 0 or bounds["y"] < 0 or bounds["width"] <= 0 or bounds["height"] <= 0:
            raise ExtractionError("component bounds must be positive and non-negative")
        if (
            bounds["x"] + bounds["width"] > dimensions["width"]
            or bounds["y"] + bounds["height"] > dimensions["height"]
        ):
            raise ExtractionError("component bounds exceed screenshot dimensions")
    return payload


def extract(log: str) -> dict[str, Any]:
    candidates = [line.partition(MARKER)[2] for line in log.splitlines() if MARKER in line]
    if len(candidates) != 1:
        raise ExtractionError(
            f"expected exactly one {MARKER} record; found {len(candidates)}"
        )
    try:
        payload = json.loads(candidates[0])
    except json.JSONDecodeError as error:
        raise ExtractionError("component inventory marker does not contain valid JSON") from error
    return validate_inventory(payload)


def write_inventory(output_argument: Path, payload: dict[str, Any]) -> dict[str, Any]:
    output = Path(os.path.abspath(os.path.expanduser(str(output_argument))))
    if output.exists() or output.is_symlink():
        raise ExtractionError("output already exists")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ExtractionError("output parent must be an existing non-symbolic-link directory")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with output.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "ok": True,
        "schema": COMMAND_SCHEMA,
        "output": output.name,
        "sha256": digest,
        "component_count": len(payload["components"]),
    }


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        print(
            json.dumps({"ok": False, "schema": COMMAND_SCHEMA, "error": "input exceeds 5 MiB"}),
            file=sys.stderr,
        )
        return 1
    try:
        log = raw.decode("utf-8")
        result = write_inventory(parse_args().output, extract(log))
    except UnicodeDecodeError:
        print(
            json.dumps({"ok": False, "schema": COMMAND_SCHEMA, "error": "input is not UTF-8"}),
            file=sys.stderr,
        )
        return 1
    except ExtractionError as error:
        print(
            json.dumps({"ok": False, "schema": COMMAND_SCHEMA, "error": str(error)}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
