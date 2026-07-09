#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def frame_dp(node, scale):
    frame = node.get("frame") or node.get("realFrame") or {}
    x_key = "x" if "x" in frame else "left"
    y_key = "y" if "y" in frame else "top"
    keys = (x_key, y_key, "width", "height")
    if not all(k in frame for k in keys):
        return ""
    vals = [frame[k] / scale for k in keys]
    return "x={:.1f} y={:.1f} w={:.1f} h={:.1f}".format(*vals)


def text_value(node):
    for key in ("text", "characters", "content", "value"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", "\\n")
    return ""


def style_bits(node):
    style = node.get("style") or {}
    bits = []
    for key in ("fontSize", "fontWeight", "color", "backgroundColor", "radius"):
        value = style.get(key, node.get(key))
        if value not in (None, "", []):
            bits.append(f"{key}={value}")
    return " ".join(bits)


def walk(node, scale, depth=0):
    if node.get("visible") is False:
        return
    name = node.get("name") or ""
    typ = node.get("type") or ""
    frame = frame_dp(node, scale)
    text = text_value(node)
    style = style_bits(node)
    if frame or text:
        indent = "  " * depth
        suffix = " | ".join(part for part in (frame, f"text={text}" if text else "", style) if part)
        print(f"{indent}{typ} {name} | {suffix}")
    for child in node.get("layers") or node.get("children") or []:
        if isinstance(child, dict):
            walk(child, scale, depth + 1)


def main():
    if len(sys.argv) != 2:
        print("usage: summarize_lanhu_json.py <version_json.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    scale = float((data.get("meta") or {}).get("sliceScale") or 1)
    artboard = data.get("artboard") or {}
    print(f"# {path}")
    print(f"device={(data.get('meta') or {}).get('device')} scale={scale}")
    print(f"artboard {frame_dp(artboard, scale)} name={artboard.get('name', '')}")
    walk(artboard, scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
