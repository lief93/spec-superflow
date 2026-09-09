from __future__ import annotations
import hashlib
import json
import re
from typing import Any


SOURCE_PAGE_SCHEMA = "android-to-harmony.source-page-spec.v1"


PAGE_SCHEMA = "android-to-harmony.page-snapshot.v2"


RUNTIME_SOURCE_MAP_SCHEMA = "android-to-harmony.runtime-source-map.v1"


SOURCE_COMPONENT_TREE_SCHEMA = "android-to-harmony.source-component-tree.v2"


BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


STRING_RESOURCE_PATTERN = re.compile(r"(?:stringResource\s*\(\s*)?(?:id\s*=\s*)?R\.string\.([A-Za-z0-9_]+)")


DRAWABLE_RESOURCE_PATTERN = re.compile(r"R\.(?:drawable|mipmap)\.([A-Za-z0-9_]+)")


HEX_COLOR_PATTERN = re.compile(r"(?:Color\s*\(\s*)?(0x[0-9A-Fa-f]{8}|#[0-9A-Fa-f]{6,8})")


QUOTED_STRING_PATTERN = re.compile(r'^"((?:[^"\\]|\\.)*)"$')


MATERIAL3_TYPOGRAPHY: dict[str, tuple[float, float, int]] = {
    "displayLarge": (57.0, 64.0, 400),
    "displayMedium": (45.0, 52.0, 400),
    "displaySmall": (36.0, 44.0, 400),
    "headlineLarge": (32.0, 40.0, 400),
    "headlineMedium": (28.0, 36.0, 400),
    "headlineSmall": (24.0, 32.0, 400),
    "titleLarge": (22.0, 28.0, 400),
    "titleMedium": (16.0, 24.0, 500),
    "titleSmall": (14.0, 20.0, 500),
    "bodyLarge": (16.0, 24.0, 400),
    "bodyMedium": (14.0, 20.0, 400),
    "bodySmall": (12.0, 16.0, 400),
    "labelLarge": (14.0, 20.0, 500),
    "labelMedium": (12.0, 16.0, 500),
    "labelSmall": (11.0, 16.0, 500),
}


def material3_text_metrics(role):
    tracking = {'displayLarge': -0.25, 'titleMedium': 0.15, 'titleSmall': 0.1,
                'bodyLarge': 0.5, 'bodyMedium': 0.25, 'bodySmall': 0.4,
                'labelLarge': 0.1, 'labelMedium': 0.5, 'labelSmall': 0.5}
    return {'include_font_padding': False, 'line_height_alignment': 'center',
            'line_height_trim': 'none', 'letter_spacing_sp': tracking.get(role, 0)}


SOURCE_LAYOUT_PRIMITIVES = {
    "Box",
    "BoxWithConstraints",
    "Column",
    "ConstraintLayout",
    "FlowColumn",
    "FlowRow",
    "LazyColumn",
    "LazyHorizontalGrid",
    "LazyRow",
    "LazyVerticalGrid",
    "ListItem",
    "Row",
    "Scaffold",
    "Spacer",
    "Surface",
}


COMPOSE_FRAMEWORK_PREFIXES = (
    "androidx.compose.",
    "androidx.constraintlayout.compose.",
)


PLATFORM_COMPONENT_IMPORT_MARKERS = (
    ".viewinterop.",
    ".interop.",
)


class RealPageError(RuntimeError):
    pass


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
