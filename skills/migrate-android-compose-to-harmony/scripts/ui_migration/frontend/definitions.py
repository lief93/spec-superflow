from __future__ import annotations
import hashlib
import re
from pathlib import Path
from typing import Any
from ui_migration.frontend.model import COMPOSE_FRAMEWORK_PREFIXES, PLATFORM_COMPONENT_IMPORT_MARKERS


def source_component_id(instance_path: str, call_id: str) -> str:
    digest = hashlib.sha256(f"{instance_path}\0{call_id}".encode("utf-8")).hexdigest()[:20]
    return f"source-{digest}"


def source_semantic_key(call: dict[str, Any]) -> str:
    call_id = str(call.get("call_id", ""))
    try:
        _source, line, component, ordinal = call_id.rsplit(":", 3)
    except ValueError:
        line = str(call.get("line", 0))
        component = str(call.get("component", "View"))
        ordinal = "0"
    composable = str(call.get("composable", "Page"))
    tokens = [re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") for value in (composable, component, line, ordinal)]
    return "_".join(value or "unknown" for value in tokens)[:120]


def definition_id(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"definition-{digest}"


def kotlin_source_metadata(
    source_root: Path | None,
    relative_source: str,
    cache: dict[str, tuple[str | None, dict[str, str]]],
) -> tuple[str | None, dict[str, str]]:
    cached = cache.get(relative_source)
    if cached is not None:
        return cached
    package_name: str | None = None
    imports: dict[str, str] = {}
    if source_root is not None:
        path = source_root / relative_source
        if path.is_file() and not path.is_symlink() and path.suffix in {".kt", ".kts"}:
            text = path.read_text(encoding="utf-8")
            package_match = re.search(r"(?m)^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)", text)
            if package_match is not None:
                package_name = package_match.group(1)
            for match in re.finditer(
                r"(?m)^\s*import\s+([A-Za-z_][A-Za-z0-9_.]*)(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?\s*$",
                text,
            ):
                qualified_name, alias = match.groups()
                imports[alias or qualified_name.rsplit(".", 1)[-1]] = qualified_name
    result = (package_name, imports)
    cache[relative_source] = result
    return result


def component_definition(
    call: dict[str, Any],
    source_root: Path | None,
    metadata_cache: dict[str, tuple[str | None, dict[str, str]]],
) -> dict[str, Any]:
    component = str(call.get("component", "View"))
    source = str(call.get("source", ""))
    containing_composable = str(call.get("composable", ""))
    package_name, imports = kotlin_source_metadata(source_root, source, metadata_cache)
    custom = call.get("custom_composable")
    definitions = custom.get("definitions") if isinstance(custom, dict) else None
    target = definitions[0] if isinstance(definitions, list) and len(definitions) == 1 else None
    if isinstance(target, dict) and isinstance(target.get("source"), str) and isinstance(target.get("composable"), str):
        target_source = target["source"]
        target_composable = target["composable"]
        target_package, _target_imports = kotlin_source_metadata(
            source_root, target_source, metadata_cache
        )
        qualified_name = (
            f"{target_package}.{target_composable}" if target_package else target_composable
        )
        return {
            "id": definition_id("project_component", target_source, target_composable,
                                *([target['declaration_id']] if target.get('declaration_id') else [])),
            "type": component,
            "component_kind": "project_component",
            "identity": {
                "status": "resolved_project_definition",
                "qualified_name": qualified_name,
                "source": target_source,
                "symbol": target_composable,
                "declaration_id": target.get('declaration_id'),
            },
            "dependency": None,
            "declared_from": {
                "source": source,
                "composable": containing_composable,
                "package": package_name,
            },
        }

    qualified_name = imports.get(component)
    if component == "Canvas":
        kind = "custom_draw"
    elif isinstance(qualified_name, str) and any(
        marker in qualified_name for marker in PLATFORM_COMPONENT_IMPORT_MARKERS
    ):
        kind = "platform_component"
    elif isinstance(qualified_name, str) and qualified_name.startswith(COMPOSE_FRAMEWORK_PREFIXES):
        kind = "compose_primitive"
    elif isinstance(qualified_name, str):
        kind = "third_party_component"
    else:
        kind = "compose_primitive"
    identity_status = "resolved_import" if qualified_name is not None else "inferred_primitive_name"
    stable_identity = qualified_name or component
    dependency = None
    if kind == "third_party_component":
        dependency = {
            "qualified_name": qualified_name,
            "package_root": ".".join(qualified_name.split(".")[:2]),
            "version": None,
            "version_status": "requires_resolved_dependency_graph",
        }
    return {
        "id": definition_id(kind, stable_identity),
        "type": component,
        "component_kind": kind,
        "identity": {
            "status": identity_status,
            "qualified_name": qualified_name,
            "source": None,
            "symbol": component,
        },
        "dependency": dependency,
        "declared_from": {
            "source": source,
            "composable": containing_composable,
            "package": package_name,
        },
    }


def kotlin_call_blocks(text: str) -> list[tuple[str, int, int, str]]:
    blocks: list[tuple[str, int, int, str]] = []
    for match in re.finditer(r"\b([A-Z][A-Za-z0-9_]*)\s*\(", text):
        open_index = text.find("(", match.start(), match.end())
        depth = 0
        quote: str | None = None
        escaped = False
        for index in range(open_index, min(len(text), open_index + 12000)):
            character = text[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character in {'"', "'"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    blocks.append((match.group(1), match.start(), index + 1, text[open_index + 1:index]))
                    break
    return blocks
