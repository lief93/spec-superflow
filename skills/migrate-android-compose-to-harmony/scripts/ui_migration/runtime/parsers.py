from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET
from page_snapshot import empty_style
from typing import Any
from ui_migration.frontend.model import BOUNDS_PATTERN, RealPageError


def bool_attribute(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() == "true"


def runtime_type(class_name: str, clickable: bool) -> str:
    simple = class_name.rsplit(".", 1)[-1]
    if simple in {"TextView"}:
        return "Text"
    if simple in {"EditText", "AutoCompleteTextView"}:
        return "TextField"
    if simple in {"ImageView", "ImageButton"}:
        return "Image"
    if simple in {"Button", "CheckBox", "Switch", "RadioButton"}:
        return simple
    if simple == "View" and clickable:
        return "Button"
    return simple or "View"


def parse_bounds(raw: str, dimensions: tuple[int, int]) -> dict[str, int] | None:
    match = BOUNDS_PATTERN.fullmatch(raw)
    if match is None:
        return None
    left, top, right, bottom = (int(value) for value in match.groups())
    left = max(0, min(left, dimensions[0]))
    right = max(0, min(right, dimensions[0]))
    top = max(0, min(top, dimensions[1]))
    bottom = max(0, min(bottom, dimensions[1]))
    if right <= left or bottom <= top:
        return None
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def parse_uiautomator_xml(
    xml_bytes: bytes,
    dimensions: tuple[int, int],
    package_name: str | None = None,
) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as error:
        raise RealPageError(f"UIAutomator XML is invalid: {error}") from error
    components: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    def walk(element: ET.Element, path: tuple[int, ...], nearest_parent: str | None) -> None:
        if element.tag != "node":
            for index, child in enumerate(element):
                walk(child, path + (index,), nearest_parent)
            return
        bounds = parse_bounds(element.attrib.get("bounds", ""), dimensions)
        package = element.attrib.get("package", "")
        resource_id = element.attrib.get("resource-id", "")
        system_bar = resource_id in {
            "android:id/statusBarBackground",
            "android:id/navigationBarBackground",
        }
        keep = bounds is not None and not system_bar and (not package_name or not package or package == package_name)
        parent_id = nearest_parent
        if keep:
            component_id = "runtime-" + "-".join(str(index) for index in path)
            clickable = bool_attribute(element.attrib.get("clickable"))
            style = empty_style()
            style["state"].update(
                {
                    "visible": True,
                    "enabled": bool_attribute(element.attrib.get("enabled"), True),
                    "selected": bool_attribute(element.attrib.get("selected")),
                    "checked": bool_attribute(element.attrib.get("checked")),
                    "clickable": clickable,
                }
            )
            text = element.attrib.get("text", "")
            description = element.attrib.get("content-desc", "")
            class_name = element.attrib.get("class", "android.view.View")
            kind = runtime_type(class_name, clickable)
            style["content"].update(
                {
                    "text": text or None,
                    "content_description": description or None,
                    "role": (
                        "textbox" if kind == "TextField"
                        else "checkbox" if kind == "CheckBox"
                        else "switch" if kind == "Switch"
                        else "radio" if kind == "RadioButton"
                        else "button" if clickable or kind in {"Button", "ImageButton"}
                        else "image" if kind == "Image"
                        else "text" if kind == "Text"
                        else None
                    ),
                }
            )
            component = {
                "id": component_id,
                "runtime_class": class_name,
                "resource_id": resource_id or None,
                "type": kind,
                "bounds_px": bounds,
                "parent_id": parent_id,
                "children_ids": [],
                "sibling_index": 0,
                "style": style,
            }
            components.append(component)
            by_id[component_id] = component
            if parent_id is not None:
                parent = by_id[parent_id]
                component["sibling_index"] = len(parent["children_ids"])
                parent["children_ids"].append(component_id)
            parent_id = component_id
        for index, child in enumerate(element):
            walk(child, path + (index,), parent_id)

    walk(root, (), None)
    return components


def parse_harmony_layout_json(
    layout_bytes: bytes,
    dimensions: tuple[int, int],
    bundle_name: str | None = None,
) -> list[dict[str, Any]]:
    try:
        root = json.loads(layout_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RealPageError(f"OpenHarmony uitest layout is invalid: {error}") from error
    if not isinstance(root, dict):
        raise RealPageError("OpenHarmony uitest layout root must be an object")
    components: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    def walk(node: Any, path: tuple[int, ...], nearest_parent: str | None) -> None:
        if not isinstance(node, dict):
            return
        attributes = node.get("attributes")
        children = node.get("children")
        parent_id = nearest_parent
        if isinstance(attributes, dict):
            bounds = parse_bounds(str(attributes.get("bounds", "")), dimensions)
            kind = str(attributes.get("type", "")).strip()
            visible = bool_attribute(str(attributes.get("visible", "true")), True)
            keep = bounds is not None and visible and bool(kind)
            if keep:
                component_id = "runtime-h-" + "-".join(str(index) for index in path)
                runtime_id = str(attributes.get("id") or attributes.get("key") or "").strip() or None
                clickable = bool_attribute(str(attributes.get("clickable", "false"))) or kind == "Button"
                style = empty_style()
                style["state"].update(
                    {
                        "visible": True,
                        "enabled": bool_attribute(str(attributes.get("enabled", "true")), True),
                        "selected": bool_attribute(str(attributes.get("selected", "false"))),
                        "checked": bool_attribute(str(attributes.get("checked", "false"))),
                        "clickable": clickable,
                    }
                )
                text = str(attributes.get("text") or attributes.get("originalText") or "")
                description = str(attributes.get("description") or "")
                hint = str(attributes.get("hint") or "")
                normalized_kind = "TextField" if kind == "TextInput" else kind
                style["content"].update(
                    {
                        "text": text or None,
                        "placeholder": hint or None,
                        "content_description": description or None,
                        "role": (
                            "textbox" if normalized_kind == "TextField"
                            else "checkbox" if normalized_kind in {"Checkbox", "CheckBox"}
                            else "switch" if normalized_kind == "Switch"
                            else "radio" if normalized_kind == "RadioButton"
                            else "button" if clickable or normalized_kind == "Button"
                            else "image" if normalized_kind == "Image"
                            else "text" if normalized_kind == "Text"
                            else None
                        ),
                    }
                )
                background = str(attributes.get("backgroundColor") or "")
                if re.fullmatch(r"#[0-9A-Fa-f]{8}", background) and background.upper() != "#00000000":
                    style["surface"]["background"] = {"type": "solid", "color": background.upper()}
                opacity = str(attributes.get("opacity") or "")
                if re.fullmatch(r"(?:0(?:\.\d+)?|1(?:\.0+)?)", opacity) and float(opacity) != 1.0:
                    style["surface"]["alpha"] = round(float(opacity), 3)
                clip = attributes.get("clip")
                if str(clip).lower() == "true":
                    style["surface"]["clip"] = True
                z_index = str(attributes.get("zIndex") or "")
                if re.fullmatch(r"-?[0-9]+(?:\.\d+)?", z_index) and float(z_index) != 0.0:
                    style["layout"]["z_index"] = round(float(z_index), 3)
                background_image = str(attributes.get("backgroundImage") or "")
                if background_image and background_image != "empty source":
                    style["asset"]["resource"] = background_image
                component = {
                    "id": component_id,
                    "runtime_id": runtime_id,
                    "runtime_class": kind,
                    "resource_id": None,
                    "type": normalized_kind,
                    "bounds_px": bounds,
                    "parent_id": parent_id,
                    "children_ids": [],
                    "sibling_index": 0,
                    "style": style,
                    "runtime_attributes": {
                        key: attributes.get(key)
                        for key in ("accessibilityId", "hierarchy", "pagePath", "origBounds", "layoutDirection")
                        if attributes.get(key) not in {None, ""}
                    },
                }
                components.append(component)
                by_id[component_id] = component
                if parent_id is not None:
                    parent = by_id[parent_id]
                    component["sibling_index"] = len(parent["children_ids"])
                    parent["children_ids"].append(component_id)
                parent_id = component_id
        if isinstance(children, list):
            for index, child in enumerate(children):
                walk(child, path + (index,), parent_id)

    if bundle_name:
        root_children = root.get("children")
        matching_roots = [
            child
            for child in root_children
            if isinstance(root_children, list)
            and isinstance(child, dict)
            and isinstance(child.get("attributes"), dict)
            and child["attributes"].get("bundleName") == bundle_name
        ] if isinstance(root_children, list) else []
        if not matching_roots:
            raise RealPageError(f"OpenHarmony uitest layout has no root for bundle: {bundle_name}")
        if len(matching_roots) != 1:
            raise RealPageError(f"OpenHarmony uitest layout has ambiguous roots for bundle: {bundle_name}")
        walk(matching_roots[0], (0,), None)
    else:
        walk(root, (), None)
    return components
