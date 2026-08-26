#!/usr/bin/env python3
"""Build a layered Android-to-Harmony capability graph and candidate fact packs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


GRAPH_SCHEMA = "android-to-harmony.capability-graph.v1"
FACT_PACK_SCHEMA = "android-to-harmony.fact-pack.v1"
REVIEW_QUEUE_SCHEMA = "android-to-harmony.review-queue.v1"
CONTRACT_SCHEMA = "android-to-harmony.migration-contract.v1"
REGISTRY_SCHEMA = "android-to-harmony.gate-profile-registry.v1"
SKILL_MANIFEST_SCHEMA = "android-to-harmony.skill-tree-manifest.v1"
CONTRACT_GENERATOR = "migrate-android-compose-to-harmony"
CONTRACT_INVENTORY_QUALITY = "candidate"
DEFAULT_REGISTRY = (
    Path(__file__).resolve().parent.parent / "assets" / "gate-profile-registry.json"
)
TEXT_SOURCE_EXTENSIONS = {
    ".gradle",
    ".java",
    ".json",
    ".kt",
    ".kts",
    ".md",
    ".pro",
    ".properties",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}
TEXT_SOURCE_BASENAMES = {
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "gradlew",
    "gradlew.bat",
}
NON_RUNTIME_MARKERS = (
    ".github/",
    "crowdin",
    "fastlane/",
    "readme",
    "changelog",
    "license",
    "docs/",
    "spotless/",
)
TEST_MARKERS = (
    "/src/test/",
    "/src/androidtest/",
    "/test/",
    "/androidtest/",
)
UI_SYSTEM_MARKERS = (
    "/theme/",
    "/color",
    "/typography",
    "/shape",
    "/dimen",
    "/dimension",
    "/font/",
    "/values/",
    "/drawable/",
    "/mipmap/",
    "/raw/",
    "/assets/",
)
PLATFORM_MARKERS = (
    "/permission",
    "/biometric",
    "/notification",
    "/receiver",
    "/service",
    "/widget",
    "/camera",
    "/location",
    "/share",
    "/bluetooth",
    "/nfc",
    "/lifecycle",
)
STORAGE_MARKERS = (
    "/dao/",
    "/database",
    "/datastore",
    "/preferences",
    "/preference",
    "/store/",
    "/cache/",
    "/local/",
    "/schema",
    "/schemas/",
    "/file/",
    "/fileutils/",
)
NETWORK_MARKERS = (
    "/network/",
    "/api/",
    "/remote/",
    "/retrofit/",
    "/paging",
    "/pagingsource",
    "/dto/",
    "/request",
    "/response",
    "/interceptor",
    "/auth/",
    "/endpoint",
)
PROJECT_MARKERS = (
    "androidmanifest.xml",
    "build.gradle",
    "settings.gradle",
    "network_security_config",
    "backup_rules",
    "data_extraction_rules",
    "proguard",
    "/manifest/",
    "/di/",
    "/module/",
)
PACKAGE_PATTERN = re.compile(r"(?m)^\s*package\s+([A-Za-z0-9_\.]+)")
IMPORT_PATTERN = re.compile(r"(?m)^\s*import\s+([A-Za-z0-9_\.\*]+)")
CLASS_DECLARATION_PATTERN = re.compile(
    r"\b(class|interface|object|sealed\s+class|sealed\s+interface|enum\s+class)\s+([A-Za-z0-9_]+)"
)
CALL_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\s*\(")


class GraphError(RuntimeError):
    """Raised when graph generation inputs are invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a layered Android-to-Harmony capability graph."
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fact-pack-dir", required=True, type=Path)
    parser.add_argument("--gate-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--skill-manifest", type=Path)
    return parser.parse_args()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise GraphError(f"unable to read JSON {path}: {error}") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GraphError(f"invalid JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise GraphError(f"JSON payload must be an object: {path}")
    return payload, raw


def validate_contract(path: Path) -> tuple[dict[str, Any], str]:
    payload, raw = load_json(path)
    if payload.get("schema") != CONTRACT_SCHEMA:
        raise GraphError(
            f"contract schema must be {CONTRACT_SCHEMA!r}; "
            f"received {payload.get('schema')!r}"
        )
    if payload.get("generator") != CONTRACT_GENERATOR:
        raise GraphError(
            f"contract generator must be {CONTRACT_GENERATOR!r}; "
            f"received {payload.get('generator')!r}"
        )
    if payload.get("inventory_quality") != CONTRACT_INVENTORY_QUALITY:
        raise GraphError(
            "contract inventory_quality must be "
            f"{CONTRACT_INVENTORY_QUALITY!r}; received "
            f"{payload.get('inventory_quality')!r}"
        )
    return payload, sha256_bytes(raw)


def validate_registry(path: Path) -> dict[str, Any]:
    payload, _ = load_json(path)
    if payload.get("schema") != REGISTRY_SCHEMA:
        raise GraphError(
            f"gate registry schema must be {REGISTRY_SCHEMA!r}; "
            f"received {payload.get('schema')!r}"
        )
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise GraphError("gate registry must contain non-empty profiles")
    return payload


def load_skill_manifest(path: Path | None) -> str | None:
    if path is None:
        return None
    payload, _ = load_json(path)
    if payload.get("schema") != SKILL_MANIFEST_SCHEMA:
        raise GraphError(
            f"skill manifest schema must be {SKILL_MANIFEST_SCHEMA!r}; "
            f"received {payload.get('schema')!r}"
        )
    digest = payload.get("tree_sha256")
    if not isinstance(digest, str) or not digest:
        raise GraphError("skill manifest is missing tree_sha256")
    return digest


def unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def slugify(value: str) -> str:
    tokens = []
    token = []
    previous_lower = False
    for char in value:
        if char.isalnum():
            if previous_lower and char.isupper():
                tokens.append("".join(token))
                token = [char]
            else:
                token.append(char)
            previous_lower = char.islower()
            continue
        if token:
            tokens.append("".join(token))
            token = []
        previous_lower = False
    if token:
        tokens.append("".join(token))
    if not tokens:
        return "node"
    return "".join(part.lower() for part in tokens if part)


def page_slug(name: str) -> str:
    return slugify(name)


def control_slug(name: str) -> str:
    return slugify(name)


def text_source_supported(source: str) -> bool:
    path = Path(source)
    return (
        path.suffix.lower() in TEXT_SOURCE_EXTENSIONS
        or path.name.lower() in TEXT_SOURCE_BASENAMES
    )


def lower_path(source: str) -> str:
    return source.replace("\\", "/").lower()


def classify_business_layer(source: str, name: str) -> str:
    lower_source = source.lower()
    lower_name = name.lower()
    if "repository" in lower_name or "repository" in lower_source:
        return "business"
    if "viewmodel" in lower_name or "viewmodel" in lower_source:
        return "business"
    if "state" in lower_name or "state" in lower_source:
        return "business"
    return "business"


def classify_data_layer(source: str, name: str) -> str | None:
    lower_source = source.lower()
    lower_name = name.lower()
    if any(marker in lower_source for marker in ("/database", "/dao/", "/store/", "/cache/")):
        return "storage"
    if "database" in lower_name or "dao" in lower_name or "store" in lower_name:
        return "storage"
    if any(marker in lower_source for marker in ("/network/", "/api", "/service/", "/request", "/response/", "/remote/")):
        return "network"
    if any(marker in lower_name for marker in ("api", "service", "interceptor", "remote")):
        return "network"
    return None


def looks_like_repository_interface(source: str, name: str) -> bool:
    lower_source = lower_path(source)
    lower_name = name.lower()
    if "repository" not in lower_name and "repository" not in lower_source:
        return False
    return not any(
        marker in lower_name or marker in lower_source
        for marker in ("impl", "/remote/", "/local/", "network", "database", "preferences")
    )


def classify_model_layer(source: str, name: str, kind: str | None) -> str:
    lower_source = lower_path(source)
    lower_name = name.lower()
    lower_kind = (kind or "").lower()
    if looks_like_repository_interface(source, name):
        return "business"
    if any(marker in lower_source for marker in STORAGE_MARKERS):
        return "storage"
    if any(marker in lower_source for marker in NETWORK_MARKERS):
        return "network"
    if any(marker in lower_name for marker in ("pagingsource", "dto", "api", "interceptor", "remote")):
        return "network"
    if any(marker in lower_name for marker in ("database", "dao", "entity", "preferences", "datastore", "migration")):
        return "storage"
    if any(marker in lower_name for marker in ("usecase", "viewmodel", "state", "intent", "reducer", "repository", "helper")):
        return "business"
    if "data class" in lower_kind or "enum" in lower_kind or "sealed" in lower_kind or "model" in lower_name:
        return "business"
    return classify_business_layer(source, name)


def classify_remaining_source(
    contract: dict[str, Any],
    source: str,
) -> tuple[str, str, str, list[dict[str, str]], str | None, dict[str, Any]]:
    lower_source = lower_path(source)
    name = Path(source).stem
    base_name = Path(source).name.lower()
    if any(marker in lower_source for marker in TEST_MARKERS) or any(
        token in name.lower() for token in ("test", "fake", "mock", "fixture")
    ):
        return (
            "test_support",
            "test-support",
            "intentionally_excluded",
            [],
            "test-support only; not production migration scope",
            build_classification(
                layer="test_support",
                gate_profile="test-support",
                confidence="high",
                priority=140,
                primary_rule="source_set_test_support",
                supporting_evidence=[
                    {"kind": "path", "detail": "test source set or Fake/Mock/Test naming"}
                ],
            ),
        )
    if (
        any(marker in lower_source for marker in NON_RUNTIME_MARKERS)
        or Path(source).suffix.lower() in {".md", ".txt"}
        or base_name in {".gitignore", ".gitattributes", ".editorconfig"}
    ):
        return (
            "project_support",
            "project-support",
            "intentionally_excluded",
            [],
            "non-runtime documentation or metadata",
            build_classification(
                layer="project_support",
                gate_profile="project-support",
                confidence="high",
                priority=140,
                primary_rule="non_runtime_metadata",
                supporting_evidence=[
                    {"kind": "path", "detail": "documentation or metadata path/extension"}
                ],
            ),
        )
    semantic = semantic_classification(source, read_source_text(contract, source))
    if semantic is not None:
        return (
            semantic["layer"],
            semantic["gate_profile"],
            "candidate",
            [],
            semantic.get("rationale"),
            semantic,
        )
    if any(
        token in name.lower()
        for token in ("api", "response", "request", "dto", "interceptor", "paging", "remote")
    ):
        return (
            "network",
            "network",
            "candidate",
            [],
            None,
            build_classification(
                layer="network",
                gate_profile="network",
                confidence="medium",
                priority=50,
                primary_rule="path_network",
                supporting_evidence=[{"kind": "path", "detail": "network-like file name"}],
            ),
        )
    if any(token in name.lower() for token in ("pref", "preference", "datastore")):
        return (
            "storage",
            "storage",
            "candidate",
            [],
            None,
            build_classification(
                layer="storage",
                gate_profile="storage",
                confidence="medium",
                priority=50,
                primary_rule="path_storage",
                supporting_evidence=[{"kind": "path", "detail": "storage-like file name"}],
            ),
        )
    if any(
        token in name.lower()
        for token in ("viewmodel", "usecase", "state", "intent", "reducer", "repository", "helper")
    ):
        if any(
            token in name.lower() for token in ("settings", "pref", "preference", "datastore", "file")
        ):
            return (
                "storage",
                "storage",
                "candidate",
                [],
                None,
                build_classification(
                    layer="storage",
                    gate_profile="storage",
                    confidence="medium",
                    priority=45,
                    primary_rule="path_storage_helper",
                    supporting_evidence=[{"kind": "path", "detail": "settings/preferences/file helper naming"}],
                ),
            )
        if "/data/app/" in lower_source and "repository" in name.lower():
            return (
                "storage",
                "storage",
                "candidate",
                [],
                None,
                build_classification(
                    layer="storage",
                    gate_profile="storage",
                    confidence="medium",
                    priority=45,
                    primary_rule="path_storage_repository",
                    supporting_evidence=[{"kind": "path", "detail": "data/app repository naming"}],
                ),
            )
        return (
            "business",
            "business",
            "candidate",
            [],
            None,
            build_classification(
                layer="business",
                gate_profile="business",
                confidence="medium",
                priority=45,
                primary_rule="path_business",
                supporting_evidence=[{"kind": "path", "detail": "ViewModel/use-case/state/helper naming"}],
            ),
        )
    if any(marker in lower_source for marker in UI_SYSTEM_MARKERS):
        return (
            "ui_system",
            "ui-system",
            "candidate",
            [],
            None,
            build_classification(
                layer="ui_system",
                gate_profile="ui-system",
                confidence="medium",
                priority=40,
                primary_rule="path_ui_system",
                supporting_evidence=[{"kind": "path", "detail": "theme/resource/style path"}],
                candidate_layers=["ui_system", "control"],
            ),
        )
    if any(marker in lower_source for marker in PLATFORM_MARKERS) and not any(
        marker in lower_source for marker in NETWORK_MARKERS
    ):
        return (
            "platform",
            "platform",
            "candidate",
            [],
            None,
            build_classification(
                layer="platform",
                gate_profile="platform",
                confidence="medium",
                priority=40,
                primary_rule="path_platform",
                supporting_evidence=[{"kind": "path", "detail": "platform capability path"}],
            ),
        )
    if any(marker in lower_source for marker in STORAGE_MARKERS):
        return (
            "storage",
            "storage",
            "candidate",
            [],
            None,
            build_classification(
                layer="storage",
                gate_profile="storage",
                confidence="medium",
                priority=40,
                primary_rule="path_storage",
                supporting_evidence=[{"kind": "path", "detail": "storage path marker"}],
            ),
        )
    if any(marker in lower_source for marker in NETWORK_MARKERS):
        return (
            "network",
            "network",
            "candidate",
            [],
            None,
            build_classification(
                layer="network",
                gate_profile="network",
                confidence="medium",
                priority=40,
                primary_rule="path_network",
                supporting_evidence=[{"kind": "path", "detail": "network path marker"}],
            ),
        )
    if base_name in {"gradlew", "gradlew.bat"} or lower_source.endswith(".properties"):
        return (
            "project",
            "project",
            "candidate",
            [],
            None,
            build_classification(
                layer="project",
                gate_profile="project",
                confidence="medium",
                priority=40,
                primary_rule="path_project_build",
                supporting_evidence=[{"kind": "path", "detail": "build tooling file"}],
            ),
        )
    if any(marker in lower_source for marker in PROJECT_MARKERS):
        return (
            "project",
            "project",
            "candidate",
            [],
            None,
            build_classification(
                layer="project",
                gate_profile="project",
                confidence="medium",
                priority=40,
                primary_rule="path_project_config",
                supporting_evidence=[{"kind": "path", "detail": "project wiring/config path"}],
            ),
        )
    if (
        name.lower().endswith("application")
        or name.lower().endswith("activity")
        or name.lower().endswith("app")
        or "module" in name.lower()
    ):
        return (
            "project",
            "project",
            "candidate",
            [],
            None,
            build_classification(
                layer="project",
                gate_profile="project",
                confidence="medium",
                priority=35,
                primary_rule="path_project_entry",
                supporting_evidence=[{"kind": "name", "detail": "application/activity/module naming"}],
            ),
        )
    if lower_source.endswith(".gradle") or lower_source.endswith(".kts") or lower_source.endswith(".pro"):
        return (
            "project",
            "project",
            "candidate",
            [],
            None,
            build_classification(
                layer="project",
                gate_profile="project",
                confidence="medium",
                priority=35,
                primary_rule="path_project_build_script",
                supporting_evidence=[{"kind": "extension", "detail": "Gradle/Proguard build script"}],
            ),
        )
    if "/res/layout/" in lower_source or name.lower().endswith("screen") or name.lower().endswith("fragment"):
        return (
            "page",
            "page",
            "candidate",
            [],
            None,
            build_classification(
                layer="page",
                gate_profile="page",
                confidence="medium",
                priority=35,
                primary_rule="path_page",
                supporting_evidence=[{"kind": "path", "detail": "layout/screen/fragment naming"}],
            ),
        )
    if any(
        token in name.lower()
        for token in ("model", "result", "option", "options", "entry", "item", "source")
    ) or name.lower().endswith("ui"):
        return (
            "business",
            "business",
            "candidate",
            [],
            None,
            build_classification(
                layer="business",
                gate_profile="business",
                confidence="low",
                priority=20,
                primary_rule="path_business_model",
                supporting_evidence=[{"kind": "name", "detail": "generic business/model naming"}],
            ),
        )
    return (
        "unclassified",
        "unclassified-production",
        "candidate",
        [
            {
                "kind": "classification",
                "reason": "unable to classify production source file deterministically",
            }
        ],
        None,
        build_classification(
            layer="unclassified",
            gate_profile="unclassified-production",
            confidence="low",
            priority=0,
            primary_rule="review_queue_required",
            supporting_evidence=[],
            candidate_layers=infer_candidate_layers_from_path(source),
        ),
    )


def read_source_text(contract: dict[str, Any], source_path: str) -> str | None:
    source = contract.get("source", {})
    if not isinstance(source, dict):
        return None
    for key in ("safe_snapshot_root", "original_root"):
        root = source.get(key)
        if not isinstance(root, str) or not root:
            continue
        candidate = Path(root) / source_path
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return None


def build_classification(
    *,
    layer: str,
    gate_profile: str,
    confidence: str,
    priority: int,
    primary_rule: str,
    supporting_evidence: list[dict[str, str]],
    opposing_evidence: list[dict[str, str]] | None = None,
    candidate_layers: list[str] | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    return {
        "layer": layer,
        "gate_profile": gate_profile,
        "confidence": confidence,
        "priority": priority,
        "primary_rule": primary_rule,
        "supporting_evidence": supporting_evidence,
        "opposing_evidence": opposing_evidence or [],
        "candidate_layers": candidate_layers or [layer],
        "rationale": rationale,
    }


def infer_candidate_layers_from_path(source: str) -> list[str]:
    lower_source = lower_path(source)
    candidates: list[str] = []
    if "/navigation/" in lower_source or "route" in lower_source or "destination" in lower_source:
        candidates.extend(["page", "project"])
    if "/theme/" in lower_source or any(
        token in lower_source for token in ("/shape", "/color", "/typography", "/style")
    ):
        candidates.extend(["ui_system", "control"])
    if "/security/" in lower_source or "/biometric" in lower_source or "crypto" in lower_source:
        candidates.extend(["platform", "business"])
    if "/data/" in lower_source:
        candidates.extend(["business", "network", "storage"])
    if "/ui/" in lower_source:
        candidates.extend(["page", "ui_system"])
    if not candidates:
        candidates.extend(["business", "page", "ui_system"])
    return unique_sorted(candidates)


def semantic_classification(source: str, text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    imports = IMPORT_PATTERN.findall(text)
    lower_imports = [value.lower() for value in imports]
    lower_text = text.lower()
    package_match = PACKAGE_PATTERN.search(text)
    package_name = package_match.group(1).lower() if package_match else ""
    file_name = Path(source).stem
    lower_name = file_name.lower()
    candidates: list[dict[str, Any]] = []

    def add(
        *,
        layer: str,
        gate_profile: str,
        confidence: str,
        priority: int,
        primary_rule: str,
        reasons: list[str],
        candidate_layers: list[str] | None = None,
    ) -> None:
        candidates.append(
            build_classification(
                layer=layer,
                gate_profile=gate_profile,
                confidence=confidence,
                priority=priority,
                primary_rule=primary_rule,
                supporting_evidence=[
                    {"kind": "semantic", "detail": reason} for reason in reasons
                ],
                candidate_layers=candidate_layers,
            )
        )

    if any(token in lower_text for token in ("org.junit", "@test", "mockk", "mockito")):
        add(
            layer="test_support",
            gate_profile="test-support",
            confidence="high",
            priority=130,
            primary_rule="semantic_test_support",
            reasons=["JUnit or mocking imports/annotations in source text"],
        )
    if (
        any(token in lower_text for token in ("@dao", "@database", "@entity", "roomdatabase"))
        or any(token in value for value in lower_imports for token in ("androidx.room", "datastore", "sharedpreferences", "preferences"))
    ):
        add(
            layer="storage",
            gate_profile="storage",
            confidence="high",
            priority=120,
            primary_rule="semantic_storage_annotations",
            reasons=["Room/DataStore/Preferences annotations or imports detected"],
        )
    if (
        any(token in lower_text for token in ("@get(", "@post(", "@put(", "@delete(", "@patch("))
        or any(token in value for value in lower_imports for token in ("retrofit2.http", "retrofit2", "okhttp3", "io.ktor", "androidx.paging"))
        or "pagingsource" in lower_text
    ):
        add(
            layer="network",
            gate_profile="network",
            confidence="high",
            priority=120,
            primary_rule="semantic_network_annotations",
            reasons=["Retrofit/Ktor/Paging annotations, imports, or supertypes detected"],
        )
    if (
        any(
            token in lower_text
            for token in (
                "broadcastreceiver",
                "appwidgetprovider",
                "biometricprompt",
                "manifest.permission",
                "cipher",
                "cryptobject",
                "service(",
                ": service",
            )
        )
        or any(
            token in value
            for value in lower_imports
            for token in (
                "android.app.service",
                "android.content.broadcastreceiver",
                "androidx.biometric",
                "javax.crypto",
                "android.appwidget",
            )
        )
    ):
        add(
            layer="platform",
            gate_profile="platform",
            confidence="high",
            priority=120,
            primary_rule="semantic_platform_security",
            reasons=["Platform receiver/service/biometric/crypto APIs detected"],
        )
    if (
        "<paths" in lower_text
        or "fileprovider" in lower_text
        or "cache-path" in lower_text
        or "external-path" in lower_text
    ):
        add(
            layer="platform",
            gate_profile="platform",
            confidence="high",
            priority=118,
            primary_rule="semantic_platform_file_provider",
            reasons=["File-provider paths XML semantics detected"],
        )
    if "<appwidget-provider" in lower_text or "app_widget_provider" in lower_text:
        add(
            layer="platform",
            gate_profile="platform",
            confidence="high",
            priority=118,
            primary_rule="semantic_platform_widget_provider",
            reasons=["App widget provider XML semantics detected"],
        )
    if "<locale-config" in lower_text:
        add(
            layer="project",
            gate_profile="project",
            confidence="high",
            priority=118,
            primary_rule="semantic_project_locale_config",
            reasons=["Locale configuration XML semantics detected"],
        )
    if (
        any(
            token in value
            for value in lower_imports
            for token in (
                "androidx.compose.ui.graphics",
                "androidx.compose.ui.text",
                "androidx.compose.foundation.shape",
                "androidx.compose.material3.colorscheme",
            )
        )
        or any(
            token in lower_text
            for token in (
                ": shape",
                "cornersbasedshape",
                "drawscope",
                "textstyle",
                "colorscheme",
                "brush",
            )
        )
    ):
        add(
            layer="ui_system",
            gate_profile="ui-system",
            confidence="high",
            priority=115,
            primary_rule="semantic_ui_theme",
            reasons=["Compose theme/shape/color/text-style imports or supertypes detected"],
            candidate_layers=["ui_system", "control"],
        )
    if (
        "@composable" in lower_text
        and any("androidx.compose" in value for value in lower_imports)
        and any(
            token in lower_text
            for token in (
                "row(",
                "row {",
                "column(",
                "column {",
                "box(",
                "box {",
                "lazycolumn(",
                "lazycolumn {",
                "surface(",
                "surface {",
            )
        )
    ):
        add(
            layer="page",
            gate_profile="page",
            confidence="high",
            priority=117,
            primary_rule="semantic_compose_page",
            reasons=["Composable function with Compose UI layout calls detected"],
            candidate_layers=["page", "control"],
        )
    if (
        "ui.harmonize" in package_name
        or "harmonize(" in lower_text
        or any(token in lower_text for token in ("colorutils", "cam16", "viewingconditions", "corepalette", "tonalpalette"))
    ):
        add(
            layer="ui_system",
            gate_profile="ui-system",
            confidence="high",
            priority=116,
            primary_rule="semantic_ui_color_harmonization",
            reasons=["Color harmonization utilities and color-model helpers detected"],
            candidate_layers=["ui_system", "control"],
        )
    if (
        any("androidx.navigation" in value for value in lower_imports)
        or "navcontroller" in lower_text
        or (
            any(token in lower_name for token in ("route", "destination", "page"))
            and any(token in lower_text for token in ("route", "destination", "navhost", "navcontroller"))
        )
        or (
            "navigation" in package_name
            and any(token in lower_name for token in ("route", "destination", "navigation", "page", "iconpair"))
        )
    ):
        add(
            layer="page",
            gate_profile="page",
            confidence="high",
            priority=110,
            primary_rule="semantic_navigation",
            reasons=["Navigation imports and route/destination/page semantics detected"],
            candidate_layers=["page", "project"],
        )
    if (
        any(token in lower_imports for token in ("example.domain.moneyamount",))
        or "domain." in lower_text
        or any(token in lower_name for token in ("moneyextensions", "collectionextensions", "stringextensions"))
    ) and not any("androidx.compose" in value for value in lower_imports):
        add(
            layer="business",
            gate_profile="business",
            confidence="medium",
            priority=95,
            primary_rule="semantic_business_domain_helper",
            reasons=["Domain imports or business helper extension semantics detected"],
        )
    if "uitext" in lower_text and any(token in lower_text for token in ("stringresource", "r.string", "errortype")):
        add(
            layer="ui_system",
            gate_profile="ui-system",
            confidence="medium",
            priority=92,
            primary_rule="semantic_ui_error_mapping",
            reasons=["UI text/resource error mapping semantics detected"],
            candidate_layers=["ui_system", "business"],
        )
    if (
        any(token in lower_text for token in ("datetimeformatter", "decimalformat", "numberformat", "simpledateformat", "localdate", "localtime", "bigdecimal"))
        and not any("androidx.compose" in value for value in lower_imports)
    ):
        add(
            layer="business",
            gate_profile="business",
            confidence="medium",
            priority=90,
            primary_rule="semantic_business_formatting",
            reasons=["Domain formatting/time/number helpers detected without UI imports"],
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item["priority"], item["layer"]))
    selected = dict(candidates[0])
    selected["opposing_evidence"] = [
        {
            "layer": candidate["layer"],
            "primary_rule": candidate["primary_rule"],
        }
        for candidate in candidates[1:]
    ]
    if package_name:
        selected["supporting_evidence"].append(
            {"kind": "package", "detail": f"package {package_name}"}
        )
    declarations = [match.group(2) for match in CLASS_DECLARATION_PATTERN.finditer(text)]
    if declarations:
        selected["supporting_evidence"].append(
            {"kind": "declaration", "detail": ", ".join(sorted(declarations[:4]))}
        )
    calls = sorted({match.group(1) for match in CALL_PATTERN.finditer(text)})
    if calls:
        selected["supporting_evidence"].append(
            {"kind": "calls", "detail": ", ".join(calls[:6])}
        )
    return selected


def compose_review_queue_entry(
    source_path: str,
    classification: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "source_path": source_path,
        "candidate_layers": (
            list(classification.get("candidate_layers", []))
            if isinstance(classification, dict)
            else infer_candidate_layers_from_path(source_path)
        ),
        "supporting_evidence": (
            list(classification.get("supporting_evidence", []))
            if isinstance(classification, dict)
            else []
        ),
        "opposing_evidence": (
            list(classification.get("opposing_evidence", []))
            if isinstance(classification, dict)
            else []
        ),
        "confidence": (
            str(classification.get("confidence"))
            if isinstance(classification, dict) and classification.get("confidence")
            else "low"
        ),
        "why_not_auto_classified": "semantic and heuristic evidence were insufficient for a single high-confidence primary owner",
        "blocking_parent_gates": ["project.child_dispositions"],
    }


def choose_control_profile(name: str, mapping_id: str | None) -> tuple[str, str | None]:
    token = f"{name} {mapping_id or ''}".lower()
    if any(keyword in token for keyword in ("picker", "menu", "dropdown", "select")):
        family = "picker" if "picker" in token else "menu"
        return "stateful-control-family", family
    return "stateless-control", None


def required_profile_fields(
    registry: dict[str, Any],
    profile: str,
) -> tuple[list[str], list[str]]:
    profiles = registry["profiles"]
    value = profiles.get(profile)
    if not isinstance(value, dict):
        raise GraphError(f"missing gate profile: {profile}")
    required_gates = value.get("required_gates")
    required_tests = value.get("required_tests")
    if not isinstance(required_gates, list) or not all(
        isinstance(item, str) for item in required_gates
    ):
        raise GraphError(f"gate profile {profile} has invalid required_gates")
    if not isinstance(required_tests, list) or not all(
        isinstance(item, str) for item in required_tests
    ):
        raise GraphError(f"gate profile {profile} has invalid required_tests")
    return list(required_gates), list(required_tests)


def make_node(
    *,
    node_id: str,
    layer: str,
    parent_id: str | None,
    status: str,
    source_revision: str,
    contract_sha256: str,
    skill_tree_digest: str | None,
    source_evidence: list[str],
    required_semantics: list[str],
    gate_profile: str,
    required_gates: list[str],
    required_tests: list[str],
    applicability: str,
    unresolved: list[dict[str, Any]] | list[Any],
    evidence_references: list[str],
    rationale: str | None = None,
    decision_owner: str | None = None,
    primary_source_files: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    node = {
        "id": node_id,
        "layer": layer,
        "parent_id": parent_id,
        "child_ids": [],
        "status": status,
        "source_revision": source_revision,
        "contract_sha256": contract_sha256,
        "skill_tree_digest": skill_tree_digest,
        "source_evidence": unique_sorted(source_evidence),
        "primary_source_files": unique_sorted(primary_source_files or []),
        "cross_reference_source_files": unique_sorted(
            [path for path in source_evidence if path not in set(primary_source_files or [])]
        ),
        "required_semantics": required_semantics,
        "selected_skill": "migrate-android-compose-to-harmony",
        "gate_profile": gate_profile,
        "required_gates": required_gates,
        "required_tests": required_tests,
        "applicability": applicability,
        "unresolved": unresolved,
        "evidence_references": evidence_references,
    }
    if rationale:
        node["rationale"] = rationale
    if decision_owner:
        node["decision_owner"] = decision_owner
    node.update(extra)
    return node


def assign_primary(
    node: dict[str, Any],
    source_paths: list[str],
    owners: dict[str, str],
) -> None:
    primary = []
    for source_path in unique_sorted(source_paths):
        if source_path in owners:
            continue
        owners[source_path] = node["id"]
        primary.append(source_path)
    node["primary_source_files"] = primary
    node["cross_reference_source_files"] = unique_sorted(
        [path for path in node.get("source_evidence", []) if path not in set(primary)]
    )


def unique_node_id(base: str, nodes_by_id: dict[str, dict[str, Any]]) -> str:
    node_id = base
    index = 2
    while node_id in nodes_by_id:
        node_id = f"{base}-{index}"
        index += 1
    return node_id


def build_review_queue(
    graph: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    entries = []
    for node in nodes:
        if node.get("layer") != "unclassified":
            continue
        source_files = node.get("primary_source_files", [])
        if not source_files:
            continue
        source_path = source_files[0]
        entries.append(
            compose_review_queue_entry(
                source_path,
                node.get("classification")
                if isinstance(node.get("classification"), dict)
                else None,
            )
        )
    entries.sort(key=lambda item: item["source_path"])
    return {
        "schema": REVIEW_QUEUE_SCHEMA,
        "source_revision": graph.get("source_revision"),
        "contract_sha256": graph.get("contract_sha256"),
        "skill_tree_digest": graph.get("skill_tree_digest"),
        "entry_count": len(entries),
        "unclassified_source_files": [entry["source_path"] for entry in entries],
        "entries": entries,
    }


def source_stem_slug(source_path: str) -> str:
    return slugify(Path(source_path).stem)


def semantic_match_key(value: str) -> str:
    key = source_stem_slug(value)
    for suffix in (
        "screen",
        "page",
        "fragment",
        "activity",
        "viewmodel",
        "repository",
        "database",
        "api",
        "test",
        "state",
        "form",
    ):
        if key.endswith(suffix) and len(key) > len(suffix):
            key = key[: -len(suffix)]
            break
    return key


def node_primary_sources(node: dict[str, Any]) -> list[str]:
    return [
        source
        for source in node.get("primary_source_files", [])
        if isinstance(source, str) and source
    ]


def route_sources(contract: dict[str, Any]) -> dict[str, str]:
    ui = contract.get("ui", {})
    if not isinstance(ui, dict):
        return {}
    routes = ui.get("routes", [])
    if not isinstance(routes, list):
        return {}
    mapping: dict[str, str] = {}
    for route in routes:
        if not isinstance(route, dict):
            continue
        source = route.get("source")
        route_value = route.get("route")
        if isinstance(source, str) and isinstance(route_value, str) and source and route_value:
            mapping[source] = route_value
    return mapping


def infer_root_qualifications(
    contract: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    route_by_source = route_sources(contract)
    qualifications: list[dict[str, Any]] = []
    for node in sorted(nodes, key=lambda item: item["id"]):
        layer = node.get("layer")
        source_files = node_primary_sources(node)
        source_path = source_files[0] if source_files else (
            node.get("source_evidence", [""])[0]
            if isinstance(node.get("source_evidence"), list) and node.get("source_evidence")
            else ""
        )
        source_symbol = Path(source_path).stem if source_path else node["id"]
        qualified = False
        qualification_kind = "non_root_child"
        evidence: dict[str, str] = {"kind": "classification", "detail": str(layer)}
        if layer == "page":
            if source_path in route_by_source:
                qualified = True
                qualification_kind = "route_inventory_root"
                evidence = {"kind": "route", "detail": route_by_source[source_path]}
            elif any(
                token in source_symbol.lower()
                for token in ("screen", "activity", "fragment", "page")
            ):
                qualified = True
                qualification_kind = "entry_screen_root"
                evidence = {"kind": "entry", "detail": source_symbol}
            else:
                qualification_kind = "non_root_page"
        qualifications.append(
            {
                "node_id": node["id"],
                "qualified_as_root": qualified,
                "qualification_kind": qualification_kind,
                "source_path": source_path,
                "source_symbol": source_symbol,
                "evidence": evidence,
            }
        )
    return qualifications


def infer_resolved_edges(
    contract: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    nodes_by_id = {
        node["id"]: node for node in nodes if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    route_by_source = route_sources(contract)
    page_nodes = [node for node in nodes if node.get("layer") == "page"]
    source_to_page_ids: dict[str, list[str]] = {}
    for node in page_nodes:
        for source in node_primary_sources(node):
            source_to_page_ids.setdefault(source, []).append(node["id"])
    batch_memberships: dict[str, list[dict[str, Any]]] = {}
    batches = contract.get("migration_batches", [])
    if isinstance(batches, list):
        for batch in batches:
            if not isinstance(batch, dict):
                continue
            for source in batch.get("source_files", []):
                if isinstance(source, str) and source:
                    batch_memberships.setdefault(source, []).append(batch)

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_edge(
        *,
        kind: str,
        from_node_id: str,
        to_node_id: str,
        source_path: str,
        source_symbol: str,
        evidence_kind: str,
        evidence_detail: str,
        consumed_by_planner: str,
    ) -> None:
        key = (kind, from_node_id, to_node_id)
        if key in seen:
            return
        seen.add(key)
        edges.append(
            {
                "edge_id": f"edge:{slugify(from_node_id)}:{slugify(kind)}:{slugify(to_node_id)}",
                "kind": kind,
                "from_node_id": from_node_id,
                "to_node_id": to_node_id,
                "source_path": source_path,
                "source_symbol": source_symbol,
                "evidence": {"kind": evidence_kind, "detail": evidence_detail},
                "consumed_by_planner": consumed_by_planner,
            }
        )

    def page_batch_members(page_node: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        source_files = node_primary_sources(page_node)
        if not source_files:
            return [], semantic_match_key(str(page_node.get("id", "")))
        source_path = source_files[0]
        return (
            batch_memberships.get(source_path, []),
            semantic_match_key(route_by_source.get(source_path, source_path)),
        )

    def source_matches_page(page_key: str, node: dict[str, Any], batches_for_page: list[dict[str, Any]]) -> bool:
        node_sources = node_primary_sources(node)
        if batches_for_page:
            batch_sources = {
                path
                for batch in batches_for_page
                for path in batch.get("source_files", [])
                if isinstance(path, str)
            }
            if set(node_sources) & batch_sources:
                return True
        return any(page_key and page_key in semantic_match_key(source) for source in node_sources)

    for page_node in sorted(page_nodes, key=lambda item: item["id"]):
        page_sources = node_primary_sources(page_node)
        if not page_sources:
            continue
        page_source = page_sources[0]
        page_symbol = Path(page_source).stem
        batches_for_page, page_key = page_batch_members(page_node)
        for child_id in page_node.get("child_ids", []):
            child = nodes_by_id.get(child_id)
            if not child or child.get("layer") != "control":
                continue
            add_edge(
                kind="page_declares_control",
                from_node_id=page_node["id"],
                to_node_id=child_id,
                source_path=page_source,
                source_symbol=page_symbol,
                evidence_kind="child",
                evidence_detail=child_id,
                consumed_by_planner="closure_and_assignment",
            )
        matched_business = [
            node
            for node in nodes
            if node.get("layer") == "business"
            and source_matches_page(page_key, node, batches_for_page)
        ]
        matched_network = [
            node
            for node in nodes
            if node.get("layer") == "network"
            and source_matches_page(page_key, node, batches_for_page)
        ]
        matched_storage = [
            node
            for node in nodes
            if node.get("layer") == "storage"
            and source_matches_page(page_key, node, batches_for_page)
        ]
        matched_platform = [
            node
            for node in nodes
            if node.get("layer") == "platform"
            and source_matches_page(page_key, node, batches_for_page)
        ]
        matched_ui = [
            node
            for node in nodes
            if node.get("layer") == "ui_system"
            and source_matches_page(page_key, node, batches_for_page)
        ]
        matched_tests = [
            node
            for node in nodes
            if node.get("layer") == "test_support"
            and source_matches_page(page_key, node, batches_for_page)
        ]

        for node in matched_business:
            add_edge(
                kind="page_uses_business",
                from_node_id=page_node["id"],
                to_node_id=node["id"],
                source_path=page_source,
                source_symbol=page_symbol,
                evidence_kind="batch_or_name",
                evidence_detail=node["id"],
                consumed_by_planner="closure_and_assignment",
            )
            for target in matched_network:
                add_edge(
                    kind="business_uses_repository",
                    from_node_id=node["id"],
                    to_node_id=target["id"],
                    source_path=node_primary_sources(node)[0],
                    source_symbol=Path(node_primary_sources(node)[0]).stem,
                    evidence_kind="batch_or_name",
                    evidence_detail=target["id"],
                    consumed_by_planner="closure_and_assignment",
                )
            for target in matched_storage:
                add_edge(
                    kind="repository_uses_storage",
                    from_node_id=node["id"],
                    to_node_id=target["id"],
                    source_path=node_primary_sources(node)[0],
                    source_symbol=Path(node_primary_sources(node)[0]).stem,
                    evidence_kind="batch_or_name",
                    evidence_detail=target["id"],
                    consumed_by_planner="closure_and_assignment",
                )
        for node in matched_platform:
            add_edge(
                kind="page_uses_platform",
                from_node_id=page_node["id"],
                to_node_id=node["id"],
                source_path=page_source,
                source_symbol=page_symbol,
                evidence_kind="batch_or_name",
                evidence_detail=node["id"],
                consumed_by_planner="closure_and_assignment",
            )
        for node in matched_ui:
            add_edge(
                kind="page_uses_ui_system",
                from_node_id=page_node["id"],
                to_node_id=node["id"],
                source_path=page_source,
                source_symbol=page_symbol,
                evidence_kind="batch_or_name",
                evidence_detail=node["id"],
                consumed_by_planner="closure_and_assignment",
            )
        for node in matched_tests:
            add_edge(
                kind="test_obligation",
                from_node_id=page_node["id"],
                to_node_id=node["id"],
                source_path=node_primary_sources(node)[0],
                source_symbol=Path(node_primary_sources(node)[0]).stem,
                evidence_kind="test",
                evidence_detail=node["id"],
                consumed_by_planner="closure_and_assignment",
            )
    return sorted(edges, key=lambda item: item["edge_id"])


def build_graph(contract: dict[str, Any], contract_sha256: str, registry: dict[str, Any], skill_tree_digest: str | None) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    source = contract.get("source", {})
    if not isinstance(source, dict):
        raise GraphError("contract source must be an object")
    git = source.get("git", {})
    if not isinstance(git, dict):
        raise GraphError("contract source.git must be an object")
    source_revision = git.get("revision")
    if not isinstance(source_revision, str) or not source_revision:
        raise GraphError("contract source.git.revision is required")
    inventory = contract.get("inventory", {})
    if not isinstance(inventory, dict):
        raise GraphError("contract inventory must be an object")
    files_by_layer = inventory.get("files_by_layer", {})
    if not isinstance(files_by_layer, dict):
        raise GraphError("contract inventory.files_by_layer must be an object")
    candidate_source_files = unique_sorted(
        [str(item) for values in files_by_layer.values() if isinstance(values, list) for item in values if isinstance(item, str)]
    )

    nodes: list[dict[str, Any]] = []
    nodes_by_id: dict[str, dict[str, Any]] = {}
    parent_children: dict[str, list[str]] = {}
    primary_owners: dict[str, str] = {}

    project_id = f"project:{source_revision}"
    project_gates, project_tests = required_profile_fields(registry, "project")
    project_node = make_node(
        node_id=project_id,
        layer="project",
        parent_id=None,
        status="candidate",
        source_revision=source_revision,
        contract_sha256=contract_sha256,
        skill_tree_digest=skill_tree_digest,
        source_evidence=candidate_source_files,
        primary_source_files=[],
        required_semantics=[
            "authoritative child dispositions are required before project verification"
        ],
        gate_profile="project",
        required_gates=project_gates,
        required_tests=project_tests,
        applicability="applicable",
        unresolved=[],
        evidence_references=[],
    )
    nodes.append(project_node)
    nodes_by_id[project_id] = project_node

    ui = contract.get("ui", {})
    if not isinstance(ui, dict):
        raise GraphError("contract ui must be an object")
    resources = ui.get("android_value_resource_inventory", {})
    resource_sources = []
    if isinstance(resources, dict):
        for item in resources.get("resources", []):
            if isinstance(item, dict) and isinstance(item.get("source"), str):
                resource_sources.append(item["source"])
    if resource_sources:
        gates, tests = required_profile_fields(registry, "ui-system")
        ui_system_id = "ui-system:resources"
        node = make_node(
            node_id=ui_system_id,
            layer="ui_system",
            parent_id=project_id,
            status="candidate",
            source_revision=source_revision,
            contract_sha256=contract_sha256,
            skill_tree_digest=skill_tree_digest,
            source_evidence=unique_sorted(resource_sources),
            primary_source_files=[],
            required_semantics=[
                "theme, token, and value resources remain candidate until verified"
            ],
            gate_profile="ui-system",
            required_gates=gates,
            required_tests=tests,
            applicability="applicable",
            unresolved=[],
            evidence_references=[],
        )
        assign_primary(node, unique_sorted(resource_sources), primary_owners)
        nodes.append(node)
        nodes_by_id[ui_system_id] = node
        parent_children.setdefault(project_id, []).append(ui_system_id)

    composables = ui.get("composables", [])
    if not isinstance(composables, list):
        raise GraphError("contract ui.composables must be a list")
    for composable in composables:
        if not isinstance(composable, dict):
            continue
        name = composable.get("name")
        source_path = composable.get("source")
        if not isinstance(name, str) or not isinstance(source_path, str):
            continue
        page_id = f"page:{page_slug(name)}"
        if page_id not in nodes_by_id:
            gates, tests = required_profile_fields(registry, "page")
            page_node = make_node(
                node_id=page_id,
                layer="page",
                parent_id=project_id,
                status="candidate",
                source_revision=source_revision,
                contract_sha256=contract_sha256,
                skill_tree_digest=skill_tree_digest,
                source_evidence=[source_path],
                primary_source_files=[],
                required_semantics=[
                    "page closure, state matrix, callbacks, and visual/manual boundaries"
                ],
                gate_profile="page",
                required_gates=gates,
                required_tests=tests,
                applicability="applicable",
                unresolved=[],
                evidence_references=[],
            )
            assign_primary(page_node, [source_path], primary_owners)
            nodes.append(page_node)
            nodes_by_id[page_id] = page_node
            parent_children.setdefault(project_id, []).append(page_id)
        components = composable.get("components", {})
        if not isinstance(components, dict):
            continue
        for component_name in sorted(components):
            records = components.get(component_name)
            if not isinstance(records, list):
                continue
            control_id = f"control:{page_slug(name)}:{control_slug(component_name)}"
            if control_id in nodes_by_id:
                continue
            mapping_id = None
            semantic_arguments: list[str] = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                if mapping_id is None and isinstance(record.get("primitive_mapping_id"), str):
                    mapping_id = record["primitive_mapping_id"]
                arguments = record.get("semantic_arguments", {})
                if isinstance(arguments, dict):
                    semantic_arguments.extend(sorted(arguments.keys()))
            profile, family = choose_control_profile(component_name, mapping_id)
            gates, tests = required_profile_fields(registry, profile)
            control_node = make_node(
                node_id=control_id,
                layer="control",
                parent_id=page_id,
                status="candidate",
                source_revision=source_revision,
                contract_sha256=contract_sha256,
                skill_tree_digest=skill_tree_digest,
                source_evidence=[source_path],
                primary_source_files=[],
                required_semantics=unique_sorted(semantic_arguments),
                gate_profile=profile,
                required_gates=gates,
                required_tests=tests,
                applicability="applicable",
                unresolved=[],
                evidence_references=[],
                mapping_id=mapping_id,
                control_family=family,
            )
            nodes.append(control_node)
            nodes_by_id[control_id] = control_node
            parent_children.setdefault(page_id, []).append(control_id)

    semantic_candidates = ui.get("semantic_translation_candidates", {})
    if isinstance(semantic_candidates, dict):
        calls = semantic_candidates.get("calls", [])
        if isinstance(calls, list):
            for call in calls:
                if not isinstance(call, dict):
                    continue
                source_path = call.get("source")
                composable_name = call.get("composable")
                component_name = call.get("component")
                if not (
                    isinstance(source_path, str)
                    and isinstance(composable_name, str)
                    and isinstance(component_name, str)
                ):
                    continue
                page_id = f"page:{page_slug(composable_name)}"
                if page_id not in nodes_by_id:
                    continue
                control_id = f"control:{page_slug(composable_name)}:{control_slug(component_name)}"
                if control_id in nodes_by_id:
                    continue
                mapping_id = (
                    call.get("primitive_mapping_id")
                    if isinstance(call.get("primitive_mapping_id"), str)
                    else None
                )
                semantic_arguments = []
                arguments = call.get("semantic_arguments", {})
                if isinstance(arguments, dict):
                    semantic_arguments.extend(sorted(arguments.keys()))
                profile, family = choose_control_profile(component_name, mapping_id)
                gates, tests = required_profile_fields(registry, profile)
                control_node = make_node(
                    node_id=control_id,
                    layer="control",
                    parent_id=page_id,
                    status="candidate",
                    source_revision=source_revision,
                    contract_sha256=contract_sha256,
                    skill_tree_digest=skill_tree_digest,
                    source_evidence=[source_path],
                    primary_source_files=[],
                    required_semantics=unique_sorted(semantic_arguments),
                    gate_profile=profile,
                    required_gates=gates,
                    required_tests=tests,
                    applicability="applicable",
                    unresolved=[],
                    evidence_references=[],
                    mapping_id=mapping_id,
                    control_family=family,
                )
                nodes.append(control_node)
                nodes_by_id[control_id] = control_node
                parent_children.setdefault(page_id, []).append(control_id)

    business = contract.get("business", {})
    if not isinstance(business, dict):
        raise GraphError("contract business must be an object")
    models = business.get("models", [])
    if isinstance(models, list):
        for model in models:
            if not isinstance(model, dict):
                continue
            name = model.get("name")
            source_path = model.get("source")
            if not isinstance(name, str) or not isinstance(source_path, str):
                continue
            layer = classify_model_layer(
                source_path,
                name,
                model.get("kind") if isinstance(model.get("kind"), str) else None,
            )
            gates, tests = required_profile_fields(
                registry,
                "business"
                if layer == "business"
                else "network"
                if layer == "network"
                else "storage",
            )
            node_id = f"{layer}:{control_slug(name)}"
            if node_id in nodes_by_id:
                continue
            semantics = (
                ["behavior contract and state transitions remain candidate"]
                if layer == "business"
                else ["candidate data-layer semantics require explicit adapter and behavior verification"]
            )
            node = make_node(
                node_id=node_id,
                layer=layer,
                parent_id=project_id,
                status="candidate",
                source_revision=source_revision,
                contract_sha256=contract_sha256,
                skill_tree_digest=skill_tree_digest,
                source_evidence=[source_path],
                primary_source_files=[],
                required_semantics=semantics,
                gate_profile="business"
                if layer == "business"
                else "network"
                if layer == "network"
                else "storage",
                required_gates=gates,
                required_tests=tests,
                applicability="applicable",
                unresolved=[],
                evidence_references=[],
            )
            assign_primary(node, [source_path], primary_owners)
            nodes.append(node)
            nodes_by_id[node_id] = node
            parent_children.setdefault(project_id, []).append(node_id)

    platform_capabilities = contract.get("platform_capabilities", [])
    if isinstance(platform_capabilities, list):
        for capability in platform_capabilities:
            if not isinstance(capability, dict):
                continue
            capability_id = capability.get("id")
            source_files = capability.get("source_files", [])
            if not isinstance(capability_id, str):
                continue
            gates, tests = required_profile_fields(registry, "platform")
            node_id = f"platform:{capability_id}"
            node = make_node(
                node_id=node_id,
                layer="platform",
                parent_id=project_id,
                status="candidate",
                source_revision=source_revision,
                contract_sha256=contract_sha256,
                skill_tree_digest=skill_tree_digest,
                source_evidence=unique_sorted(
                    [str(item) for item in source_files if isinstance(item, str)]
                ),
                primary_source_files=[],
                required_semantics=[
                    str(capability.get("harmony_target", "candidate platform mapping"))
                ],
                gate_profile="platform",
                required_gates=gates,
                required_tests=tests,
                applicability="applicable",
                unresolved=[],
                evidence_references=[],
            )
            assign_primary(
                node,
                unique_sorted([str(item) for item in source_files if isinstance(item, str)]),
                primary_owners,
            )
            nodes.append(node)
            nodes_by_id[node_id] = node
            parent_children.setdefault(project_id, []).append(node_id)

    for source_path in candidate_source_files:
        if source_path in primary_owners or not text_source_supported(source_path):
            continue
        layer, gate_profile, status, unresolved, rationale, classification = classify_remaining_source(
            contract,
            source_path,
        )
        gates, tests = required_profile_fields(registry, gate_profile)
        node_id = unique_node_id(
            f"{layer}:{slugify(source_path.replace('/', ' '))}",
            nodes_by_id,
        )
        node = make_node(
            node_id=node_id,
            layer=layer,
            parent_id=project_id,
            status=status,
            source_revision=source_revision,
            contract_sha256=contract_sha256,
            skill_tree_digest=skill_tree_digest,
            source_evidence=[source_path],
            primary_source_files=[],
            required_semantics=["deterministic fallback ownership from safe contract inventory"],
            gate_profile=gate_profile,
            required_gates=gates,
            required_tests=tests,
            applicability=(
                "not_applicable_to_runtime"
                if status == "intentionally_excluded"
                else "applicable"
            ),
            unresolved=unresolved,
            evidence_references=[],
            rationale=rationale,
            classification=classification,
        )
        assign_primary(node, [source_path], primary_owners)
        nodes.append(node)
        nodes_by_id[node_id] = node
        parent_children.setdefault(project_id, []).append(node_id)

    for node in nodes:
        node["child_ids"] = sorted(parent_children.get(node["id"], []))

    claimed = set(primary_owners)
    explicit_non_runtime = set()
    unclassified_sources = set()
    for node in nodes:
        if node.get("status") == "intentionally_excluded":
            explicit_non_runtime.update(node.get("primary_source_files", []))
        if node.get("layer") == "unclassified":
            unclassified_sources.update(node.get("primary_source_files", []))
    coverage = {
        "contract_source_file_count": len(candidate_source_files),
        "assigned_primary_source_file_count": len(claimed),
        "explicit_non_runtime_source_file_count": len(explicit_non_runtime),
        "unclassified_source_files": sorted(unclassified_sources),
        "unassigned_source_files": sorted(
            source_path for source_path in candidate_source_files if source_path not in claimed
        ),
    }
    nodes.sort(key=lambda item: item["id"])
    graph = {
        "schema": GRAPH_SCHEMA,
        "source_revision": source_revision,
        "contract_sha256": contract_sha256,
        "skill_tree_digest": skill_tree_digest,
        "selected_skill": "migrate-android-compose-to-harmony",
        "gate_registry_schema": registry["schema"],
        "coverage": coverage,
        "root_qualification": infer_root_qualifications(contract, nodes),
        "resolved_edges": infer_resolved_edges(contract, nodes),
        "nodes": nodes,
    }
    review_queue = build_review_queue(graph, nodes)
    return graph, nodes_by_id, review_queue


def build_fact_pack(
    layer: str,
    graph: dict[str, Any],
    nodes: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    project_sources = graph["coverage"]["contract_source_file_count"]
    payload = {
        "schema": FACT_PACK_SCHEMA,
        "layer": layer,
        "source_revision": graph["source_revision"],
        "contract_sha256": graph["contract_sha256"],
        "skill_tree_digest": graph["skill_tree_digest"],
        "candidate_source_files": unique_sorted(
            [source for node in nodes for source in node.get("source_evidence", [])]
        ),
        "node_ids": [node["id"] for node in nodes],
        "status": "candidate",
        "authoritative": False,
        "project_source_file_count": project_sources,
    }
    if layer == "project":
        ui = contract.get("ui", {}) if isinstance(contract.get("ui"), dict) else {}
        payload["summary"] = {
            "route_count": len(ui.get("routes", [])) if isinstance(ui.get("routes"), list) else 0,
            "platform_capability_count": len(contract.get("platform_capabilities", []))
            if isinstance(contract.get("platform_capabilities"), list)
            else 0,
            "resource_count": len(
                (
                    ui.get("android_value_resource_inventory", {}).get("resources", [])
                    if isinstance(ui.get("android_value_resource_inventory"), dict)
                    else []
                )
            ),
        }
    return payload


def materialize_graph_outputs(
    contract: dict[str, Any],
    contract_sha256: str,
    registry: dict[str, Any],
    skill_tree_digest: str | None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    graph, _, review_queue = build_graph(
        contract,
        contract_sha256,
        registry,
        skill_tree_digest,
    )
    fact_packs: dict[str, dict[str, Any]] = {}
    fact_pack_paths: list[str] = []
    for layer in (
        "project",
        "business",
        "network",
        "storage",
        "platform",
        "ui_system",
        "page",
        "control",
        "test_support",
        "project_support",
        "unclassified",
    ):
        layer_nodes = [node for node in graph["nodes"] if node["layer"] == layer]
        if not layer_nodes and layer != "project":
            continue
        filename = f"{layer.replace('_', '-')}-fact-pack.json"
        fact_packs[filename] = build_fact_pack(
            layer,
            graph,
            layer_nodes or [graph["nodes"][0]],
            contract,
        )
        fact_pack_paths.append(filename)
    graph["fact_packs"] = fact_pack_paths
    review_queue_bytes = json.dumps(
        review_queue,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8") + b"\n"
    graph["review_queue"] = {
        "schema": REVIEW_QUEUE_SCHEMA,
        "path": "review-queue.json",
        "sha256": sha256_bytes(review_queue_bytes),
        "entry_count": review_queue["entry_count"],
        "unclassified_source_files": review_queue["unclassified_source_files"],
    }
    return graph, fact_packs, review_queue


def main() -> int:
    args = parse_args()
    try:
        contract, contract_sha256 = validate_contract(args.contract.resolve())
        registry = validate_registry(args.gate_registry.resolve())
        skill_tree_digest = load_skill_manifest(
            args.skill_manifest.resolve() if args.skill_manifest else None
        )
        graph, fact_packs, review_queue = materialize_graph_outputs(
            contract,
            contract_sha256,
            registry,
            skill_tree_digest,
        )
        fact_pack_dir = args.fact_pack_dir.resolve()
        fact_pack_dir.mkdir(parents=True, exist_ok=True)
        for filename, fact_pack in fact_packs.items():
            fact_pack_path = fact_pack_dir / filename
            write_json(fact_pack_path, fact_pack)
        write_json(args.output.resolve().with_name("review-queue.json"), review_queue)
        write_json(args.output.resolve(), graph)
    except GraphError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "node_count": len(graph["nodes"]),
                "fact_pack_count": len(graph["fact_packs"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
