from __future__ import annotations
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from init_harmony_project import sha256_file
from pathlib import Path
from typing import Any
from ui_migration.arkui.fonts import normalized_font_name
from ui_migration.contracts.material_icons import material_icon_identity
from ui_migration.common import ArkUIPageError, RESOURCE_NAME_PATTERN, pascal_identifier


def load_theme_resources(target: Path, module: str, metadata_dir=None) -> tuple[set[str], dict[str, str]]:
    resources: set[str] = set()
    string_values: dict[str, str] = {}
    manifest_path = (metadata_dir or target / '.migration') / 'compose-theme-resources.json'
    if metadata_dir is not None and metadata_dir != target / '.migration':
        from ui_migration.target_access import check_manifest_outputs, checked_path
        checked_path(metadata_dir, manifest_path)
        check_manifest_outputs(target, module, manifest_path)
    if manifest_path.exists():
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ArkUIPageError("theme resource manifest is not a regular file")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ArkUIPageError(f"theme resource manifest is invalid: {error}") from error
        if isinstance(manifest, dict) and manifest.get("module") == module:
            outputs = manifest.get("outputs")
            names = manifest.get("generated_resource_names")
            if not isinstance(outputs, dict) or not isinstance(names, dict):
                raise ArkUIPageError("theme resource manifest outputs are invalid")
            for relative, metadata in outputs.items():
                if not isinstance(relative, str) or not isinstance(metadata, dict) or not isinstance(metadata.get("sha256"), str):
                    raise ArkUIPageError("theme resource manifest output entry is invalid")
                destination = target / relative
                if not destination.is_file() or destination.is_symlink() or sha256_file(destination) != metadata["sha256"]:
                    raise ArkUIPageError(f"generated theme resource changed after generation: {relative}")
                generated = names.get(relative, [])
                if not isinstance(generated, list) or not all(isinstance(item, str) for item in generated):
                    raise ArkUIPageError("theme resource manifest generated names are invalid")
                resources.update(generated)

    string_path = target / "AppScope/resources/base/element/string.json"
    if string_path.exists():
        if string_path.is_symlink() or not string_path.is_file():
            raise ArkUIPageError("string resource file is not a regular file")
        try:
            strings = json.loads(string_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ArkUIPageError(f"string resource file is invalid: {error}") from error
        values = strings.get("string") if isinstance(strings, dict) else None
        if not isinstance(values, list):
            raise ArkUIPageError("string resource file must contain a string array")
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                resources.add(f"string:{item['name']}")
                if isinstance(item.get("value"), str):
                    string_values[item["name"]] = item["value"]
    media_root = target / module / "src/main/resources/base/media"
    if media_root.exists():
        if media_root.is_symlink() or not media_root.is_dir():
            raise ArkUIPageError("base media resource directory is not a regular directory")
        for media in media_root.iterdir():
            if media.is_file() and not media.is_symlink() and RESOURCE_NAME_PATTERN.fullmatch(media.stem) is not None:
                resources.add(f"media:{media.stem}")
    return resources, string_values


def load_page_font_faces(target: Path, module: str, page: dict[str, Any], metadata_dir=None) -> list[dict[str, Any]]:
    faces = page.get("font_faces", [])
    if not isinstance(faces, list):
        raise ArkUIPageError("page fontFaces must be a list")
    if not faces:
        return []
    ledger_path = (metadata_dir or target / '.migration') / 'assets.json'
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise ArkUIPageError("page fonts require a verified target asset ledger")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema") != "android-to-harmony.asset-ledger.v1":
        raise ArkUIPageError("unsupported font asset ledger")
    result = []
    for face in faces:
        if not isinstance(face, dict) or set(face) != {"family", "resource", "weight"}:
            raise ArkUIPageError("page font face must have family/resource/weight")
        family, resource, weight = face["family"], face["resource"], face["weight"]
        if not isinstance(family, str) or not isinstance(resource, str) or RESOURCE_NAME_PATTERN.fullmatch(resource) is None or type(weight) is not int or not 1 <= weight <= 1000:
            raise ArkUIPageError("invalid page font face")
        matches = [(path, meta) for path, meta in ledger.get("assets", {}).items()
                   if isinstance(meta, dict) and Path(meta.get("asset_path", "")).stem == resource
                   and Path(meta.get("asset_path", "")).parent.name == "font"]
        if len(matches) != 1:
            raise ArkUIPageError(f"missing or ambiguous font asset {resource}")
        relative, metadata = matches[0]
        destination = target / relative
        raw_root = (target / module / "src/main/resources/rawfile").resolve()
        if destination.is_symlink() or not destination.resolve().is_relative_to(raw_root) or not destination.is_file() or sha256_file(destination) != metadata.get("destination_sha256"):
            raise ArkUIPageError(f"font asset hash/path mismatch: {relative}")
        result.append({"alias": pascal_identifier(resource) + str(weight), "weight": weight,
                       "rawfile": destination.resolve().relative_to(raw_root).as_posix(),
                       "target_path": relative, "sha256": metadata["destination_sha256"],
                       "match_names": [normalized_font_name(family)]})
    return result


def derive_page_tinted_vectors(
    target: Path,
    module: str,
    page_identity: str,
    android_page_input: dict[str, Any] | None,
) -> tuple[dict[tuple[str, str], str], dict[Path, bytes], list[dict[str, str]]]:
    if android_page_input is None:
        return {}, {}, []
    media_root = target / module / "src/main/resources/base/media"
    mappings: dict[tuple[str, str], str] = {}
    payloads: dict[Path, bytes] = {}
    records: list[dict[str, str]] = []
    for component in android_page_input["components"]:
        asset = component["style"]["asset"]
        resource = asset.get("resource")
        original_resource = resource
        material_icon = material_icon_identity(resource)
        if material_icon:
            resource = material_icon[1]
        tint = asset.get("tint")
        if (
            not isinstance(resource, str)
            or RESOURCE_NAME_PATTERN.fullmatch(resource) is None
            or not isinstance(tint, str)
            or re.fullmatch(r"#[0-9A-Fa-f]{8}", tint) is None
            or (original_resource, tint) in mappings
        ):
            continue
        source = media_root / f"{resource}.svg"
        if not source.is_file() or source.is_symlink():
            continue
        source_bytes = source.read_bytes()
        try:
            root = ET.fromstring(source_bytes)
        except ET.ParseError as error:
            raise ArkUIPageError(f"target vector resource is malformed: {resource}") from error
        alpha = int(tint[1:3], 16) / 255
        rgb = f"#{tint[3:].upper()}"
        shape_names = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
        for element in root.iter():
            local_name = element.tag.rsplit("}", 1)[-1]
            if local_name not in shape_names:
                continue
            fill = element.get("fill")
            if fill is None or fill.lower() != "none":
                element.set("fill", rgb)
                if alpha < 1:
                    existing_alpha = float(element.get("fill-opacity", "1"))
                    element.set(
                        "fill-opacity",
                        f"{existing_alpha * alpha:.6f}".rstrip("0").rstrip("."),
                    )
            stroke = element.get("stroke")
            if stroke is not None and stroke.lower() != "none":
                element.set("stroke", rgb)
                if alpha < 1:
                    existing_alpha = float(element.get("stroke-opacity", "1"))
                    element.set(
                        "stroke-opacity",
                        f"{existing_alpha * alpha:.6f}".rstrip("0").rstrip("."),
                    )
        if root.tag.startswith("{http://www.w3.org/2000/svg}"):
            ET.register_namespace("", "http://www.w3.org/2000/svg")
        output_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        output_name = f"a2h_{page_identity[:8]}_{resource}_{tint[1:].lower()}"
        if RESOURCE_NAME_PATTERN.fullmatch(output_name) is None:
            raise ArkUIPageError(f"derived page vector name is invalid: {output_name}")
        destination = media_root / f"{output_name}.svg"
        mappings[(original_resource, tint)] = output_name
        payloads[destination] = output_bytes
        records.append({
            "source_resource": resource,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "tint": tint.upper(),
            "output": destination.relative_to(target).as_posix(),
            "sha256": hashlib.sha256(output_bytes).hexdigest(),
        })
    return mappings, payloads, sorted(records, key=lambda item: item["output"])
