"""Source identity and stable hashes; no target-project operations."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
from ui_migration.common import ArkUIPageError, IDENTIFIER_PATTERN


def require_safe_relative_source(value: str) -> str:
    candidate = Path(value)
    if (
        not value
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.as_posix() != value
    ):
        raise ArkUIPageError("root source must be a normalized contract-relative path")
    return value


def require_contract_ui(
    contract: dict[str, Any], root_source: str, root_composable: str
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    if IDENTIFIER_PATTERN.fullmatch(root_composable) is None:
        raise ArkUIPageError("root composable must be a Kotlin identifier")
    ui = contract.get("ui")
    semantic = ui.get("semantic_translation_candidates") if isinstance(ui, dict) else None
    graph = ui.get("custom_composable_call_graph") if isinstance(ui, dict) else None
    composables = ui.get("composables") if isinstance(ui, dict) else None
    if not isinstance(semantic, dict) or not isinstance(semantic.get("calls"), list):
        raise ArkUIPageError("contract has no semantic Compose call inventory")
    if not isinstance(graph, dict) or not isinstance(graph.get("transitive_closures"), list):
        raise ArkUIPageError("contract has no transitive custom composable closures")
    if not isinstance(composables, list):
        raise ArkUIPageError("contract has no Compose definition inventory")
    matches = [
        item
        for item in graph["transitive_closures"]
        if isinstance(item, dict)
        and item.get("root")
        == {"source": root_source, "composable": root_composable}
    ]
    if len(matches) != 1:
        raise ArkUIPageError(
            "exact root source/composable closure was not found"
            if not matches
            else "exact root source/composable closure is not unique"
        )
    definitions: dict[tuple[str, str], dict[str, Any]] = {}
    for item in composables:
        if not isinstance(item, dict):
            raise ArkUIPageError("Compose definition inventory is invalid")
        source = item.get("source")
        name = item.get("name")
        parameters = item.get("parameters")
        if not isinstance(source, str) or not isinstance(name, str) or not isinstance(parameters, list):
            raise ArkUIPageError("Compose definition inventory entry is invalid")
        key = (source, name)
        if key in definitions:
            raise ArkUIPageError(f"duplicate Compose definition: {source}#{name}")
        definitions[key] = item
    return matches[0], semantic["calls"], definitions


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
