from __future__ import annotations
import json
import os
from init_harmony_project import has_external_ownership_proof, sha256_file
from pathlib import Path
from ui_migration.common import ArkUIPageError, MANIFEST_SCHEMA, MODULE_PATTERN, TARGET_STATE_SCHEMA


def normalize_target(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise ArkUIPageError(f"target must not be a symbolic link: {absolute}")
    target = absolute.resolve()
    if not target.is_dir():
        raise ArkUIPageError(f"target project does not exist: {target}")
    state_path = target / ".migration" / "state.json"
    if not state_path.is_file() or state_path.is_symlink():
        raise ArkUIPageError("target project marker is missing")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArkUIPageError(f"target project marker is invalid: {error}") from error
    if (
        not isinstance(state, dict)
        or state.get("schema") != TARGET_STATE_SCHEMA
        or state.get("generator") != "migrate-android-compose-to-harmony"
        or not has_external_ownership_proof(target, state)
    ):
        raise ArkUIPageError("target project ownership proof is invalid")
    return target


def require_module(target: Path, module: str) -> Path:
    if MODULE_PATTERN.fullmatch(module) is None:
        raise ArkUIPageError(
            "module must start with a letter and contain only letters, digits, underscores, or hyphens"
        )
    module_root = target / module
    main_root = module_root / "src" / "main"
    if module_root.is_symlink() or not module_root.is_dir():
        raise ArkUIPageError(f"target module does not exist: {module}")
    if main_root.is_symlink() or not main_root.is_dir():
        raise ArkUIPageError(f"target module main source set is missing: {module}")
    return module_root


def validate_previous(
    target: Path,
    output_path: Path,
    manifest_path: Path,
    root: dict[str, str],
    module: str,
    force: bool,
) -> None:
    output_exists = output_path.exists()
    manifest_exists = manifest_path.exists()
    if not output_exists and not manifest_exists:
        return
    if not force:
        raise ArkUIPageError("generated ArkUI page already exists; use --force only for unchanged generated outputs")
    if not output_exists or not manifest_exists or output_path.is_symlink() or manifest_path.is_symlink():
        raise ArkUIPageError("forced regeneration requires the complete previous generated output and manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArkUIPageError(f"previous ArkUI generation manifest is invalid: {error}") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("module") != module
        or manifest.get("root") != root
    ):
        raise ArkUIPageError("previous ArkUI generation manifest does not own this output")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise ArkUIPageError("previous ArkUI generation manifest outputs are invalid")
    relative = output_path.relative_to(target).as_posix()
    if relative not in outputs:
        raise ArkUIPageError("previous ArkUI generation manifest does not own the page output")
    for owned_relative, metadata in outputs.items():
        if (
            not isinstance(owned_relative, str)
            or not isinstance(metadata, dict)
            or not isinstance(metadata.get("sha256"), str)
        ):
            raise ArkUIPageError("previous ArkUI generation manifest output entry is invalid")
        owned_path = target / owned_relative
        if (
            not owned_path.is_file()
            or owned_path.is_symlink()
            or metadata["sha256"] != sha256_file(owned_path)
        ):
            raise ArkUIPageError(
                f"generated ArkUI output changed after generation: {owned_relative}"
            )
