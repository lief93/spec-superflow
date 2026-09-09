from __future__ import annotations
import re
from decimal import Decimal
from page_component_catalog import NATIVE_BUTTONS


MANIFEST_SCHEMA = "android-to-harmony.arkui-page-generation.v1"

TARGET_STATE_SCHEMA = "android-to-harmony.project-state.v1"

MODULE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

RESOURCE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

PAGE_INPUT_MAX_BYTES = 10 * 1024 * 1024

LANHU_VERSION_KEYS = {"meta", "assets", "artboard"}

LANHU_COMPONENT_MANIFEST_SCHEMA = "android-to-harmony.lanhu-component-manifest.v1"

FONT_WEIGHT_VALUES = {
    "Thin": 100,
    "ExtraLight": 200,
    "Light": 300,
    "Normal": 400,
    "Regular": 400,
    "Medium": 500,
    "SemiBold": 600,
    "Bold": 700,
    "ExtraBold": 800,
    "Black": 900,
}

FONT_KEY_SUFFIXES = {
    "thin": 100,
    "extralight": 200,
    "light": 300,
    "regular": 400,
    "normal": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
    "extrabold": 800,
    "black": 900,
}

DIMENSION_PATTERN = re.compile(r"^(-?[0-9]+(?:\.[0-9]+)?)\s*\.\s*(dp|sp)$")

EXPANDABLE_THEN_MODIFIERS = {
    "width",
    "height",
    "size",
    "fillMaxWidth",
    "fillMaxHeight",
    "fillMaxSize",
    "padding",
    "background",
    "weight",
    "wrapContentWidth",
    "wrapContentHeight",
    "wrapContentSize",
    "matchParentSize",
    "widthIn",
    "requiredWidthIn",
    "heightIn",
    "sizeIn",
    "alpha",
    "offset",
    "rotate",
    "clickable",
}

OPTIONAL_FONT_COLOR_PREFIX = "__optional_font_color__:"

FALLBACK_LIST_ITEM_TYPE = "GeneratedFallbackListItem"

ROOT_PUBLIC_PARAMETER_ALIASES = {
    "enabled": "enabledValue",
}

BUTTON_CONTAINER_COMPONENTS = NATIVE_BUTTONS

STACK_RENDERED_COMPONENTS = {
    "Box",
    "BoxWithConstraints",
    "Canvas",
    "DatePickerDialog",
    "AnimatedVisibility",
    "ModalBottomSheet",
    "PullToRefreshBox",
    "Surface",
    "TopAppBar",
    "CenterAlignedTopAppBar",
}

PAGE_SNAPSHOT_COLUMN_COMPONENTS = {"Column", "LazyColumn", "Card"}

PAGE_SNAPSHOT_ROW_COMPONENTS = {"Row", "LazyRow", "BottomAppBar"}

PAGE_SNAPSHOT_FLOW_COMPONENTS = (
    PAGE_SNAPSHOT_COLUMN_COMPONENTS | PAGE_SNAPSHOT_ROW_COMPONENTS
)

PAGE_RUNTIME_OVERLAY_LEAF_TYPES = (
    BUTTON_CONTAINER_COMPONENTS
    | {"Text", "BasicText", "ClickableText", "BasicTextField", "TextField", "OutlinedTextField"}
    | {"Image", "Icon", "AsyncImage", "ProgressRing"}
)

BLANK_UNSAFE_PARENT_COMPONENTS = BUTTON_CONTAINER_COMPONENTS | STACK_RENDERED_COMPONENTS | {"ListItem", "Stack"}

PAGE_DRIVEN_BASELINE_PX = Decimal("3")

PAGE_DRIVEN_BASELINE_VP = Decimal("0.85")

PAGE_DRIVEN_RASTER_PIXEL_VP = Decimal("0.285")


class ArkUIPageError(RuntimeError):
    pass


def pascal_identifier(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    candidate = "".join(word[:1].upper() + word[1:] for word in words) or "Page"
    if candidate[0].isdigit():
        candidate = f"Page{candidate}"
    return candidate


def split_arguments(value: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False
    for character in value:
        if quote is not None:
            current.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
            current.append(character)
        elif character in "([{<":
            depth += 1
            current.append(character)
        elif character in ")]}>":
            depth = max(0, depth - 1)
            current.append(character)
        elif character == "," and depth == 0:
            chunks.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if current or value.strip():
        chunks.append("".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def named_arguments(value: str) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    named: dict[str, str] = {}
    for chunk in split_arguments(value):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", chunk, re.S)
        if match is None:
            positional.append(chunk)
        else:
            named[match.group(1)] = match.group(2).strip()
    return positional, named


def decimal_literal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def arkts_string(value: str) -> str:
    escapes = {'\\': '\\\\', "'": "\\'", '\n': '\\n', '\r': '\\r', '\t': '\\t'}
    return "'" + ''.join(escapes.get(char, f'\\u{ord(char):04x}' if ord(char) < 32 or char in '\u2028\u2029' else char)
                         for char in value) + "'"
