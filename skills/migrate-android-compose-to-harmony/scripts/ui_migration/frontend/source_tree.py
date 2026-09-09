from __future__ import annotations
from collections import defaultdict
from typing import Any
from ui_migration.frontend.page_model import SOURCE_SCHEMA, finite_number


class SourceTree:
    def __init__(self, payload: dict[str, Any], *, allow_multiple_roots: bool = False) -> None:
        from ui_migration.contracts.source_storage import unpack_source_page
        payload = unpack_source_page(payload)
        if payload.get("schema") != SOURCE_SCHEMA:
            raise ValueError(f"unsupported source page schema: {payload.get('schema')!r}")
        raw_components = payload.get("components")
        if not isinstance(raw_components, list) or not raw_components:
            raise ValueError("source page must contain components")
        self.payload = payload
        self.nodes: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        for raw in raw_components:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                raise ValueError("every source component must have a string id")
            component_id = raw["id"]
            if component_id in self.nodes:
                raise ValueError(f"duplicate source component id: {component_id}")
            self.nodes[component_id] = raw
            self.order.append(component_id)

        roots = [node for node in self.nodes.values() if node.get("parent_id") is None]
        if not roots or (len(roots) != 1 and not allow_multiple_roots):
            raise ValueError(f"source page must have exactly one root; found {len(roots)}")
        self.root_id = roots[0]["id"]
        self.root_ids = [node['id'] for node in roots]
        derived_children: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in self.nodes.values():
            parent_id = node.get("parent_id")
            if parent_id is None:
                continue
            if parent_id not in self.nodes:
                raise ValueError(f"unknown parent {parent_id!r} for {node['id']!r}")
            derived_children[parent_id].append(node)
        for children in derived_children.values():
            children.sort(
                key=lambda item: (
                    finite_number(item.get("sibling_index")) or 0,
                    self.order.index(item["id"]),
                )
            )
        self.children = {
            parent_id: [child["id"] for child in children]
            for parent_id, children in derived_children.items()
        }
        self._validate_declared_children()
        self._validate_connected()

    def _validate_declared_children(self) -> None:
        for node in self.nodes.values():
            declared = node.get("children_ids")
            if declared is None:
                continue
            if not isinstance(declared, list):
                raise ValueError(f"children_ids must be a list for {node['id']!r}")
            actual = self.children.get(node["id"], [])
            if declared and declared != actual:
                raise ValueError(
                    f"child order mismatch for {node['id']!r}: declared={declared}, actual={actual}"
                )

    def _validate_connected(self) -> None:
        visited: set[str] = set()

        def visit(component_id: str, active: set[str]) -> None:
            if component_id in active:
                raise ValueError(f"source component cycle at {component_id!r}")
            if component_id in visited:
                return
            visited.add(component_id)
            for child_id in self.children.get(component_id, []):
                visit(child_id, active | {component_id})

        for root_id in self.root_ids:
            visit(root_id, set())
        if visited != set(self.nodes):
            missing = sorted(set(self.nodes) - visited)
            raise ValueError(f"source components are disconnected: {missing}")
