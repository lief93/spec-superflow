"""Explicit, module-scoped writes into existing Harmony projects."""
import hashlib
import json
import os
from pathlib import Path

from ui_migration.common import MODULE_PATTERN


def add_target_arguments(parser):
    parser.add_argument('--existing-target', action='store_true',
                        help='Write into an existing Harmony project without a migration project marker.')
    parser.add_argument('--target-metadata-dir', type=Path,
                        help='Stable directory outside the target for generation ownership records; required with --existing-target.')


def checked_path(root, path):
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(root):
        # Accept OS aliases such as /var -> /private/var without resolving
        # symlinks inside the selected project boundary.
        for ancestor in path.parents:
            if ancestor.resolve() == root and not ancestor.is_symlink():
                path = root / path.relative_to(ancestor)
                break
    if not path.is_relative_to(root):
        raise ValueError(f'output must stay inside {root}: {path}')
    for current in (path, *path.parents):
        if current.is_symlink():
            raise ValueError(f'output path must not contain symbolic links: {current}')
        if current == root:
            break
    return path


def metadata_directory(target, module, existing_target=False, metadata_dir=None):
    if not existing_target:
        if metadata_dir is not None:
            raise ValueError('--target-metadata-dir requires --existing-target')
        return Path(target).resolve() / '.migration'
    if metadata_dir is None:
        raise ValueError('--existing-target requires a stable --target-metadata-dir outside the target')
    raw_target = Path(target).expanduser().absolute()
    if raw_target.is_symlink() or not raw_target.is_dir():
        raise ValueError('existing target must be a regular project directory')
    target = raw_target.resolve()
    if MODULE_PATTERN.fullmatch(module) is None:
        raise ValueError('invalid Harmony module name')
    for relative in ('build-profile.json5', 'oh-package.json5', f'{module}/src/main/module.json5'):
        path = checked_path(target, target / relative)
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f'existing Harmony project file is missing: {path}')
    for relative in (f'{module}/src/main/ets', f'{module}/src/main/resources'):
        if not checked_path(target, target / relative).is_dir():
            raise ValueError(f'existing Harmony module directory is missing: {relative}')
    raw_metadata = Path(metadata_dir).expanduser().absolute()
    if raw_metadata.is_symlink():
        raise ValueError('target metadata directory must not be a symbolic link')
    base = raw_metadata.resolve()
    if base.exists() and not base.is_dir():
        raise ValueError('target metadata directory must be a directory')
    if base.is_relative_to(target) or target.is_relative_to(base):
        raise ValueError('target metadata directory and target must be separate')
    identity = hashlib.sha256(str(target).encode()).hexdigest()[:24]
    location = checked_path(base, base / identity / module)
    for current in (location, location.parent):
        if current.exists() and not current.is_dir():
            raise ValueError('target metadata location must be a directory')
    return location


def check_manifest_outputs(target, module, manifest_path):
    if manifest_path.is_symlink():
        raise ValueError('generation manifest must not be a symbolic link')
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('outputs'), dict):
        raise ValueError('generation manifest outputs are invalid')
    for relative in manifest.get('outputs', {}):
        output = checked_path(target / module / 'src/main', target / relative)
        main = target / module / 'src/main'
        if not (output.is_relative_to(main / 'resources') or
                (output.is_relative_to(main / 'ets') and output.suffix == '.ets')):
            raise ValueError(f'generation manifest cannot own project configuration: {relative}')


def asset_metadata(target, destination, existing_target, metadata_dir):
    target = Path(target).expanduser().resolve()
    if not existing_target:
        return metadata_directory(target, 'entry', False, metadata_dir)
    destination = checked_path(target, Path(destination).expanduser().absolute())
    relative = destination.relative_to(target)
    module = relative.parts[0]
    if existing_target:
        checked_path(target / module / 'src/main/resources', destination)
    return metadata_directory(target, module, existing_target, metadata_dir)
