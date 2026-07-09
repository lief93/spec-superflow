#!/usr/bin/env python3
"""Compare Lanhu artboard and device screenshots in dp coordinates."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "Pillow is required. Use a temporary venv, for example:\n"
        "python3 -m venv /tmp/codex-pillow-venv && "
        "/tmp/codex-pillow-venv/bin/pip install Pillow"
    ) from exc


@dataclass(frozen=True)
class Box:
    name: str
    x: float
    y: float
    w: float
    h: float


def parse_box(raw: str) -> Box:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("box must be name=x,y,w,h")
    name, values = raw.split("=", 1)
    parts = [float(part) for part in values.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("box must be name=x,y,w,h")
    return Box(name, *parts)


def parse_hex(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("color must be RRGGBB")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def to_px(box: Box, scale: float) -> tuple[int, int, int, int]:
    x1 = round(box.x * scale)
    y1 = round(box.y * scale)
    x2 = round((box.x + box.w) * scale)
    y2 = round((box.y + box.h) * scale)
    return x1, y1, x2, y2


def dark_bbox(image: Image.Image, area: tuple[int, int, int, int], threshold: int, left_zone: int | None):
    pix = image.load()
    x1, y1, x2, y2 = area
    if left_zone is not None:
        x2 = min(x2, x1 + left_zone)
    xs: list[int] = []
    ys: list[int] = []
    for y in range(max(0, y1), min(image.height, y2)):
        for x in range(max(0, x1), min(image.width, x2)):
            r, g, b = pix[x, y][:3]
            if r < threshold and g < threshold and b < threshold:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def color_bbox(
    image: Image.Image,
    area: tuple[int, int, int, int],
    color: tuple[int, int, int],
    tolerance: int,
):
    pix = image.load()
    x1, y1, x2, y2 = area
    xs: list[int] = []
    ys: list[int] = []
    tr, tg, tb = color
    for y in range(max(0, y1), min(image.height, y2)):
        for x in range(max(0, x1), min(image.width, x2)):
            r, g, b = pix[x, y][:3]
            if abs(r - tr) <= tolerance and abs(g - tg) <= tolerance and abs(b - tb) <= tolerance:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def fmt_bbox(bbox, scale: float, origin: tuple[int, int]):
    if bbox is None:
        return "none"
    x1, y1, x2, y2 = bbox
    ox, oy = origin
    return (
        f"x={x1 / scale:.1f}-{x2 / scale:.1f}dp "
        f"y={y1 / scale:.1f}-{y2 / scale:.1f}dp "
        f"relLeft={(x1 - ox) / scale:.1f}dp "
        f"relTop={(y1 - oy) / scale:.1f}dp "
        f"relRight={(origin[0] + 0 - x2) / scale:.1f}dp"
    )


def compare_image(label: str, path: Path, boxes: list[Box], args) -> None:
    image = Image.open(path).convert("RGBA")
    scale = image.width / args.design_width
    print(f"\n== {label}: {path} size={image.size} scale={scale:.4g}px/dp")
    for box in boxes:
        area = to_px(box, scale)
        x1, y1, x2, y2 = area
        print(f"[{box.name}] box x={box.x:.1f} y={box.y:.1f} w={box.w:.1f} h={box.h:.1f}dp")
        left_zone = round(args.left_zone * scale) if args.left_zone else None
        dark = dark_bbox(image, area, args.dark_threshold, left_zone)
        if dark:
            dx1, dy1, dx2, dy2 = dark
            print(
                "  dark "
                f"x={dx1 / scale:.1f}-{dx2 / scale:.1f}dp "
                f"y={dy1 / scale:.1f}-{dy2 / scale:.1f}dp "
                f"left={(dx1 - x1) / scale:.1f}dp "
                f"top={(dy1 - y1) / scale:.1f}dp "
                f"right={(x2 - dx2) / scale:.1f}dp "
                f"bottom={(y2 - dy2) / scale:.1f}dp"
            )
        else:
            print("  dark none")
        if args.color:
            colored = color_bbox(image, area, args.color, args.color_tolerance)
            if colored:
                cx1, cy1, cx2, cy2 = colored
                print(
                    "  color "
                    f"x={cx1 / scale:.1f}-{cx2 / scale:.1f}dp "
                    f"y={cy1 / scale:.1f}-{cy2 / scale:.1f}dp "
                    f"w={(cx2 - cx1 + 1) / scale:.1f}dp "
                    f"h={(cy2 - cy1 + 1) / scale:.1f}dp"
                )
            else:
                print("  color none")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artboard", type=Path)
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--box", action="append", type=parse_box, required=True, help="name=x,y,w,h in dp")
    parser.add_argument("--design-width", type=float, default=360.0)
    parser.add_argument("--dark-threshold", type=int, default=95)
    parser.add_argument("--left-zone", type=float, default=0.0, help="limit dark-pixel search to left N dp")
    parser.add_argument("--color", type=parse_hex)
    parser.add_argument("--color-tolerance", type=int, default=3)
    args = parser.parse_args()

    compare_image("design", args.artboard, args.box, args)
    compare_image("screenshot", args.screenshot, args.box, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
