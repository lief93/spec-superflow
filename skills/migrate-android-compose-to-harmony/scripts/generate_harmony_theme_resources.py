#!/usr/bin/env python3
"""Generate candidate HarmonyOS theme resources from a migration contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from init_harmony_project import (
    has_external_ownership_proof,
    load_contract,
    sha256_file,
)


MANIFEST_SCHEMA = "android-to-harmony.compose-theme-resources.v1"
TARGET_STATE_SCHEMA = "android-to-harmony.project-state.v1"
MODULE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
RESOURCE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
COLOR_LITERAL_PATTERN = re.compile(
    r"\s*Color\s*\(\s*0x([0-9A-Fa-f]{8})\s*\)\s*"
)
NAMED_COLORS = {
    "Color.Black": "#FF000000",
    "Color.White": "#FFFFFFFF",
    "Color.Transparent": "#00000000",
    "Color.Red": "#FFFF0000",
    "Color.Green": "#FF00FF00",
    "Color.Blue": "#FF0000FF",
    "Color.Yellow": "#FFFFFF00",
    "Color.Gray": "#FF888888",
    "Color.DarkGray": "#FF444444",
    "Color.LightGray": "#FFCCCCCC",
    "Color.Cyan": "#FF00FFFF",
    "Color.Magenta": "#FFFF00FF",
}
MATERIAL3_LIGHT_COLOR_DEFAULTS = {
    # AndroidX ColorLightTokens / PaletteTokens, baseline v0_210.
    "onPrimary": "#FFFFFFFF",
    "onSurface": "#FF1D1B20",
    "surfaceContainerHighest": "#FFE6E0E9",
    "surfaceContainer": "#FFF3EDF7",
    "error": "#FFB3261E",
    "primary": "#FF6750A4",
    "primaryContainer": "#FFEADDFF",
    "onPrimaryContainer": "#FF21005D",
    "inversePrimary": "#FFD0BCFF",
    "secondary": "#FF625B71",
    "onSecondary": "#FFFFFFFF",
    "secondaryContainer": "#FFE8DEF8",
    "onSecondaryContainer": "#FF1D192B",
    "tertiary": "#FF7D5260",
    "onTertiary": "#FFFFFFFF",
    "tertiaryContainer": "#FFFFD8E4",
    "onTertiaryContainer": "#FF31111D",
    "background": "#FFFEF7FF",
    "onBackground": "#FF1D1B20",
    "surface": "#FFFEF7FF",
    "surfaceVariant": "#FFE7E0EC",
    "onSurfaceVariant": "#FF49454F",
    "surfaceTint": "#FF6750A4",
    "inverseSurface": "#FF322F35",
    "inverseOnSurface": "#FFF5EFF7",
    "onError": "#FFFFFFFF",
    "errorContainer": "#FFF9DEDC",
    "onErrorContainer": "#FF410E0B",
    "outline": "#FF79747E",
    "outlineVariant": "#FFCAC4D0",
    "scrim": "#FF000000",
    "surfaceBright": "#FFFEF7FF",
    "surfaceDim": "#FFDED8E1",
    "surfaceContainerHigh": "#FFECE6F0",
    "surfaceContainerLow": "#FFF7F2FA",
    "surfaceContainerLowest": "#FFFFFFFF",
    "primaryFixed": "#FFEADDFF",
    "primaryFixedDim": "#FFD0BCFF",
    "onPrimaryFixed": "#FF21005D",
    "onPrimaryFixedVariant": "#FF4F378B",
    "secondaryFixed": "#FFE8DEF8",
    "secondaryFixedDim": "#FFCCC2DC",
    "onSecondaryFixed": "#FF1D192B",
    "onSecondaryFixedVariant": "#FF4A4458",
    "tertiaryFixed": "#FFFFD8E4",
    "tertiaryFixedDim": "#FFEFB8C8",
    "onTertiaryFixed": "#FF31111D",
    "onTertiaryFixedVariant": "#FF633B48",
}


class ThemeResourceError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate candidate HarmonyOS color, float, font-plan, typography, "
            "and shape resources from a migration contract."
        )
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--module", default="entry")
    parser.add_argument("--force", action="store_true")
    from ui_migration.target_access import add_target_arguments
    add_target_arguments(parser)
    return parser.parse_args()


def normalize_target(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise ThemeResourceError(f"target must not be a symbolic link: {absolute}")
    target = absolute.resolve()
    if not target.is_dir():
        raise ThemeResourceError(f"target project does not exist: {target}")
    state_path = target / ".migration" / "state.json"
    if not state_path.is_file() or state_path.is_symlink():
        raise ThemeResourceError("target project marker is missing")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ThemeResourceError(f"target project marker is invalid: {error}") from error
    if (
        not isinstance(state, dict)
        or state.get("schema") != TARGET_STATE_SCHEMA
        or state.get("generator") != "migrate-android-compose-to-harmony"
        or not has_external_ownership_proof(target, state)
    ):
        raise ThemeResourceError("target project ownership proof is invalid")
    return target


def require_safe_module(target: Path, module: str) -> Path:
    if MODULE_PATTERN.fullmatch(module) is None:
        raise ThemeResourceError(
            "module must start with a letter and contain only letters, digits, underscores, or hyphens"
        )
    module_root = target / module
    if module_root.is_symlink() or not module_root.is_dir():
        raise ThemeResourceError(f"target module does not exist: {module}")
    main_root = module_root / "src" / "main"
    if main_root.is_symlink() or not main_root.is_dir():
        raise ThemeResourceError(f"target module main source set is missing: {module}")
    return module_root


def require_theme_inventory(contract: dict[str, Any]) -> dict[str, Any]:
    ui = contract.get("ui")
    inventory = ui.get("compose_theme_token_inventory") if isinstance(ui, dict) else None
    if (
        not isinstance(inventory, dict)
        or inventory.get("status") != "candidate_requires_review"
        or inventory.get("authoritative") is not False
    ):
        raise ThemeResourceError(
            "contract has no candidate Compose theme token inventory"
        )
    for key in (
        "tokens",
        "color_schemes",
        "typography_sets",
        "shape_sets",
        "theme_applications",
    ):
        if not isinstance(inventory.get(key), list):
            raise ThemeResourceError(f"theme inventory {key} must be a list")
    if "extended_color_sets" not in inventory:
        inventory["extended_color_sets"] = []
    elif not isinstance(inventory.get("extended_color_sets"), list):
        raise ThemeResourceError("theme inventory extended_color_sets must be a list")
    return inventory


def snake_name(value: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    second = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", second).strip("_").lower()
    if not normalized or normalized[0].isdigit():
        normalized = f"token_{normalized}"
    if RESOURCE_NAME_PATTERN.fullmatch(normalized) is None:
        raise ThemeResourceError(f"cannot create Harmony resource name from: {value}")
    return normalized


def normalize_color(value: Any) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6,8}", value):
        return value.upper()
    return None


def color_from_semantics(semantics: Any) -> str | None:
    if not isinstance(semantics, dict):
        return None
    resolved = semantics.get("resolved_token")
    if isinstance(resolved, dict) and resolved.get("status") == "resolved_unique":
        color = normalize_color(resolved.get("argb_hex"))
        if color is not None:
            return color
    expression = semantics.get("expression")
    if not isinstance(expression, str):
        return None
    literal = COLOR_LITERAL_PATTERN.fullmatch(expression)
    if literal is not None:
        return f"#{literal.group(1).upper()}"
    return NAMED_COLORS.get(expression.strip())


def one_dimension(semantics: Any) -> tuple[str, str] | None:
    if not isinstance(semantics, dict):
        return None
    dimensions = semantics.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) != 1:
        return None
    dimension = dimensions[0]
    if not isinstance(dimension, dict):
        return None
    value = dimension.get("value")
    unit = dimension.get("unit")
    if (
        not isinstance(value, str)
        or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value) is None
        or unit not in {"dp", "sp"}
    ):
        return None
    return value, "vp" if unit == "dp" else "fp"


def add_resource(
    resources: dict[str, str],
    collisions: dict[str, set[str]],
    name: str,
    value: str,
) -> None:
    if name in collisions:
        collisions[name].add(value)
        return
    existing = resources.get(name)
    if existing is not None and existing != value:
        del resources[name]
        collisions[name] = {existing, value}
        return
    resources[name] = value


def unique_scheme(
    inventory: dict[str, Any],
    variant: str,
    unresolved: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matches = [
        item
        for item in inventory["color_schemes"]
        if isinstance(item, dict) and item.get("variant") == variant
    ]
    if len(matches) > 1:
        unresolved.append(
            {
                "kind": "color_scheme",
                "name": variant,
                "reason": "multiple candidate schemes require explicit reconciliation",
                "candidate_count": len(matches),
            }
        )
        return None
    return matches[0] if matches else None


def build_candidate_resources(
    inventory: dict[str, Any],
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, str],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    base_colors: dict[str, str] = {}
    dark_colors: dict[str, str] = {}
    floats: dict[str, str] = {}
    base_color_collisions: dict[str, set[str]] = {}
    dark_color_collisions: dict[str, set[str]] = {}
    float_collisions: dict[str, set[str]] = {}
    unresolved: list[dict[str, Any]] = []
    font_copy_plan: list[dict[str, Any]] = []
    typography_contracts: list[dict[str, Any]] = []
    shape_contracts: list[dict[str, Any]] = []

    for token in inventory["tokens"]:
        if not isinstance(token, dict) or not isinstance(token.get("name"), str):
            raise ThemeResourceError("theme inventory token is invalid")
        token_name = token["name"]
        kind = token.get("kind")
        if kind == "color":
            color = normalize_color(token.get("argb_hex"))
            if color is None:
                color = color_from_semantics(token)
            if color is None:
                unresolved.append(
                    {
                        "kind": "color_token",
                        "name": token_name,
                        "reason": "color expression is not statically resolved",
                    }
                )
            else:
                add_resource(
                    base_colors,
                    base_color_collisions,
                    f"compose_color_{snake_name(token_name)}",
                    color,
                )
        elif kind == "dimension":
            dimension = one_dimension(token)
            if dimension is None:
                unresolved.append(
                    {
                        "kind": "dimension_token",
                        "name": token_name,
                        "reason": "dimension token must contain exactly one literal dp or sp value",
                    }
                )
            else:
                add_resource(
                    floats,
                    float_collisions,
                    f"compose_dimension_{snake_name(token_name)}",
                    f"{dimension[0]}{dimension[1]}",
                )
        elif kind in {"font", "font_family"}:
            keys = token.get("font_resource_keys")
            if isinstance(keys, list) and all(
                isinstance(key, str) and key for key in keys
            ) and keys:
                font_copy_plan.append(
                    {
                        "name": token_name,
                        "kind": kind,
                        "font_resource_keys": sorted(set(keys)),
                        "status": "requires_manifest_approved_opaque_copy",
                    }
                )

    for variant, destination, collisions in (
        ("light", base_colors, base_color_collisions),
        ("dark", dark_colors, dark_color_collisions),
    ):
        scheme = unique_scheme(inventory, variant, unresolved)
        if scheme is None:
            continue
        roles = scheme.get("roles")
        if not isinstance(roles, dict):
            raise ThemeResourceError(f"{variant} color scheme roles must be an object")
        for role_name, semantics in sorted(roles.items()):
            color = color_from_semantics(semantics)
            if color is None:
                unresolved.append(
                    {
                        "kind": "color_role",
                        "name": f"{variant}.{role_name}",
                        "reason": "color role is not statically resolved",
                    }
                )
                continue
            add_resource(
                destination,
                collisions,
                f"compose_theme_{snake_name(str(role_name))}",
                color,
            )
        if variant == "light":
            for role_name, color in sorted(MATERIAL3_LIGHT_COLOR_DEFAULTS.items()):
                if role_name in roles:
                    continue
                add_resource(
                    destination,
                    collisions,
                    f"compose_theme_{snake_name(role_name)}",
                    color,
                )

    for extended_set in inventory.get("extended_color_sets", []):
        if not isinstance(extended_set, dict) or not isinstance(
            extended_set.get("name"), str
        ):
            raise ThemeResourceError("theme inventory extended color set is invalid")
        variant = extended_set.get("variant")
        if variant == "dark":
            destination = dark_colors
            collisions = dark_color_collisions
        else:
            destination = base_colors
            collisions = base_color_collisions
        roles = extended_set.get("roles")
        if not isinstance(roles, dict):
            raise ThemeResourceError("extended color set roles must be an object")
        for role_name, semantics in sorted(roles.items()):
            color = color_from_semantics(semantics)
            if color is None:
                unresolved.append(
                    {
                        "kind": "extended_color_role",
                        "name": f"{extended_set['name']}.{role_name}",
                        "reason": "extended color role is not statically resolved",
                    }
                )
                continue
            add_resource(
                destination,
                collisions,
                f"compose_extended_color_{snake_name(str(role_name))}",
                color,
            )

    for typography in inventory["typography_sets"]:
        if not isinstance(typography, dict) or not isinstance(
            typography.get("name"), str
        ):
            raise ThemeResourceError("theme inventory typography set is invalid")
        styles = typography.get("styles")
        if not isinstance(styles, dict):
            raise ThemeResourceError("typography styles must be an object")
        typography_contracts.append(
            {
                "name": typography["name"],
                "styles": styles,
                "status": "candidate_requires_review",
            }
        )
        for role_name, style in sorted(styles.items()):
            properties = style.get("properties") if isinstance(style, dict) else None
            if not isinstance(properties, dict):
                continue
            for property_name in ("fontSize", "lineHeight", "letterSpacing"):
                if property_name not in properties:
                    continue
                dimension = one_dimension(properties[property_name])
                qualified = f"{typography['name']}.{role_name}.{property_name}"
                if dimension is None:
                    unresolved.append(
                        {
                            "kind": "typography_dimension",
                            "name": qualified,
                            "reason": "typography dimension is not one literal dp or sp value",
                        }
                    )
                    continue
                add_resource(
                    floats,
                    float_collisions,
                    "compose_typography_"
                    f"{snake_name(str(role_name))}_{snake_name(property_name)}",
                    f"{dimension[0]}{dimension[1]}",
                )

    for shapes in inventory["shape_sets"]:
        if not isinstance(shapes, dict) or not isinstance(shapes.get("name"), str):
            raise ThemeResourceError("theme inventory shape set is invalid")
        roles = shapes.get("roles")
        if not isinstance(roles, dict):
            raise ThemeResourceError("shape roles must be an object")
        for role_name, semantics in sorted(roles.items()):
            contract = {
                "set": shapes["name"],
                "role": role_name,
                "semantics": semantics,
                "status": "candidate_requires_review",
            }
            dimension = one_dimension(semantics)
            if dimension is None:
                contract["float_resource"] = None
                unresolved.append(
                    {
                        "kind": "shape_dimension",
                        "name": f"{shapes['name']}.{role_name}",
                        "reason": "shape requires explicit multi-corner or dynamic translation",
                    }
                )
            else:
                resource_name = f"compose_shape_{snake_name(str(role_name))}_radius"
                add_resource(
                    floats,
                    float_collisions,
                    resource_name,
                    f"{dimension[0]}{dimension[1]}",
                )
                contract["float_resource"] = resource_name
            shape_contracts.append(contract)

    for collisions in (
        base_color_collisions,
        dark_color_collisions,
        float_collisions,
    ):
        for resource_name, candidate_values in sorted(collisions.items()):
            unresolved.append(
                {
                    "kind": "resource_name_collision",
                    "resource_name": resource_name,
                    "candidate_values": sorted(candidate_values),
                }
            )

    return (
        base_colors,
        dark_colors,
        floats,
        unresolved,
        font_copy_plan,
        typography_contracts,
        shape_contracts,
    )


def load_resource_payload(path: Path, category: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ThemeResourceError(f"resource output must not be a symbolic link: {path}")
    if not path.exists():
        return {category: []}
    if not path.is_file():
        raise ThemeResourceError(f"resource output is not a file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ThemeResourceError(f"invalid Harmony resource file {path}: {error}") from error
    values = payload.get(category) if isinstance(payload, dict) else None
    if not isinstance(values, list):
        raise ThemeResourceError(f"Harmony resource file has no {category} array: {path}")
    names: set[str] = set()
    for item in values:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("value"), str)
            or item["name"] in names
        ):
            raise ThemeResourceError(f"Harmony resource entry is invalid: {path}")
        names.add(item["name"])
    return payload


def json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def load_previous_manifest(
    manifest_path: Path,
    target: Path,
    module: str,
    force: bool,
) -> dict[str, Any] | None:
    if manifest_path.is_symlink():
        raise ThemeResourceError("theme resource manifest must not be a symbolic link")
    if not manifest_path.exists():
        return None
    if not force:
        raise ThemeResourceError(
            "theme resources already exist; pass --force to replace unchanged generated outputs"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ThemeResourceError(f"invalid theme resource manifest: {error}") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("target_root") != "."
        or manifest.get("module") != module
        or not isinstance(manifest.get("outputs"), dict)
    ):
        raise ThemeResourceError("theme resource manifest is invalid")
    for relative, metadata in manifest["outputs"].items():
        if (
            not isinstance(relative, str)
            or not isinstance(metadata, dict)
            or not isinstance(metadata.get("sha256"), str)
        ):
            raise ThemeResourceError("theme resource manifest output is invalid")
        output = target / relative
        if (
            not output.is_file()
            or output.is_symlink()
            or sha256_file(output) != metadata["sha256"]
        ):
            raise ThemeResourceError(
                f"refusing to replace a generated theme output that changed: {relative}"
            )
    return manifest


def merge_resources(
    path: Path,
    category: str,
    generated: dict[str, str],
    previous_names: set[str],
) -> tuple[dict[str, Any], list[str]]:
    payload = load_resource_payload(path, category)
    retained = [
        item for item in payload[category] if item["name"] not in previous_names
    ]
    retained_names = {item["name"] for item in retained}
    conflicts = retained_names.intersection(generated)
    if conflicts:
        raise ThemeResourceError(
            "generated theme resource conflicts with an existing target resource: "
            + ", ".join(sorted(conflicts))
        )
    generated_names = sorted(generated)
    payload[category] = retained + [
        {"name": name, "value": generated[name]} for name in generated_names
    ]
    return payload, generated_names


def commit_payloads(
    payloads: dict[Path, bytes],
    deletions: set[Path] | None = None,
) -> None:
    deletion_paths = deletions or set()
    if set(payloads).intersection(deletion_paths):
        raise ThemeResourceError("theme resource output cannot be written and deleted")
    temporary_files: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    replaced: set[Path] = set()
    destinations = list(payloads) + sorted(deletion_paths)
    try:
        for destination in destinations:
            if destination in payloads:
                destination.parent.mkdir(parents=True, exist_ok=True)
            current = destination.parent
            while current != current.parent:
                if current.is_symlink():
                    raise ThemeResourceError(
                        f"theme resource output path contains a symbolic link: {destination}"
                    )
                current = current.parent
            backup = destination.with_name(f".{destination.name}.compose-theme-backup")
            if backup.exists() or backup.is_symlink():
                raise ThemeResourceError(f"refusing while backup exists: {backup}")
        for destination in payloads:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.compose-theme-",
                dir=destination.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payloads[destination])
                stream.flush()
                os.fsync(stream.fileno())
            temporary_files[destination] = temporary
        for destination in destinations:
            if destination.exists():
                backup = destination.with_name(
                    f".{destination.name}.compose-theme-backup"
                )
                os.replace(destination, backup)
                backups[destination] = backup
        for destination in payloads:
            os.replace(temporary_files[destination], destination)
            replaced.add(destination)
        for backup in backups.values():
            backup.unlink(missing_ok=True)
    except Exception:
        for destination in reversed(destinations):
            if destination in replaced:
                destination.unlink(missing_ok=True)
            backup = backups.get(destination)
            if backup is not None and backup.exists():
                os.replace(backup, destination)
        raise
    finally:
        for temporary in temporary_files.values():
            temporary.unlink(missing_ok=True)


def generate(
    contract_path: Path,
    target_path: Path,
    module: str,
    force: bool,
    *, existing_target=False, target_metadata_dir=None,
) -> dict[str, Any]:
    from ui_migration.target_access import metadata_directory, check_manifest_outputs, checked_path
    metadata = metadata_directory(target_path, module, existing_target, target_metadata_dir)
    target = target_path.expanduser().resolve() if existing_target else normalize_target(target_path)
    require_safe_module(target, module)
    contract, resolved_contract = load_contract(contract_path)
    if contract is None or resolved_contract is None:
        raise ThemeResourceError("migration contract is required")
    inventory = require_theme_inventory(contract)
    manifest_path = metadata / 'compose-theme-resources.json'
    if existing_target:
        checked_path(metadata, manifest_path)
        check_manifest_outputs(target, module, manifest_path)
    previous = load_previous_manifest(
        manifest_path,
        target,
        module,
        force,
    )
    previous_names = (
        previous.get("generated_resource_names", {})
        if isinstance(previous, dict)
        else {}
    )
    if not isinstance(previous_names, dict):
        raise ThemeResourceError("theme resource manifest generated names are invalid")

    (
        base_colors,
        dark_colors,
        floats,
        unresolved,
        font_copy_plan,
        typography_contracts,
        shape_contracts,
    ) = build_candidate_resources(inventory)
    relative_outputs: list[tuple[str, str, dict[str, str]]] = [
        (
            f"{module}/src/main/resources/base/element/color.json",
            "color",
            base_colors,
        )
    ]
    if floats:
        relative_outputs.append(
            (
                f"{module}/src/main/resources/base/element/float.json",
                "float",
                floats,
            )
        )
    if dark_colors:
        relative_outputs.append(
            (
                f"{module}/src/main/resources/dark/element/color.json",
                "color",
                dark_colors,
            )
        )

    output_bytes: dict[Path, bytes] = {}
    output_metadata: dict[str, Any] = {}
    generated_names: dict[str, list[str]] = {}
    for relative, category, generated_values in relative_outputs:
        if existing_target:
            if not generated_values:
                continue
            relative = str(Path(relative).with_name('migration_' + Path(relative).name))
            destination = checked_path(target / module / 'src/main/resources', target / relative)
            if destination.exists() and (previous is None or relative not in previous['outputs']):
                raise ThemeResourceError(f'refusing to replace an unowned theme file: {relative}')
            for other in destination.parent.glob('*.json'):
                if other == destination:
                    continue
                checked_path(target, other)
                payload = json.loads(other.read_text(encoding='utf-8'))
                names_in_other = {item.get('name') for item in payload.get(category, []) if isinstance(item, dict)}
                conflicts = names_in_other.intersection(generated_values)
                if conflicts:
                    raise ThemeResourceError('generated theme resource conflicts with an existing target resource: ' + ', '.join(sorted(conflicts)))
        previous_for_output = previous_names.get(relative, [])
        if not isinstance(previous_for_output, list) or not all(
            isinstance(name, str) for name in previous_for_output
        ):
            raise ThemeResourceError(
                f"theme resource manifest names are invalid for: {relative}"
            )
        payload, names = merge_resources(
            target / relative,
            category,
            generated_values,
            set(previous_for_output),
        )
        encoded = json_bytes(payload)
        output_bytes[target / relative] = encoded
        generated_names[relative] = names
        output_metadata[relative] = {
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "category": category,
            "generated_resource_count": len(names),
        }

    obsolete_outputs: set[Path] = set()
    if previous is not None:
        current_outputs = set(output_metadata)
        obsolete_outputs = {
            target / relative
            for relative in previous["outputs"]
            if relative not in current_outputs
        }

    source = contract.get("source")
    git = source.get("git") if isinstance(source, dict) else None
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generator": "migrate-android-compose-to-harmony",
        "status": "candidate_requires_review",
        "authoritative": False,
        "target_root": ".",
        "module": module,
        "contract_sha256": sha256_file(resolved_contract),
        "source_revision": git.get("revision") if isinstance(git, dict) else None,
        "resource_skeleton_complete": not unresolved,
        "unresolved": unresolved,
        "font_copy_plan": font_copy_plan,
        "typography_contracts": typography_contracts,
        "shape_contracts": shape_contracts,
        "generated_resource_names": generated_names,
        "outputs": output_metadata,
        "limitations": [
            "Generated resources cover only statically resolved candidate theme declarations.",
            "Font files are never read or copied here; each font plan requires manifest-approved opaque copying.",
            "Typography weights, families, shapes, runtime theme selection, and Material defaults still require ArkUI implementation review.",
        ],
    }
    output_bytes[manifest_path] = json_bytes(manifest)
    commit_payloads(output_bytes, obsolete_outputs)
    return {
        "target": str(target),
        "module": module,
        "manifest": str(manifest_path) if existing_target else ".migration/compose-theme-resources.json",
        "resource_skeleton_complete": not unresolved,
        "unresolved_count": len(unresolved),
        "font_copy_plan_count": len(font_copy_plan),
        "output_count": len(output_metadata),
    }


def main() -> int:
    args = parse_args()
    try:
        result = generate(
            args.contract,
            args.target,
            args.module,
            args.force,
            existing_target=args.existing_target, target_metadata_dir=args.target_metadata_dir,
        )
    except (ThemeResourceError, OSError, TypeError, ValueError) as error:
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
                **result,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
