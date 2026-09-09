#!/usr/bin/env python3
"""Analyze a text-only Android UI snapshot into a migration contract."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

from validate_ai_safe_tree import validate as validate_ai_safe_tree
from ui_migration.frontend.ui_declarations import NATIVE_SLOTS
from ui_migration.frontend.source_symbols import SourceSymbolIndex, resolve_functions, function_identity
from ui_migration.progress import Progress, checkpoint, step, tracked


PRIMITIVE_MAPPING_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "compose-arkui-primitive-mappings.json"
)
PRIMITIVE_MAPPING_CATALOG_SCHEMA = (
    "android-to-harmony.primitive-component-mapping-catalog.v1"
)
PRIMITIVE_MAPPING_CANDIDATES_SCHEMA = (
    "android-to-harmony.primitive-component-mapping-candidates.v1"
)
COMPOSE_COMPONENTS = (
    "AlertDialog",
    "AnimatedContent",
    "AnimatedVisibility",
    "BasicText",
    "BasicTextField",
    "BottomAppBar",
    "Box",
    "BoxWithConstraints",
    "PullToRefreshBox",
    "Button",
    "Canvas",
    "Card",
    "CenterAlignedTopAppBar",
    "Checkbox",
    "Column",
    "ConstraintLayout",
    "ContextualFlowRow",
    "CircularProgressIndicator",
    "Dialog",
    "DatePicker",
    "DatePickerDialog",
    "DecorationBox",
    "DropdownMenu",
    "DropdownMenuItem",
    "Divider",
    "ElevatedCard",
    "ExposedDropdownMenuBox",
    "FilterChip",
    "ListItem",
    "LargeFlexibleTopAppBar",
    "FloatingActionButton",
    "SmallFloatingActionButton",
    "ExtendedFloatingActionButton",
    "FlowRow",
    "HorizontalPager",
    "VerticalPager",
    "HorizontalDivider",
    "VerticalDivider",
    "Icon",
    "IconButton",
    "Image",
    "LazyColumn",
    "LazyVerticalStaggeredGrid",
    "LazyVerticalGrid",
    "LazyRow",
    "LinearProgressIndicator",
    "ModalBottomSheet",
    "NavigationBar",
    "NavigationBarItem",
    "NavigationDrawer",
    "NavigationRail",
    "NavigationRailItem",
    "OutlinedButton",
    "OutlinedCard",
    "OutlinedIconButton",
    "OutlinedTextField",
    "RadioButton",
    "Row",
    "Scaffold",
    "PrimaryTabRow",
    "SecondaryTabRow",
    "Slider",
    "SnackbarHost",
    "Spacer",
    "Surface",
    "Switch",
    "Tab",
    "TabRow",
    "Text",
    "TextButton",
    "TextField",
    "TimePicker",
    "TimeInput",
    "TopAppBar",
    "ClickableText",
)
CUSTOM_IMAGE_COMPONENT_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9_]*Image)\s*\("
)
MODIFIER_CALLS = (
    "align",
    "aspectRatio",
    "background",
    "border",
    "clickable",
    "fillMaxHeight",
    "fillMaxSize",
    "fillMaxWidth",
    "height",
    "padding",
    "requiredSize",
    "semantics",
    "size",
    "testTag",
    "weight",
    "width",
)
LAYER_RULES = (
    ("test", ("/src/test/", "/src/androidtest/", "test/", "/baseline-profile/")),
    ("ui", ("/ui/", "/screen/", "/screens/", "/component/", "/components/", "/theme/")),
    ("viewmodel", ("/viewmodel/", "viewmodel.kt")),
    ("model", ("/model/", "/entity/", "/domain/", "/common/")),
    ("network", ("/network/", "/api/", "interceptor")),
    ("database", ("/database/", "/dao/", "room")),
    ("storage", ("/preference/", "/preferences/", "/datastore/", "/cache/")),
    ("platform", ("/service/", "/bluetooth/", "/media/", "/permission/", "/widget/")),
)
CAPABILITY_RULES = (
    {
        "id": "bluetooth",
        "patterns": ("android.bluetooth", "BluetoothAdapter", "BluetoothDevice"),
        "harmony_target": "ConnectivityKit Bluetooth APIs",
        "risk": "high",
    },
    {
        "id": "audio-media",
        "patterns": ("android.media", "MediaPlayer", "AudioTrack", "AudioManager"),
        "harmony_target": "AudioKit and AVSessionKit",
        "risk": "high",
    },
    {
        "id": "background-service",
        "patterns": ("android.app.Service", ": Service(", "startForegroundService"),
        "harmony_target": "ExtensionAbility or background task APIs",
        "risk": "high",
    },
    {
        "id": "room-database",
        "patterns": ("androidx.room", "@Database", "@Dao", "@Entity"),
        "harmony_target": "RelationalStore or approved ORM",
        "risk": "medium",
    },
    {
        "id": "preferences",
        "patterns": ("SharedPreferences", "DataStore", "Preference"),
        "harmony_target": "Preferences",
        "risk": "low",
    },
    {
        "id": "http-client",
        "patterns": ("okhttp3", "io.ktor.client", "retrofit2"),
        "harmony_target": "NetworkKit or @ohos/axios",
        "risk": "medium",
    },
    {
        "id": "navigation-compose",
        "patterns": ("androidx.navigation.compose", "NavHost", "NavController"),
        "harmony_target": "Navigation and NavPathStack",
        "risk": "medium",
    },
    {
        "id": "viewmodel-stateflow",
        "patterns": ("ViewModel", "StateFlow", "MutableStateFlow", "collectAsState"),
        "harmony_target": "ArkUI V2 observed state and explicit ViewModel",
        "risk": "medium",
    },
    {
        "id": "runtime-permission",
        "patterns": (
            "requestPermissions",
            "checkSelfPermission",
            "ActivityResultContracts.RequestPermission",
            "ActivityResultContracts.RequestMultiplePermissions",
        ),
        "harmony_target": "abilityAccessCtrl and module permissions",
        "risk": "high",
    },
    {
        "id": "local-files",
        "patterns": ("java.io.File", "contentResolver", "MediaStore"),
        "harmony_target": "FileKit and user file APIs",
        "risk": "high",
    },
    {
        "id": "scheduled-work",
        "patterns": ("WorkManager", "Worker(", "AlarmManager", "setExactAndAllowWhileIdle"),
        "harmony_target": "Background task and agent APIs",
        "risk": "high",
    },
    {
        "id": "camera-gallery",
        "patterns": ("android.hardware.camera", "CameraManager", "TakePicture", "PickVisualMedia"),
        "harmony_target": "CameraKit and PhotoAccessHelper",
        "risk": "high",
    },
    {
        "id": "notifications-push",
        "patterns": ("NotificationManager", "NotificationCompat", "FirebaseMessagingService"),
        "harmony_target": "NotificationKit and approved push service",
        "risk": "high",
    },
    {
        "id": "webview",
        "patterns": ("android.webkit.WebView", "WebViewClient", "JavascriptInterface"),
        "harmony_target": "ArkUI Web component",
        "risk": "medium",
    },
    {
        "id": "biometrics",
        "patterns": ("BiometricPrompt", "BiometricManager", "USE_BIOMETRIC"),
        "harmony_target": "HarmonyOS user authentication APIs",
        "risk": "high",
    },
    {
        "id": "location",
        "patterns": ("LocationManager", "FusedLocationProviderClient", "ACCESS_FINE_LOCATION"),
        "harmony_target": "LocationKit",
        "risk": "high",
    },
    {
        "id": "app-widget-glance",
        "patterns": (
            "androidx.glance.appwidget",
            "GlanceAppWidget",
            "GlanceAppWidgetReceiver",
            "android.appwidget",
        ),
        "harmony_target": "FormExtensionAbility and ArkUI Form",
        "risk": "high",
    },
)
DEPENDENCY_MAPPINGS = (
    ("androidx.compose", "ArkUI declarative components", "translate"),
    ("androidx.navigation", "Navigation/NavPathStack", "translate"),
    ("androidx.lifecycle", "UIAbility lifecycle and ArkUI state", "translate"),
    ("androidx.glance", "FormExtensionAbility and ArkUI Form", "translate"),
    ("kotlinx.coroutines", "Promise/async tasks or TaskPool", "translate"),
    ("androidx.room", "RelationalStore or approved ORM", "replace"),
    ("okhttp", "NetworkKit or @ohos/axios", "replace"),
    ("ktor", "NetworkKit or @ohos/axios", "replace"),
    ("gson", "JSON.parse/stringify and typed mappers", "translate"),
    ("kotlinx.serialization", "JSON.parse/stringify and typed mappers", "translate"),
)
STANDARD_DEPENDENCY_CONFIGURATIONS = {
    "annotationProcessor",
    "api",
    "compileOnly",
    "implementation",
    "kapt",
    "ksp",
    "runtimeOnly",
    "testAnnotationProcessor",
    "testApi",
    "testCompileOnly",
    "testImplementation",
    "testKapt",
    "testKsp",
    "testRuntimeOnly",
    "androidTestAnnotationProcessor",
    "androidTestApi",
    "androidTestCompileOnly",
    "androidTestImplementation",
    "androidTestKapt",
    "androidTestKsp",
    "androidTestRuntimeOnly",
}
VARIANT_CONFIGURATION_SUFFIXES = (
    "AnnotationProcessor",
    "CompileOnly",
    "Implementation",
    "RuntimeOnly",
    "Api",
    "Kapt",
    "Ksp",
)
UI_SEMANTIC_ARGUMENTS = {
    "alwaysShowLabel",
    "alignment",
    "alpha",
    "backgroundColor",
    "bitmap",
    "border",
    "checked",
    "color",
    "colorFilter",
    "colors",
    "columns",
    "confirmButton",
    "dismissButton",
    "dragHandle",
    "sheetState",
    "sheetMaxWidth",
    "sheetGesturesEnabled",
    "contentWindowInsets",
    "content",
    "containerColor",
    "container",
    "contentAlignment",
    "contentColor",
    "contentDescription",
    "contentPadding",
    "contentScale",
    "contentKey",
    "dismissButton",
    "divider",
    "drawerContent",
    "drawerState",
    "drawStopIndicator",
    "elevation",
    "enabled",
    "enter",
    "expanded",
    "exit",
    "filterQuality",
    "flingBehavior",
    "fontFamily",
    "fontSize",
    "fontStyle",
    "fontWeight",
    "gapSize",
    "gesturesEnabled",
    "hostState",
    "header",
    "horizontalAlignment",
    "horizontalArrangement",
    "icon",
    "imageVector",
    "indicator",
    "interactionSource",
    "itemCount",
    "itemVerticalAlignment",
    "isError",
    "isRefreshing",
    "keyboardActions",
    "keyboardOptions",
    "leadingIcon",
    "label",
    "lineHeight",
    "letterSpacing",
    "layoutType",
    "maxItemsInEachRow",
    "maxLines",
    "minLines",
    "model",
    "onClick",
    "onCheckedChange",
    "onDismissRequest",
    "onDraw",
    "onExpandedChange",
    "onTextLayout",
    "onValueChange",
    "onValueChangeFinished",
    "overflow",
    "offset",
    "painter",
    "placeholder",
    "pageSize",
    "pageSpacing",
    "pageNestedScrollConnection",
    "snapPosition",
    "overscrollEffect",
    "prefix",
    "progress",
    "propagateMinConstraints",
    "properties",
    "readOnly",
    "rows",
    "reverseLayout",
    "selected",
    "selectedContentColor",
    "selectedTabIndex",
    "scrimColor",
    "shadowElevation",
    "shape",
    "singleLine",
    "softWrap",
    "state",
    "steps",
    "startIndent",
    "strokeCap",
    "strokeWidth",
    "style",
    "suffix",
    "supportingText",
    "targetState",
    "contentWindowInsets",
    "text",
    "textAlign",
    "textDecoration",
    "textStyle",
    "thickness",
    "tint",
    "title",
    "thumbContent",
    "thumb",
    "track",
    "tonalElevation",
    "trackColor",
    "trailingIcon",
    "transitionSpec",
    "unselectedContentColor",
    "userScrollEnabled",
    "value",
    "valueRange",
    "visible",
    "verticalAlignment",
    "verticalArrangement",
    "verticalItemSpacing",
    "visualTransformation",
    "windowInsets",
}
from ui_migration.controls.registry import CONTROLS
COMPOSE_COMPONENTS = tuple(dict.fromkeys((*COMPOSE_COMPONENTS, *sorted(CONTROLS.names))))
UI_SEMANTIC_ARGUMENTS.update(name for control in CONTROLS for name in control.arguments | control.slots)
IMAGE_STATE_ARGUMENTS = {
    "error",
    "failure",
    "loading",
    "onError",
    "onLoading",
    "placeholder",
    "success",
}
PROGRESS_COMPONENTS = {
    "CircularProgressIndicator",
    "LinearProgressIndicator",
}


class AnalysisError(RuntimeError):
    pass


def load_primitive_mapping_catalog() -> tuple[
    list[dict[str, Any]], dict[str, dict[str, Any]]
]:
    raw = json.loads(PRIMITIVE_MAPPING_CATALOG_PATH.read_text(encoding="utf-8"))
    if raw.get("schema") != PRIMITIVE_MAPPING_CATALOG_SCHEMA:
        raise AnalysisError("primitive component mapping catalog schema is invalid")
    mappings = raw.get("mappings")
    if not isinstance(mappings, list):
        raise AnalysisError("primitive component mapping catalog mappings must be a list")
    by_component: dict[str, dict[str, Any]] = {}
    ids: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict) or not isinstance(mapping.get("id"), str):
            raise AnalysisError("primitive component mapping entry is invalid")
        mapping_id = mapping["id"]
        if mapping_id in ids:
            raise AnalysisError(f"duplicate primitive component mapping id: {mapping_id}")
        ids.add(mapping_id)
        source_components = mapping.get("source_components")
        if not isinstance(source_components, list) or not source_components:
            raise AnalysisError(
                f"primitive component mapping has no source components: {mapping_id}"
            )
        for component in source_components:
            if not isinstance(component, str) or not component:
                raise AnalysisError(
                    f"primitive component mapping source component is invalid: {mapping_id}"
                )
            if component in by_component:
                raise AnalysisError(
                    f"duplicate primitive source component mapping: {component}"
                )
            by_component[component] = mapping
        source_import_prefixes = mapping.get(
            "source_import_prefixes",
            ["androidx.compose."],
        )
        if (
            not isinstance(source_import_prefixes, list)
            or not source_import_prefixes
            or not all(
                isinstance(prefix, str) and prefix.endswith(".")
                for prefix in source_import_prefixes
            )
        ):
            raise AnalysisError(
                f"primitive component mapping import prefixes are invalid: {mapping_id}"
            )
    return mappings, by_component


CONTRACT_OWNER_SCHEMA = "android-to-harmony.contract-owner.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a code-only Android UI to HarmonyOS migration contract."
    )
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_snapshot(snapshot: Path) -> tuple[Path, dict[str, Any]]:
    requested = Path(os.path.abspath(os.path.expanduser(str(snapshot))))
    validation = validate_ai_safe_tree(
        requested,
        require_safe_manifest=True,
    )
    if not validation.get("ok"):
        violations = validation.get("violations", [])
        first = violations[0] if violations else {"reason": "unknown"}
        raise AnalysisError(
            "snapshot failed current privacy validation: "
            f"{first.get('path', '<unknown>')} ({first.get('reason', 'unknown')})"
        )

    snapshot = requested.resolve()
    manifest_path = snapshot / ".android-to-harmony-safe.json"
    if not manifest_path.is_file():
        raise AnalysisError("safe snapshot marker is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise AnalysisError("safe snapshot marker must be a JSON object")
    guarantees = manifest.get("guarantees", {})
    if (
        manifest.get("schema") != "android-to-harmony.safe-snapshot.v1"
        or not isinstance(guarantees, dict)
        or (
            guarantees.get("known_image_paths_copied") is not False
            and
            guarantees.get("contains_original_image_files") is not False
            and guarantees.get("contains_image_bytes") is not False
        )
        or guarantees.get("utf8_text_only") is not True
        or guarantees.get("contains_symbolic_links") is not False
        or guarantees.get("file_hashes_recorded") is not True
    ):
        raise AnalysisError("snapshot does not satisfy the required privacy contract")
    return snapshot, manifest


def load_text_files(snapshot: Path, manifest: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    text_files = manifest.get("text_files")
    hashes = manifest.get("text_file_sha256")
    if not isinstance(text_files, list) or not all(
        isinstance(relative, str) for relative in text_files
    ):
        raise AnalysisError("snapshot text_files must be a list of paths")
    if not isinstance(hashes, dict):
        raise AnalysisError("snapshot text_file_sha256 map is missing")
    if len(text_files) != len(set(text_files)):
        raise AnalysisError("snapshot text_files contains duplicate paths")

    expected_files = set(text_files)
    expected_files.add(".android-to-harmony-safe.json")
    actual_files: set[str] = set()
    for current_root, directories, filenames in os.walk(snapshot):
        current = Path(current_root)
        for directory in directories:
            child = current / directory
            if child.is_symlink():
                raise AnalysisError(
                    f"snapshot contains a symbolic link: "
                    f"{child.relative_to(snapshot).as_posix()}"
                )
        for filename in filenames:
            child = current / filename
            relative = child.relative_to(snapshot).as_posix()
            if child.is_symlink() or not child.is_file():
                raise AnalysisError(f"unsafe snapshot path: {relative}")
            actual_files.add(relative)
    unexpected = sorted(actual_files - expected_files)
    missing = sorted(expected_files - actual_files)
    if unexpected or missing:
        details: list[str] = []
        if unexpected:
            details.append(f"unexpected: {unexpected[0]}")
        if missing:
            details.append(f"missing: {missing[0]}")
        raise AnalysisError(
            "snapshot tree does not exactly match its manifest ("
            + "; ".join(details)
            + ")"
        )

    for relative in text_files:
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or "\\" in relative
        ):
            raise AnalysisError(f"unsafe snapshot path: {relative}")
        expected_hash = hashes.get(relative)
        if not isinstance(expected_hash, str):
            raise AnalysisError(f"snapshot hash is missing for: {relative}")
        path = (snapshot / relative).resolve()
        if snapshot not in path.parents or not path.is_file() or path.is_symlink():
            raise AnalysisError(f"unsafe snapshot path: {relative}")
        content = path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise AnalysisError(f"snapshot file changed after audit: {relative}")
        # PSI expects normalized document newlines, as Path.read_text does elsewhere.
        result[relative] = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return result


def normalize_output(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise AnalysisError(f"output must not be a symbolic link: {absolute}")
    return absolute.resolve()


def require_separate_output(
    output: Path,
    snapshot: Path,
    manifest: dict[str, Any],
) -> None:
    protected_roots = [snapshot]
    original_root = manifest.get("source_root")
    if isinstance(original_root, str) and original_root:
        protected_roots.append(
            Path(os.path.abspath(os.path.expanduser(original_root))).resolve()
        )
    for protected in protected_roots:
        if (
            output == protected
            or protected in output.parents
            or output in protected.parents
        ):
            raise AnalysisError(
                "contract output must be separate from source and snapshot directories"
            )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contract_owner_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.owner.json")


def owns_existing_contract(path: Path, owner_path: Path) -> bool:
    if (
        not path.is_file()
        or path.is_symlink()
        or not owner_path.is_file()
        or owner_path.is_symlink()
    ):
        return False
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False
    return (
        isinstance(owner, dict)
        and owner.get("schema") == CONTRACT_OWNER_SCHEMA
        and owner.get("generator") == "migrate-android-compose-to-harmony"
        and owner.get("output_name") == path.name
        and owner.get("contract_sha256") == sha256_file(path)
    )


def write_contract(
    output: Path,
    contract: dict[str, Any],
    force: bool,
) -> None:
    owner_path = contract_owner_path(output)
    if output.exists() and output.is_dir():
        raise AnalysisError(f"contract output is a directory: {output}")
    if owner_path.exists() and owner_path.is_dir():
        raise AnalysisError(f"contract owner is a directory: {owner_path}")
    if output.exists() or owner_path.exists():
        if not force:
            raise AnalysisError(
                "contract output already exists; pass --force to replace it"
            )
        if not owns_existing_contract(output, owner_path):
            raise AnalysisError(
                "refusing to replace a contract without a matching owner record"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.analyze-",
        dir=output.parent,
    )
    os.close(descriptor)
    owner_descriptor, owner_temporary_name = tempfile.mkstemp(
        prefix=f".{owner_path.name}.analyze-",
        dir=output.parent,
    )
    os.close(owner_descriptor)
    temporary = Path(temporary_name)
    owner_temporary = Path(owner_temporary_name)
    output_backup: Path | None = None
    owner_backup: Path | None = None
    try:
        temporary.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        owner_temporary.write_text(
            json.dumps(
                {
                    "schema": CONTRACT_OWNER_SCHEMA,
                    "generator": "migrate-android-compose-to-harmony",
                    "output_name": output.name,
                    "contract_sha256": sha256_file(temporary),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if output.exists():
            output_backup = output.with_name(f".{output.name}.backup")
            owner_backup = owner_path.with_name(f".{owner_path.name}.backup")
            if output_backup.exists() or owner_backup.exists():
                raise AnalysisError(
                    "refusing contract replacement while backup files exist"
                )
            os.replace(output, output_backup)
            os.replace(owner_path, owner_backup)
        os.replace(temporary, output)
        os.replace(owner_temporary, owner_path)
        if output_backup is not None:
            output_backup.unlink()
        if owner_backup is not None:
            owner_backup.unlink()
    except (OSError, AnalysisError):
        if output_backup is not None and output_backup.exists():
            if output.exists():
                output.unlink()
            os.replace(output_backup, output)
        if owner_backup is not None and owner_backup.exists():
            if owner_path.exists():
                owner_path.unlink()
            os.replace(owner_backup, owner_path)
        raise
    finally:
        if temporary.exists():
            temporary.unlink()
        if owner_temporary.exists():
            owner_temporary.unlink()


def classify_file(relative: str) -> str:
    normalized = f"/{relative.lower()}"
    for layer, markers in LAYER_RULES:
        if any(marker in normalized for marker in markers):
            return layer
    if relative.endswith((".kt", ".java")):
        return "source"
    if relative.endswith((".gradle", ".gradle.kts", ".toml", ".properties")):
        return "build"
    if relative.endswith(".xml"):
        return "resource"
    return "other"


def lexical_code_mask(text: str, *, mask_strings: bool = True) -> str:
    """Mask comments and optionally literals without changing source offsets."""

    masked = list(text)
    state = "code"
    delimiter = ""
    block_depth = 0
    index = 0

    def blank(start: int, end: int) -> None:
        for position in range(start, min(end, len(masked))):
            if masked[position] not in {"\r", "\n"}:
                masked[position] = " "

    while index < len(text):
        if state == "line_comment":
            if text[index] in {"\r", "\n"}:
                state = "code"
                index += 1
            else:
                blank(index, index + 1)
                index += 1
            continue

        if state == "block_comment":
            if text.startswith("/*", index):
                blank(index, index + 2)
                block_depth += 1
                index += 2
            elif text.startswith("*/", index):
                blank(index, index + 2)
                block_depth -= 1
                index += 2
                if block_depth == 0:
                    state = "code"
            else:
                blank(index, index + 1)
                index += 1
            continue

        if state == "string":
            if text.startswith(delimiter, index):
                if mask_strings:
                    blank(index, index + len(delimiter))
                index += len(delimiter)
                state = "code"
            elif len(delimiter) == 1 and text[index] == "\\":
                if mask_strings:
                    blank(index, index + 2)
                index += 2
            else:
                if mask_strings:
                    blank(index, index + 1)
                index += 1
            continue

        if text.startswith("//", index):
            blank(index, index + 2)
            state = "line_comment"
            index += 2
        elif text.startswith("/*", index):
            blank(index, index + 2)
            state = "block_comment"
            block_depth = 1
            index += 2
        elif text.startswith('"""', index) or text.startswith("'''", index):
            delimiter = text[index : index + 3]
            if mask_strings:
                blank(index, index + 3)
            state = "string"
            index += 3
        elif text[index] in {'"', "'"}:
            delimiter = text[index]
            if mask_strings:
                blank(index, index + 1)
            state = "string"
            index += 1
        else:
            index += 1
    return "".join(masked)


def extract_balanced_block(text: str, opening: int) -> str:
    if opening < 0 or opening >= len(text) or text[opening] != "{":
        return ""
    code = lexical_code_mask(text)
    depth = 0
    for index in range(opening, len(text)):
        character = code[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[opening : index + 1]
    return text[opening:]


def balanced_closing(
    code: str,
    opening: int,
    opening_character: str,
    closing_character: str,
) -> int | None:
    if opening < 0 or opening >= len(code) or code[opening] != opening_character:
        return None
    depth = 0
    for index in range(opening, len(code)):
        if code[index] == opening_character:
            depth += 1
        elif code[index] == closing_character:
            depth -= 1
            if depth == 0:
                return index
    return None


def split_top_level(expression: str) -> list[str]:
    code = lexical_code_mask(expression, mask_strings=False)
    chunks: list[str] = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0, "<": 0}
    pairs = {")": "(", "]": "[", "}": "{", ">": "<"}
    for index, character in enumerate(code):
        if character in depths:
            depths[character] += 1
        elif character in pairs:
            opener = pairs[character]
            depths[opener] = max(0, depths[opener] - 1)
        elif character == "," and not any(depths.values()):
            chunks.append(expression[start:index])
            start = index + 1
    chunks.append(expression[start:])
    return chunks


def split_top_level_spans(expression: str) -> list[tuple[str, int, int]]:
    code = lexical_code_mask(expression, mask_strings=False)
    chunks: list[tuple[str, int, int]] = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0, "<": 0}
    pairs = {")": "(", "]": "[", "}": "{", ">": "<"}

    def append_chunk(raw_start: int, raw_end: int) -> None:
        chunk_start = raw_start
        chunk_end = raw_end
        while chunk_start < chunk_end and expression[chunk_start].isspace():
            chunk_start += 1
        while chunk_end > chunk_start and expression[chunk_end - 1].isspace():
            chunk_end -= 1
        chunks.append((expression[chunk_start:chunk_end], chunk_start, chunk_end))

    for index, character in enumerate(code):
        if character in depths:
            depths[character] += 1
        elif character in pairs:
            opener = pairs[character]
            depths[opener] = max(0, depths[opener] - 1)
        elif character == "," and not any(depths.values()):
            append_chunk(start, index)
            start = index + 1
    append_chunk(start, len(expression))
    return chunks


def trim_with_code_mask(original: str, code: str) -> str:
    start = 0
    end = len(code)
    while start < end and code[start].isspace():
        start += 1
    while end > start and code[end - 1].isspace():
        end -= 1
    return original[start:end].strip()


def split_named_argument(argument: str) -> tuple[str, str] | None:
    code = lexical_code_mask(argument, mask_strings=False)
    depths = {"(": 0, "[": 0, "{": 0, "<": 0}
    pairs = {")": "(", "]": "[", "}": "{", ">": "<"}
    for index, character in enumerate(code):
        if character in depths:
            depths[character] += 1
        elif character in pairs:
            opener = pairs[character]
            depths[opener] = max(0, depths[opener] - 1)
        elif character == "=" and not any(depths.values()):
            name = code[:index].strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is not None:
                return name, trim_with_code_mask(argument[index + 1 :], code[index + 1 :])
            return None
    return None


def normalize_expression(expression: str) -> str:
    # Kotlin newlines separate when branches/statements; string whitespace is data.
    # Keep executable expressions intact instead of turning them into log summaries.
    return lexical_code_mask(expression, mask_strings=False).strip()


def expression_semantics(expression: str) -> dict[str, Any]:
    normalized = normalize_expression(expression)
    return {
        "expression": normalized,
        "dimension_resources": sorted(
            set(
                re.findall(
                    r"\bdimensionResource\s*\(\s*(?:id\s*=\s*)?"
                    r"R\.dimen\.([A-Za-z0-9_]+)",
                    expression,
                )
            )
        ),
        "dimensions": [
            {"value": value, "unit": unit}
            for value, unit in re.findall(
                r"(?<![A-Za-z0-9_])(-?[0-9]+(?:\.[0-9]+)?)\s*\.\s*(dp|sp)\b",
                expression,
            )
        ],
    }


def extract_assignment_expression(text: str, code: str, start: int) -> str:
    index = start
    while index < len(code) and code[index].isspace():
        index += 1
    expression_start = index
    depths = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}
    while index < len(code):
        character = code[index]
        if character in depths:
            depths[character] += 1
        elif character in pairs:
            opener = pairs[character]
            if depths[opener] == 0:
                break
            depths[opener] -= 1
        elif character == ";" and not any(depths.values()):
            break
        elif character in {"\r", "\n"} and not any(depths.values()):
            next_index = index + 1
            while next_index < len(code) and code[next_index].isspace():
                next_index += 1
            if code.startswith("else", next_index):
                index = next_index
                continue
            break
        index += 1
    return text[expression_start:index].strip().rstrip(",")


def extract_kotlin_val_declarations(
    relative: str,
    text: str,
) -> list[dict[str, Any]]:
    code = lexical_code_mask(text)
    declarations: list[dict[str, Any]] = []
    pattern = re.compile(
        r"\b(?:(?:private|internal|public|protected)\s+)?(?:const\s+)?"
        r"val\s+([A-Za-z_][A-Za-z0-9_]*)"
        r"(?:\s*:\s*[^=\r\n]+)?\s*="
    )
    for match in pattern.finditer(code):
        expression = extract_assignment_expression(text, code, match.end())
        if not expression:
            continue
        declarations.append(
            {
                "source": relative,
                "line": text.count("\n", 0, match.start()) + 1,
                "name": match.group(1),
                "expression": expression,
            }
        )
    return declarations


def extract_data_class_factory_functions(
    relative: str,
    text: str,
    code: str,
    class_name: str,
    constructor_closing: int,
) -> list[dict[str, Any]]:
    body_opening = code.find("{", constructor_closing + 1)
    if body_opening < 0:
        return []
    body_closing = balanced_closing(code, body_opening, "{", "}")
    if body_closing is None:
        return []
    body = text[body_opening + 1 : body_closing]
    body_code = code[body_opening + 1 : body_closing]
    factories: list[dict[str, Any]] = []
    for companion_match in re.finditer(r"\bcompanion\s+object\b", body_code):
        companion_opening = body_code.find("{", companion_match.end())
        if companion_opening < 0:
            continue
        companion_closing = balanced_closing(body_code, companion_opening, "{", "}")
        if companion_closing is None:
            continue
        companion_body = body[companion_opening + 1 : companion_closing]
        companion_body_code = body_code[companion_opening + 1 : companion_closing]
        for function_match in re.finditer(r"\bfun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", companion_body_code):
            parameter_opening = function_match.end() - 1
            parameter_closing = balanced_closing(companion_body_code, parameter_opening, "(", ")")
            if parameter_closing is None:
                continue
            parameters = compact_parameters(companion_body[parameter_opening + 1 : parameter_closing])
            cursor = parameter_closing + 1
            while cursor < len(companion_body_code) and companion_body_code[cursor].isspace():
                cursor += 1
            if cursor < len(companion_body_code) and companion_body_code[cursor] == ":":
                cursor += 1
                while cursor < len(companion_body_code) and companion_body_code[cursor].isspace():
                    cursor += 1
                return_type_start = cursor
                while (
                    cursor < len(companion_body_code)
                    and companion_body_code[cursor] not in {"{", "=", "\n", "\r"}
                ):
                    cursor += 1
                return_type = normalize_expression(companion_body[return_type_start:cursor])
                if return_type.rsplit(".", 1)[-1].replace("?", "") != class_name:
                    continue
            while cursor < len(companion_body_code) and companion_body_code[cursor].isspace():
                cursor += 1
            return_expression: str | None = None
            local_values: dict[str, str] = {}
            static_record = False
            if cursor < len(companion_body_code) and companion_body_code[cursor] == "{":
                function_closing = balanced_closing(companion_body_code, cursor, "{", "}")
                if function_closing is None:
                    continue
                function_body = companion_body[cursor + 1 : function_closing]
                function_body_code = companion_body_code[cursor + 1 : function_closing]
                local_values = local_value_expressions(function_body, function_body_code)
                static_record = (len(re.findall(r'\breturn\b', function_body_code)) == 1
                                 and not re.search(r'\b(?:if|when|for|while|try|throw|var)\b', function_body_code))
                for return_match in re.finditer(r"\breturn\b", function_body_code):
                    expression_start = return_match.end()
                    expression_end = local_value_expression_end(function_body_code, expression_start)
                    candidate = normalize_expression(function_body[expression_start:expression_end])
                    if re.match(rf"{re.escape(class_name)}\s*\(", candidate, re.S) is not None:
                        return_expression = candidate
                        break
            elif cursor < len(companion_body_code) and companion_body_code[cursor] == "=":
                expression_start = cursor + 1
                expression_end = local_value_expression_end(companion_body_code, expression_start)
                candidate = normalize_expression(companion_body[expression_start:expression_end])
                if re.match(rf"{re.escape(class_name)}\s*\(", candidate, re.S) is not None:
                    return_expression = candidate
                    static_record = True
            if return_expression is None:
                continue
            factory: dict[str, Any] = {
                "name": function_match.group(1),
                "line": text.count("\n", 0, body_opening + 1 + companion_opening + 1 + function_match.start()) + 1,
                "return_expression": return_expression,
                "parameters": parameters,
                "static_record": static_record,
            }
            if local_values:
                factory["local_values"] = local_values
            factories.append(factory)
    return factories


def extract_static_string_helpers(files: dict[str, str]) -> list[dict[str, Any]]:
    helpers = []
    # Recognize the complete grouping algorithm, never infer behavior from a helper's name.
    grouping = re.compile(
        r'val(?P<builder>\w+)=StringBuilder\(\)var(?P<count>\w+)=0'
        r'for\((?P<char>\w+)inthis\)\{if\((?P=count)>0&&(?P=count)%(?P<group>\w+)==0\)'
        r'\{(?P=builder)\.append\((?P<divider>\w+)\)\}'
        r'(?P=builder)\.append\((?P=char)\)(?P=count)\+\+\}'
        r'return(?P=builder)\.toString\(\)')
    for source, text in sorted(files.items()):
        if not source.endswith('.kt'):
            continue
        code = lexical_code_mask(text)
        for match in re.finditer(r'\bfun\s+String\.(\w+)\s*\(', code):
            end = balanced_closing(code, match.end() - 1, '(', ')')
            if end is None:
                continue
            signature = re.match(r'\s*:\s*String\s*\{', code[end + 1:])
            if signature is None:
                continue
            opening = end + signature.end()
            closing = balanced_closing(code, opening, '{', '}')
            if closing is None:
                continue
            body = re.sub(r'\s+', '', code[opening + 1:closing])
            algorithm = grouping.fullmatch(body)
            if algorithm is None:
                continue
            helpers.append({'name': match.group(1), 'source': source,
                            'line': text.count('\n', 0, match.start()) + 1,
                            'kind': 'group_string', 'group_parameter': algorithm['group'],
                            'separator_parameter': algorithm['divider'],
                            'parameters': compact_parameters(text[match.end():end])})
    return helpers


def extract_kotlin_data_classes(files: dict[str, str]) -> dict[str, Any]:
    classes: list[dict[str, Any]] = []
    for relative, text in sorted(files.items()):
        if not relative.endswith((".kt", ".kts")):
            continue
        code = lexical_code_mask(text)
        for match in re.finditer(r"\bdata\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code):
            opening = match.end() - 1
            closing = balanced_closing(code, opening, "(", ")")
            if closing is None:
                continue
            properties: list[dict[str, Any]] = []
            for chunk in split_top_level(text[opening + 1 : closing]):
                chunk, annotations = strip_parameter_annotations(chunk)
                property_match = re.match(
                    r"\s*(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^=,\r\n]+?)(?:\s*=\s*(.+))?\s*$",
                    chunk,
                    re.S,
                )
                if property_match is None:
                    continue
                property_item: dict[str, Any] = {
                    "name": property_match.group(1),
                    "type": normalize_expression(property_match.group(2)),
                }
                if annotations:
                    property_item["annotations"] = annotations
                if property_match.group(3) is not None:
                    property_item["default"] = normalize_expression(property_match.group(3))
                properties.append(property_item)
            item: dict[str, Any] = {
                    "source": relative,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "name": match.group(1),
                    "properties": properties,
                }
            factories = extract_data_class_factory_functions(
                relative,
                text,
                code,
                match.group(1),
                closing,
            )
            if factories:
                item["factories"] = factories
            classes.append(item)
        for match in re.finditer(r"\bsealed\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code):
            class_name = match.group(1)
            opening = match.end() - 1
            closing = balanced_closing(code, opening, "(", ")")
            if closing is None:
                continue
            body_opening = code.find("{", closing)
            body_closing = balanced_closing(code, body_opening, "{", "}") if body_opening >= 0 else None
            if body_opening < 0 or body_closing is None:
                continue
            properties = []
            for chunk in split_top_level(text[opening + 1 : closing]):
                chunk, annotations = strip_parameter_annotations(chunk)
                property_match = re.match(
                    r"\s*(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^=,\r\n]+?)(?:\s*=\s*(.+))?\s*$",
                    chunk,
                    re.S,
                )
                if property_match is None:
                    continue
                property_item: dict[str, Any] = {
                    "name": property_match.group(1),
                    "type": normalize_expression(property_match.group(2)),
                }
                if annotations:
                    property_item["annotations"] = annotations
                if property_match.group(3) is not None:
                    property_item["default"] = normalize_expression(property_match.group(3))
                properties.append(property_item)
            if not properties:
                continue
            body = text[body_opening + 1 : body_closing]
            body_code = code[body_opening + 1 : body_closing]
            objects: list[dict[str, Any]] = []
            object_pattern = re.compile(
                rf"\bobject\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*{re.escape(class_name)}\s*\(",
            )
            for object_match in object_pattern.finditer(body_code):
                object_opening = object_match.end() - 1
                object_closing = balanced_closing(body_code, object_opening, "(", ")")
                if object_closing is None:
                    continue
                arguments = [
                    normalize_expression(item)
                    for item in split_top_level(body[object_opening + 1 : object_closing])
                    if normalize_expression(item)
                ]
                objects.append(
                    {
                        "name": object_match.group(1),
                        "expression": f"{class_name}.{object_match.group(1)}",
                        "arguments": arguments,
                    }
                )
            if objects:
                classes.append(
                    {
                        "source": relative,
                        "line": text.count("\n", 0, match.start()) + 1,
                        "name": class_name,
                        "kind": "sealed_resource_class",
                        "properties": properties,
                        "objects": objects,
                    }
                )
    return {
        "status": "candidate_requires_review",
        "authoritative": False,
        "class_count": len(classes),
        "classes": classes,
        "string_helpers": extract_static_string_helpers(files),
        "limitations": [
            "Only primary-constructor data class properties are retained.",
            "Property types are candidates until imports, aliases, generics, and runtime defaults are reconciled.",
        ],
    }


def top_level_semicolon(value: str) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
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
        elif character in "([{<":
            depth += 1
        elif character in ")]}>":
            depth = max(0, depth - 1)
        elif character == ";" and depth == 0:
            return index
    return None


def kotlin_string_literal_value(value: str) -> str | None:
    stripped = normalize_expression(value)
    if not (stripped.startswith('"') and stripped.endswith('"')):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, str) else None


def enum_constructor_string_parameters(parameters_source: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for index, chunk in enumerate(split_top_level(parameters_source)):
        normalized = normalize_expression(chunk)
        match = re.search(
            r"\b(?:(?:override)\s+)?(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*String\b",
            normalized,
        )
        if match is not None:
            result.append((index, match.group(1)))
    return result


def extract_kotlin_enums(files: dict[str, str]) -> dict[str, Any]:
    classes: list[dict[str, Any]] = []
    for relative, text in sorted(files.items()):
        if not relative.endswith((".kt", ".kts")):
            continue
        code = lexical_code_mask(text)
        for match in re.finditer(r"\benum\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\b", code):
            cursor = match.end()
            while cursor < len(code) and code[cursor].isspace():
                cursor += 1
            string_parameters: list[tuple[int, str]] = []
            if cursor < len(code) and code[cursor] == "(":
                closing = balanced_closing(code, cursor, "(", ")")
                if closing is None:
                    continue
                string_parameters = enum_constructor_string_parameters(text[cursor + 1 : closing])
                cursor = closing + 1
            body_opening = code.find("{", cursor)
            if body_opening < 0:
                continue
            body_closing = balanced_closing(code, body_opening, "{", "}")
            if body_closing is None:
                continue
            body = text[body_opening + 1 : body_closing]
            entry_end = top_level_semicolon(body)
            entries_source = body if entry_end is None else body[:entry_end]
            values: list[str] = []
            string_properties: dict[str, dict[str, str]] = collections.defaultdict(dict)
            for chunk in split_top_level(entries_source):
                entry = normalize_expression(chunk)
                entry_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\b(?:\s*\((.*)\))?", entry, re.S)
                if entry_match is not None:
                    entry_name = entry_match.group(1)
                    values.append(entry_name)
                    if string_parameters and entry_match.group(2) is not None:
                        arguments = split_top_level(entry_match.group(2))
                        for parameter_index, property_name in string_parameters:
                            if parameter_index >= len(arguments):
                                continue
                            literal = kotlin_string_literal_value(arguments[parameter_index])
                            if literal is not None:
                                string_properties[property_name][entry_name] = literal
            if values:
                item = {
                    "source": relative,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "name": match.group(1),
                    "values": values,
                }
                if string_properties:
                    item["string_properties"] = {
                        name: dict(mapping)
                        for name, mapping in sorted(string_properties.items())
                    }
                classes.append(item)
    return {
        "status": "candidate_requires_review",
        "authoritative": False,
        "class_count": len(classes),
        "classes": classes,
        "limitations": [
            "Enum entry names and literal String constructor properties are retained as candidates; non-literal constructor values and member functions require source reconciliation.",
            "Enum entry names may be used as string-backed UI state only after imports and aliases are reconciled by the generator.",
        ],
    }


def strip_leading_kotlin_annotations(chunk: str) -> str:
    stripped = chunk.lstrip()
    while stripped.startswith("@"):
        annotation = re.match(
            r"@(?:[A-Za-z_][A-Za-z0-9_]*:)?[A-Za-z_][A-Za-z0-9_.]*",
            stripped,
        )
        if annotation is None:
            break
        index = annotation.end()
        if index < len(stripped) and stripped[index] == "(":
            code = lexical_code_mask(stripped)
            closing = balanced_closing(code, index, "(", ")")
            if closing is None:
                break
            index = closing + 1
        stripped = stripped[index:].lstrip()
    return stripped


def call_named_arguments(
    expression: str,
) -> tuple[str, dict[str, str]] | None:
    code = lexical_code_mask(expression)
    match = re.match(
        r"\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\(",
        code,
    )
    if match is None:
        return None
    opening = match.end() - 1
    closing = balanced_closing(code, opening, "(", ")")
    if closing is None:
        return None
    arguments: dict[str, str] = {}
    for chunk in split_top_level(expression[opening + 1 : closing]):
        named = split_named_argument(chunk)
        if named is not None:
            arguments[named[0]] = named[1]
    return match.group(1).rsplit(".", 1)[-1], arguments


def parse_conditional_binding(
    declaration: dict[str, Any],
) -> dict[str, str] | None:
    expression = declaration["expression"]
    code = lexical_code_mask(expression)
    match = re.match(r"\s*if\s*\(", code)
    if match is None:
        return None
    condition_opening = match.end() - 1
    condition_closing = balanced_closing(
        code,
        condition_opening,
        "(",
        ")",
    )
    if condition_closing is None:
        return None
    true_opening = code.find("{", condition_closing + 1)
    true_closing = balanced_closing(code, true_opening, "{", "}")
    if true_closing is None:
        return None
    else_match = re.match(r"\s*else\s*\{", code[true_closing + 1 :])
    if else_match is None:
        return None
    false_opening = true_closing + 1 + else_match.end() - 1
    false_closing = balanced_closing(code, false_opening, "{", "}")
    if false_closing is None:
        return None
    return {
        "name": declaration["name"],
        "condition": normalize_expression(
            expression[condition_opening + 1 : condition_closing]
        ),
        "when_true": normalize_expression(
            expression[true_opening + 1 : true_closing]
        ),
        "when_false": normalize_expression(
            expression[false_opening + 1 : false_closing]
        ),
    }


def extract_compose_theme_tokens(files: dict[str, str]) -> dict[str, Any]:
    tokens: list[dict[str, Any]] = []
    color_schemes: list[dict[str, Any]] = []
    extended_color_sets: list[dict[str, Any]] = []
    color_accessors: list[dict[str, str]] = []
    typography_sets: list[dict[str, Any]] = []
    shape_sets: list[dict[str, Any]] = []
    theme_applications: list[dict[str, Any]] = []
    data_classes = extract_kotlin_data_classes(files)["classes"]
    color_data_classes: dict[str, dict[str, str | None]] = {}
    for data_class in data_classes:
        properties = data_class.get("properties")
        if not isinstance(properties, list):
            continue
        color_properties: dict[str, str | None] = {}
        for property_item in properties:
            if not isinstance(property_item, dict):
                continue
            name = property_item.get("name")
            kotlin_type = str(property_item.get("type", "")).replace("?", "").strip()
            if not isinstance(name, str) or kotlin_type.rsplit(".", 1)[-1] != "Color":
                continue
            default = property_item.get("default")
            color_properties[name] = default if isinstance(default, str) else None
        if color_properties:
            color_data_classes[str(data_class["name"])] = color_properties

    def inferred_theme_variant(name: str) -> str | None:
        lowered = name.lower()
        if lowered.startswith("light"):
            return "light"
        if lowered.startswith("dark"):
            return "dark"
        return None

    for relative, text in sorted(files.items()):
        if not relative.endswith((".kt", ".kts")):
            continue
        for accessor in re.finditer(r'\bval\s+MaterialTheme\.(\w+)\s*:\s*(\w+)\s+@Composable\s+get\(\)\s*=\s*(\w+)\.current', lexical_code_mask(text)):
            if accessor.group(2) in color_data_classes:
                color_accessors.append({'source': relative, 'expression': 'MaterialTheme.' + accessor.group(1),
                                        'type': accessor.group(2), 'composition_local': accessor.group(3)})
        declarations = extract_kotlin_val_declarations(relative, text)
        conditional_bindings = [
            parsed
            for declaration in declarations
            if (parsed := parse_conditional_binding(declaration)) is not None
        ]
        for declaration in declarations:
            expression = declaration["expression"]
            parsed_call = call_named_arguments(expression)
            callee = parsed_call[0] if parsed_call is not None else None
            arguments = parsed_call[1] if parsed_call is not None else {}
            token: dict[str, Any] | None = None
            if callee == "Color" or re.fullmatch(
                r"Color\.[A-Za-z_][A-Za-z0-9_]*",
                normalize_expression(expression),
            ):
                token = {
                    **declaration,
                    "kind": "color",
                    **expression_semantics(expression),
                }
                argb = re.fullmatch(
                    r"\s*Color\s*\(\s*0x([0-9A-Fa-f]{8})\s*\)\s*",
                    expression,
                )
                if argb is not None:
                    token["argb_hex"] = f"#{argb.group(1).upper()}"
            elif callee in {"Font", "FontFamily"} or re.fullmatch(
                r"FontFamily\.[A-Za-z_][A-Za-z0-9_]*",
                normalize_expression(expression),
            ):
                token = {
                    **declaration,
                    "kind": "font_family" if callee != "Font" else "font",
                    **expression_semantics(expression),
                    "font_resource_keys": sorted(
                        set(
                            re.findall(
                                r"\bR\.font\.([A-Za-z_][A-Za-z0-9_]*)",
                                expression,
                            )
                        )
                    ),
                }
            else:
                semantics = expression_semantics(expression)
                if semantics["dimensions"] and re.fullmatch(
                    r"\s*-?[0-9]+(?:\.[0-9]+)?\s*\.\s*(?:dp|sp)\s*",
                    expression,
                ):
                    token = {
                        **declaration,
                        "kind": "dimension",
                        **semantics,
                    }
                else:
                    number = re.fullmatch(
                        r"\s*(-?[0-9]+(?:\.[0-9]+)?)(?:[fFdD])?\s*",
                        expression,
                    )
                    if number is not None:
                        token = {
                            **declaration,
                            "kind": "number",
                            "value": number.group(1),
                            **semantics,
                        }
            if token is not None:
                tokens.append(token)

            if callee in {
                "lightColorScheme",
                "darkColorScheme",
                "lightColors",
                "darkColors",
            }:
                color_schemes.append(
                    {
                        "source": relative,
                        "line": declaration["line"],
                        "name": declaration["name"],
                        "constructor": callee,
                        "variant": "light" if callee.startswith("light") else "dark",
                        "roles": {
                            name: expression_semantics(value)
                            for name, value in sorted(arguments.items())
                        },
                    }
                )
            elif callee in color_data_classes:
                roles: dict[str, Any] = {}
                for property_name, default in sorted(color_data_classes[callee].items()):
                    value = arguments.get(property_name) or default
                    if value is None:
                        continue
                    roles[property_name] = expression_semantics(value)
                if roles:
                    extended_color_sets.append(
                        {
                            "source": relative,
                            "line": declaration["line"],
                            "name": declaration["name"],
                            "constructor": callee,
                            "variant": inferred_theme_variant(declaration["name"]),
                            "roles": roles,
                        }
                    )
            elif callee == "Typography":
                from kotlin_psi import parse_declarations
                syntax = parse_declarations(text)
                scope = {'source': relative, 'imports': syntax['imports'],
                         'bindings': {p['name']: p['expression'] for p in syntax['globalProperties']
                                      if p.get('owner') is None}}
                styles: dict[str, Any] = {}
                for role, value in sorted(arguments.items()):
                    style = expression_semantics(value)
                    style['source_scope'] = scope
                    nested = call_named_arguments(value)
                    if nested is not None and nested[0] == "TextStyle":
                        style["properties"] = {
                            name: expression_semantics(nested_value)
                            for name, nested_value in sorted(nested[1].items())
                        }
                    styles[role] = style
                typography_sets.append(
                    {
                        "source": relative,
                        "line": declaration["line"],
                        "name": declaration["name"],
                        "styles": styles,
                    }
                )
            elif callee == "Shapes":
                shape_sets.append(
                    {
                        "source": relative,
                        "line": declaration["line"],
                        "name": declaration["name"],
                        "roles": {
                            name: expression_semantics(value)
                            for name, value in sorted(arguments.items())
                        },
                    }
                )

        code = lexical_code_mask(text)
        for match in re.finditer(r"\bMaterialTheme\s*\(", code):
            opening = match.end() - 1
            closing = balanced_closing(code, opening, "(", ")")
            if closing is None:
                continue
            arguments: dict[str, str] = {}
            for chunk in split_top_level(text[opening + 1 : closing]):
                named = split_named_argument(chunk)
                if named is not None:
                    arguments[named[0]] = named[1]
            referenced_variables = {
                normalize_expression(value)
                for value in arguments.values()
                if re.fullmatch(
                    r"[A-Za-z_][A-Za-z0-9_]*",
                    normalize_expression(value),
                )
            }
            theme_applications.append(
                {
                    "source": relative,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "arguments": {
                        name: expression_semantics(value)
                        for name, value in sorted(arguments.items())
                    },
                    "conditional_bindings": [
                        binding
                        for binding in conditional_bindings
                        if binding["name"] in referenced_variables
                    ],
                }
            )

    tokens_by_name: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for token in tokens:
        tokens_by_name[token["name"]].append(token)

    def resolve_token(
        semantics: dict[str, Any],
        allowed_kinds: set[str],
    ) -> None:
        name = semantics["expression"]
        copied_color = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.copy\s*\((.*)\)",
            name,
            re.S,
        )
        if copied_color is not None and "color" in allowed_kinds:
            arguments = {
                key: value
                for chunk in split_top_level(copied_color.group(2))
                if (named := split_named_argument(chunk)) is not None
                for key, value in [named]
            }
            alpha = arguments.get("alpha")
            alpha_match = re.fullmatch(
                r"\s*([0-9]+(?:\.[0-9]+)?)(?:[fFdD])?\s*",
                alpha or "",
            )
            if alpha_match is not None:
                alpha_value = float(alpha_match.group(1))
                candidates = [
                    token
                    for token in tokens_by_name.get(copied_color.group(1), [])
                    if token["kind"] == "color" and isinstance(token.get("argb_hex"), str)
                ]
                if len(candidates) == 1 and 0 <= alpha_value <= 1:
                    base = candidates[0]["argb_hex"]
                    alpha_hex = f"{int(alpha_value * 255 + 0.5):02X}"
                    semantics["resolved_token"] = {
                        "status": "resolved_unique",
                        "name": copied_color.group(1),
                        "kind": "color",
                        "argb_hex": f"#{alpha_hex}{base[-6:]}",
                        "alpha_override": alpha_match.group(1),
                    }
            return
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            return
        candidates = [
            token
            for token in tokens_by_name.get(name, [])
            if token["kind"] in allowed_kinds
        ]
        if not candidates:
            return
        if len(candidates) > 1:
            semantics["resolved_token"] = {
                "status": "ambiguous",
                "name": name,
                "candidate_count": len(candidates),
                "candidate_kinds": sorted({item["kind"] for item in candidates}),
            }
            return
        candidate = candidates[0]
        resolved: dict[str, Any] = {
            "status": "resolved_unique",
            "name": name,
            "kind": candidate["kind"],
        }
        if "argb_hex" in candidate:
            resolved["argb_hex"] = candidate["argb_hex"]
        if "font_resource_keys" in candidate:
            resolved["font_resource_keys"] = candidate["font_resource_keys"]
        if candidate.get("dimensions"):
            resolved["dimensions"] = candidate["dimensions"]
        semantics["resolved_token"] = resolved

    for scheme in color_schemes:
        for role in scheme["roles"].values():
            resolve_token(role, {"color"})
    for extended_set in extended_color_sets:
        for role in extended_set["roles"].values():
            resolve_token(role, {"color"})
    for typography in typography_sets:
        for style in typography["styles"].values():
            for property_name, property_semantics in style.get(
                "properties", {}
            ).items():
                if property_name == "fontFamily":
                    resolve_token(property_semantics, {"font", "font_family"})
                elif property_name in {"fontSize", "lineHeight", "letterSpacing"}:
                    resolve_token(property_semantics, {"dimension"})

    return {
        "status": "candidate_requires_review",
        "authoritative": False,
        "token_count": len(tokens),
        "tokens": sorted(
            tokens,
            key=lambda item: (item["source"], item["line"], item["name"]),
        ),
        "color_scheme_count": len(color_schemes),
        "color_schemes": sorted(
            color_schemes,
            key=lambda item: (item["source"], item["line"], item["name"]),
        ),
        "extended_color_set_count": len(extended_color_sets),
        "color_accessors": color_accessors,
        "extended_color_sets": sorted(
            extended_color_sets,
            key=lambda item: (item["source"], item["line"], item["name"]),
        ),
        "typography_set_count": len(typography_sets),
        "typography_sets": sorted(
            typography_sets,
            key=lambda item: (item["source"], item["line"], item["name"]),
        ),
        "shape_set_count": len(shape_sets),
        "shape_sets": sorted(
            shape_sets,
            key=lambda item: (item["source"], item["line"], item["name"]),
        ),
        "theme_application_count": len(theme_applications),
        "theme_applications": sorted(
            theme_applications,
            key=lambda item: (item["source"], item["line"]),
        ),
        "limitations": [
            "Static Kotlin scanning does not resolve aliases, delegated values, helper-returned themes, CompositionLocal overrides, or generated code.",
            "Bare token references are resolved only when one compatible declaration is unique across the snapshot; duplicate names remain explicitly ambiguous.",
            "Color, typography, shape, and dimension expressions remain candidate source tokens until imports and runtime branches are reconciled.",
            "Material defaults still require the project's resolved Compose Material version.",
        ],
    }


def ordered_modifier_chain(expression: str) -> list[dict[str, Any]]:
    code = lexical_code_mask(expression, mask_strings=False)
    result: list[dict[str, Any]] = []
    depths = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}
    index = 0
    while index < len(code):
        character = code[index]
        if character in depths:
            depths[character] += 1
        elif character in pairs:
            opener = pairs[character]
            depths[opener] = max(0, depths[opener] - 1)
        elif character == "." and not any(depths.values()):
            match = re.match(
                r"\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(",
                code[index:],
            )
            if match is not None:
                opening = index + match.end() - 1
                closing = balanced_closing(code, opening, "(", ")")
                if closing is not None:
                    arguments = expression[opening + 1 : closing]
                    semantics = expression_semantics(arguments)
                    item = {
                        "name": match.group(1),
                        "arguments": semantics.pop("expression"),
                        **semantics,
                    }
                    next_index = closing + 1
                    while next_index < len(code) and code[next_index].isspace():
                        next_index += 1
                    if next_index < len(code) and code[next_index] == "{":
                        lambda_closing = balanced_closing(code, next_index, "{", "}")
                        if lambda_closing is not None:
                            item["trailing_lambda"] = normalize_expression(expression[next_index : lambda_closing + 1])
                            next_index = lambda_closing + 1
                    # Display-normalized expressions cannot be reparsed safely: newlines
                    # separate Kotlin statements and string contents must stay intact.
                    item["syntax_expression"] = expression[index + 1 : next_index].strip()
                    result.append(item)
                    index = next_index
                    continue
            match = re.match(
                r"\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{",
                code[index:],
            )
            if match is not None:
                opening = index + match.end() - 1
                closing = balanced_closing(code, opening, "{", "}")
                if closing is not None:
                    arguments = expression[opening + 1 : closing]
                    semantics = expression_semantics(arguments)
                    result.append(
                        {
                            "name": match.group(1),
                            "arguments": semantics.pop("expression"),
                            "syntax_expression": expression[index + 1 : closing + 1].strip(),
                            **semantics,
                        }
                    )
                    index = closing + 1
                    continue
        index += 1
    return result


def local_value_expressions(body: str, body_code: str, top_level_only: bool = False) -> dict[str, str]:
    values: dict[str, str] = {}
    end_code = lexical_code_mask(body, mask_strings=False)
    for match in re.finditer(r"\b(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*[^=\n]+)?\s*=", body_code):
        prefix = body_code[:match.start()]
        if top_level_only and (prefix.count('{') != prefix.count('}') or prefix.count('(') != prefix.count(')')):
            continue
        expression_start = match.end()
        expression_end = local_value_expression_end(end_code, expression_start)
        expression = body[expression_start:expression_end].strip()
        if expression:
            values[match.group(1)] = expression
    for match in re.finditer(r"\b(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*[^=\n]+)?\s+by\s+", body_code):
        prefix = body_code[:match.start()]
        if top_level_only and (prefix.count('{') != prefix.count('}') or prefix.count('(') != prefix.count(')')):
            continue
        expression_start = match.end()
        expression_end = local_value_expression_end(end_code, expression_start)
        expression = body[expression_start:expression_end].strip()
        if expression:
            values[match.group(1)] = expression
    return values


def local_value_expression_end(code: str, start: int) -> int:
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    index = start
    seen_token = False
    while index < len(code):
        char = code[index]
        if char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth > 0:
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]" and bracket_depth > 0:
            bracket_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}" and brace_depth > 0:
            brace_depth -= 1
        elif char in {"\n", "\r"} and seen_token and paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
            next_index = index + 1
            while next_index < len(code) and code[next_index].isspace():
                next_index += 1
            if next_index < len(code) and code[next_index] == ".":
                index += 1
                continue
            if code.startswith("else", next_index) and (
                next_index + len("else") == len(code)
                or not (code[next_index + len("else")].isalnum() or code[next_index + len("else")] == "_")
            ):
                index += 1
                continue
            return index
        if not char.isspace():
            seen_token = True
        index += 1
    return index


def trailing_lambda_parameter_names(lambda_source: str) -> list[str]:
    match = re.match(
        r"\s*([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\s*->",
        lexical_code_mask(lambda_source),
    )
    if match is None:
        return []
    return [name.strip() for name in match.group(1).split(",")]


def canvas_draw_commands(lambda_source: str) -> list[dict[str, Any]]:
    code = lexical_code_mask(lambda_source, mask_strings=False)
    commands: list[dict[str, Any]] = []
    index = 0
    while index < len(code):
        match = re.search(r"\bdrawArc\s*\(", code[index:])
        if match is None:
            break
        opening = index + match.end() - 1
        closing = balanced_closing(code, opening, "(", ")")
        if closing is None:
            break
        arguments: dict[str, str] = {}
        for chunk, _, _ in split_top_level_spans(lambda_source[opening + 1 : closing]):
            named = split_named_argument(chunk)
            if named is not None:
                arguments[named[0]] = normalize_expression(named[1])
        commands.append({"kind": "arc", "arguments": arguments})
        index = closing + 1
    return commands


def receiver_expression_before_member_call(body: str, body_code: str, dot_index: int) -> str | None:
    end = dot_index
    while end > 0 and body_code[end - 1].isspace():
        end -= 1
    start = end
    call_receiver = start > 0 and body_code[start - 1] == ")"
    if call_receiver:
        depth = 1
        start -= 1
        while start > 0 and depth:
            start -= 1
            depth += (body_code[start] == ")") - (body_code[start] == "(")
        if depth:
            return None
    name_end = start
    while start > 0:
        char = body_code[start - 1]
        if char.isalnum() or char in {"_", ".", "?"}:
            start -= 1
            continue
        break
    receiver = body[start:end].strip()
    if receiver.endswith("?"):
        receiver = receiver[:-1].strip()
    name = body[start:name_end] if call_receiver else receiver
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:(?:\?\.|\.)[A-Za-z_][A-Za-z0-9_]*)*", name):
        return None
    return normalize_expression(receiver)


def implicit_it_let_scopes(body: str, body_code: str) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    for match in re.finditer(r"\.let\s*\{", body_code):
        receiver = receiver_expression_before_member_call(body, body_code, match.start())
        if receiver is None:
            continue
        opening = match.end() - 1
        closing = balanced_closing(body_code, opening, "{", "}")
        if closing is None:
            continue
        raw_lambda_body = body[opening + 1 : closing]
        parameters = trailing_lambda_parameter_names(raw_lambda_body)
        if len(parameters) > 1:
            continue
        scopes.append(
            {
                "start": opening + 1,
                "end": closing,
                "parameter": parameters[0] if parameters else "it",
                "receiver": receiver,
            }
        )
    return scopes


def implicit_it_expression(expression: str, scope: dict[str, Any]) -> str | None:
    parameter = scope["parameter"]
    receiver = scope["receiver"]
    stripped = expression.strip()
    if stripped == parameter:
        return f"{receiver} ?: \"\""
    member_access = re.fullmatch(
        rf"{re.escape(parameter)}((?:\.[A-Za-z_][A-Za-z0-9_]*)+)(.*)",
        stripped,
        re.S,
    )
    if member_access is not None:
        return f"{receiver}?.{member_access.group(1)[1:]}{member_access.group(2)}"
    return None


def rewrite_implicit_it_member_access(expression: str, scope: dict[str, Any]) -> str | None:
    direct = implicit_it_expression(expression, scope)
    if direct is not None:
        return direct
    parameter = scope["parameter"]
    receiver = scope["receiver"]
    masked = lexical_code_mask(expression)
    if re.search(rf"\b{re.escape(parameter)}\.", masked) is None:
        return None
    rewritten = re.sub(rf"\b{re.escape(parameter)}\.", f"{receiver}?.", expression)
    return normalize_expression(rewritten)


def enclosing_if_conditions(body: str, body_code: str) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    chain_members: set[int] = set()

    def next_token(index: int) -> int:
        while index < len(body_code) and body_code[index].isspace():
            index += 1
        return index

    def read_branch(start: int) -> tuple[str, int, int] | None:
        condition_open = body_code.find("(", start)
        condition_close = balanced_closing(body_code, condition_open, "(", ")")
        if condition_close is None:
            return None
        block_open = next_token(condition_close + 1)
        if block_open >= len(body_code) or body_code[block_open] != "{":
            return None
        block_close = balanced_closing(body_code, block_open, "{", "}")
        if block_close is None:
            return None
        condition = body[condition_open + 1 : condition_close].strip()
        return (condition, block_open + 1, block_close) if condition else None

    for match in re.finditer(r"\bif\s*\(", body_code):
        if match.start() in chain_members:
            continue
        branch_start = match.start()
        prior: list[str] = []
        chain: list[dict[str, Any]] = []
        while (branch := read_branch(branch_start)) is not None:
            condition, start, end = branch
            expression = " && ".join([*(f"!({item})" for item in prior), f"({condition})"]) if prior else condition
            chain.append({'start': start, 'end': end, 'condition': expression,
                          'branch_id': 'then' if not prior else f'else-if-{len(prior)}'})
            prior.append(condition)
            else_start = next_token(end + 1)
            if not body_code.startswith('else', else_start):
                break
            else_open = next_token(else_start + 4)
            if re.match(r'if\s*\(', body_code[else_open:]):
                chain_members.add(else_open)
                branch_start = else_open
                continue
            if else_open < len(body_code) and body_code[else_open] == '{':
                else_close = balanced_closing(body_code, else_open, '{', '}')
                if else_close is not None:
                    chain.append({'start': else_open + 1, 'end': else_close,
                                  'condition': ' && '.join(f'!({item})' for item in prior),
                                  'branch_id': 'else'})
            break
        branches = [item['branch_id'] for item in chain]
        if chain and 'else' not in branches:
            branches.append('else')
        conditions.extend({**item, 'group_id': f'if:{match.start()}', 'branches': branches} for item in chain)
    return conditions


def enclosing_when_conditions(body: str, body_code: str) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for match in re.finditer(r"\bwhen\s*(\(|\{)", body_code):
        subject: str | None = None
        if match.group(1) == "(":
            subject_open = match.end() - 1
            subject_close = balanced_closing(body_code, subject_open, "(", ")")
            if subject_close is None:
                continue
            subject = normalize_expression(body[subject_open + 1 : subject_close])
            block_open = subject_close + 1
        else:
            block_open = match.end() - 1
        while block_open < len(body_code) and body_code[block_open].isspace():
            block_open += 1
        if block_open >= len(body_code) or body_code[block_open] != "{":
            continue
        block_close = balanced_closing(body_code, block_open, "{", "}")
        if block_close is None:
            continue
        if subject is not None and not subject:
            continue
        branch_code = body_code[block_open + 1 : block_close]
        branch_offset = block_open + 1
        prior_conditions: list[str] = []
        branches = []
        for branch in re.finditer(r"(?m)^([^\n]*?)->", branch_code):
            prefix = branch_code[: branch.start()]
            if prefix.count("{") != prefix.count("}"):
                continue
            label = normalize_expression(body[branch_offset + branch.start(1) : branch_offset + branch.end(1)])
            if not label:
                continue
            branches.append((branch, label))
        for index, (branch, label) in enumerate(branches):
            branch_start = branch_offset + branch.end()
            while branch_start < block_close and body_code[branch_start].isspace():
                branch_start += 1
            if branch_start >= block_close:
                continue
            if body_code[branch_start] == "{":
                branch_end = balanced_closing(body_code, branch_start, "{", "}")
                if branch_end is None or branch_end > block_close:
                    continue
                range_start = branch_start + 1
            else:
                branch_end = (
                    branch_offset + branches[index + 1][0].start()
                    if index + 1 < len(branches)
                    else block_close
                )
                range_start = branch_start
            if label == "else":
                if not prior_conditions:
                    continue
                condition = "!(" + " || ".join(prior_conditions) + ")"
            else:
                if subject is None:
                    branch_condition = label
                elif label.startswith(("is ", "!is ")):
                    branch_condition = f"{subject} {label}"
                else:
                    branch_condition = f"{subject} == {label}"
                condition = (
                    f"({branch_condition}) && !({' || '.join(prior_conditions)})"
                    if prior_conditions
                    else branch_condition
                )
                prior_conditions.append(branch_condition)
            conditions.append(
                {
                    "start": range_start,
                    "end": branch_end,
                    "condition": condition,
                    "group_id": f"when:{match.start()}",
                    "branch_id": label,
                    "branches": [item[1] for item in branches],
                }
            )
    return conditions


def lazy_items_scopes(body: str, body_code: str) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    for match in re.finditer(r"\b(items|itemsIndexed)\s*\(", body_code):
        opening = body_code.find("(", match.start())
        if opening < 0:
            continue
        closing = balanced_closing(body_code, opening, "(", ")")
        if closing is None:
            continue
        raw_arguments = body[opening + 1 : closing]
        collection_expression: str | None = None
        for chunk, _, _ in split_top_level_spans(raw_arguments):
            named = split_named_argument(chunk)
            if named is None:
                if collection_expression is None:
                    collection_expression = chunk.strip()
            elif named[0] in {"items", "count"}:
                collection_expression = named[1].strip()
        if collection_expression is None:
            continue
        lambda_opening = closing + 1
        while lambda_opening < len(body_code) and body_code[lambda_opening].isspace():
            lambda_opening += 1
        if lambda_opening >= len(body_code) or body_code[lambda_opening] != "{":
            continue
        lambda_end = balanced_closing(body_code, lambda_opening, "{", "}")
        if lambda_end is None:
            continue
        raw_lambda_body = body[lambda_opening + 1 : lambda_end]
        from kotlin_psi import parse_expression
        parameters = parse_expression('{' + raw_lambda_body + '}').get('parameterPatterns') or ['it']
        indexed = match.group(1) == 'itemsIndexed'
        if len(parameters) != (2 if indexed else 1):
            continue
        scopes.append(
            {
                "start": lambda_opening + 1,
                "end": lambda_end,
                "collection": normalize_expression(collection_expression),
                "item_parameter": parameters[-1],
                "accepts_count": not indexed,
                **({'index_parameter': parameters[0]} if indexed else {}),
            }
        )
    return scopes


def for_each_scopes(body: str, body_code: str) -> list[dict[str, Any]]:
    from kotlin_psi import parse_declarations
    scopes: list[dict[str, Any]] = []
    if 'forEach' not in body_code:
        return scopes
    prefix = 'fun scopedContent() {\n'
    syntax = parse_declarations(prefix + body + '\n}')
    for call in syntax.get('qualifiedCalls', []):
        if call.get('callee') not in {'forEach', 'forEachIndexed'} or len(call.get('lambdaScopes', [])) != 1:
            continue
        scope = call['lambdaScopes'][0]
        parameters = scope['expression'].get('parameterPatterns') or ['it']
        indexed = call['callee']=='forEachIndexed'
        if len(parameters) != (2 if indexed else 1):
            continue
        scopes.append(
            {
                "start": scope['start'] - len(prefix),
                "end": scope['end'] - len(prefix),
                "collection": call['receiver'],
                "item_parameter": parameters[-1],
                **({'index_parameter':parameters[0]} if indexed else {}),
            }
        )
    return scopes


def extract_semantic_ui_calls(
    relative: str,
    source_text: str,
    composable: str,
    body: str,
    body_opening: int,
    associated_custom_images: set[str],
    resolved_custom_composables: dict[str, list[dict[str, str]]],
    resolved_custom_composable_parameters: dict[str, list[dict[str, str]]],
    slot_parameter_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    body_code = lexical_code_mask(body)
    from kotlin_psi import parse_declarations
    scope_prefix = 'fun __scope() {'
    scope_syntax = parse_declarations(scope_prefix + body + '}')
    scoped_bindings = scope_syntax['localBindings']
    from ui_migration.frontend.callable_inventory import callable_field_names
    from kotlin_psi import parse_expression
    callable_names = callable_field_names(parse_declarations(source_text))
    stored_lambdas = []
    def collect_lambdas(node):
        if isinstance(node, dict):
            if node.get('kind')=='lambda':
                stored_lambdas.append(node)
            for value in node.values():
                collect_lambdas(value)
        elif isinstance(node, list):
            for value in node:
                collect_lambdas(value)
    for binding in scoped_bindings:
        expression = parse_expression(binding['expression'])
        collect_lambdas(expression)
        def has_callable(node):
            if isinstance(node, dict):
                return node.get('kind') in ('lambda','callable_reference') or any(has_callable(v) for v in node.values())
            return isinstance(node, list) and any(has_callable(v) for v in node)
        if has_callable(expression):
            callable_names.add(binding['name'])
    qualified_calls = {call['start'] - len(scope_prefix): call['name'] for call in scope_syntax['qualifiedCalls']}
    file_values = local_value_expressions(source_text, lexical_code_mask(source_text), top_level_only=True)
    let_scopes = implicit_it_let_scopes(body, body_code)
    if_conditions = enclosing_if_conditions(body, body_code)
    when_conditions = enclosing_when_conditions(body, body_code)
    item_scopes = lazy_items_scopes(body, body_code)
    item_scopes.extend(for_each_scopes(body, body_code))
    item_scopes.extend({**scope, 'start': scope['start'] - len(scope_prefix),
                        'end': scope['end'] - len(scope_prefix)}
                       for scope in scope_syntax.get('forLoops', []))
    slot_parameter_names = slot_parameter_names or set()
    candidates: list[dict[str, Any]] = []
    for match in re.finditer(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(\(|\{)",
        body_code,
    ):
        local_values = {}
        for binding in sorted(scoped_bindings, key=lambda entry: entry['start']):
            if binding['start'] <= match.start() + len(scope_prefix) < binding['end']:
                expression = binding['expression']
                if binding.get('delegated'):
                    expression = 'run { val ' + binding['name'] + ' by ' + expression + '; ' + binding['name'] + ' }'
                local_values[binding['name']] = expression
        opening = match.end() - 1
        delimiter = match.group(2)
        if delimiter == "(":
            closing = balanced_closing(body_code, opening, "(", ")")
            if closing is None:
                continue
            raw_arguments = body[opening + 1 : closing]
        else:
            closing = opening
            raw_arguments = ""
        argument_spans = [span for span in split_top_level_spans(raw_arguments) if span[0].strip()]
        argument_chunks = [chunk for chunk, _, _ in argument_spans]
        named_arguments = dict(
            named
            for chunk in argument_chunks
            if (named := split_named_argument(chunk)) is not None
        )
        modifier_expression = named_arguments.get("modifier", "")
        if not modifier_expression:
            for chunk in argument_chunks:
                if split_named_argument(chunk) is not None:
                    continue
                candidate = chunk.strip()
                if re.match(r"^Modifier\b", lexical_code_mask(candidate)) is not None:
                    modifier_expression = candidate
                    break
        positional_arguments = []
        for chunk in argument_chunks:
            if split_named_argument(chunk) is not None:
                continue
            candidate = chunk.strip()
            if not candidate or candidate == modifier_expression.strip():
                continue
            positional_arguments.append(expression_semantics(candidate))
        component = match.group(1)
        callable_invocation = component in callable_names or component == 'invoke'
        definition_name = qualified_calls.get(match.start(), component)
        if definition_name not in resolved_custom_composables:
            definition_name = component
        known_component = (
            component in COMPOSE_COMPONENTS
            or component in NATIVE_SLOTS
            or component in associated_custom_images
            or definition_name in resolved_custom_composables
            or component in slot_parameter_names
            or callable_invocation
        )
        if component[:1].islower() and not known_component:
            continue
        if (
            not known_component
            and not modifier_expression
            and "contentPadding" not in named_arguments
        ):
            continue
        after_call = closing + 1
        while after_call < len(body_code) and body_code[after_call].isspace():
            after_call += 1
        lambda_opening = opening if delimiter == "{" else after_call
        span_end = closing + 1
        trailing_lambda_expression = None
        raw_trailing_lambda_body: str | None = None
        trailing_lambda_parameters: list[str] = []
        trailing_lambda_span: tuple[int, int] | None = None
        if lambda_opening < len(body_code) and body_code[lambda_opening] == "{":
            lambda_end = balanced_closing(body_code, lambda_opening, "{", "}")
            if lambda_end is not None:
                span_end = lambda_end + 1
                raw_lambda_body = body[lambda_opening + 1 : lambda_end]
                raw_trailing_lambda_body = raw_lambda_body
                trailing_lambda_parameters = trailing_lambda_parameter_names(raw_lambda_body)
                lambda_body = normalize_expression(raw_lambda_body)
                trailing_lambda_expression = "{}" if not lambda_body else f"{{ {lambda_body} }}"
                trailing_lambda_span = (lambda_opening + 1, lambda_end)
        line = source_text.count("\n", 0, body_opening + match.start()) + 1
        implicit_scope = next(
            (
                scope
                for scope in sorted(
                    let_scopes,
                    key=lambda item: item["end"] - item["start"],
                )
                if scope["start"] <= match.start() < scope["end"]
            ),
            None,
        )
        visibility_conditions = [
            condition["condition"]
            for condition in sorted(
                if_conditions + when_conditions,
                key=lambda item: (item["start"], -(item["end"] - item["start"])),
            )
            if condition["start"] <= match.start() < condition["end"]
        ]
        visibility_condition = (
            " && ".join(f"({condition})" for condition in visibility_conditions)
            if len(visibility_conditions) > 1
            else visibility_conditions[0] if visibility_conditions else None
        )
        item_scope = next(
            (
                scope
                for scope in sorted(
                    item_scopes,
                    key=lambda item: item["end"] - item["start"],
                )
                if scope["start"] <= match.start() < scope["end"]
            ),
            None,
        )
        semantic_arguments = {
            name: expression_semantics(expression)
            for name, expression in named_arguments.items()
            if name in UI_SEMANTIC_ARGUMENTS
        }
        for name, semantics in semantic_arguments.items():
            expression = semantics.get("expression")
            if not isinstance(expression, str):
                continue
            local_expression = local_values.get(expression.strip())
            if local_expression is not None:
                semantics["resolved_local_expression"] = local_expression
            elif implicit_scope is not None:
                resolved_it = rewrite_implicit_it_member_access(expression, implicit_scope)
                if resolved_it is not None:
                    semantics["resolved_local_expression"] = resolved_it
        if implicit_scope is not None and component in {"Text", "BasicText", "ClickableText"}:
            for semantics in positional_arguments:
                expression = semantics.get("expression")
                if not isinstance(expression, str) or "resolved_local_expression" in semantics:
                    continue
                resolved_it = rewrite_implicit_it_member_access(expression, implicit_scope)
                if resolved_it is not None:
                    semantics["resolved_local_expression"] = resolved_it
        state_slots: list[dict[str, Any]] = []
        if component in associated_custom_images or component.endswith("Image"):
            for name, expression in sorted(named_arguments.items()):
                if name not in IMAGE_STATE_ARGUMENTS:
                    continue
                component_calls = re.findall(
                    r"\b([A-Z][A-Za-z0-9_]*)\s*\(",
                    lexical_code_mask(expression),
                )
                state_slots.append(
                    {
                        "name": name,
                        "component_calls": component_calls,
                        "contains_progress_indicator": any(
                            item in PROGRESS_COMPONENTS for item in component_calls
                        ),
                    }
                )
        modifier_chain = ordered_modifier_chain(modifier_expression)
        if implicit_scope is not None:
            for modifier in modifier_chain:
                arguments = modifier.get("arguments")
                if not isinstance(arguments, str):
                    continue
                resolved_arguments = rewrite_implicit_it_member_access(arguments, implicit_scope)
                if resolved_arguments is not None:
                    modifier["resolved_arguments"] = resolved_arguments
        candidate: dict[str, Any] = {
                "source": relative,
                "composable": composable,
                "line": line,
                "component": component,
                "call_id": "",
                "parent_call_id": None,
                "semantic_arguments": semantic_arguments,
                "positional_arguments": positional_arguments,
                "ordered_modifier_chain": modifier_chain,
                "modifier_expression": modifier_expression,
                "state_slots": state_slots,
                "trailing_lambda_parameters": trailing_lambda_parameters,
                "_start": match.start(),
                "_end": span_end,
            }
        if component == 'DecorationBox' and re.search(
            r'\bOutlinedTextFieldDefaults\s*\.\s*$', body_code[:match.start()]
        ):
            candidate['decoration_kind'] = 'material3-outlined'
        native_slots = NATIVE_SLOTS.get(component, set()) if definition_name not in resolved_custom_composables else set()
        if native_slots:
            candidate['native_slot_arguments'] = {name: expression for name, expression in named_arguments.items()
                                                  if name in native_slots}
            spans = []
            for chunk, chunk_start, chunk_end in argument_spans:
                named = split_named_argument(chunk)
                if named is not None and named[0] in native_slots:
                    spans.append({'name': named[0], 'start': opening + 1 + chunk_start,
                                  'end': opening + 1 + chunk_end})
            if component == 'Scaffold' and trailing_lambda_span is not None:
                spans.append({'name': 'content', 'start': trailing_lambda_span[0],
                              'end': trailing_lambda_span[1]})
            candidate['_slot_argument_spans'] = spans
        if component in slot_parameter_names or callable_invocation:
            candidate["slot_invocation"] = {
                "name": component,
                **({'expression':qualified_calls.get(match.start(), component)} if callable_invocation else {}),
                "arguments": [normalize_expression(chunk) for chunk in argument_chunks],
            }
        if component == "Canvas" and raw_trailing_lambda_body is not None:
            commands = canvas_draw_commands(raw_trailing_lambda_body)
            if commands:
                candidate["custom_draw_commands"] = commands
        if local_values:
            candidate["local_values"] = local_values
        if file_values:
            candidate["file_values"] = file_values
        if visibility_condition is not None:
            candidate["visibility_condition"] = expression_semantics(visibility_condition)
            candidate["ui_state_path"] = [
                {key: condition[key] for key in ("group_id", "branch_id", "branches", "condition")}
                for condition in sorted(if_conditions + when_conditions,
                                        key=lambda item: (item["start"], -item["end"]))
                if condition["start"] <= match.start() < condition["end"]
            ]
        if item_scope is not None:
            candidate["list_item_context"] = {
                "collection": item_scope["collection"],
                "item_parameter": item_scope["item_parameter"],
                "accepts_count": item_scope.get("accepts_count", False),
                **({'index_parameter':item_scope['index_parameter']} if 'index_parameter' in item_scope else {}),
            }
            candidate['list_item_contexts'] = [
                {'scope_id': f'{relative}:{composable}:{scope["start"]}',
                 **{key: scope[key] for key in ('collection', 'item_parameter', 'index_parameter', 'accepts_count') if key in scope}}
                for scope in sorted(item_scopes, key=lambda scope: (scope['start'], -scope['end']))
                if scope['start'] <= match.start() < scope['end']
            ]
        definitions = resolved_custom_composables.get(definition_name)
        if definitions is not None:
            invocation_arguments: list[dict[str, Any]] = []
            supplied_names: set[str] = set()
            slot_argument_spans: list[dict[str, Any]] = []
            parameters = resolved_custom_composable_parameters.get(definition_name) or []
            slot_parameter_names_for_component = {
                parameter["name"]
                for parameter in parameters
                if isinstance(parameter.get("name"), str)
                and isinstance(parameter.get("type"), str)
                and is_compose_slot_parameter_type(parameter["type"])
            }
            for chunk, chunk_start, chunk_end in argument_spans:
                named = split_named_argument(chunk)
                if named is None:
                    semantics = expression_semantics(chunk)
                    expression = semantics.get("expression")
                    if isinstance(expression, str):
                        local_expression = local_values.get(expression.strip())
                        if local_expression is not None:
                            semantics["resolved_local_expression"] = local_expression
                    invocation_arguments.append({"name": None, **semantics})
                else:
                    name, expression = named
                    supplied_names.add(name)
                    semantics = expression_semantics(expression)
                    local_expression = local_values.get(semantics["expression"].strip())
                    if local_expression is not None:
                        semantics["resolved_local_expression"] = local_expression
                    invocation_arguments.append({"name": name, **semantics})
                    if name in slot_parameter_names_for_component:
                        slot_argument_spans.append(
                            {
                                "name": name,
                                "start": opening + 1 + chunk_start,
                                "end": opening + 1 + chunk_end,
                            }
                        )
            if trailing_lambda_expression is not None and parameters:
                last_parameter = parameters[-1]
                last_name = last_parameter.get("name")
                last_type = last_parameter.get("type", "")
                if (
                    isinstance(last_name, str)
                    and last_name not in supplied_names
                    and is_compose_slot_parameter_type(last_type)
                    and trailing_lambda_span is not None
                ):
                    slot_argument_spans.append(
                        {
                            "name": last_name,
                            "start": trailing_lambda_span[0],
                            "end": trailing_lambda_span[1],
                        }
                    )
                if (
                    isinstance(last_name, str)
                    and last_name not in supplied_names
                    and "->" in last_type
                ):
                    invocation_arguments.append(
                        {
                            "name": last_name,
                            **expression_semantics(trailing_lambda_expression),
                        }
                    )
            candidate["custom_composable"] = {
                "status": "resolved_project_definition",
                "definitions": definitions,
                "arguments": invocation_arguments,
            }
            if slot_argument_spans:
                candidate["_slot_argument_spans"] = slot_argument_spans
        candidates.append(candidate)
    for ordinal, candidate in enumerate(candidates, start=1):
        candidate['source_order'] = ordinal
        candidate["call_id"] = (
            f"{relative}:{candidate['line']}:{candidate['component']}:{ordinal}"
        )
    for candidate in candidates:
        parents = [
            possible
            for possible in candidates
            if possible["_start"] < candidate["_start"] < possible["_end"]
        ]
        if parents:
            parent = min(parents, key=lambda item: item["_end"] - item["_start"])
            candidate["parent_call_id"] = parent["call_id"]
    by_call_id = {candidate["call_id"]: candidate for candidate in candidates}
    for candidate in candidates:
        parent = by_call_id.get(candidate.get("parent_call_id"))
        spans = parent.get("_slot_argument_spans") if isinstance(parent, dict) else None
        if not isinstance(spans, list):
            continue
        for span in spans:
            if (
                isinstance(span, dict)
                and isinstance(span.get("name"), str)
                and isinstance(span.get("start"), int)
                and isinstance(span.get("end"), int)
                and span["start"] <= candidate["_start"] < span["end"]
            ):
                candidate["slot_argument_name"] = span["name"]
                break
    for candidate in candidates:
        if candidate.get('parent_call_id') is None and any(
                entry['expression'] in stored_lambdas
                and entry['start']-len(scope_prefix)<=candidate['_start']<entry['end']-len(scope_prefix)
                for entry in scope_syntax.get('lambdas', [])):
            candidate['callable_definition_only'] = True
        candidate.pop("_start")
        candidate.pop("_end")
        candidate.pop("_slot_argument_spans", None)
    return candidates


def strip_parameter_annotations(value: str) -> tuple[str, list[str]]:
    annotations: list[str] = []
    remaining = value.strip()
    while remaining.startswith("@"):
        match = re.match(r"@([A-Za-z_][A-Za-z0-9_.]*)", remaining)
        if match is None:
            break
        annotations.append(match.group(1).rsplit(".", 1)[-1])
        index = match.end()
        while index < len(remaining) and remaining[index].isspace():
            index += 1
        if index < len(remaining) and remaining[index] == "(":
            closing = balanced_closing(remaining, index, "(", ")")
            if closing is None:
                break
            index = closing + 1
        remaining = remaining[index:].strip()
    return remaining, annotations


def is_compose_slot_parameter_type(kotlin_type: str) -> bool:
    normalized = re.sub(r"\s+", " ", kotlin_type.strip()).replace("?", "")
    return "@Composable" in normalized and "-> Unit" in normalized


def compact_parameters(parameters: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    parameters = lexical_code_mask(parameters, mask_strings=False)
    depth = 0
    current: list[str] = []
    chunks: list[str] = []
    for character in parameters:
        if character in "(<[{":
            depth += 1
        elif character in ")>]}":
            depth = max(0, depth - 1)
        if character == "," and depth == 0:
            chunks.append("".join(current))
            current = []
        else:
            current.append(character)
    chunks.append("".join(current))
    for chunk in chunks:
        cleaned = re.sub(r"\s+", " ", chunk.strip())
        if not cleaned:
            continue
        cleaned, annotations = strip_parameter_annotations(cleaned)
        match = re.match(r"(?:\w+\s+)?(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?$", cleaned)
        if match is not None:
            parameter = {
                "name": match.group(1),
                "type": match.group(2).strip(),
            }
            if annotations:
                parameter["annotations"] = annotations
            if match.group(3) is not None:
                parameter["default"] = match.group(3).strip()
            results.append(parameter)
    return results


def extract_function_parameters(text: str, function_match: re.Match[str]) -> str:
    opening = text.find("(", function_match.end())
    if opening == -1:
        return ""
    depth = 0
    for index in range(opening, min(len(text), opening + 4000)):
        character = text[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    return ""


def find_function_body_opening(text: str, function_match: re.Match[str]) -> int:
    code = lexical_code_mask(text)
    parameters_opening = code.find("(", function_match.end())
    parameters_closing = balanced_closing(code, parameters_opening, "(", ")")
    if parameters_closing is None:
        return -1
    for index in range(parameters_closing + 1, min(len(code), parameters_closing + 4000)):
        if code[index] == "=":
            return -1
        if code[index] == "{":
            return index
    return -1


def find_function_expression_body_span(
    text: str,
    function_match: re.Match[str],
) -> tuple[int, int] | None:
    code = lexical_code_mask(text)
    parameters_opening = code.find("(", function_match.end())
    parameters_closing = balanced_closing(code, parameters_opening, "(", ")")
    if parameters_closing is None:
        return None
    depth = 0
    for index in range(parameters_closing + 1, min(len(code), parameters_closing + 4000)):
        character = code[index]
        if character in "([{<":
            depth += 1
        elif character in ")]}>":
            depth = max(0, depth - 1)
        elif character == "{" and depth == 0:
            return None
        elif character == "=" and depth == 0:
            expression_start = index + 1
            while expression_start < len(code) and code[expression_start].isspace():
                expression_start += 1
            expression_end = local_value_expression_end(
                lexical_code_mask(text, mask_strings=False),
                expression_start,
            )
            if expression_end <= expression_start:
                return None
            return expression_start, expression_end
    return None


def collect_custom_image_associations(
    files: dict[str, str],
) -> dict[str, dict[str, Any]]:
    imports: dict[str, dict[str, str]] = collections.defaultdict(dict)
    definitions: dict[str, list[str]] = collections.defaultdict(list)
    for relative, text in files.items():
        if not relative.endswith((".kt", ".kts")):
            continue
        code = lexical_code_mask(text)
        for match in re.finditer(
            r"(?m)^\s*import\s+([A-Za-z_][A-Za-z0-9_.]*)"
            r"(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?\s*$",
            code,
        ):
            imported = match.group(1)
            local_name = match.group(2) or imported.rsplit(".", 1)[-1]
            if (
                local_name not in COMPOSE_COMPONENTS
                and CUSTOM_IMAGE_COMPONENT_PATTERN.fullmatch(f"{local_name}(")
            ):
                imports[relative][local_name] = imported
        for annotation in re.finditer(r"@Composable\b", code):
            function_match = re.search(
                r"\bfun\s+(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)\s*(?=\()",
                code[annotation.end() : annotation.end() + 1200],
            )
            if function_match is None:
                continue
            function_name = function_match.group(1)
            if (
                function_name not in COMPOSE_COMPONENTS
                and CUSTOM_IMAGE_COMPONENT_PATTERN.fullmatch(f"{function_name}(")
            ):
                definitions[function_name].append(relative)
    return {
        "imports": {
            relative: dict(sorted(values.items()))
            for relative, values in sorted(imports.items())
        },
        "definitions": {
            name: sorted(set(paths))
            for name, paths in sorted(definitions.items())
        },
    }


def collect_composable_associations(
    files: dict[str, str],
) -> dict[str, dict[str, Any]]:
    index = SourceSymbolIndex(files)
    from ui_migration.frontend.callable_inventory import lambda_functions
    ui_functions = {source:[*index.ui_functions(source), *lambda_functions(index, source)]
                    for source in tracked(index.syntax, 'content-function-inventory')}
    packages: dict[str, str] = {}
    imports: dict[str, dict[str, str]] = collections.defaultdict(dict)
    parameters_by_source: dict[str, dict[str, list[dict[str, str]]]] = (
        collections.defaultdict(dict)
    )

    for relative, text in files.items():
        if not relative.endswith((".kt", ".kts")):
            continue
        syntax = index.syntax[relative]
        packages[relative] = syntax['package']
        imports[relative] = syntax['imports']

        for function in ui_functions[relative]:
            function_name = function['name']
            parameters = compact_parameters(function['parameters_text'][1:-1])
            parameters_by_source[relative][function_name] = parameters

    resolved: dict[str, dict[str, list[dict[str, str]]]] = collections.defaultdict(dict)
    for relative in tracked(packages, 'cross-file-symbols'):
        syntax = index.syntax[relative]
        names = {f['name'] for f in index.functions} | set(syntax['imports'])
        names.update(c['name'] for c in syntax['qualifiedCalls'])
        for name in tracked(sorted(names), 'symbol-resolution', lambda name: relative + ':' + name):
            targets = resolve_functions(index.functions, name, source=relative, imports=syntax['imports'],
                                        package=syntax['package'], wildcards=syntax['wildcardImports'])
            targets = [f for f in targets if index.roles[function_identity(f)]=='content']
            if targets:
                resolved[relative][name] = [{'source':f['source'], 'composable':f['name']}
                                            for f in targets]

    return {
        "ui_functions": ui_functions,
        "imports": {
            relative: dict(sorted(values.items()))
            for relative, values in sorted(imports.items())
        },
        "resolved": {
            relative: dict(sorted(values.items()))
            for relative, values in sorted(resolved.items())
        },
        "parameters": {
            relative: dict(sorted(values.items()))
            for relative, values in sorted(parameters_by_source.items())
        },
    }


def extract_composables(
    relative: str,
    text: str,
    image_associations: dict[str, dict[str, Any]] | None = None,
    composable_associations: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    code = lexical_code_mask(text)
    associations = image_associations or {"imports": {}, "definitions": {}}
    resolved_custom_composables = (composable_associations or {"resolved": {}})[
        "resolved"
    ].get(relative, {})
    parameter_inventory = (composable_associations or {"parameters": {}}).get(
        "parameters",
        {},
    )
    resolved_custom_composable_parameters: dict[str, list[dict[str, str]]] = {}
    for component_name, definitions in resolved_custom_composables.items():
        if len(definitions) != 1:
            continue
        definition = definitions[0]
        resolved_custom_composable_parameters[component_name] = (
            parameter_inventory.get(definition["source"], {}).get(definition["composable"], [])
        )
    inventory = (composable_associations or {}).get('ui_functions', {})
    functions = inventory.get(relative)
    if functions is None:
        functions = SourceSymbolIndex({relative:text}).ui_functions(relative)
    for function in tracked(functions, 'compose-extraction', lambda item: relative + ':' + item['name']):
        function_name = function['name']
        parameters = function['parameters_text'][1:-1]
        body_opening = function['body_start']
        body = function['body']['text']
        body_code = lexical_code_mask(body)
        component_counts = {
            component: len(re.findall(rf"\b{re.escape(component)}\s*\(", body_code))
            for component in COMPOSE_COMPONENTS
        }
        custom_image_candidates: list[dict[str, Any]] = []
        rejected_suffix_only_count = 0
        custom_counts = collections.Counter(
            CUSTOM_IMAGE_COMPONENT_PATTERN.findall(body_code)
        )
        for component, count in sorted(custom_counts.items()):
            if component in COMPOSE_COMPONENTS:
                continue
            evidence: list[dict[str, str]] = []
            for source in associations["definitions"].get(component, []):
                evidence.append(
                    {
                        "kind": "composable_definition",
                        "source": source,
                    }
                )
            imported = associations["imports"].get(relative, {}).get(component)
            if imported is not None:
                evidence.append(
                    {
                        "kind": "import",
                        "source": relative,
                        "symbol": imported,
                    }
                )
            if evidence:
                component_counts[component] = count
                custom_image_candidates.append(
                    {
                        "name": component,
                        "call_count": count,
                        "evidence": evidence,
                    }
                )
            else:
                rejected_suffix_only_count += count
        modifier_counts = {
            modifier: len(re.findall(rf"\.{re.escape(modifier)}\s*\(", body_code))
            for modifier in MODIFIER_CALLS
        }
        resource_keys = sorted(
            set(
                re.findall(
                    r"(?:stringResource|painterResource)\s*\(\s*"
                    r"(?:id\s*=\s*)?R\.(?:string|drawable|mipmap)\.([A-Za-z0-9_]+)",
                    body,
                )
            )
        )
        literal_text = sorted(
            set(
                match[:200]
                for match in re.findall(
                    r"\bText\s*\(\s*(?:text\s*=\s*)?\"([^\"\\]*(?:\\.[^\"\\]*)*)\"",
                    body,
                )
            )
        )
        parameter_items = compact_parameters(parameters)
        slot_parameter_names = {
            item["name"]
            for item in parameter_items
            if isinstance(item.get("name"), str)
            and isinstance(item.get("type"), str)
            and is_compose_slot_parameter_type(item["type"])
        }
        results.append(
            {
                "source": relative,
                "name": function_name,
                "declaration_id": function_identity(function),
                "callable_expression": function.get('callable_expression'),
                "parameters": parameter_items,
                "components": {
                    key: value for key, value in component_counts.items() if value > 0
                },
                "modifiers": {
                    key: value for key, value in modifier_counts.items() if value > 0
                },
                "custom_image_component_candidates": custom_image_candidates,
                "rejected_suffix_only_image_call_count": rejected_suffix_only_count,
                "resource_keys": resource_keys,
                "literal_text": literal_text,
                "semantic_ui_calls": extract_semantic_ui_calls(
                    relative,
                    text,
                    function_name,
                    body,
                    body_opening,
                    set(associations["imports"].get(relative, {}))
                    | set(associations["definitions"]),
                    resolved_custom_composables,
                    resolved_custom_composable_parameters,
                    slot_parameter_names,
                ),
            }
        )
    return results


class _OffsetMatch:
    """Expose a re.Match-like end offset for a slice-relative match."""

    def __init__(self, match: re.Match[str], offset: int):
        self._match = match
        self._offset = offset

    def end(self) -> int:
        return self._offset + self._match.end()


def extract_modules(files: dict[str, str]) -> list[str]:
    modules: set[str] = set()
    for relative, text in files.items():
        if not relative.endswith(("settings.gradle", "settings.gradle.kts")):
            continue
        for include_call in re.findall(r"\binclude\s*\(([^)]*)\)", text):
            modules.update(re.findall(r"[\"'](:[^\"']+)[\"']", include_call))
        for include_line in re.findall(r"(?m)^\s*include\s+(.+)$", text):
            modules.update(re.findall(r"[\"'](:[^\"']+)[\"']", include_line))
    return sorted(modules)


def declared_custom_configurations(text: str, code: str) -> set[str]:
    names = set(
        re.findall(
            r"\b(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s+by\s+"
            r"configurations\.(?:creating|getting|registering)\b",
            code,
        )
    )
    names.update(
        re.findall(
            r"\b(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"configurations\.(?:create|maybeCreate|register|named)\s*\(",
            code,
        )
    )
    for match in re.finditer(
        r"\bconfigurations\.(?:create|maybeCreate|register|named|getByName)"
        r"\s*\(\s*([\"'])([A-Za-z_][A-Za-z0-9_]*)\1",
        text,
    ):
        prefix = code[match.start() : match.start() + len("configurations.")]
        if prefix == "configurations.":
            names.add(match.group(2))
    return names


def is_dependency_configuration(name: str, custom: set[str]) -> bool:
    if name in STANDARD_DEPENDENCY_CONFIGURATIONS or name in custom:
        return True
    return (
        name[:1].islower()
        and any(name.endswith(suffix) for suffix in VARIANT_CONFIGURATION_SUFFIXES)
    )


def iter_dependency_calls(text: str) -> Iterable[tuple[str, str]]:
    code = lexical_code_mask(text)
    custom = declared_custom_configurations(text, code)
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", code):
        configuration = match.group(1)
        if not is_dependency_configuration(configuration, custom):
            continue
        opening = match.end() - 1
        depth = 1
        for index in range(opening + 1, len(code)):
            character = code[index]
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    yield configuration, text[opening + 1 : index]
                    break


def extract_dependencies(files: dict[str, str]) -> list[dict[str, str]]:
    dependencies: dict[str, dict[str, str]] = {}
    for relative, text in files.items():
        if not relative.endswith(("build.gradle", "build.gradle.kts")):
            continue
        for configuration, expression in iter_dependency_calls(text):
            without_comments = lexical_code_mask(
                expression,
                mask_strings=False,
            )
            cleaned = re.sub(
                r"\s+",
                " ",
                without_comments.strip().rstrip(","),
            )
            if len(cleaned) > 240:
                cleaned = cleaned[:240]
            key = f"{configuration}:{cleaned}"
            target = "manual mapping required"
            action = "review"
            lowered = cleaned.lower()
            for marker, mapped_target, mapped_action in DEPENDENCY_MAPPINGS:
                if marker in lowered:
                    target = mapped_target
                    action = mapped_action
                    break
            dependencies[key] = {
                "configuration": configuration,
                "android": cleaned,
                "harmony_target": target,
                "action": action,
                "declared_in": relative,
            }
    return sorted(
        dependencies.values(),
        key=lambda item: (item["configuration"], item["android"], item["declared_in"]),
    )


def kotlin_route_constants(
    files: dict[str, str],
) -> dict[str, dict[str, str]]:
    declarations: dict[str, dict[str, str]] = {}
    constant_pattern = re.compile(
        r"\bconst\s+val\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        r"(\"(?:\\.|[^\"\\])*\"|[A-Za-z_][A-Za-z0-9_.]*)"
    )
    for relative, text in files.items():
        if not relative.endswith((".kt", ".kts")):
            continue
        for match in constant_pattern.finditer(text):
            name = match.group(1)
            declarations.setdefault(
                name,
                {
                    "name": name,
                    "expression": match.group(2),
                    "declared_in": relative,
                },
            )
        for object_match in re.finditer(
            r"\b(?:private\s+)?object\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{",
            text,
        ):
            object_name = object_match.group(1)
            opening = text.find("{", object_match.start())
            body = extract_balanced_block(text, opening)
            for match in constant_pattern.finditer(body):
                name = match.group(1)
                declarations[f"{object_name}.{name}"] = {
                    "name": name,
                    "expression": match.group(2),
                    "declared_in": relative,
                }
    for relative, text in files.items():
        if not relative.endswith((".kt", ".kts")):
            continue
        code = lexical_code_mask(text)
        for enum_match in re.finditer(
            r"\benum\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            code,
        ):
            enum_name = enum_match.group(1)
            parameters_opening = enum_match.end() - 1
            parameters_closing = balanced_closing(
                code,
                parameters_opening,
                "(",
                ")",
            )
            if parameters_closing is None:
                continue
            parameter_names: list[str | None] = []
            for parameter in split_top_level(
                text[parameters_opening + 1 : parameters_closing]
            ):
                name_match = re.search(
                    r"\b(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:",
                    parameter,
                )
                parameter_names.append(
                    name_match.group(1) if name_match is not None else None
                )
            try:
                route_index = parameter_names.index("route")
            except ValueError:
                continue
            body_opening = code.find("{", parameters_closing + 1)
            body_closing = balanced_closing(code, body_opening, "{", "}")
            if body_opening < 0 or body_closing is None:
                continue
            body = text[body_opening + 1 : body_closing]
            body_code = code[body_opening + 1 : body_closing]
            for entry_match in re.finditer(
                r"(?m)^\s*([A-Z][A-Z0-9_]*)\s*\(",
                body_code,
            ):
                prefix = body_code[: entry_match.start()]
                if (
                    prefix.count("{") != prefix.count("}")
                    or prefix.count("(") != prefix.count(")")
                    or prefix.count("[") != prefix.count("]")
                ):
                    continue
                entry_opening = entry_match.end() - 1
                entry_closing = balanced_closing(
                    body_code,
                    entry_opening,
                    "(",
                    ")",
                )
                if entry_closing is None:
                    continue
                arguments = split_top_level(
                    body[entry_opening + 1 : entry_closing]
                )
                if route_index >= len(arguments):
                    continue
                route = resolve_kotlin_route_expression(
                    arguments[route_index],
                    declarations,
                )
                if route is None:
                    continue
                entry_name = entry_match.group(1)
                symbol = f"{enum_name}.{entry_name}.route"
                declarations[symbol] = {
                    "name": symbol,
                    "expression": json.dumps(route),
                    "declared_in": relative,
                }
        for class_match in re.finditer(
            r"\b(?:sealed\s+)?(?:class|interface)\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",
            code,
        ):
            class_name = class_match.group(1)
            body_opening = code.find("{", class_match.end())
            body_closing = balanced_closing(code, body_opening, "{", "}")
            if body_opening < 0 or body_closing is None:
                continue
            body = text[body_opening + 1 : body_closing]
            body_code = code[body_opening + 1 : body_closing]
            if (
                re.search(
                    r"\bval\s+route\s*:\s*String\s*"
                    r"get\s*\(\s*\)\s*=\s*this\s*::\s*class\s*"
                    r"\.\s*java\s*\.\s*simpleName\b",
                    body_code,
                )
                is None
            ):
                continue

            def collect_simple_name_route_objects(
                owner: str,
                current_body: str,
                current_code: str,
            ) -> None:
                for object_match in re.finditer(
                    r"\b(?:(?:data|private|internal|public)\s+)*object\s+"
                    r"([A-Za-z_][A-Za-z0-9_]*)\b",
                    current_code,
                ):
                    prefix = current_code[: object_match.start()]
                    if prefix.count("{") != prefix.count("}"):
                        continue
                    object_name = object_match.group(1)
                    header_start = object_match.end()
                    body_start = current_code.find("{", header_start)
                    line_end = current_code.find("\n", header_start)
                    if line_end < 0:
                        line_end = len(current_code)
                    header_end = (
                        min(body_start, line_end)
                        if body_start >= 0
                        else line_end
                    )
                    header = current_code[header_start:header_end]
                    if (
                        re.search(
                            rf":\s*(?:[A-Za-z_][A-Za-z0-9_.]*\.)?"
                            rf"{re.escape(class_name)}\b",
                            header,
                        )
                        is None
                    ):
                        continue
                    symbol = f"{owner}.{object_name}.route"
                    declarations[symbol] = {
                        "name": symbol,
                        "expression": json.dumps(object_name),
                        "declared_in": relative,
                    }
                    if body_start < 0:
                        continue
                    object_body_end = balanced_closing(
                        current_code,
                        body_start,
                        "{",
                        "}",
                    )
                    if object_body_end is None:
                        continue
                    collect_simple_name_route_objects(
                        f"{owner}.{object_name}",
                        current_body[body_start + 1 : object_body_end],
                        current_code[body_start + 1 : object_body_end],
                    )

            collect_simple_name_route_objects(class_name, body, body_code)
    return declarations


def resolve_kotlin_route_constant(
    symbol: str,
    declarations: dict[str, dict[str, str]],
    resolving: set[str] | None = None,
) -> str | None:
    declaration = declarations.get(symbol)
    if declaration is None:
        declaration = declarations.get(symbol.rsplit(".", 1)[-1])
    if declaration is None:
        return None
    key = f"{declaration['declared_in']}:{declaration['name']}"
    active = set() if resolving is None else set(resolving)
    if key in active:
        return None
    active.add(key)
    expression = declaration["expression"]
    if not (expression.startswith('"') and expression.endswith('"')):
        return resolve_kotlin_route_constant(expression, declarations, active)

    value = expression[1:-1]

    def replace_reference(match: re.Match[str]) -> str:
        referenced = match.group(1) or match.group(2)
        resolved = resolve_kotlin_route_constant(
            referenced,
            declarations,
            active,
        )
        return resolved if resolved is not None else match.group(0)

    return re.sub(
        r"\$(?:\{([A-Za-z_][A-Za-z0-9_.]*)\}|([A-Za-z_][A-Za-z0-9_.]*))",
        replace_reference,
        value,
    )


def resolve_kotlin_route_expression(
    expression: str,
    declarations: dict[str, dict[str, str]],
) -> str | None:
    token_pattern = re.compile(
        r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_.]*'
    )
    parts: list[str] = []
    cursor = 0
    for index, match in enumerate(token_pattern.finditer(expression)):
        separator = expression[cursor : match.start()]
        if index == 0:
            if separator.strip():
                return None
        elif re.fullmatch(r"\s*\+\s*", separator) is None:
            return None
        token = match.group(0)
        if token.startswith('"'):
            try:
                value = json.loads(token)
            except json.JSONDecodeError:
                return None
            unresolved = False

            def replace_reference(reference: re.Match[str]) -> str:
                nonlocal unresolved
                symbol = reference.group(1) or reference.group(2)
                resolved = resolve_kotlin_route_constant(symbol, declarations)
                if resolved is None:
                    unresolved = True
                    return reference.group(0)
                return resolved

            value = re.sub(
                r"\$(?:\{([A-Za-z_][A-Za-z0-9_.]*)\}|"
                r"([A-Za-z_][A-Za-z0-9_.]*))",
                replace_reference,
                value,
            )
            if unresolved:
                return None
            parts.append(value)
        else:
            resolved = resolve_kotlin_route_constant(token, declarations)
            if resolved is None:
                return None
            parts.append(resolved)
        cursor = match.end()
    if not parts or expression[cursor:].strip():
        return None
    return "".join(parts)


def extract_routes(files: dict[str, str]) -> list[dict[str, Any]]:
    routes: dict[tuple[str, str], dict[str, Any]] = {}
    constants = kotlin_route_constants(files)
    composable_call = (
        r"(?:composable[A-Za-z0-9_]*|"
        r"[A-Za-z_][A-Za-z0-9_]*Composable[A-Za-z0-9_]*)"
    )
    route_call = rf"(?:{composable_call}|navigation)"
    patterns = (
        rf"\b{composable_call}\s*\(\s*"
        r"(?:route\s*=\s*)?[\"']([^\"']+)[\"'](?!\s*\+)",
        r"\broute\s*[:=]\s*[\"']([^\"']+)[\"']",
        r"\b(?:object|data object)\s+(\w+)\s*:\s*\w+\s*\(\s*[\"']([^\"']+)[\"']",
    )
    for relative, text in files.items():
        if not relative.endswith((".kt", ".kts")):
            continue
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                route = match.group(match.lastindex or 1)
                if "$" in route:
                    continue
                if "/" in route or route.isidentifier() or "{" in route:
                    routes[(relative, route)] = {
                        "source": relative,
                        "route": route,
                        "kind": "string",
                        "arguments": sorted(
                            set(
                                re.findall(
                                    r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                                    route,
                                )
                            )
                        ),
                        "detector": "regex-v2",
                }
        code = lexical_code_mask(text)
        for match in re.finditer(rf"\b{route_call}\s*\(", code):
            opening = match.end() - 1
            closing = balanced_closing(code, opening, "(", ")")
            if closing is None:
                continue
            raw_arguments = text[opening + 1 : closing]
            chunks = split_top_level(raw_arguments)
            named_arguments = dict(
                named
                for chunk in chunks
                if (named := split_named_argument(chunk)) is not None
            )
            route_expression = named_arguments.get("route")
            if route_expression is None and chunks:
                first = chunks[0].strip()
                if split_named_argument(first) is None:
                    route_expression = first
            if route_expression is not None:
                symbol_match = re.fullmatch(
                    r"\s*([A-Za-z_][A-Za-z0-9_.]*)\s*",
                    route_expression,
                )
                if symbol_match is not None:
                    symbol = symbol_match.group(1)
                    route = resolve_kotlin_route_constant(symbol, constants)
                    if route is not None:
                        declaration = constants.get(symbol)
                        if declaration is None:
                            declaration = constants.get(symbol.rsplit(".", 1)[-1])
                        routes[(relative, route)] = {
                            "source": relative,
                            "declared_in": (
                                declaration["declared_in"]
                                if declaration is not None
                                else relative
                            ),
                            "route": route,
                            "symbol": symbol,
                            "kind": "symbolic",
                            "arguments": sorted(
                                set(
                                    re.findall(
                                        r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                                        route,
                                    )
                                )
                            ),
                            "detector": "regex-v2",
                        }
                        continue
            route_code = lexical_code_mask(route_expression or "", mask_strings=False)
            if route_expression is None or (
                "+" not in route_code and "$" not in route_code
            ):
                continue
            route = resolve_kotlin_route_expression(route_expression, constants)
            if route is None:
                continue
            routes[(relative, route)] = {
                "source": relative,
                "route": route,
                "kind": "expression",
                "expression": normalize_expression(route_expression),
                "arguments": sorted(
                    set(
                        re.findall(
                            r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                            route,
                        )
                    )
                ),
                "detector": "static-expression-v1",
            }
        for match in re.finditer(
            rf"\b{route_call}\s*\(\s*(?:route\s*=\s*)?"
            r"([A-Za-z_][A-Za-z0-9_.]*)",
            text,
        ):
            symbol = match.group(1)
            route = resolve_kotlin_route_constant(symbol, constants)
            if route is None:
                continue
            declaration = constants.get(symbol)
            if declaration is None:
                declaration = constants.get(symbol.rsplit(".", 1)[-1])
            routes[(relative, route)] = {
                "source": relative,
                "declared_in": (
                    declaration["declared_in"]
                    if declaration is not None
                    else relative
                ),
                "route": route,
                "symbol": symbol,
                "kind": "symbolic",
                "arguments": sorted(
                    set(
                        re.findall(
                            r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                            route,
                        )
                    )
                ),
                "detector": "regex-v2",
            }
        for match in re.finditer(
            r"\b(?:composable|navigation)\s*<\s*([A-Za-z_][A-Za-z0-9_.]*)\s*>",
            text,
        ):
            qualified_name = match.group(1)
            route = qualified_name.rsplit(".", 1)[-1]
            declaration = re.search(
                rf"\b(?:data\s+class|class|data\s+object|object)\s+"
                rf"{re.escape(route)}\s*(?:\(([^)]*)\))?",
                text,
            )
            arguments = compact_parameters(declaration.group(1) or "") if declaration else []
            routes[(relative, route)] = {
                "source": relative,
                "route": route,
                "kind": "type-safe",
                "arguments": arguments,
                "detector": "regex-v2",
            }
    return sorted(routes.values(), key=lambda item: (item["source"], item["route"]))


def extract_tests(files: dict[str, str]) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    for relative, text in files.items():
        if not relative.endswith((".kt", ".java")) or "@Test" not in text:
            continue
        names = [
            match.group(1)
            for match in re.finditer(
                r"@Test(?:\([^)]*\))?\s*(?:suspend\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*)",
                text,
            )
        ]
        tests.append({"source": relative, "test_names": names})
    return tests


def extract_models(files: dict[str, str]) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    pattern = re.compile(
        r"\b(data\s+class|sealed\s+class|sealed\s+interface|enum\s+class|"
        r"interface|class)\s+([A-Za-z_][A-Za-z0-9_]*)"
    )
    for relative, text in files.items():
        if not relative.endswith((".kt", ".java")):
            continue
        layer = classify_file(relative)
        if layer not in {"model", "viewmodel", "network", "database", "storage"}:
            continue
        for kind, name in pattern.findall(text):
            models.append({"source": relative, "kind": kind, "name": name, "layer": layer})
    return models


def detect_capabilities(files: dict[str, str]) -> list[dict[str, Any]]:
    scanned_files: dict[str, str] = {}
    for relative, text in files.items():
        if relative.endswith((".kt", ".java")):
            scanned_files[relative] = lexical_code_mask(text)
        elif relative.endswith((".kts", ".gradle")):
            scanned_files[relative] = lexical_code_mask(text, mask_strings=False)
        elif relative.endswith(".xml"):
            scanned_files[relative] = re.sub(
                r"<!--.*?-->", "", text, flags=re.DOTALL
            )
        elif relative.endswith(".toml"):
            scanned_files[relative] = "\n".join(
                line.split("#", 1)[0] for line in text.splitlines()
            )
    capabilities: list[dict[str, Any]] = []
    for rule in CAPABILITY_RULES:
        matched_files = sorted(
            relative
            for relative, text in scanned_files.items()
            if any(pattern in text for pattern in rule["patterns"])
        )
        if matched_files:
            capabilities.append(
                {
                    "id": rule["id"],
                    "risk": rule["risk"],
                    "harmony_target": rule["harmony_target"],
                    "source_files": matched_files,
                }
            )
    return capabilities


def count_suffixes(paths: Iterable[str]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for relative in paths:
        suffix = Path(relative).suffix.lower() or "<none>"
        counts[suffix] += 1
    return dict(sorted(counts.items()))


def extract_android_imports(files: dict[str, str]) -> list[dict[str, str]]:
    imports: set[tuple[str, str]] = set()
    for relative, text in files.items():
        if not relative.endswith((".java", ".kt", ".kts")):
            continue
        for imported in re.findall(
            r"(?m)^\s*import\s+((?:android|androidx)\.[A-Za-z0-9_.*]+)",
            text,
        ):
            imports.add((relative, imported))
    return [
        {
            "source": source,
            "import": imported,
            "status": "requires_mapping_review",
        }
        for source, imported in sorted(imports)
    ]


ANDROID_XML_NAMESPACE = "http://schemas.android.com/apk/res/android"
ANDROID_XML_PREFIXES = {
    ANDROID_XML_NAMESPACE: "android",
    "http://schemas.android.com/apk/res-auto": "app",
    "http://schemas.android.com/tools": "tools",
}


def android_xml_name(name: str) -> str:
    if name.startswith("{") and "}" in name:
        namespace, local = name[1:].split("}", 1)
        prefix = ANDROID_XML_PREFIXES.get(namespace, namespace)
        return f"{prefix}:{local}"
    return name


def android_view_name(tag: str, attributes: dict[str, str]) -> str:
    local = android_xml_name(tag).rsplit(":", 1)[-1]
    if local == "view" and "class" in attributes:
        local = attributes["class"]
    return local.rsplit(".", 1)[-1]


def android_resource_id(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"@\+?id/([A-Za-z_][A-Za-z0-9_]*)", value)
    return match.group(1) if match else None


def android_resource_reference(value: str | None, resource_type: str) -> str | None:
    if not value:
        return None
    match = re.fullmatch(
        rf"@\+?{re.escape(resource_type)}/([A-Za-z_][A-Za-z0-9_]*)", value
    )
    return match.group(1) if match else None


def extract_android_view_layouts(files: dict[str, str]) -> dict[str, Any]:
    layouts: list[dict[str, Any]] = []
    layout_path = re.compile(r"(?:^|/)res/(layout[^/]*)/([^/]+)\.xml$")
    for relative, text in sorted(files.items()):
        match = layout_path.search(relative)
        if not match:
            continue
        try:
            document_root = ET.fromstring(text)
        except ET.ParseError as error:
            raise AnalysisError(f"invalid Android layout XML: {relative}: {error}") from error

        data_variables: list[dict[str, str]] = []
        content_root = document_root
        if android_view_name(document_root.tag, {}) == "layout":
            content_children: list[ET.Element] = []
            for child in list(document_root):
                if android_view_name(child.tag, {}) == "data":
                    for variable in list(child):
                        if android_view_name(variable.tag, {}) != "variable":
                            continue
                        name = variable.attrib.get("name")
                        variable_type = variable.attrib.get("type")
                        if name and variable_type:
                            data_variables.append(
                                {"name": name, "type": variable_type}
                            )
                else:
                    content_children.append(child)
            if len(content_children) != 1:
                raise AnalysisError(
                    f"Android data-binding layout must contain one root view: {relative}"
                )
            content_root = content_children[0]

        views: list[dict[str, Any]] = []

        def visit(element: ET.Element, parent_index: int | None, depth: int) -> None:
            attributes = {
                android_xml_name(key): value
                for key, value in sorted(element.attrib.items())
            }
            index = len(views)
            bindings = {
                key: value
                for key, value in attributes.items()
                if value.startswith("@{") or value.startswith("@={")
            }
            views.append(
                {
                    "index": index,
                    "parent_index": parent_index,
                    "depth": depth,
                    "view": android_view_name(element.tag, attributes),
                    "id": android_resource_id(attributes.get("android:id")),
                    "attributes": attributes,
                    "bindings": bindings,
                    **(
                        {
                            "included_layout": attributes.get("layout", "").removeprefix(
                                "@layout/"
                            )
                        }
                        if android_view_name(element.tag, attributes) == "include"
                        and attributes.get("layout", "").startswith("@layout/")
                        else {}
                    ),
                }
            )
            for child in list(element):
                visit(child, index, depth + 1)

        visit(content_root, None, 0)
        layouts.append(
            {
                "source": relative,
                "name": match.group(2),
                "qualifier": match.group(1),
                "root_view": views[0]["view"],
                "data_variables": sorted(
                    data_variables, key=lambda item: (item["name"], item["type"])
                ),
                "views": views,
            }
        )

    return {
        "status": "candidate_requires_review",
        "authoritative": False,
        "layout_count": len(layouts),
        "limitations": [
            "Static XML parsing does not resolve resource aliases, styles, themes, includes, or runtime BindingAdapters.",
            "Runtime visibility and data-binding branches require source reconciliation.",
        ],
        "layouts": layouts,
    }


def extract_android_navigation_graphs(files: dict[str, str]) -> dict[str, Any]:
    graphs: list[dict[str, Any]] = []
    navigation_path = re.compile(
        r"(?:^|/)res/(navigation[^/]*)/([^/]+)\.xml$"
    )
    app_namespace = "http://schemas.android.com/apk/res-auto"
    android_name = f"{{{ANDROID_XML_NAMESPACE}}}name"
    android_label = f"{{{ANDROID_XML_NAMESPACE}}}label"
    android_default_value = f"{{{ANDROID_XML_NAMESPACE}}}defaultValue"
    app_start_destination = f"{{{app_namespace}}}startDestination"
    app_destination = f"{{{app_namespace}}}destination"
    app_graph = f"{{{app_namespace}}}graph"
    app_arg_type = f"{{{app_namespace}}}argType"
    app_nullable = f"{{{app_namespace}}}nullable"
    app_uri = f"{{{app_namespace}}}uri"
    app_pop_up_to = f"{{{app_namespace}}}popUpTo"
    app_pop_up_to_inclusive = f"{{{app_namespace}}}popUpToInclusive"
    app_launch_single_top = f"{{{app_namespace}}}launchSingleTop"
    destination_types = {"activity", "dialog", "fragment", "navigation"}

    for relative, text in sorted(files.items()):
        match = navigation_path.search(relative)
        if not match:
            continue
        try:
            root = ET.fromstring(text)
        except ET.ParseError as error:
            raise AnalysisError(
                f"invalid Android navigation XML: {relative}: {error}"
            ) from error
        if android_view_name(root.tag, {}) != "navigation":
            raise AnalysisError(
                f"Android navigation XML must use a navigation root: {relative}"
            )

        destinations: list[dict[str, Any]] = []
        for element in root.iter():
            destination_type = android_view_name(element.tag, {})
            if destination_type not in destination_types or element is root:
                continue
            destination_id = android_resource_id(
                element.attrib.get(f"{{{ANDROID_XML_NAMESPACE}}}id")
            )
            if not destination_id:
                continue
            actions: list[dict[str, Any]] = []
            arguments: list[dict[str, Any]] = []
            deep_links: list[str] = []
            for child in list(element):
                child_type = android_view_name(child.tag, {})
                if child_type == "action":
                    actions.append(
                        {
                            "id": android_resource_id(
                                child.attrib.get(
                                    f"{{{ANDROID_XML_NAMESPACE}}}id"
                                )
                            ),
                            "destination": android_resource_id(
                                child.attrib.get(app_destination)
                            ),
                            "pop_up_to": android_resource_id(
                                child.attrib.get(app_pop_up_to)
                            ),
                            "pop_up_to_inclusive": child.attrib.get(
                                app_pop_up_to_inclusive
                            ),
                            "launch_single_top": child.attrib.get(
                                app_launch_single_top
                            ),
                        }
                    )
                elif child_type == "argument":
                    name = child.attrib.get(android_name)
                    if name:
                        arguments.append(
                            {
                                "name": name,
                                "arg_type": child.attrib.get(app_arg_type),
                                "nullable": child.attrib.get(app_nullable),
                                "default_value": child.attrib.get(
                                    android_default_value
                                ),
                            }
                        )
                elif child_type == "deepLink":
                    uri = child.attrib.get(app_uri)
                    if uri:
                        deep_links.append(uri)
            destinations.append(
                {
                    "id": destination_id,
                    "type": destination_type,
                    "class_name": element.attrib.get(android_name),
                    "label": element.attrib.get(android_label),
                    "actions": sorted(
                        actions,
                        key=lambda item: (
                            item["id"] or "",
                            item["destination"] or "",
                        ),
                    ),
                    "arguments": sorted(
                        arguments, key=lambda item: item["name"]
                    ),
                    "deep_links": sorted(deep_links),
                }
            )

        includes = sorted(
            {
                included
                for element in root.iter()
                if android_view_name(element.tag, {}) == "include"
                for included in [
                    android_resource_reference(element.attrib.get(app_graph), "navigation")
                ]
                if included
            }
        )
        graphs.append(
            {
                "source": relative,
                "name": match.group(2),
                "qualifier": match.group(1),
                "id": android_resource_id(
                    root.attrib.get(f"{{{ANDROID_XML_NAMESPACE}}}id")
                )
                or match.group(2),
                "start_destination": android_resource_id(
                    root.attrib.get(app_start_destination)
                ),
                "includes": includes,
                "destinations": sorted(
                    destinations, key=lambda item: (item["id"], item["type"])
                ),
            }
        )

    return {
        "status": "candidate_requires_review",
        "authoritative": False,
        "navigation_graph_count": len(graphs),
        "limitations": [
            "Static Navigation XML parsing does not resolve resource overlays, generated Safe Args classes, or runtime navigation calls.",
            "Included and nested graphs are inventoried but must be reconciled into one runtime back stack.",
        ],
        "graphs": graphs,
    }


def extract_android_activities(files: dict[str, str]) -> dict[str, Any]:
    activities: dict[str, dict[str, Any]] = {}
    android_name = f"{{{ANDROID_XML_NAMESPACE}}}name"
    android_exported = f"{{{ANDROID_XML_NAMESPACE}}}exported"
    android_launch_mode = f"{{{ANDROID_XML_NAMESPACE}}}launchMode"
    for relative, text in sorted(files.items()):
        if not relative.endswith("AndroidManifest.xml"):
            continue
        try:
            root = ET.fromstring(text)
        except ET.ParseError as error:
            raise AnalysisError(f"invalid Android manifest XML: {relative}: {error}") from error
        for element in root.iter("activity"):
            name = element.attrib.get(android_name)
            if not name:
                continue
            actions = {
                action.attrib.get(android_name)
                for intent_filter in element.findall("intent-filter")
                for action in intent_filter.findall("action")
            }
            categories = {
                category.attrib.get(android_name)
                for intent_filter in element.findall("intent-filter")
                for category in intent_filter.findall("category")
            }
            activities[name] = {
                "source": relative,
                "name": name,
                "exported": element.attrib.get(android_exported),
                "launch_mode": element.attrib.get(android_launch_mode),
                "launcher": (
                    "android.intent.action.MAIN" in actions
                    and "android.intent.category.LAUNCHER" in categories
                ),
            }

    layout_bindings: set[tuple[str, str, str]] = set()
    navigation_candidates: list[dict[str, Any]] = []
    binding_pattern = re.compile(
        r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)[^\n{]*?"
        r"\bBindingActivity\s*<[^>]+>\s*\(\s*R\.layout\.([A-Za-z_][A-Za-z0-9_]*)"
    )
    class_pattern = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)")
    set_content_view_pattern = re.compile(
        r"\bsetContentView\s*\(\s*R\.layout\.([A-Za-z_][A-Za-z0-9_]*)\s*\)"
    )
    for relative, text in sorted(files.items()):
        if not relative.endswith((".kt", ".java")):
            continue
        code = lexical_code_mask(text)
        for activity, layout in binding_pattern.findall(code):
            layout_bindings.add((activity, layout, relative))
        class_declarations = list(class_pattern.finditer(code))
        for match in set_content_view_pattern.finditer(code):
            owners = [
                declaration
                for declaration in class_declarations
                if declaration.start() < match.start()
            ]
            if owners:
                layout_bindings.add(
                    (owners[-1].group(1), match.group(1), relative)
                )
        constants = {
            name: value
            for name, value in re.findall(
                r'\bconst\s+val\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"\\]*)"',
                lexical_code_mask(text, mask_strings=False),
            )
        }
        intent_pattern = re.compile(
            r"\bintentOf\s*<\s*([A-Za-z_][A-Za-z0-9_.]*)\s*>"
        )
        for intent in intent_pattern.finditer(code):
            opening = code.find("{", intent.end())
            if opening == -1:
                continue
            closing = balanced_closing(code, opening, "{", "}")
            if closing is None:
                continue
            owners = [
                declaration
                for declaration in class_declarations
                if declaration.start() < intent.start()
            ]
            body = text[opening + 1 : closing]
            body_code = lexical_code_mask(body, mask_strings=False)
            extras: list[dict[str, str]] = []
            for extra in re.finditer(
                r"\bputExtra\s*\(\s*"
                r"([A-Za-z_][A-Za-z0-9_]*|\"[^\"\\]*\")\s+to\s+"
                r"([^,)\n]+)",
                body_code,
            ):
                key_expression = extra.group(1)
                literal_key = (
                    key_expression[1:-1]
                    if key_expression.startswith('"')
                    else constants.get(key_expression, key_expression)
                )
                extras.append(
                    {
                        "key": literal_key,
                        "key_expression": key_expression,
                        "value_expression": normalize_expression(extra.group(2)),
                    }
                )
            navigation_candidates.append(
                {
                    "source": relative,
                    "owner": owners[-1].group(1) if owners else None,
                    "target_activity": intent.group(1),
                    "mechanism": "intentOf",
                    "extras": extras,
                }
            )
        for helper_call in re.finditer(
            r"\b([A-Z][A-Za-z0-9_]*Activity)\.startActivity\s*\(", code
        ):
            owners = [
                declaration
                for declaration in class_declarations
                if declaration.start() < helper_call.start()
            ]
            navigation_candidates.append(
                {
                    "source": relative,
                    "owner": owners[-1].group(1) if owners else None,
                    "target_activity": helper_call.group(1),
                    "mechanism": "activity_helper_call",
                    "extras": [],
                }
            )

    return {
        "status": "candidate_requires_review",
        "authoritative": False,
        "activity_count": len(activities),
        "limitations": [
            "Static manifest and source scanning does not resolve aliases, inheritance, or runtime navigation.",
            "Only directly declared activity-to-layout bindings are candidates.",
        ],
        "activities": [activities[name] for name in sorted(activities)],
        "layout_bindings": [
            {"activity": activity, "layout": layout, "source": source}
            for activity, layout, source in sorted(layout_bindings)
        ],
        "navigation_candidates": sorted(
            navigation_candidates,
            key=lambda item: (
                item["source"],
                item["target_activity"],
                item["owner"] or "",
            ),
        ),
    }


def extract_android_binding_adapters(files: dict[str, str]) -> dict[str, Any]:
    adapters: list[dict[str, Any]] = []
    for relative, text in sorted(files.items()):
        if not relative.endswith((".kt", ".kts")):
            continue
        code = lexical_code_mask(text, mask_strings=False)
        for annotation in re.finditer(
            r"@BindingAdapter\s*\((.*?)\)", code, flags=re.DOTALL
        ):
            function = re.search(
                r"\bfun\s+([A-Za-z_][A-Za-z0-9_]*)\s*",
                code[annotation.end() : annotation.end() + 1200],
            )
            if function is None:
                continue
            function_match = _OffsetMatch(function, annotation.end())
            attributes = re.findall(r'"([^"\\]+)"', annotation.group(1))
            if not attributes:
                continue
            adapters.append(
                {
                    "source": relative,
                    "line": text.count("\n", 0, annotation.start()) + 1,
                    "attributes": attributes,
                    "function": function.group(1),
                    "parameters": compact_parameters(
                        extract_function_parameters(text, function_match)
                    ),
                }
            )
    return {
        "status": "candidate_requires_review",
        "authoritative": False,
        "adapter_count": len(adapters),
        "limitations": [
            "Static annotation scanning does not prove generated data-binding invocation or runtime behavior.",
            "Adapter function bodies and transitive library behavior require source reconciliation.",
        ],
        "adapters": sorted(
            adapters,
            key=lambda item: (item["source"], item["line"], item["function"]),
        ),
    }


def normalized_xml_text(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext()).strip())


def extract_android_value_resources(files: dict[str, str]) -> dict[str, Any]:
    resources: list[dict[str, Any]] = []
    values_path = re.compile(r"(?:^|/)res/(values[^/]*)/([^/]+)\.xml$")
    for relative, text in sorted(files.items()):
        match = values_path.search(relative)
        if not match:
            continue
        try:
            root = ET.fromstring(text)
        except ET.ParseError as error:
            raise AnalysisError(f"invalid Android values XML: {relative}: {error}") from error
        if android_view_name(root.tag, {}) != "resources":
            raise AnalysisError(f"Android values XML must use a resources root: {relative}")
        for element in list(root):
            attributes = {
                android_xml_name(key): value
                for key, value in sorted(element.attrib.items())
                if android_xml_name(key) not in {"name", "type"}
            }
            name = element.attrib.get("name")
            resource_type = android_view_name(element.tag, {})
            if resource_type == "item":
                resource_type = element.attrib.get("type", "item")
            if not name:
                continue
            items: list[dict[str, str]] = []
            if resource_type == "style":
                for item in list(element):
                    item_name = item.attrib.get("name")
                    if item_name:
                        items.append(
                            {"name": item_name, "value": normalized_xml_text(item)}
                        )
                value = ""
            else:
                value = normalized_xml_text(element)
            resources.append(
                {
                    "source": relative,
                    "qualifier": match.group(1),
                    "type": resource_type,
                    "name": name,
                    "value": value,
                    "attributes": attributes,
                    "items": items,
                }
            )
    return {
        "status": "candidate_requires_review",
        "authoritative": False,
        "resource_count": len(resources),
        "limitations": [
            "Static values XML parsing does not resolve resource overlays, theme inheritance, or runtime configuration selection.",
            "Inline markup and formatting spans require source reconciliation.",
        ],
        "resources": sorted(
            resources,
            key=lambda item: (
                item["source"], item["type"], item["name"]
            ),
        ),
    }


def build_batches(files_by_layer: dict[str, list[str]]) -> list[dict[str, Any]]:
    definitions = (
        ("foundation", ("build", "resource", "model"), "Models, resources, and project contracts"),
        ("data", ("network", "database", "storage"), "Network and persistence adapters"),
        ("platform", ("platform",), "HarmonyOS-specific capability adapters"),
        ("features", ("viewmodel", "ui"), "ArkUI pages, state, and navigation"),
        ("verification", ("test",), "Unit, integration, and UI behavior tests"),
        ("remaining", ("source", "other"), "Unclassified source requiring review"),
    )
    batches: list[dict[str, Any]] = []
    for batch_id, layers, goal in definitions:
        paths = sorted(
            path for layer in layers for path in files_by_layer.get(layer, [])
        )
        if paths:
            batches.append(
                {
                    "id": batch_id,
                    "goal": goal,
                    "status": "pending",
                    "source_file_count": len(paths),
                    "source_files": paths,
                }
            )
    return batches


def build_custom_composable_closures(
    composables: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    definitions = {
        (item["source"], item["name"]): {
            "source": item["source"],
            "composable": item["name"],
        }
        for item in composables
    }
    adjacency: dict[tuple[str, str], set[tuple[str, str]]] = (
        collections.defaultdict(set)
    )
    for edge in edges:
        caller = (edge["caller"]["source"], edge["caller"]["composable"])
        callee = (edge["callee"]["source"], edge["callee"]["composable"])
        adjacency[caller].add(callee)
    calls_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = (
        collections.defaultdict(list)
    )
    for call in calls:
        calls_by_definition[(call["source"], call["composable"])].append(call)

    roots = sorted(
        key
        for key in definitions
        if key in adjacency or key in calls_by_definition
    )
    closures: list[dict[str, Any]] = []
    for root in tracked(roots, 'call-closures', lambda item: item[0] + ':' + item[1]):
        reached: set[tuple[str, str]] = set()
        active: set[tuple[str, str]] = set()
        cycle_edges: set[tuple[tuple[str, str], tuple[str, str]]] = set()

        def visit(current: tuple[str, str]) -> None:
            if current in active:
                return
            if current in reached:
                return
            reached.add(current)
            active.add(current)
            for callee in sorted(adjacency.get(current, set())):
                if callee in active:
                    cycle_edges.add((current, callee))
                    continue
                visit(callee)
            active.remove(current)

        visit(root)
        closure_calls = [
            call
            for definition in reached
            for call in calls_by_definition.get(definition, [])
        ]
        primitive_calls = [
            call for call in closure_calls if call.get("custom_composable") is None
        ]
        project_calls = [
            call for call in closure_calls if call.get("custom_composable") is not None
        ]
        unmapped = collections.Counter(
            call["component"]
            for call in primitive_calls
            if "primitive_mapping_id" not in call
        )
        closures.append(
            {
                "root": definitions[root],
                "reached_definition_count": len(reached),
                "reached_definitions": [
                    definitions[key]
                    for key in sorted(reached)
                    if key in definitions
                ],
                "edge_count": sum(
                    1
                    for caller in reached
                    for callee in adjacency.get(caller, set())
                    if callee in reached
                ),
                "project_component_call_count": len(project_calls),
                "primitive_call_count": len(primitive_calls),
                "mapped_primitive_call_count": sum(
                    1 for call in primitive_calls if "primitive_mapping_id" in call
                ),
                "unmapped_primitive_components": [
                    {"component": component, "call_count": count}
                    for component, count in sorted(unmapped.items())
                ],
                "cycle_detected": bool(cycle_edges),
                "cycle_edges": [
                    {
                        "caller": definitions.get(
                            caller,
                            {"source": caller[0], "composable": caller[1]},
                        ),
                        "callee": definitions.get(
                            callee,
                            {"source": callee[0], "composable": callee[1]},
                        ),
                    }
                    for caller, callee in sorted(cycle_edges)
                ],
            }
        )
    return closures


def analyze(snapshot: Path, manifest: dict[str, Any], files: dict[str, str]) -> dict[str, Any]:
    primitive_mappings, primitive_mappings_by_component = (
        load_primitive_mapping_catalog()
    )
    files_by_layer: dict[str, list[str]] = collections.defaultdict(list)
    for relative in files:
        files_by_layer[classify_file(relative)].append(relative)
    sorted_layers = {
        layer: sorted(paths) for layer, paths in sorted(files_by_layer.items())
    }

    image_associations = step('image-associations', collect_custom_image_associations, files)
    composable_associations = step('composable-associations', collect_composable_associations, files)
    composables = [
        composable
        for relative, text in tracked(list(files.items()), 'source-files', lambda item: item[0])
        if relative.endswith((".kt", ".kts"))
        for composable in extract_composables(
            relative,
            text,
            image_associations,
            composable_associations,
        )
    ]
    component_totals: collections.Counter[str] = collections.Counter()
    modifier_totals: collections.Counter[str] = collections.Counter()
    custom_image_candidates: dict[str, dict[str, Any]] = {}
    semantic_ui_calls: list[dict[str, Any]] = []
    rejected_suffix_only_image_call_count = 0
    for composable in composables:
        semantic_ui_calls.extend({**call, 'declaration_id': composable.get('declaration_id')}
                                 for call in composable.pop("semantic_ui_calls"))
        component_totals.update(composable["components"])
        modifier_totals.update(composable["modifiers"])
        rejected_suffix_only_image_call_count += composable[
            "rejected_suffix_only_image_call_count"
        ]
        for candidate in composable["custom_image_component_candidates"]:
            aggregate = custom_image_candidates.setdefault(
                candidate["name"],
                {
                    "name": candidate["name"],
                    "evidence": [],
                    "uses": [],
                },
            )
            for evidence in candidate["evidence"]:
                if evidence not in aggregate["evidence"]:
                    aggregate["evidence"].append(evidence)
            aggregate["uses"].append(
                {
                    "source": composable["source"],
                    "composable": composable["name"],
                    "call_count": candidate["call_count"],
                }
            )

    custom_composable_edges: list[dict[str, Any]] = []
    referenced_primitive_mapping_ids: set[str] = set()
    for call in tracked(semantic_ui_calls, 'primitive-mapping', lambda item: item['source'] + ':' + item['composable']):
        custom_composable = call.get("custom_composable")
        if custom_composable is None:
            primitive_mapping = primitive_mappings_by_component.get(call["component"])
            if primitive_mapping is not None:
                imported_symbol = composable_associations["imports"].get(
                    call["source"], {}
                ).get(call["component"])
                allowed_import_prefixes = primitive_mapping.get(
                    "source_import_prefixes",
                    ["androidx.compose."],
                )
                if imported_symbol is not None and not any(
                    imported_symbol.startswith(prefix)
                    for prefix in allowed_import_prefixes
                ):
                    call["primitive_mapping_resolution"] = {
                        "status": "rejected_explicit_non_compose_import",
                        "imported_symbol": imported_symbol,
                    }
                    continue
                mapping_id = primitive_mapping["id"]
                call["primitive_mapping_id"] = mapping_id
                if imported_symbol is None:
                    call["primitive_mapping_resolution"] = {
                        "status": "unresolved_simple_name"
                    }
                else:
                    call["primitive_mapping_resolution"] = {
                        "status": "explicit_compose_import",
                        "imported_symbol": imported_symbol,
                    }
                referenced_primitive_mapping_ids.add(mapping_id)
            continue
        for definition in custom_composable["definitions"]:
            custom_composable_edges.append(
                {
                    "caller": {
                        "source": call["source"],
                        "composable": call["composable"],
                    },
                    "callee": definition,
                    "line": call["line"],
                    "call_id": call["call_id"],
                }
            )

    custom_composable_closures = step('call-closures', build_custom_composable_closures,
        composables,
        custom_composable_edges,
        semantic_ui_calls,
    )

    capabilities = step('platform-capabilities', detect_capabilities, files)
    dependencies = step('dependencies', extract_dependencies, files)
    high_risk = [capability["id"] for capability in capabilities if capability["risk"] == "high"]
    risks: list[dict[str, Any]] = []
    if high_risk:
        risks.append(
            {
                "severity": "high",
                "id": "platform-parity",
                "message": "Platform-specific behavior requires explicit HarmonyOS adapters.",
                "capabilities": high_risk,
            }
        )
    if manifest.get("source_git", {}).get("dirty"):
        risks.append(
            {
                "severity": "medium",
                "id": "dirty-source",
                "message": "Source snapshot was created from a dirty Git working tree.",
                "dirty_entry_count": manifest["source_git"]["dirty_entry_count"],
            }
        )
    if manifest.get("blocked_file_count", 0) > 0:
        risks.append(
            {
                "severity": "high",
                "id": "blocked-source-files",
                "message": "Some candidate source files were excluded by the privacy gate.",
                "blocked_file_count": manifest["blocked_file_count"],
            }
        )
    android_imports = step('android-imports', extract_android_imports, files)
    if android_imports:
        risks.append(
            {
                "severity": "medium",
                "id": "candidate-import-reconciliation",
                "message": (
                    "Android imports require explicit mapped, excluded, "
                    "or unsupported classification."
                ),
                "import_count": len(android_imports),
            }
        )

    checkpoint('contract-inventories')
    return {
        "schema": "android-to-harmony.migration-contract.v1",
        "generator": "migrate-android-compose-to-harmony",
        "inventory_quality": "candidate",
        "source": {
            "safe_snapshot_root": str(snapshot),
            "original_root": manifest.get("source_root"),
            "git": manifest.get("source_git"),
        },
        "privacy": {
            "validation_policy": manifest.get("policy_version"),
            "known_image_paths_copied": manifest.get("guarantees", {}).get(
                "known_image_paths_copied",
                False,
            ),
            "embedded_image_scan": manifest.get("guarantees", {}).get(
                "embedded_image_scan",
                {
                    "policy": "legacy",
                    "status": "unknown",
                },
            ),
            "absolute_image_absence_proven": False,
            "credential_literal_scan": manifest.get("guarantees", {}).get(
                "credential_literal_scan",
                {
                    "policy": "legacy",
                    "status": "unknown",
                },
            ),
            "local_only_asset_count": manifest.get("local_only_asset_count", 0),
            "blocked_file_count": manifest.get("blocked_file_count", 0),
            "safe_snapshot_schema": manifest.get("schema"),
        },
        "inventory": {
            "status": "candidate_requires_review",
            "authoritative": False,
            "text_file_count": len(files),
            "files_by_suffix": count_suffixes(files),
            "files_by_layer": sorted_layers,
            "gradle_modules": extract_modules(files),
            "ignored_file_count": manifest.get("ignored_file_count", 0),
            "ignored_files": manifest.get("ignored_files", []),
            "pruned_directory_count": manifest.get(
                "pruned_directory_count",
                0,
            ),
            "pruned_directories": manifest.get("pruned_directories", []),
            "android_imports_requiring_review": android_imports,
        },
        "dependency_inventory": {
            "status": "candidate_requires_review",
            "authoritative": False,
            "candidate_count": len(dependencies),
            "count_semantics": "approximate",
            "limitations": [
                "Static Gradle call scanning is not a resolved dependency graph.",
                "Dynamic configuration names and dependencies added by plugins may be missed.",
            ],
        },
        "dependencies": dependencies,
        "ui": {
            "composable_count": len(composables),
            "composables": sorted(
                composables, key=lambda item: (item["source"], item["name"])
            ),
            "component_totals": dict(sorted(component_totals.items())),
            "modifier_totals": dict(sorted(modifier_totals.items())),
            "compose_theme_token_inventory": extract_compose_theme_tokens(files),
            "kotlin_data_class_inventory": extract_kotlin_data_classes(files),
            "kotlin_enum_inventory": extract_kotlin_enums(files),
            "primitive_component_mapping_catalog": {
                "schema": PRIMITIVE_MAPPING_CANDIDATES_SCHEMA,
                "status": "candidate_requires_review",
                "authoritative": False,
                "mapping_count": len(referenced_primitive_mapping_ids),
                "limitations": [
                    "Explicit non-Compose imports are rejected, but unresolved simple-name matching can still be wrong with wildcard imports, aliases, or symbol shadowing.",
                    "Compose Material dependency versions and theme defaults must be resolved before implementation.",
                    "Project-defined components remain target-local and are never promoted by this catalog match.",
                ],
                "mappings": [
                    mapping
                    for mapping in primitive_mappings
                    if mapping["id"] in referenced_primitive_mapping_ids
                ],
            },
            "semantic_translation_candidates": {
                "status": "candidate_requires_review",
                "authoritative": False,
                "limitations": [
                    "Lightweight Kotlin call scanning is not a complete Kotlin AST.",
                    "Dynamic modifiers, aliases, helper-returned modifiers, and DSL-generated UI may be missed.",
                    "Call hierarchy represents lexical nesting and must be reconciled with runtime branches.",
                ],
                "calls": sorted(
                    semantic_ui_calls,
                    key=lambda item: (
                        item["source"],
                        item["line"],
                        item["call_id"],
                    ),
                ),
            },
            "custom_composable_call_graph": {
                "status": "candidate_requires_review",
                "authoritative": False,
                "edge_count": len(custom_composable_edges),
                "closure_count": len(custom_composable_closures),
                "limitations": [
                    "Static call resolution covers project @Composable definitions reached by explicit imports, same-package visibility, or same-file definitions.",
                    "Wildcard imports, function-valued variables, overload resolution, generated code, and runtime branches may be missed.",
                ],
                "edges": sorted(
                    custom_composable_edges,
                    key=lambda item: (
                        item["caller"]["source"],
                        item["caller"]["composable"],
                        item["callee"]["source"],
                        item["callee"]["composable"],
                        item["line"],
                    ),
                ),
                "transitive_closures": custom_composable_closures,
            },
            "android_view_layout_inventory": extract_android_view_layouts(files),
            "android_navigation_inventory": extract_android_navigation_graphs(files),
            "android_activity_inventory": extract_android_activities(files),
            "android_binding_adapter_inventory": extract_android_binding_adapters(files),
            "android_value_resource_inventory": extract_android_value_resources(files),
            "custom_image_component_inventory": {
                "status": "candidate_requires_review",
                "authoritative": False,
                "candidate_count": len(custom_image_candidates),
                "rejected_suffix_only_call_count": (
                    rejected_suffix_only_image_call_count
                ),
                "limitations": [
                    (
                        "Associated imports and definitions can still produce false positives "
                        "through aliases or symbol shadowing."
                    ),
                    (
                        "Image-rendering components without an *Image name, explicit import, "
                        "or visible @Composable definition may be missed."
                    ),
                ],
                "candidates": [
                    {
                        **candidate,
                        "evidence": sorted(
                            candidate["evidence"],
                            key=lambda item: (
                                item["kind"],
                                item["source"],
                                item.get("symbol", ""),
                            ),
                        ),
                        "uses": sorted(
                            candidate["uses"],
                            key=lambda item: (
                                item["source"],
                                item["composable"],
                            ),
                        ),
                    }
                    for _, candidate in sorted(custom_image_candidates.items())
                ],
            },
            "routes": extract_routes(files),
        },
        "business": {
            "models": extract_models(files),
            "tests": extract_tests(files),
        },
        "platform_capabilities": capabilities,
        "migration_batches": build_batches(sorted_layers),
        "risks": risks,
        "completion_gates": [
            "Candidate inventory and ignored paths are reconciled against the source build graph",
            "HarmonyOS build succeeds",
            "Pure business behavior contracts pass",
            "Demand-related ArkTS UITest flows pass on a device",
            "UI structure contracts pass without image exposure",
            "Every unsupported platform capability is explicitly documented",
        ],
    }


def main() -> int:
    args = parse_args()
    try:
        with Progress('analysis'):
            snapshot, manifest = step('validate-snapshot', load_snapshot, args.snapshot)
            files = step('load-source-files', load_text_files, snapshot, manifest)
            contract = step('analyze-project', analyze, snapshot, manifest, files)
            output = normalize_output(args.output)
            require_separate_output(output, snapshot, manifest)
            step('write-contract', write_contract, output, contract, args.force)
    except (
        AnalysisError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema": "android-to-harmony.command-result.v1",
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "schema": "android-to-harmony.command-result.v1",
                "output": str(output),
                "owner": str(contract_owner_path(output)),
                "composable_count": contract["ui"]["composable_count"],
                "module_count": len(contract["inventory"]["gradle_modules"]),
                "platform_capability_count": len(contract["platform_capabilities"]),
                "risk_count": len(contract["risks"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
