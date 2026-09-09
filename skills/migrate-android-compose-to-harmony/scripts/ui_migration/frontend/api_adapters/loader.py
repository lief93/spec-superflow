"""Explicit trusted-code loader. Scanning a repository never invokes this loader."""
import hashlib
from types import ModuleType
import json
from pathlib import Path

from .registry import AdapterRegistry


def load_adapters(manifest: Path | None, builtins=()):
    if manifest is None:
        return AdapterRegistry(builtins)
    if manifest.is_symlink():
        raise ValueError('adapter manifest must not be a symlink')
    root = manifest.resolve().parent
    data = json.loads(manifest.read_text())
    if data.get('schema') != 'ui-migration.api-adapters.v1' or not isinstance(data.get('modules'), list):
        raise ValueError('invalid API adapter manifest')
    identities, modules = [], []
    for record in data['modules']:
        relative = Path(record['path'])
        path = root / relative
        if relative.is_absolute() or '..' in relative.parts or path.suffix != '.py' or any(
                candidate.is_symlink() for candidate in (path, *path.parents) if candidate != root.parent):
            raise ValueError('adapter module must be an ordinary Python file within its manifest directory')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != record.get('sha256'):
            raise ValueError('adapter module SHA mismatch: ' + str(relative))
        identities.append({'path': str(relative), 'sha256': digest})
        modules.append((path, digest, raw))
    adapters = list(builtins)
    component_adapters = []
    # Verify every file before executing any trusted extension.
    for path, digest, raw in modules:
        module = ModuleType('ui_project_adapter_' + digest)
        module.__file__ = str(path)
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        declared = getattr(module, 'ADAPTERS', None)
        if not isinstance(declared, (tuple, list)):
            raise ValueError('extension must export an ADAPTERS list')
        adapters.extend(declared)
        components = getattr(module, 'COMPONENT_ADAPTERS', [])
        if not isinstance(components, (tuple, list)):
            raise ValueError('COMPONENT_ADAPTERS must be a list')
        component_adapters.extend(components)
    return AdapterRegistry(adapters, identities, component_adapters)
