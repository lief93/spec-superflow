"""Resolve page/discovery locations without changing JSON import coordinates."""
import os
from pathlib import Path

from ui_migration.common import MODULE_PATTERN


def ets_directory(target, module, directory=None, *, default='', option='directory'):
    if MODULE_PATTERN.fullmatch(module) is None:
        raise ValueError('invalid Harmony module name')
    target = Path(target).expanduser().resolve()
    root = target / module / 'src/main/ets'
    path = Path(directory).expanduser() if directory is not None else root / default
    if not path.is_absolute():
        path = target / path
    path = Path(os.path.abspath(path))
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'{option} must be inside {root}: {path}')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'{option} must not contain symbolic links: {part}')
        if part.resolve() == target:
            break
    path = path.resolve()
    if path.exists() and not path.is_dir():
        raise ValueError(f'{option} must be a directory: {path}')
    return path


def page_directory(target, module, directory=None):
    return ets_directory(target, module, directory, default='generated', option='--page-output-dir')


def relocate_import(module, original_directory, output_directory):
    if not module.startswith(('./', '../')):
        return module
    relative = os.path.relpath(Path(original_directory) / module, output_directory).replace(os.sep, '/')
    return relative if relative.startswith('.') else './' + relative
