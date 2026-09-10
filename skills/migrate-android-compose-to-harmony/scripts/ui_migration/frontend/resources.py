from __future__ import annotations
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any
from ui_migration.frontend.bindings import number
from ui_migration.frontend.definitions import kotlin_call_blocks


def runtime_asset_rules(
    source_root: Path | None,
    values: dict[tuple[str, str], str],
) -> list[dict[str, Any]]:
    if source_root is None or not source_root.is_dir() or source_root.is_symlink():
        return []

    rules: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    available_symbols: set[str] = set()
    labeled_rule_models: set[str] = set()

    def asset(resource: str) -> dict[str, Any]:
        file = find_resource_file(source_root, resource)
        return {
            "resource": resource,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest() if file is not None else None,
        }

    for path in sorted(source_root.rglob("*.kt")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.relative_to(source_root).as_posix()
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            continue
        for available_match in re.finditer(
            r"\bavailable\s*=\s*listOf\s*\((.*?)\)", text, re.S
        ):
            available_symbols.update(
                re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b", available_match.group(1))
            )
        for call_name, start, _end, body in kotlin_call_blocks(text):
            line = text.count("\n", 0, start) + 1
            label_match = re.search(r"\blabel\s*=.*?R\.string\.([A-Za-z0-9_]+)", body, re.S)
            selected_match = re.search(r"\bselected\s*=\s*R\.(?:drawable|mipmap)\.([A-Za-z0-9_]+)", body)
            unselected_match = re.search(r"\bunselected\s*=\s*R\.(?:drawable|mipmap)\.([A-Za-z0-9_]+)", body)
            if label_match is not None and selected_match is not None and unselected_match is not None:
                label = values.get(("string", label_match.group(1)))
                if isinstance(label, str):
                    route_match = re.search(r"\broute\s*=\s*([A-Za-z_][A-Za-z0-9_.]*)", body)
                    route = route_match.group(1) if route_match is not None else None
                    key = ("navigation_item", label, unselected_match.group(1), selected_match.group(1))
                    rules[key] = {
                        "role": "navigation_item",
                        "label": label,
                        "model_type": call_name,
                        "asset": asset(unselected_match.group(1)),
                        "selected_asset": asset(selected_match.group(1)),
                        "route": route,
                        "source": {"source": relative, "line": line},
                    }

            title_match = re.search(r"\btitle\s*=\s*\"((?:[^\"\\]|\\.)*)\"", body)
            url_asset_match = re.search(
                r"(?:getMockImageUrl|drawableResource|imageResource)\s*\(\s*\"([a-z][a-z0-9_]*)\"\s*\)",
                body,
            )
            if title_match is not None and url_asset_match is not None:
                try:
                    label = json.loads(f'"{title_match.group(1)}"')
                except json.JSONDecodeError:
                    label = title_match.group(1)
                key = ("titled_asset_record", label, url_asset_match.group(1), None)
                rules[key] = {
                    "role": "titled_asset_record",
                    "label": label,
                    "model_type": call_name,
                    "asset": asset(url_asset_match.group(1)),
                    "selected_asset": None,
                    "route": None,
                    "source": {"source": relative, "line": line},
                }

            prefix = text[max(0, start - 160):start]
            object_match = re.search(
                r"\bobject\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$",
                prefix,
            )
            drawable_match = re.search(r"R\.(?:drawable|mipmap)\.([A-Za-z0-9_]+)", body)
            string_match = re.search(r"R\.string\.([A-Za-z0-9_]+)", body)
            if object_match is not None and drawable_match is not None and string_match is not None:
                label = values.get(("string", string_match.group(1)))
                if isinstance(label, str):
                    model_symbol = f"{call_name}.{object_match.group(1)}"
                    labeled_rule_models.add(call_name)
                    key = ("labeled_asset_object", label, drawable_match.group(1), None)
                    rules[key] = {
                        "role": "labeled_asset_object",
                        "label": label,
                        "model_type": call_name,
                        "asset": asset(drawable_match.group(1)),
                        "selected_asset": None,
                        "route": None,
                        "model_symbol": model_symbol,
                        "source": {"source": relative, "line": line},
                    }
    for rule in rules.values():
        model_symbol = rule.get("model_symbol")
        if isinstance(model_symbol, str) and rule.get("model_type") in labeled_rule_models:
            rule["availability"] = (
                "available" if model_symbol in available_symbols else "unavailable"
            )
        else:
            rule["availability"] = "unknown"
        rule.pop("model_symbol", None)
    return sorted(rules.values(), key=lambda item: (item["role"], item["label"], item["source"]["source"]))


def resource_values(contract: dict[str, Any]) -> dict[tuple[str, str], str]:
    ui = contract.get("ui")
    inventory = ui.get("android_value_resource_inventory") if isinstance(ui, dict) else None
    raw = inventory.get("resources") if isinstance(inventory, dict) else None
    result: dict[tuple[str, str], str] = {}
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind, name, value = item.get("type"), item.get("name"), item.get("value")
        qualifier = item.get("qualifier")
        if isinstance(kind, str) and isinstance(name, str) and isinstance(value, str):
            key = (kind, name)
            if key not in result or qualifier == "values":
                result[key] = re.sub(r'\\(u[0-9a-fA-F]{4}|[ntr\\\"\'])',
                    lambda m: chr(int(m[1][1:], 16)) if m[1].startswith('u') else
                    {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', "'": "'"}[m[1]], value) if kind == 'string' else value
    return result


def find_resource_file(source_root: Path | None, resource: str) -> Path | None:
    if source_root is None or not source_root.is_dir():
        return None
    resource_roots = [source_root / "src" / "main" / "res"]
    resource_roots.extend(
        child / "src" / "main" / "res"
        for child in source_root.iterdir()
        if child.is_dir() and not child.is_symlink()
    )
    candidates = sorted(
        path
        for resource_root in resource_roots
        if resource_root.is_dir()
        for path in resource_root.glob(f"*/{resource}.*")
        if path.is_file() and not path.is_symlink()
    )
    defaults = [path for path in candidates if path.parent.name in {"drawable", "mipmap"}]
    return (defaults or candidates or [None])[0]


def _safe_asset_candidates(source_root: Path | None) -> dict[str, list[dict[str, Any]]]:
    if source_root is None:
        return {}
    manifest = source_root / ".android-to-harmony-safe.json"
    if not manifest.is_file() or manifest.is_symlink():
        return {}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    original_root = payload.get("source_root")
    original_root_path = Path(original_root) if isinstance(original_root, str) else None
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in payload.get("local_only_assets") or []:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        sha256 = item.get("sha256")
        if not isinstance(path, str) or not isinstance(sha256, str):
            continue
        resource_path = Path(path)
        if resource_path.parent.name.split("-", 1)[0] not in {"drawable", "mipmap"}:
            continue
        evidence: dict[str, Any] = {"path": path, "sha256": sha256}
        original = original_root_path / path if original_root_path is not None else None
        if original is not None and original.is_file() and not original.is_symlink():
            if hashlib.sha256(original.read_bytes()).hexdigest() == sha256:
                dimensions = android_vector_dimensions(original)
                if dimensions is not None:
                    evidence["width_dp"], evidence["height_dp"] = dimensions
        candidates[resource_path.stem].append(evidence)
    return candidates


def _select_asset_candidates(candidates, source_relative):
    module = source_relative.split('/src/', 1)[0] + '/src/' if source_relative and '/src/' in source_relative else None
    result = {}
    for name, items in candidates.items():
        scoped = [item for item in items if module and item['path'].startswith(module)]
        selected = scoped or items
        if len({item['sha256'] for item in selected}) == 1:
            result[name] = dict(selected[0])
    return result


def safe_asset_index(source_root: Path | None, source_relative: str | None = None) -> dict[str, dict[str, Any]]:
    return _select_asset_candidates(_safe_asset_candidates(source_root), source_relative)


def safe_asset_indexes(source_root: Path | None, sources):
    candidates = _safe_asset_candidates(source_root)
    return (_select_asset_candidates(candidates, None),
            {source: _select_asset_candidates(candidates, source) for source in dict.fromkeys(sources)})


def android_vector_dimensions(path: Path | None) -> tuple[float, float] | None:
    if path is None or path.suffix.lower() != ".xml":
        return None
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    if root.tag.rsplit("}", 1)[-1] != "vector":
        return None
    android_namespace = "{http://schemas.android.com/apk/res/android}"

    def dimension(name: str) -> float | None:
        raw = root.get(android_namespace + name)
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(?:dp|dip)", raw or "")
        return number(match.group(1)) if match is not None else None

    width, height = dimension("width"), dimension("height")
    return (width, height) if width is not None and height is not None else None
