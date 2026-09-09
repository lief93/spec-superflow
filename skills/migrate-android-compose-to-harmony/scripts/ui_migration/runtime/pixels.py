from __future__ import annotations
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from ui_migration.frontend.model import RealPageError


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return max(abs(left[index] - right[index]) for index in range(3))


def detect_text_field_surface(
    crop: Any,
    dominant: tuple[int, int, int],
    density: float,
) -> dict[str, Any] | None:
    pixels = crop.load()
    row_counts = [
        sum(color_distance(pixels[x, y], dominant) >= 8 for x in range(crop.width))
        for y in range(crop.height)
    ]
    horizontal_threshold = max(4, round(crop.width * 0.45))
    horizontal_edges = [
        index for index, count in enumerate(row_counts) if count >= horizontal_threshold
    ]
    if len(horizontal_edges) < 2:
        return None
    top = horizontal_edges[0]
    bottom = horizontal_edges[-1]
    surface_height = bottom - top + 1
    if surface_height < 8:
        return None
    column_counts = [
        sum(color_distance(pixels[x, y], dominant) >= 8 for y in range(top, bottom + 1))
        for x in range(crop.width)
    ]
    vertical_threshold = max(4, round(surface_height * 0.45))
    vertical_edges = [
        index for index, count in enumerate(column_counts) if count >= vertical_threshold
    ]
    if len(vertical_edges) < 2:
        return None
    left = vertical_edges[0]
    right = vertical_edges[-1]
    surface_width = right - left + 1
    if surface_width < crop.width * 0.5:
        return None

    edge_pixels = []
    for x in range(left, right + 1):
        edge_pixels.extend((pixels[x, top], pixels[x, bottom]))
    for y in range(top, bottom + 1):
        edge_pixels.extend((pixels[left, y], pixels[right, y]))
    border_colors = Counter(
        color for color in edge_pixels if color_distance(color, dominant) >= 8
    )
    if not border_colors:
        return None
    border_color, _count = border_colors.most_common(1)[0]

    border_width_px = 1
    while border_width_px < min(8, surface_height // 2):
        sample_y = top + border_width_px
        matching = sum(
            color_distance(pixels[x, sample_y], border_color) <= 3
            for x in range(left, right + 1)
        )
        if matching < surface_width * 0.45:
            break
        border_width_px += 1

    inner_left = min(right, left + border_width_px + 1)
    inner_top = min(bottom, top + border_width_px + 1)
    inner_right = max(inner_left + 1, right - border_width_px)
    inner_bottom = max(inner_top + 1, bottom - border_width_px)
    inner = crop.crop((inner_left, inner_top, inner_right, inner_bottom))
    inner_data = inner.get_flattened_data() if hasattr(inner, "get_flattened_data") else inner.getdata()
    background, _background_count = Counter(inner_data).most_common(1)[0]

    foreground_points = [
        (x, y)
        for y in range(top + border_width_px, bottom - border_width_px + 1)
        for x in range(left + border_width_px, right - border_width_px + 1)
        if color_distance(pixels[x, y], background) >= 32
        and color_distance(pixels[x, y], border_color) >= 16
    ]
    content_padding_dp = None
    if len(foreground_points) >= 5:
        content_left = min(x for x, _y in foreground_points)
        horizontal = round((content_left - left) / density, 3)
        if horizontal >= 0:
            content_padding_dp = {
                "left": horizontal,
                "right": horizontal,
                "top": 0.0,
                "bottom": 0.0,
            }

    top_edge_x = [
        x for x in range(left, right + 1)
        if color_distance(pixels[x, top], border_color) <= 3
    ]
    radius_px = min(top_edge_x) - left if top_edge_x else 0
    radius_dp = round(radius_px / density, 3)
    return {
        "bounds_px": {
            "x": left,
            "y": top,
            "width": surface_width,
            "height": surface_height,
        },
        "background": "#FF" + "".join(f"{channel:02X}" for channel in background),
        "border": {
            "width_dp": round(border_width_px / density, 3),
            "color": "#FF" + "".join(f"{channel:02X}" for channel in border_color),
            "style": "solid",
        },
        "corner_radius_dp": {
            "top_left": radius_dp,
            "top_right": radius_dp,
            "bottom_right": radius_dp,
            "bottom_left": radius_dp,
        },
        "content_padding_dp": content_padding_dp,
    }


def apply_screenshot_visual_facts(
    screenshot_path: Path,
    runtime_components: list[dict[str, Any]],
    density: float,
    font_scale: float,
) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as error:
        raise RealPageError(
            "Pillow is unavailable in the current Python interpreter "
            f"({sys.executable}); run this high-fidelity capture with an interpreter "
            "where `import PIL` succeeds"
        ) from error
    image = Image.open(screenshot_path).convert("RGB")
    runtime_by_id = {component["id"]: component for component in runtime_components}
    sampled = 0

    def inherits_parent_pixels(
        component: dict[str, Any], dominant: tuple[int, int, int]
    ) -> bool:
        parent = runtime_by_id.get(component.get("parent_id", ""))
        parent_bounds = parent.get("bounds_px") if isinstance(parent, dict) else None
        bounds = component["bounds_px"]
        if not isinstance(parent_bounds, dict):
            return False
        child_left = bounds["x"]
        child_top = bounds["y"]
        child_right = child_left + bounds["width"]
        child_bottom = child_top + bounds["height"]
        parent_left = parent_bounds["x"]
        parent_top = parent_bounds["y"]
        parent_right = parent_left + parent_bounds["width"]
        parent_bottom = parent_top + parent_bounds["height"]
        if (
            child_left < parent_left
            or child_top < parent_top
            or child_right > parent_right
            or child_bottom > parent_bottom
        ):
            return False
        sample_points: set[tuple[int, int]] = set()
        step_x = max(1, bounds["width"] // 12)
        step_y = max(1, bounds["height"] // 12)
        if child_top > parent_top:
            sample_points.update(
                (x, child_top - 1)
                for x in range(child_left, child_right, step_x)
            )
        if child_bottom < parent_bottom:
            sample_points.update(
                (x, child_bottom)
                for x in range(child_left, child_right, step_x)
            )
        if child_left > parent_left:
            sample_points.update(
                (child_left - 1, y)
                for y in range(child_top, child_bottom, step_y)
            )
        if child_right < parent_right:
            sample_points.update(
                (child_right, y)
                for y in range(child_top, child_bottom, step_y)
            )
        if len(sample_points) < 4:
            return False
        matching = sum(
            color_distance(image.getpixel(point), dominant) <= 8
            for point in sample_points
        )
        return matching / len(sample_points) >= 0.8

    for component in runtime_components:
        component_type = component["type"]
        if component_type not in {
            "Text", "TextField", "Button", "View", "FrameLayout", "LinearLayout", "RelativeLayout",
            "ConstraintLayout", "root", "Stack", "Column", "Row", "Flex", "Grid",
            "List", "Scroll", "Scroller", "Refresh", "RelativeContainer", "Surface",
            "Card", "Box",
        }:
            continue
        bounds = component["bounds_px"]
        crop = image.crop(
            (
                bounds["x"],
                bounds["y"],
                bounds["x"] + bounds["width"],
                bounds["y"] + bounds["height"],
            )
        )
        pixel_data = (
            crop.get_flattened_data()
            if hasattr(crop, "get_flattened_data")
            else crop.getdata()
        )
        colors = Counter(pixel_data).most_common(24)
        if not colors:
            continue
        dominant, dominant_count = colors[0]
        pixel_paths: list[str] = []
        if component_type == "Text":
            minimum_count = max(5, int(bounds["width"] * bounds["height"] * 0.001))
            foreground = next(
                (
                    color
                    for color, count in colors[1:]
                    if count >= minimum_count and color_distance(color, dominant) >= 24
                ),
                None,
            )
            if foreground is not None:
                component["style"]["typography"]["color"] = "#FF" + "".join(f"{channel:02X}" for channel in foreground)
                pixel_paths.append("style.typography.color")
        elif component_type == "TextField":
            surface = detect_text_field_surface(crop, dominant, density)
            if surface is not None:
                local_bounds = surface["bounds_px"]
                visual_bounds_px = {
                    "x": bounds["x"] + local_bounds["x"],
                    "y": bounds["y"] + local_bounds["y"],
                    "width": local_bounds["width"],
                    "height": local_bounds["height"],
                }
                component["visual_bounds_px"] = visual_bounds_px
                component["visual_bounds_dp"] = {
                    name: round(value / density, 3)
                    for name, value in visual_bounds_px.items()
                }
                component["style"]["surface"]["background"] = {
                    "type": "solid",
                    "color": surface["background"],
                }
                component["style"]["surface"]["border"] = surface["border"]
                component["style"]["surface"]["corner_radius_dp"] = surface["corner_radius_dp"]
                if surface["content_padding_dp"] is not None:
                    component["style"]["layout"]["padding_dp"] = surface["content_padding_dp"]
                pixel_paths.extend((
                    "style.surface.background",
                    "style.surface.border",
                    "style.surface.corner_radius_dp",
                ))
                if surface["content_padding_dp"] is not None:
                    pixel_paths.append("style.layout.padding_dp")
        elif (
            component_type == "Button" or component["style"]["state"].get("clickable") is True
        ) and dominant_count > bounds["width"] * bounds["height"] * 0.25:
            component["style"]["surface"]["background"] = {
                "type": "solid",
                "color": "#FF" + "".join(f"{channel:02X}" for channel in dominant),
            }
            matching_pixels: list[tuple[int, int]] = []
            pixels = crop.load()
            for y in range(crop.height):
                for x in range(crop.width):
                    if color_distance(pixels[x, y], dominant) <= 3:
                        matching_pixels.append((x, y))
            if matching_pixels:
                min_x = min(x for x, _ in matching_pixels)
                max_x = max(x for x, _ in matching_pixels)
                min_y = min(y for _, y in matching_pixels)
                max_y = max(y for _, y in matching_pixels)
                top_x = [x for x, y in matching_pixels if y == min_y]
                bottom_x = [x for x, y in matching_pixels if y == max_y]
                left_y = [y for x, y in matching_pixels if x == min_x]
                right_y = [y for x, y in matching_pixels if x == max_x]
                top_left = round(((min(top_x) - min_x) + (min(left_y) - min_y)) / 2 / density, 3)
                top_right = round(((max_x - max(top_x)) + (min(right_y) - min_y)) / 2 / density, 3)
                bottom_right = round(((max_x - max(bottom_x)) + (max_y - max(right_y))) / 2 / density, 3)
                bottom_left = round(((min(bottom_x) - min_x) + (max_y - max(left_y))) / 2 / density, 3)
                component["style"]["surface"]["corner_radius_dp"] = {
                    "top_left": top_left,
                    "top_right": top_right,
                    "bottom_right": bottom_right,
                    "bottom_left": bottom_left,
                }
                pixel_paths.append("style.surface.corner_radius_dp")
            border_band = min(8, max(1, min(crop.width, crop.height) // 8))
            border_pixels = [
                pixels[x, y]
                for y in range(crop.height)
                for x in range(crop.width)
                if (
                    x < border_band
                    or y < border_band
                    or x >= crop.width - border_band
                    or y >= crop.height - border_band
                )
                and color_distance(pixels[x, y], dominant) >= 24
            ]
            border_area = max(
                1,
                2 * border_band * (crop.width + crop.height - 2 * border_band),
            )
            if len(border_pixels) / border_area >= 0.05:
                border_color, _border_count = Counter(border_pixels).most_common(1)[0]
                top_flags = [
                    any(
                        color_distance(pixels[x, y], border_color) <= 8
                        for y in range(border_band)
                    )
                    for x in range(crop.width)
                ]
                run_count = 0
                in_run = False
                for flag in top_flags:
                    if flag and not in_run:
                        run_count += 1
                    in_run = flag
                border_style = "dashed" if run_count >= 3 else "solid"
                component["style"]["surface"]["border"] = {
                    "width_dp": round(max(1, min(3, border_band // 2)) / density, 3),
                    "color": "#FF" + "".join(f"{channel:02X}" for channel in border_color),
                    "style": border_style,
                    **({"dash_dp": [4.0, 4.0]} if border_style == "dashed" else {}),
                }
                pixel_paths.append("style.surface.border")
                if border_style == "dashed":
                    component["style"]["surface"]["corner_radius_dp"] = {
                        "top_left": 10.0,
                        "top_right": 10.0,
                        "bottom_right": 10.0,
                        "bottom_left": 10.0,
                    }
                    pixel_paths.append("style.surface.corner_radius_dp")
            shadow_pad = min(24, bounds["x"], bounds["y"], image.width - bounds["x"] - bounds["width"], image.height - bounds["y"] - bounds["height"])
            if shadow_pad >= 4 and bounds["width"] >= image.width * 0.5:
                outer = image.crop((
                    bounds["x"] - shadow_pad,
                    bounds["y"] - shadow_pad,
                    bounds["x"] + bounds["width"] + shadow_pad,
                    bounds["y"] + bounds["height"] + shadow_pad,
                ))
                outer_pixels = outer.load()
                shadow_ring = [
                    outer_pixels[x, y]
                    for y in range(outer.height)
                    for x in range(outer.width)
                    if (
                        x < shadow_pad
                        or y < shadow_pad
                        or x >= outer.width - shadow_pad
                        or y >= outer.height - shadow_pad
                    )
                ]
                darker_fraction = sum(
                    sum(pixel) / 3 < 248 for pixel in shadow_ring
                ) / max(1, len(shadow_ring))
                if darker_fraction >= 0.2:
                    component["style"]["surface"]["shadows"] = [{
                        "color": "#1A000000",
                        "offset_x_dp": 0.0,
                        "offset_y_dp": 4.0,
                        "blur_radius_dp": 12.0,
                        "spread_radius_dp": 0.0,
                    }]
                    pixel_paths.append("style.surface.shadows")
                    sampled_radius = component["style"]["surface"].get("corner_radius_dp")
                    if isinstance(sampled_radius, dict):
                        radius = max(float(value) for value in sampled_radius.values())
                        component["style"]["surface"]["corner_radius_dp"] = {
                            edge: radius
                            for edge in ("top_left", "top_right", "bottom_right", "bottom_left")
                        }
            pixel_paths.append("style.surface.background")
        elif (
            dominant_count > bounds["width"] * bounds["height"] * 0.25
            and not inherits_parent_pixels(component, dominant)
        ):
            component["style"]["surface"]["background"] = {
                "type": "solid",
                "color": "#FF" + "".join(f"{channel:02X}" for channel in dominant),
            }
            pixel_paths.append("style.surface.background")
            parent = runtime_by_id.get(component.get("parent_id", ""))
            parent_bounds = parent.get("bounds_px") if isinstance(parent, dict) else None
            if (
                isinstance(parent_bounds, dict)
                and bounds["x"] == parent_bounds["x"]
                and bounds["width"] == parent_bounds["width"]
            ):
                sample_x = sorted({
                    bounds["x"],
                    bounds["x"] + bounds["width"] // 4,
                    bounds["x"] + bounds["width"] // 2,
                    bounds["x"] + (bounds["width"] * 3) // 4,
                    bounds["x"] + bounds["width"] - 1,
                })

                def row_matches(row: int) -> bool:
                    return sum(
                        color_distance(image.getpixel((x, row)), dominant) <= 8
                        for x in sample_x
                    ) >= max(1, len(sample_x) - 2)

                top = bounds["y"]
                bottom = bounds["y"] + bounds["height"]
                while top > parent_bounds["y"] and row_matches(top - 1):
                    top -= 1
                parent_bottom = parent_bounds["y"] + parent_bounds["height"]
                while bottom < parent_bottom and row_matches(bottom):
                    bottom += 1
                if top != bounds["y"] or bottom != bounds["y"] + bounds["height"]:
                    component["visual_bounds_px"] = {
                        "x": bounds["x"],
                        "y": top,
                        "width": bounds["width"],
                        "height": bottom - top,
                    }
                    component["visual_bounds_dp"] = {
                        name: round(value / density, 3)
                        for name, value in component["visual_bounds_px"].items()
                    }
        if pixel_paths:
            component["pixel_provenance_paths"] = pixel_paths
            sampled += 1
    return {
        "available": True,
        "method": "component-bounded exact-color frequency and contrast sampling",
        "sampled_component_count": sampled,
    }


def screenshot_surface_regions(
    screenshot_path: Path,
    dimensions: tuple[int, int],
    density: float,
) -> list[dict[str, Any]]:
    """Find large screenshot-proven surfaces omitted by the runtime tree.

    Accessibility trees often flatten a project Card into its text/control
    descendants.  This detector retains only long, centered, solid-color runs;
    source-component ownership is established separately before a region enters
    the page snapshot.
    """
    from PIL import Image, ImageChops

    image = Image.open(screenshot_path).convert("RGB")
    width, height = dimensions
    if image.size != dimensions:
        raise RealPageError("screenshot dimensions changed during surface analysis")
    pixels = image.load()
    pixel_data = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
    common_colors = [
        color
        for color, count in Counter(pixel_data).most_common(12)
        if count >= width * height * 0.01
    ]
    minimum_run = round(width * 0.5)
    maximum_run = round(width * 0.95)
    maximum_gap = round(80 * density)
    boundary_tolerance = round(width * 0.1)
    candidates: list[dict[str, Any]] = []

    for color in common_colors:
        difference = ImageChops.difference(
            image, Image.new("RGB", image.size, color)
        )
        channel_masks = [
            channel.point([255, 255, 255] + [0] * 253)
            for channel in difference.split()
        ]
        color_mask = ImageChops.multiply(
            ImageChops.multiply(channel_masks[0], channel_masks[1]),
            channel_masks[2],
        ).tobytes()
        groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for y in range(height):
            row = color_mask[y * width:(y + 1) * width]
            best = max(
                re.finditer(b"\xff+", row),
                key=lambda match: match.end() - match.start(),
                default=None,
            )
            best_left = best.start() if best is not None else 0
            best_right = best.end() if best is not None else 0
            run_width = best_right - best_left
            centered = abs((best_left + best_right) / 2 - width / 2) <= width * 0.12
            bounded = best_left >= width * 0.02 and best_right <= width * 0.98
            edge_anchor = (
                "left"
                if best_left <= width * 0.02 and run_width >= minimum_run
                else "right"
                if best_right >= width * 0.98 and run_width >= minimum_run
                else None
            )
            qualifies = (
                minimum_run <= run_width <= maximum_run and centered and bounded
            ) or edge_anchor is not None
            if not qualifies:
                continue
            if (
                current is None
                or y - current["last_y"] > maximum_gap
                or edge_anchor != current["edge_anchor"]
                or abs(best_left - current["reference_left"]) > boundary_tolerance
                or abs(best_right - current["reference_right"]) > boundary_tolerance
            ):
                if current is not None:
                    groups.append(current)
                current = {
                    "first_y": y,
                    "last_y": y,
                    "left": best_left,
                    "right": best_right,
                    "reference_left": best_left,
                    "reference_right": best_right,
                    "first_left": best_left,
                    "qualified_rows": 1,
                    "edge_anchor": edge_anchor,
                }
            else:
                current["last_y"] = y
                current["left"] = min(current["left"], best_left)
                current["right"] = max(current["right"], best_right)
                current["qualified_rows"] += 1
                if current["qualified_rows"] == 8:
                    current["reference_left"] = best_left
                    current["reference_right"] = best_right
        if current is not None:
            groups.append(current)

        for group in groups:
            region_height = group["last_y"] - group["first_y"] + 1
            region_width = group["right"] - group["left"]
            if region_height < round(40 * density) or group["qualified_rows"] < round(8 * density):
                continue
            radius = max(
                0.0,
                min(24.0, round(2 * max(0, group["first_left"] - group["left"]) / density, 3)),
            )
            candidate = {
                "bounds_px": {
                    "x": group["left"],
                    "y": group["first_y"],
                    "width": region_width,
                    "height": region_height,
                },
                "background": "#FF" + "".join(f"{channel:02X}" for channel in color),
                "corner_radius_dp": radius,
                "qualified_rows": group["qualified_rows"],
            }
            if group["edge_anchor"] is not None:
                candidate["edge_anchor"] = group["edge_anchor"]
            candidates.append(candidate)

    def intersection_over_union(left: dict[str, int], right: dict[str, int]) -> float:
        left_x2, left_y2 = left["x"] + left["width"], left["y"] + left["height"]
        right_x2, right_y2 = right["x"] + right["width"], right["y"] + right["height"]
        intersection = max(0, min(left_x2, right_x2) - max(left["x"], right["x"])) * max(
            0, min(left_y2, right_y2) - max(left["y"], right["y"])
        )
        union = left["width"] * left["height"] + right["width"] * right["height"] - intersection
        return intersection / union if union else 0.0

    def refine_vertical_bounds(candidate: dict[str, Any]) -> None:
        bounds = candidate["bounds_px"]
        color = tuple(
            int(candidate["background"][index:index + 2], 16)
            for index in (3, 5, 7)
        )
        search_pad = round(64 * density)
        search_top = max(0, bounds["y"] - search_pad)
        search_bottom = min(height, bounds["y"] + bounds["height"] + search_pad)
        candidate_top = bounds["y"]
        candidate_bottom = bounds["y"] + bounds["height"]
        candidate_height = bounds["height"]
        segments: list[tuple[int, int, int]] = []
        maximum_internal_gap = max(2, round(4 * density))
        probe_fractions = (
            (0.01, 0.05, 0.1, 0.25, 0.4)
            if candidate.get("edge_anchor") == "left"
            else (0.6, 0.75, 0.9, 0.95, 0.99)
            if candidate.get("edge_anchor") == "right"
            else (0.25, 0.4, 0.5, 0.6, 0.75)
        )
        for fraction in probe_fractions:
            probe_x = bounds["x"] + round(bounds["width"] * fraction)
            start: int | None = None
            last_match: int | None = None
            for row in range(search_top, search_bottom + 1):
                matches = (
                    row < search_bottom
                    and color_distance(pixels[probe_x, row], color) <= 2
                )
                if matches and start is None:
                    start = row
                    last_match = row
                elif matches:
                    last_match = row
                elif (
                    start is not None
                    and last_match is not None
                    and row - last_match > maximum_internal_gap
                ):
                    end = last_match + 1
                    overlap = max(0, min(end, candidate_bottom) - max(start, candidate_top))
                    if (
                        overlap >= candidate_height * 0.6
                        and end - start >= candidate_height * 0.75
                        and end - start <= candidate_height + round(64 * density)
                    ):
                        segments.append((start, end, overlap))
                    start = None
                    last_match = None
        if not segments:
            return
        refined_top, refined_bottom, _ = max(
            segments,
            key=lambda segment: (
                segment[2],
                segment[1] - segment[0],
                -abs(segment[0] - candidate_top),
            ),
        )
        bounds["y"] = refined_top
        bounds["height"] = refined_bottom - refined_top
        inset_x = max(1, round(bounds["width"] * 0.1))
        inset_y = max(1, round(bounds["height"] * 0.1))
        interior = image.crop((
            bounds["x"] + inset_x,
            bounds["y"] + inset_y,
            bounds["x"] + bounds["width"] - inset_x,
            bounds["y"] + bounds["height"] - inset_y,
        ))
        interior_pixels = (
            interior.get_flattened_data()
            if hasattr(interior, "get_flattened_data")
            else interior.getdata()
        )
        interior_color, _ = Counter(interior_pixels).most_common(1)[0]
        candidate["background"] = "#FF" + "".join(
            f"{channel:02X}" for channel in interior_color
        )

    for candidate in candidates:
        refine_vertical_bounds(candidate)

    deduplicated: list[dict[str, Any]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            -item["qualified_rows"],
            -(item["bounds_px"]["width"] * item["bounds_px"]["height"]),
        ),
    ):
        if any(
            intersection_over_union(candidate["bounds_px"], existing["bounds_px"]) >= 0.75
            for existing in deduplicated
        ):
            continue
        deduplicated.append(candidate)
    return deduplicated
