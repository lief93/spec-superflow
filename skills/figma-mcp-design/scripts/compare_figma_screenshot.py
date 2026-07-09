#!/usr/bin/env python3
"""Compare Figma and implementation screenshots by design-coordinate boxes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
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


@dataclass(frozen=True)
class Measurement:
    left: float
    top: float
    right: float
    bottom: float
    width: float
    height: float


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


def dark_bbox(
    image: Image.Image,
    area: tuple[int, int, int, int],
    threshold: int,
    left_zone_px: int | None,
) -> tuple[int, int, int, int] | None:
    pix = image.load()
    x1, y1, x2, y2 = area
    if left_zone_px is not None:
        x2 = min(x2, x1 + left_zone_px)
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
) -> tuple[int, int, int, int] | None:
    pix = image.load()
    x1, y1, x2, y2 = area
    tr, tg, tb = color
    xs: list[int] = []
    ys: list[int] = []
    for y in range(max(0, y1), min(image.height, y2)):
        for x in range(max(0, x1), min(image.width, x2)):
            r, g, b = pix[x, y][:3]
            if abs(r - tr) <= tolerance and abs(g - tg) <= tolerance and abs(b - tb) <= tolerance:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def measure(
    bbox: tuple[int, int, int, int] | None,
    scale: float,
    area: tuple[int, int, int, int],
) -> Measurement | None:
    if bbox is None:
        return None
    x1, y1, x2, y2 = bbox
    ax1, ay1, ax2, ay2 = area
    return Measurement(
        left=(x1 - ax1) / scale,
        top=(y1 - ay1) / scale,
        right=(ax2 - x2) / scale,
        bottom=(ay2 - y2) / scale,
        width=(x2 - x1 + 1) / scale,
        height=(y2 - y1 + 1) / scale,
    )


def fmt_measure(value: Measurement | None) -> str:
    if value is None:
        return "none"
    return (
        f"left={value.left:.1f} top={value.top:.1f} "
        f"right={value.right:.1f} bottom={value.bottom:.1f} "
        f"w={value.width:.1f} h={value.height:.1f}"
    )


def fmt_delta(reference: Measurement | None, implementation: Measurement | None) -> str:
    if reference is None or implementation is None:
        return "delta unavailable"
    return (
        f"delta left={implementation.left - reference.left:+.1f} "
        f"top={implementation.top - reference.top:+.1f} "
        f"right={implementation.right - reference.right:+.1f} "
        f"bottom={implementation.bottom - reference.bottom:+.1f} "
        f"w={implementation.width - reference.width:+.1f} "
        f"h={implementation.height - reference.height:+.1f}"
    )


def image_scale(image: Image.Image, design_width: float) -> float:
    return image.width / design_width


def analyze_image(path: Path, design_width: float, box: Box, args) -> tuple[Measurement | None, Measurement | None]:
    image = Image.open(path).convert("RGBA")
    scale = image_scale(image, design_width)
    area = to_px(box, scale)
    left_zone_px = round(args.left_zone * scale) if args.left_zone else None
    dark = measure(dark_bbox(image, area, args.dark_threshold, left_zone_px), scale, area)
    colored = None
    if args.color:
        colored = measure(color_bbox(image, area, args.color, args.color_tolerance), scale, area)
    return dark, colored


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path, help="Figma screenshot")
    parser.add_argument("implementation", type=Path, help="App/browser screenshot")
    parser.add_argument("--box", action="append", type=parse_box, required=True, help="name=x,y,w,h in design units")
    parser.add_argument("--design-width", type=float, required=True, help="Reference node width in Figma units")
    parser.add_argument("--implementation-design-width", type=float, help="Override when implementation screenshot uses another design width")
    parser.add_argument("--dark-threshold", type=int, default=95)
    parser.add_argument("--left-zone", type=float, default=0.0, help="Limit dark-pixel search to left N design units")
    parser.add_argument("--color", type=parse_hex, help="Compare a specific RRGGBB fill color")
    parser.add_argument("--color-tolerance", type=int, default=3)
    args = parser.parse_args()

    ref = Image.open(args.reference)
    impl = Image.open(args.implementation)
    ref_scale = image_scale(ref, args.design_width)
    impl_width = args.implementation_design_width or args.design_width
    impl_scale = image_scale(impl, impl_width)
    print(f"reference={args.reference} size={ref.size} scale={ref_scale:.4g}px/unit")
    print(f"implementation={args.implementation} size={impl.size} scale={impl_scale:.4g}px/unit")

    for box in args.box:
        ref_dark, ref_color = analyze_image(args.reference, args.design_width, box, args)
        impl_dark, impl_color = analyze_image(args.implementation, impl_width, box, args)
        print(f"\n[{box.name}] box x={box.x:.1f} y={box.y:.1f} w={box.w:.1f} h={box.h:.1f}")
        print(f"  dark reference       {fmt_measure(ref_dark)}")
        print(f"  dark implementation {fmt_measure(impl_dark)}")
        print(f"  dark {fmt_delta(ref_dark, impl_dark)}")
        if args.color:
            print(f"  color reference       {fmt_measure(ref_color)}")
            print(f"  color implementation {fmt_measure(impl_color)}")
            print(f"  color {fmt_delta(ref_color, impl_color)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
