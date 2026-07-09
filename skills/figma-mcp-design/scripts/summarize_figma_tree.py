#!/usr/bin/env python3
"""Summarize raw Figma node/tree JSON into implementation facts.

The script is intentionally deterministic: it does not infer UI semantics or
generate code. It normalizes coordinates relative to the target root node and
prints only the fields that are useful for implementation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FRAME_KEYS = (
    "absoluteBoundingBox",
    "absoluteRenderBounds",
    "boundingBox",
    "bounds",
    "frame",
    "realFrame",
)
CHILD_KEYS = ("children", "layers")
TEXT_KEYS = ("characters", "text", "content", "value")
VECTOR_TYPES = {"VECTOR", "BOOLEAN_OPERATION", "STAR", "LINE", "REGULAR_POLYGON"}


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


def parse_box(raw: str) -> Box:
    parts = [float(part) for part in raw.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--within must be x,y,w,h")
    return Box(*parts)


def load_jsonish(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        start = min(
            [idx for idx in (text.find("{"), text.find("[")) if idx >= 0],
            default=-1,
        )
        if start < 0:
            raise
        data, _ = decoder.raw_decode(text[start:])
        return data


def unwrap_root(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return {"type": "ROOT", "name": "list-root", "children": data}
    if not isinstance(data, dict):
        raise SystemExit("Input must be a JSON object or array.")

    for key in ("node", "document", "artboard", "root"):
        value = data.get(key)
        if isinstance(value, dict):
            return value

    nodes = data.get("nodes")
    if isinstance(nodes, dict) and nodes:
        first = next(iter(nodes.values()))
        if isinstance(first, dict):
            document = first.get("document")
            if isinstance(document, dict):
                return document
            return first
    if isinstance(nodes, list):
        return {"type": "ROOT", "name": "nodes-root", "children": nodes}

    return data


def frame_for(node: dict[str, Any]) -> Box | None:
    for key in FRAME_KEYS:
        frame = node.get(key)
        box = box_from_mapping(frame)
        if box:
            return box
    return box_from_mapping(node)


def box_from_mapping(value: Any) -> Box | None:
    if not isinstance(value, dict):
        return None
    x = value.get("x", value.get("left"))
    y = value.get("y", value.get("top"))
    w = value.get("width", value.get("w"))
    h = value.get("height", value.get("h"))
    if None in (x, y, w, h):
        return None
    try:
        return Box(float(x), float(y), float(w), float(h))
    except (TypeError, ValueError):
        return None


def children_of(node: dict[str, Any]) -> list[dict[str, Any]]:
    for key in CHILD_KEYS:
        children = node.get(key)
        if isinstance(children, list):
            return [child for child in children if isinstance(child, dict)]
    return []


def text_value(node: dict[str, Any]) -> str:
    for key in TEXT_KEYS:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", "\\n")
    return ""


def color_to_hex(color: dict[str, Any], opacity: float | None = None) -> str:
    r = round(float(color.get("r", 0)) * 255)
    g = round(float(color.get("g", 0)) * 255)
    b = round(float(color.get("b", 0)) * 255)
    a = color.get("a", opacity)
    base = f"#{r:02X}{g:02X}{b:02X}"
    if a is not None and float(a) < 0.999:
        return f"{base}@{float(a):.2f}"
    return base


def paint_summary(node: dict[str, Any], key: str) -> str:
    paints = node.get(key)
    if not isinstance(paints, list):
        return ""
    values: list[str] = []
    for paint in paints:
        if not isinstance(paint, dict) or paint.get("visible") is False:
            continue
        paint_type = paint.get("type")
        if paint_type == "SOLID" and isinstance(paint.get("color"), dict):
            values.append(color_to_hex(paint["color"], paint.get("opacity")))
        elif paint_type:
            values.append(str(paint_type))
    return ",".join(values[:3])


def style_bits(node: dict[str, Any]) -> str:
    style = node.get("style") if isinstance(node.get("style"), dict) else {}
    bits: list[str] = []

    font_parts = []
    for key in ("fontFamily", "fontPostScriptName"):
        value = style.get(key, node.get(key))
        if value:
            font_parts.append(str(value))
            break
    for key in ("fontSize", "fontWeight"):
        value = style.get(key, node.get(key))
        if value not in (None, ""):
            font_parts.append(str(value))
    line = style.get("lineHeightPx", style.get("lineHeightPercent", node.get("lineHeight")))
    if line not in (None, ""):
        font_parts.append(f"line={line}")
    if font_parts:
        bits.append("font=" + "/".join(font_parts))

    fills = paint_summary(node, "fills")
    if fills:
        bits.append(f"fills={fills}")
    strokes = paint_summary(node, "strokes")
    if strokes:
        bits.append(f"strokes={strokes}")

    for key in ("cornerRadius", "rectangleCornerRadii", "opacity"):
        value = node.get(key)
        if value not in (None, "", []):
            bits.append(f"{key}={value}")

    layout = node.get("layoutMode")
    if layout:
        layout_bits = [str(layout)]
        for key in (
            "primaryAxisAlignItems",
            "counterAxisAlignItems",
            "itemSpacing",
            "paddingLeft",
            "paddingRight",
            "paddingTop",
            "paddingBottom",
        ):
            value = node.get(key)
            if value not in (None, ""):
                layout_bits.append(f"{key}={value}")
        bits.append("layout=" + " ".join(layout_bits))

    return " ".join(bits)


def intersects(a: Box, b: Box) -> bool:
    return a.x < b.right and a.right > b.x and a.y < b.bottom and a.bottom > b.y


def is_visible(node: dict[str, Any], include_hidden: bool) -> bool:
    if include_hidden:
        return True
    if node.get("visible") is False:
        return False
    if node.get("opacity") == 0:
        return False
    return True


def root_origin(root: dict[str, Any]) -> tuple[float, float]:
    frame = frame_for(root)
    if frame:
        return frame.x, frame.y
    return 0.0, 0.0


def fmt_num(value: float) -> str:
    if abs(value - round(value)) < 0.01:
        return str(int(round(value)))
    return f"{value:.1f}"


def summarize(
    node: dict[str, Any],
    args: argparse.Namespace,
    origin: tuple[float, float],
    depth: int = 0,
    parent_vector: bool = False,
) -> None:
    if depth > args.max_depth:
        return
    if not is_visible(node, args.include_hidden):
        return

    node_type = str(node.get("type") or node.get("nodeType") or "")
    if args.types and node_type not in args.types:
        should_print = False
    else:
        should_print = True

    frame = frame_for(node)
    rel_box = None
    if frame:
        rel_box = Box(frame.x - origin[0], frame.y - origin[1], frame.w, frame.h)
        if (rel_box.w < args.min_size or rel_box.h < args.min_size) and not text_value(node):
            should_print = False
        if args.within and not intersects(rel_box, args.within):
            should_print = False

    text = text_value(node)
    if should_print and (rel_box or text):
        parts: list[str] = []
        if rel_box:
            parts.append(
                "x={} y={} w={} h={}".format(
                    fmt_num(rel_box.x),
                    fmt_num(rel_box.y),
                    fmt_num(rel_box.w),
                    fmt_num(rel_box.h),
                )
            )
        if text:
            parts.append(f"text={text}")
        style = style_bits(node)
        if style:
            parts.append(style)
        node_id = node.get("id")
        name = str(node.get("name") or "")
        label = " ".join(part for part in (node_type, name, f"id={node_id}" if node_id else "") if part)
        print(f"{'  ' * depth}{label} | {' | '.join(parts)}")

    is_vector = node_type in VECTOR_TYPES
    if args.hide_vector_children and (parent_vector or is_vector):
        return
    for child in children_of(node):
        summarize(child, args, origin, depth + 1, is_vector)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--max-depth", type=int, default=12)
    parser.add_argument("--min-size", type=float, default=0.0)
    parser.add_argument("--within", type=parse_box, help="Only print nodes intersecting x,y,w,h relative to root")
    parser.add_argument("--types", help="Comma-separated Figma node types to print")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--hide-vector-children", action="store_true")
    args = parser.parse_args()
    args.types = set(part.strip() for part in args.types.split(",")) if args.types else None

    data = load_jsonish(args.json_file)
    root = unwrap_root(data)
    origin = root_origin(root)
    root_frame = frame_for(root)

    print(f"# {args.json_file}")
    print(
        "root type={} name={} id={} origin={},{} size={}".format(
            root.get("type", ""),
            root.get("name", ""),
            root.get("id", ""),
            fmt_num(origin[0]),
            fmt_num(origin[1]),
            f"{fmt_num(root_frame.w)}x{fmt_num(root_frame.h)}" if root_frame else "unknown",
        )
    )
    summarize(root, args, origin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
