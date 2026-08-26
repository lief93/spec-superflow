#!/usr/bin/env python3
"""Generate candidate migration backlog slices from a migration contract."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA = "android-to-harmony.migration-backlog.v1"
CONTRACT_SCHEMA = "android-to-harmony.migration-contract.v1"
CONTRACT_GENERATOR = "migrate-android-compose-to-harmony"
CONTRACT_INVENTORY_QUALITY = "candidate"
REQUIRED_GATES = [
    "slice_ledger",
    "inventory_reconciliation",
    "build",
    "unit_tests",
    "ui_tests",
    "device_test",
    "visual_review",
]
STOPWORDS = {
    "ability",
    "adapter",
    "android",
    "app",
    "base",
    "binding",
    "class",
    "common",
    "component",
    "compose",
    "composable",
    "components",
    "core",
    "default",
    "entry",
    "feature",
    "features",
    "fragment",
    "graph",
    "java",
    "json",
    "kotlin",
    "layout",
    "layouts",
    "module",
    "navigation",
    "page",
    "pages",
    "resource",
    "resources",
    "screen",
    "screens",
    "source",
    "src",
    "test",
    "tests",
    "values",
    "view",
    "views",
    "xml",
}
PATH_PART_STOPWORDS = {
    "androidtest",
    "java",
    "kotlin",
    "layout",
    "main",
    "navigation",
    "res",
    "src",
    "test",
    "values",
}


class BacklogError(ValueError):
    """Raised when backlog generation inputs are invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a candidate Android-to-Harmony migration backlog."
    )
    parser.add_argument("--contract", required=True, help="Input migration contract")
    parser.add_argument("--output", required=True, help="Output backlog JSON path")
    return parser.parse_args()


def load_contract(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise BacklogError(f"unable to read contract: {error}") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BacklogError(f"invalid JSON contract: {error}") from error
    if not isinstance(payload, dict):
        raise BacklogError("contract must decode to a JSON object")
    schema = payload.get("schema")
    if schema != CONTRACT_SCHEMA:
        raise BacklogError(
            "contract schema must be "
            f"{CONTRACT_SCHEMA!r}; received {schema!r}"
        )
    generator = payload.get("generator")
    if generator != CONTRACT_GENERATOR:
        raise BacklogError(
            "contract generator must be "
            f"{CONTRACT_GENERATOR!r}; received {generator!r}"
        )
    inventory_quality = payload.get("inventory_quality")
    if inventory_quality != CONTRACT_INVENTORY_QUALITY:
        raise BacklogError(
            "contract inventory_quality must be "
            f"{CONTRACT_INVENTORY_QUALITY!r}; received {inventory_quality!r}"
        )
    return payload, hashlib.sha256(raw).hexdigest()


def split_tokens(value: str | None) -> list[str]:
    if not value:
        return []
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    tokens = re.findall(r"[A-Za-z0-9]+", expanded)
    return [
        token.lower()
        for token in tokens
        if len(token) >= 3 and token.lower() not in STOPWORDS
    ]


def split_slug_tokens(value: str | None) -> list[str]:
    if not value:
        return []
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", expanded)]


def path_tokens(path: str) -> set[str]:
    tokens: set[str] = set()
    for part in Path(path).parts:
        if part.lower() in PATH_PART_STOPWORDS:
            continue
        stem = Path(part).stem
        tokens.update(split_tokens(stem))
    return tokens


def unique_strings(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def slugify(*parts: str | None) -> str:
    tokens: list[str] = []
    for part in parts:
        tokens.extend(split_slug_tokens(part))
    return "-".join(tokens) or "item"


def module_prefix(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else path


def normalize_graph_reference(value: str | None) -> str | None:
    if not value:
        return None
    if "/" not in value:
        return value
    return value.rsplit("/", 1)[-1]


def collect_source_files(contract: dict[str, Any]) -> list[str]:
    files: set[str] = set()
    inventory = contract.get("inventory", {})
    if isinstance(inventory, dict):
        files_by_layer = inventory.get("files_by_layer", {})
        if isinstance(files_by_layer, dict):
            for values in files_by_layer.values():
                if isinstance(values, list):
                    files.update(
                        str(value) for value in values if isinstance(value, str)
                    )
    for batch in contract.get("migration_batches", []):
        if isinstance(batch, dict):
            files.update(
                str(value)
                for value in batch.get("source_files", [])
                if isinstance(value, str)
            )
    for capability in contract.get("platform_capabilities", []):
        if isinstance(capability, dict):
            files.update(
                str(value)
                for value in capability.get("source_files", [])
                if isinstance(value, str)
            )
    ui = contract.get("ui", {})
    if isinstance(ui, dict):
        for composable in ui.get("composables", []):
            if isinstance(composable, dict) and isinstance(
                composable.get("source"), str
            ):
                files.add(composable["source"])
        for closure in ui.get("custom_composable_call_graph", {}).get(
            "transitive_closures", []
        ):
            if not isinstance(closure, dict):
                continue
            root = closure.get("root", {})
            if isinstance(root, dict) and isinstance(root.get("source"), str):
                files.add(root["source"])
            for reached in closure.get("reached_definitions", []):
                if isinstance(reached, dict) and isinstance(reached.get("source"), str):
                    files.add(reached["source"])
        for route in ui.get("routes", []):
            if isinstance(route, dict):
                for key in ("source", "declared_in"):
                    if isinstance(route.get(key), str):
                        files.add(route[key])
        for inventory_key, source_key in (
            ("android_view_layout_inventory", "source"),
            ("android_activity_inventory", "source"),
            ("android_navigation_inventory", "source"),
            ("android_binding_adapter_inventory", "source"),
        ):
            inventory_value = ui.get(inventory_key, {})
            if not isinstance(inventory_value, dict):
                continue
            for item in inventory_value.get("layouts", []):
                if isinstance(item, dict) and isinstance(item.get(source_key), str):
                    files.add(item[source_key])
            for item in inventory_value.get("activities", []):
                if isinstance(item, dict) and isinstance(item.get(source_key), str):
                    files.add(item[source_key])
            for item in inventory_value.get("layout_bindings", []):
                if isinstance(item, dict) and isinstance(item.get("source"), str):
                    files.add(item["source"])
            for item in inventory_value.get("graphs", []):
                if isinstance(item, dict) and isinstance(item.get(source_key), str):
                    files.add(item[source_key])
            for item in inventory_value.get("adapters", []):
                if isinstance(item, dict) and isinstance(item.get(source_key), str):
                    files.add(item[source_key])
        resource_inventory = ui.get("android_value_resource_inventory", {})
        if isinstance(resource_inventory, dict):
            for item in resource_inventory.get("resources", []):
                if isinstance(item, dict) and isinstance(item.get("source"), str):
                    files.add(item["source"])
    business = contract.get("business", {})
    if isinstance(business, dict):
        for item in business.get("models", []):
            if isinstance(item, dict) and isinstance(item.get("source"), str):
                files.add(item["source"])
        for item in business.get("tests", []):
            if isinstance(item, dict) and isinstance(item.get("source"), str):
                files.add(item["source"])
    return sorted(files)


class ContractIndex:
    def __init__(self, contract: dict[str, Any]) -> None:
        self.contract = contract
        self.all_sources = collect_source_files(contract)
        self.unassigned = set(self.all_sources)
        self.file_tokens = {source: path_tokens(source) for source in self.all_sources}
        self.sources_by_category: dict[str, set[str]] = collections.defaultdict(set)
        self.names_by_category: dict[str, dict[str, set[str]]] = collections.defaultdict(
            lambda: collections.defaultdict(set)
        )
        self.batch_ids_by_source: dict[str, set[str]] = collections.defaultdict(set)
        self.capability_ids_by_source: dict[str, set[str]] = collections.defaultdict(set)
        self.test_records_by_source: dict[str, list[dict[str, Any]]] = (
            collections.defaultdict(list)
        )
        self.resource_records_by_source: dict[str, list[dict[str, Any]]] = (
            collections.defaultdict(list)
        )
        self.composable_names_by_source: dict[str, set[str]] = collections.defaultdict(
            set
        )
        self.closure_sources_by_root: dict[str, set[str]] = collections.defaultdict(set)
        self.closure_names_by_root: dict[str, set[str]] = collections.defaultdict(set)
        self.layout_sources_by_name: dict[str, str] = {}
        self.graph_sources_by_name: dict[str, str] = {}
        self.activity_sources_by_graph: dict[str, set[str]] = collections.defaultdict(set)
        self.activity_layout_sources_by_activity: dict[str, set[str]] = (
            collections.defaultdict(set)
        )
        self.activities = self._load_activities()
        self.destinations = self._load_destinations()
        self.binding_adapters = self._load_binding_adapters()
        self.capabilities = self._load_capabilities()
        self.batches = self._load_batches()
        self._load_composables()
        self._load_closures()
        self._load_models()
        self._load_tests()
        self._load_resources()
        self._load_layouts_and_graphs()

    def _load_batches(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for batch in self.contract.get("migration_batches", []):
            if not isinstance(batch, dict):
                continue
            result.append(batch)
            batch_id = batch.get("id")
            if not isinstance(batch_id, str):
                continue
            for source in batch.get("source_files", []):
                if isinstance(source, str):
                    self.batch_ids_by_source[source].add(batch_id)
        return result

    def _load_capabilities(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for capability in self.contract.get("platform_capabilities", []):
            if not isinstance(capability, dict):
                continue
            result.append(capability)
            capability_id = capability.get("id")
            if not isinstance(capability_id, str):
                continue
            for source in capability.get("source_files", []):
                if isinstance(source, str):
                    self.capability_ids_by_source[source].add(capability_id)
        return result

    def _load_tests(self) -> None:
        business = self.contract.get("business", {})
        if not isinstance(business, dict):
            return
        for record in business.get("tests", []):
            if not isinstance(record, dict):
                continue
            source = record.get("source")
            if not isinstance(source, str):
                continue
            test_names = record.get("test_names", [])
            self.test_records_by_source[source].append(
                {
                    "source": source,
                    "test_names": [
                        value for value in test_names if isinstance(value, str)
                    ],
                }
            )

    def _load_resources(self) -> None:
        ui = self.contract.get("ui", {})
        if not isinstance(ui, dict):
            return
        inventory = ui.get("android_value_resource_inventory", {})
        if not isinstance(inventory, dict):
            return
        for record in inventory.get("resources", []):
            if not isinstance(record, dict):
                continue
            source = record.get("source")
            if not isinstance(source, str):
                continue
            self.resource_records_by_source[source].append(
                {
                    "source": source,
                    "name": record.get("name"),
                    "type": record.get("type"),
                }
            )

    def _load_composables(self) -> None:
        ui = self.contract.get("ui", {})
        if not isinstance(ui, dict):
            return
        for record in ui.get("composables", []):
            if not isinstance(record, dict):
                continue
            source = record.get("source")
            name = record.get("name")
            if isinstance(source, str) and isinstance(name, str):
                self.composable_names_by_source[source].add(name)
                self.sources_by_category["ui"].add(source)

    def _load_closures(self) -> None:
        ui = self.contract.get("ui", {})
        if not isinstance(ui, dict):
            return
        graph = ui.get("custom_composable_call_graph", {})
        if not isinstance(graph, dict):
            return
        for closure in graph.get("transitive_closures", []):
            if not isinstance(closure, dict):
                continue
            root = closure.get("root", {})
            if not isinstance(root, dict):
                continue
            root_source = root.get("source")
            root_name = root.get("composable")
            if not isinstance(root_source, str):
                continue
            self.sources_by_category["ui"].add(root_source)
            self.closure_sources_by_root[root_source].add(root_source)
            if isinstance(root_name, str):
                self.closure_names_by_root[root_source].add(root_name)
                self.composable_names_by_source[root_source].add(root_name)
            for reached in closure.get("reached_definitions", []):
                if not isinstance(reached, dict):
                    continue
                source = reached.get("source")
                name = reached.get("composable")
                if isinstance(source, str):
                    self.closure_sources_by_root[root_source].add(source)
                    self.sources_by_category["ui"].add(source)
                if isinstance(source, str) and isinstance(name, str):
                    self.closure_names_by_root[root_source].add(name)
                    self.composable_names_by_source[source].add(name)

    def _classify_source(self, source: str, name: str | None = None) -> str | None:
        lower_path = source.lower()
        lower_name = (name or Path(source).stem).lower()
        if "/src/test/" in lower_path or "/src/androidtest/" in lower_path:
            return None
        if "viewmodel" in lower_name or "viewmodel" in lower_path:
            return "viewmodel"
        if "repository" in lower_name or "repository" in lower_path:
            return "repository"
        if "usecase" in lower_name or "usecase" in lower_path or "use_case" in lower_path:
            return "usecase"
        if lower_name.endswith("state") or "state" in lower_path:
            return "state"
        if any(
            marker in lower_path
            for marker in (
                "/dao/",
                "/database/",
                "/network/",
                "/request/",
                "/response/",
                "/mapper/",
                "/store/",
                "/cache/",
                "/model/",
                "service",
                "interceptor",
            )
        ):
            return "data"
        return None

    def _add_category_name(self, category: str, source: str, name: str) -> None:
        if not name:
            return
        self.sources_by_category[category].add(source)
        self.names_by_category[category][source].add(name)

    def _load_models(self) -> None:
        business = self.contract.get("business", {})
        if isinstance(business, dict):
            for record in business.get("models", []):
                if not isinstance(record, dict):
                    continue
                source = record.get("source")
                name = record.get("name")
                if not isinstance(source, str) or not isinstance(name, str):
                    continue
                category = self._classify_source(source, name)
                if category is not None:
                    self._add_category_name(category, source, name)
        for source in self.all_sources:
            category = self._classify_source(source)
            if category is not None:
                self._add_category_name(category, source, Path(source).stem)

    def _load_layouts_and_graphs(self) -> None:
        ui = self.contract.get("ui", {})
        if not isinstance(ui, dict):
            return
        layout_inventory = ui.get("android_view_layout_inventory", {})
        if isinstance(layout_inventory, dict):
            for layout in layout_inventory.get("layouts", []):
                if not isinstance(layout, dict):
                    continue
                source = layout.get("source")
                name = layout.get("name")
                if isinstance(source, str) and isinstance(name, str):
                    self.layout_sources_by_name[name] = source
                    self.sources_by_category["ui"].add(source)
        graph_inventory = ui.get("android_navigation_inventory", {})
        if isinstance(graph_inventory, dict):
            for graph in graph_inventory.get("graphs", []):
                if not isinstance(graph, dict):
                    continue
                source = graph.get("source")
                name = graph.get("name")
                graph_id = graph.get("id")
                if isinstance(source, str):
                    self.sources_by_category["ui"].add(source)
                if isinstance(source, str) and isinstance(name, str):
                    self.graph_sources_by_name[name] = source
                if isinstance(source, str) and isinstance(graph_id, str):
                    self.graph_sources_by_name[graph_id] = source

        activity_inventory = ui.get("android_activity_inventory", {})
        if not isinstance(activity_inventory, dict):
            return
        for binding in activity_inventory.get("layout_bindings", []):
            if not isinstance(binding, dict):
                continue
            activity = binding.get("activity")
            layout_name = binding.get("layout")
            source = binding.get("source")
            if isinstance(activity, str) and isinstance(source, str):
                self.activity_layout_sources_by_activity[activity].add(source)
            if not isinstance(layout_name, str):
                continue
            layout_source = self.layout_sources_by_name.get(layout_name)
            if layout_source is None:
                continue
            activity_name = binding.get("activity")
            if isinstance(activity_name, str):
                self.activity_layout_sources_by_activity[activity_name].add(layout_source)
            for layout in layout_inventory.get("layouts", []):
                if not isinstance(layout, dict) or layout.get("name") != layout_name:
                    continue
                for view in layout.get("views", []):
                    if not isinstance(view, dict):
                        continue
                    attributes = view.get("attributes", {})
                    if not isinstance(attributes, dict):
                        continue
                    graph_reference = normalize_graph_reference(
                        attributes.get("app:navGraph") or attributes.get("app:graph")
                    )
                    if graph_reference is None:
                        continue
                    graph_source = self.graph_sources_by_name.get(graph_reference)
                    if graph_source is not None and isinstance(activity_name, str):
                        self.activity_sources_by_graph[activity_name].add(graph_source)

    def _load_activities(self) -> list[dict[str, Any]]:
        ui = self.contract.get("ui", {})
        if not isinstance(ui, dict):
            return []
        inventory = ui.get("android_activity_inventory", {})
        if not isinstance(inventory, dict):
            return []
        return [item for item in inventory.get("activities", []) if isinstance(item, dict)]

    def _load_destinations(self) -> list[dict[str, Any]]:
        ui = self.contract.get("ui", {})
        if not isinstance(ui, dict):
            return []
        inventory = ui.get("android_navigation_inventory", {})
        if not isinstance(inventory, dict):
            return []
        destinations: list[dict[str, Any]] = []
        for graph in inventory.get("graphs", []):
            if not isinstance(graph, dict):
                continue
            for destination in graph.get("destinations", []):
                if not isinstance(destination, dict):
                    continue
                destinations.append({"graph": graph, "destination": destination})
        return destinations

    def _load_binding_adapters(self) -> list[dict[str, Any]]:
        ui = self.contract.get("ui", {})
        if not isinstance(ui, dict):
            return []
        inventory = ui.get("android_binding_adapter_inventory", {})
        if not isinstance(inventory, dict):
            return []
        return [item for item in inventory.get("adapters", []) if isinstance(item, dict)]

    def find_class_source(self, class_name: str | None) -> str | None:
        if not class_name:
            return None
        stem = class_name.rsplit(".", 1)[-1]
        matches = [
            source for source in self.all_sources if Path(source).stem == stem
        ]
        return sorted(matches)[0] if matches else None

    def closure_sources_for(self, source: str | None) -> list[str]:
        if source is None:
            return []
        return sorted(self.closure_sources_by_root.get(source, {source}))

    def match_sources(self, tokens: list[str], categories: tuple[str, ...]) -> list[str]:
        token_set = set(tokens)
        if not token_set:
            return []
        candidates: list[tuple[int, str]] = []
        pool: set[str] = set()
        for category in categories:
            pool.update(self.sources_by_category.get(category, set()))
        for source in pool:
            overlap = token_set.intersection(self.file_tokens.get(source, set()))
            if not overlap:
                continue
            candidates.append((len(overlap), source))
        if not candidates:
            return []
        max_score = max(score for score, _ in candidates)
        if max_score > 1:
            candidates = [
                (score, source)
                for score, source in candidates
                if score == max_score
            ]
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return unique_strings([source for _, source in candidates])

    def expand_batch_sources(
        self, seeds: list[str], categories: tuple[str, ...]
    ) -> list[str]:
        batch_ids: set[str] = set()
        for source in seeds:
            batch_ids.update(self.batch_ids_by_source.get(source, set()))
        if not batch_ids:
            return []
        expanded: list[str] = []
        for source in self.all_sources:
            if not self.batch_ids_by_source.get(source, set()).intersection(batch_ids):
                continue
            if any(source in self.sources_by_category.get(category, set()) for category in categories):
                expanded.append(source)
        return unique_strings(expanded)

    def match_tests(self, tokens: list[str]) -> list[str]:
        token_set = set(tokens)
        if not token_set:
            return []
        matches: list[tuple[int, str]] = []
        for source in self.test_records_by_source:
            overlap = token_set.intersection(self.file_tokens.get(source, set()))
            if overlap:
                matches.append((len(overlap), source))
        if not matches:
            return []
        max_score = max(score for score, _ in matches)
        if max_score > 1:
            matches = [
                (score, source)
                for score, source in matches
                if score == max_score
            ]
        matches.sort(key=lambda item: (-item[0], item[1]))
        return unique_strings([source for _, source in matches])

    def match_resources(
        self, tokens: list[str], module_prefixes: set[str] | None = None
    ) -> list[str]:
        token_set = set(tokens)
        matches: list[tuple[int, str]] = []
        for source in self.resource_records_by_source:
            score = 0
            if token_set:
                score += len(token_set.intersection(self.file_tokens.get(source, set())))
            if module_prefixes and module_prefix(source) in module_prefixes:
                score += 1
            if score:
                matches.append((score, source))
        matches.sort(key=lambda item: (-item[0], item[1]))
        return unique_strings([source for _, source in matches])

    def derive_names(self, category: str, sources: list[str]) -> list[str]:
        names: set[str] = set()
        for source in sources:
            names.update(self.names_by_category.get(category, {}).get(source, set()))
        return sorted(names)

    def derive_composables(self, sources: list[str]) -> list[str]:
        names: set[str] = set()
        for source in sources:
            names.update(self.composable_names_by_source.get(source, set()))
        return sorted(names)

    def derive_tests(self, sources: list[str]) -> list[dict[str, Any]]:
        tests: list[dict[str, Any]] = []
        for source in sorted(set(sources)):
            for record in self.test_records_by_source.get(source, []):
                tests.append(
                    {
                        "source": record["source"],
                        "test_names": sorted(set(record["test_names"])),
                    }
                )
        return tests

    def derive_resources(self, sources: list[str]) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        for source in sorted(set(sources)):
            records = self.resource_records_by_source.get(source)
            if records:
                resources.extend(records)
                continue
            if source.endswith((".xml", ".json")) and "/res/" in source:
                resources.append(
                    {
                        "source": source,
                        "name": Path(source).stem,
                        "type": "source_file",
                    }
                )
        return resources

    def derive_platform(self, sources: list[str], tokens: list[str]) -> list[str]:
        source_set = set(sources)
        token_set = set(tokens)
        matched: set[str] = set()
        for capability in self.capabilities:
            capability_id = capability.get("id")
            if not isinstance(capability_id, str):
                continue
            capability_sources = {
                source
                for source in capability.get("source_files", [])
                if isinstance(source, str)
            }
            if source_set.intersection(capability_sources):
                matched.add(capability_id)
                continue
            if token_set.intersection(path_tokens(capability_id)):
                matched.add(capability_id)
        return sorted(matched)

    def derive_batch_ids(self, sources: list[str]) -> list[str]:
        batch_ids: set[str] = set()
        for source in sources:
            batch_ids.update(self.batch_ids_by_source.get(source, set()))
        return sorted(batch_ids)

    def choose_screen(self, preferred: str | None, sources: list[str]) -> str | None:
        if preferred:
            return preferred
        for name in self.derive_composables(sources):
            if any(name.endswith(suffix) for suffix in ("Screen", "Page", "Dialog", "Form")):
                return name
        for source in sources:
            stem = Path(source).stem
            if stem:
                return stem
        return None

    def claim(
        self, primary_candidates: list[str], related_candidates: list[str]
    ) -> tuple[list[str], list[str]]:
        primary: list[str] = []
        related: list[str] = []
        seen: set[str] = set()
        for source in primary_candidates:
            if source not in self.all_sources or source in seen:
                continue
            seen.add(source)
            if source in self.unassigned:
                primary.append(source)
                self.unassigned.remove(source)
            else:
                related.append(source)
        for source in related_candidates:
            if source not in self.all_sources or source in seen:
                continue
            seen.add(source)
            related.append(source)
        return primary, related

    def make_item(
        self,
        *,
        item_id: str,
        title: str,
        kind: str,
        route: str | None,
        screen: str | None,
        primary_candidates: list[str],
        related_candidates: list[str],
        candidate_basis: list[str],
        platform_hint: str | None = None,
    ) -> dict[str, Any] | None:
        primary, related = self.claim(primary_candidates, related_candidates)
        if not primary:
            return None
        descriptor_sources = primary + related
        platform = self.derive_platform(descriptor_sources, split_tokens(platform_hint or route or screen or title))
        if platform_hint:
            platform = sorted(set(platform + [platform_hint]))
        return {
            "id": item_id,
            "title": title,
            "kind": kind,
            "status": "pending",
            "candidate": True,
            "route": route,
            "screen": self.choose_screen(screen, descriptor_sources),
            "composable": self.derive_composables(descriptor_sources),
            "state": self.derive_names("state", descriptor_sources),
            "viewmodel": self.derive_names("viewmodel", descriptor_sources),
            "usecase": self.derive_names("usecase", descriptor_sources),
            "repository": self.derive_names("repository", descriptor_sources),
            "data": self.derive_names("data", descriptor_sources),
            "platform": platform,
            "resources": self.derive_resources(descriptor_sources),
            "tests": self.derive_tests(descriptor_sources),
            "source_files": primary,
            "related_source_files": related,
            "required_gates": list(REQUIRED_GATES),
            "batch_ids": self.derive_batch_ids(descriptor_sources),
            "candidate_basis": candidate_basis,
        }


def build_route_items(index: ContractIndex) -> list[dict[str, Any]]:
    ui = index.contract.get("ui", {})
    if not isinstance(ui, dict):
        return []
    items: list[dict[str, Any]] = []
    for route in sorted(
        [item for item in ui.get("routes", []) if isinstance(item, dict)],
        key=lambda item: (str(item.get("source", "")), str(item.get("route", ""))),
    ):
        route_value = route.get("route")
        if not isinstance(route_value, str):
            continue
        tokens = split_tokens(route_value)
        route_source = route.get("source") if isinstance(route.get("source"), str) else None
        declared_in = (
            route.get("declared_in") if isinstance(route.get("declared_in"), str) else None
        )
        primary_candidates: list[str] = []
        if route_source is not None:
            primary_candidates.append(route_source)
        if declared_in is not None and declared_in != route_source:
            primary_candidates.append(declared_in)
        for source in index.match_sources(tokens, ("ui",)):
            primary_candidates.extend(index.closure_sources_for(source))
        matched_viewmodels = index.match_sources(tokens, ("viewmodel",))
        if not matched_viewmodels:
            matched_viewmodels = index.expand_batch_sources(
                primary_candidates,
                ("viewmodel",),
            )
        matched_states = index.match_sources(tokens, ("state",))
        if not matched_states:
            matched_states = index.expand_batch_sources(
                primary_candidates,
                ("state",),
            )
        primary_candidates.extend(matched_viewmodels + matched_states)
        module_prefixes = {module_prefix(source) for source in primary_candidates}
        enriched_tokens = sorted(
            {
                token
                for source in primary_candidates
                for token in index.file_tokens.get(source, set())
            }.union(tokens)
        )
        related_candidates = index.match_sources(tokens, ("repository", "usecase", "data"))
        if related_candidates:
            related_candidates.extend(
                index.expand_batch_sources(related_candidates, ("repository",))
            )
            related_candidates.extend(
                index.expand_batch_sources(related_candidates, ("usecase", "data"))
            )
        related_candidates.extend(index.match_tests(enriched_tokens))
        related_candidates.extend(index.match_resources(enriched_tokens, module_prefixes))
        item = index.make_item(
            item_id=f"route-{slugify(route_value)}",
            title=f"Route {route_value}",
            kind="route",
            route=route_value,
            screen=None,
            primary_candidates=primary_candidates,
            related_candidates=related_candidates,
            candidate_basis=[
                "ui.routes",
                "ui.composables",
                "ui.custom_composable_call_graph",
                "migration_batches",
            ],
        )
        if item is not None:
            items.append(item)
    return items


def build_activity_items(index: ContractIndex) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for activity in sorted(index.activities, key=lambda item: str(item.get("name", ""))):
        name = activity.get("name")
        if not isinstance(name, str):
            continue
        tokens = split_tokens(name)
        source = activity.get("source") if isinstance(activity.get("source"), str) else None
        activity_key = name.rsplit(".", 1)[-1]
        primary_candidates: list[str] = []
        if source is not None:
            primary_candidates.append(source)
        primary_candidates.extend(
            sorted(index.activity_layout_sources_by_activity.get(activity_key, set()))
        )
        primary_candidates.extend(
            sorted(index.activity_sources_by_graph.get(activity_key, set()))
        )
        related_candidates = index.match_resources(
            tokens, {module_prefix(candidate) for candidate in primary_candidates}
        )
        item = index.make_item(
            item_id=f"activity-{slugify(name)}",
            title=f"Activity {activity_key}",
            kind="android-activity",
            route=None,
            screen=name,
            primary_candidates=primary_candidates,
            related_candidates=related_candidates,
            candidate_basis=[
                "ui.android_activity_inventory",
                "ui.android_view_layout_inventory",
                "ui.android_navigation_inventory",
            ],
        )
        if item is not None:
            items.append(item)
    return items


def build_destination_items(index: ContractIndex) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in sorted(
        index.destinations,
        key=lambda item: (
            str(item["graph"].get("source", "")),
            str(item["destination"].get("id", "")),
        ),
    ):
        graph = entry["graph"]
        destination = entry["destination"]
        screen = destination.get("class_name") if isinstance(destination.get("class_name"), str) else None
        route = destination.get("id") if isinstance(destination.get("id"), str) else None
        source = index.find_class_source(screen)
        tokens = split_tokens(route) + split_tokens(screen) + split_tokens(
            str(graph.get("name", ""))
        )
        if source is not None:
            tokens.extend(sorted(index.file_tokens.get(source, set())))
        primary_candidates: list[str] = []
        if source is not None:
            primary_candidates.extend(index.closure_sources_for(source))
        matched_viewmodels = index.match_sources(tokens, ("viewmodel",))
        if not matched_viewmodels:
            matched_viewmodels = index.expand_batch_sources(
                primary_candidates,
                ("viewmodel",),
            )
        matched_states = index.match_sources(tokens, ("state",))
        if not matched_states:
            matched_states = index.expand_batch_sources(
                primary_candidates,
                ("state",),
            )
        primary_candidates.extend(matched_viewmodels + matched_states)
        module_prefixes = {module_prefix(candidate) for candidate in primary_candidates}
        enriched_tokens = sorted(
            {
                token
                for source_name in primary_candidates
                for token in index.file_tokens.get(source_name, set())
            }.union(tokens)
        )
        related_candidates = []
        graph_source = graph.get("source")
        if isinstance(graph_source, str):
            related_candidates.append(graph_source)
        related_candidates.extend(index.match_sources(tokens, ("repository", "usecase", "data")))
        related_candidates.extend(index.match_tests(enriched_tokens))
        related_candidates.extend(index.match_resources(enriched_tokens, module_prefixes))
        item = index.make_item(
            item_id=f"destination-{slugify(route or screen)}",
            title=f"Destination {route or screen}",
            kind="android-destination",
            route=route,
            screen=screen,
            primary_candidates=primary_candidates,
            related_candidates=related_candidates,
            candidate_basis=[
                "ui.android_navigation_inventory",
                "ui.custom_composable_call_graph",
                "migration_batches",
            ],
        )
        if item is not None:
            items.append(item)
    return items


def build_binding_adapter_items(index: ContractIndex) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for adapter in sorted(
        index.binding_adapters,
        key=lambda item: (str(item.get("source", "")), str(item.get("function", ""))),
    ):
        source = adapter.get("source")
        function = adapter.get("function")
        if not isinstance(source, str) or not isinstance(function, str):
            continue
        attributes = [
            value for value in adapter.get("attributes", []) if isinstance(value, str)
        ]
        tokens = split_tokens(function) + [
            token for attribute in attributes for token in split_tokens(attribute)
        ]
        item = index.make_item(
            item_id=f"binding-adapter-{slugify(function)}",
            title=f"BindingAdapter {function}",
            kind="binding-adapter",
            route=None,
            screen=function,
            primary_candidates=[source],
            related_candidates=index.match_resources(tokens, {module_prefix(source)}),
            candidate_basis=[
                "ui.android_binding_adapter_inventory",
                "migration_batches",
            ],
        )
        if item is not None:
            items.append(item)
    return items


def build_capability_items(index: ContractIndex) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for capability in sorted(
        index.capabilities,
        key=lambda item: str(item.get("id", "")),
    ):
        capability_id = capability.get("id")
        if not isinstance(capability_id, str):
            continue
        source_files = [
            source
            for source in capability.get("source_files", [])
            if isinstance(source, str)
        ]
        tokens = split_tokens(capability_id)
        related_candidates = index.match_tests(tokens) + index.match_resources(
            tokens, {module_prefix(source) for source in source_files}
        )
        item = index.make_item(
            item_id=f"capability-{slugify(capability_id)}",
            title=f"Platform capability {capability_id}",
            kind="platform-capability",
            route=None,
            screen=None,
            primary_candidates=source_files,
            related_candidates=related_candidates,
            candidate_basis=["platform_capabilities", "migration_batches"],
            platform_hint=capability_id,
        )
        if item is not None:
            items.append(item)
    return items


def build_batch_items(index: ContractIndex) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for batch in sorted(index.batches, key=lambda item: str(item.get("id", ""))):
        batch_id = batch.get("id")
        if not isinstance(batch_id, str) or batch_id == "remaining":
            continue
        source_files = [
            source
            for source in batch.get("source_files", [])
            if isinstance(source, str)
        ]
        if not source_files:
            continue
        goal = batch.get("goal") if isinstance(batch.get("goal"), str) else batch_id
        item = index.make_item(
            item_id=f"batch-{slugify(batch_id)}",
            title=goal,
            kind="batch",
            route=None,
            screen=None,
            primary_candidates=source_files,
            related_candidates=[],
            candidate_basis=["migration_batches"],
        )
        if item is not None:
            items.append(item)
    return items


def generate_backlog(contract: dict[str, Any], contract_sha256: str) -> dict[str, Any]:
    index = ContractIndex(contract)
    items: list[dict[str, Any]] = []
    items.extend(build_route_items(index))
    items.extend(build_activity_items(index))
    items.extend(build_destination_items(index))
    items.extend(build_binding_adapter_items(index))
    items.extend(build_capability_items(index))
    items.extend(build_batch_items(index))
    assigned_primary = unique_strings(
        [source for item in items for source in item["source_files"]]
    )
    return {
        "schema": SCHEMA,
        "generator": "migrate-android-compose-to-harmony",
        "status": "pending",
        "candidate": True,
        "candidate_dispatch_only": True,
        "contract": {
            "schema": contract.get("schema"),
            "inventory_quality": contract.get("inventory_quality"),
            "source_revision": (
                contract.get("source", {})
                .get("git", {})
                .get("revision")
                if isinstance(contract.get("source"), dict)
                else None
            ),
            "sha256": contract_sha256,
        },
        "authoritative_completion_sources": [
            "slice_ledger",
            "inventory_reconciliation",
        ],
        "planning_notes": [
            "Backlog items are candidate dispatch plans only and remain pending until real migration work is executed.",
            "A backlog item does not prove completion; final status must come from slice ledgers plus authoritative inventory reconciliation.",
            "Unsupported or intentionally excluded work still needs an explicit disposition instead of silent omission.",
        ],
        "contract_completion_gates": [
            gate
            for gate in contract.get("completion_gates", [])
            if isinstance(gate, str)
        ],
        "items": items,
        "coverage": {
            "contract_source_file_count": len(index.all_sources),
            "assigned_primary_source_file_count": len(assigned_primary),
            "unassigned_source_file_count": len(index.unassigned),
            "unassigned_source_files": sorted(index.unassigned),
        },
    }


def write_output(path: Path, payload: dict[str, Any]) -> str:
    if path.exists():
        raise BacklogError("output path already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2) + "\n"
    path.write_text(rendered, encoding="utf-8")
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def main() -> int:
    args = parse_args()
    contract_path = Path(args.contract).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    try:
        contract, contract_sha256 = load_contract(contract_path)
        backlog = generate_backlog(contract, contract_sha256)
        output_sha256 = write_output(output_path, backlog)
    except (BacklogError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(output_path),
                "schema": SCHEMA,
                "item_count": len(backlog["items"]),
                "coverage": backlog["coverage"],
                "sha256": output_sha256,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
