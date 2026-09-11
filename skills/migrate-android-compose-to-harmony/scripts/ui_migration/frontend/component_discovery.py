"""Discover unique same-name target declarations and use their defaults."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess

from .component_reuse import ComponentAdapter


from ui_migration.arkts_sdk import parser_runtime


def target_inventory(target, module, component_dir=None, page_output_dir=None):
    from ui_migration.target_paths import ets_directory, page_directory
    target = Path(target).expanduser().resolve()
    root = ets_directory(target, module, component_dir, option='--component-dir')
    output = page_directory(target, module, page_output_dir)
    if root.is_relative_to(output):
        raise ValueError('--component-dir must not be inside --page-output-dir')
    if component_dir is not None and not root.is_dir():
        raise ValueError('--component-dir does not exist: ' + str(root))
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {'generated', 'oh_modules', 'node_modules', 'build', '.hvigor'}
                         and Path(directory)/d != output
                         and not (Path(directory)/d).is_symlink())
        files.extend(str(Path(directory)/name) for name in sorted(names)
                     if name.endswith('.ets') and not (Path(directory)/name).is_symlink())
    if not files:
        return {'components':[], 'diagnostics':[], 'files':0, 'root':str(root)}
    node, compiler = parser_runtime()
    script = Path(__file__).resolve().parents[2]/'arkts_component_inventory.cjs'
    result = subprocess.run([node, str(script), compiler], input=json.dumps({'files':files}),
                            text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise ValueError('ArkTS component discovery failed: ' + result.stderr[-2000:])
    inventory = json.loads(result.stdout)
    for item in inventory['components']:
        relative = os.path.relpath(Path(item['path']).with_suffix(''), target/module/'src/main/ets/generated').replace(os.sep, '/')
        item['module'] = relative if relative.startswith('.') else './' + relative
    inventory.update(files=len(files), root=str(root))
    return inventory


@dataclass(frozen=True)
class DiscoveredComponentAdapter(ComponentAdapter):
    target_parameters: tuple = field(default_factory=tuple)
    error: str | None = None
    call_style: str = 'properties'

    def bind(self, definition, node, evaluate):
        from .component_arguments import bind_default_arguments
        return bind_default_arguments(self, definition, node)


def discover_adapters(definitions, explicit, inventory):
    adapters, decisions = [], []
    by_name = {}
    for candidate in inventory['components']:
        by_name.setdefault(candidate['name'], []).append(candidate)
    for definition in definitions:
        if definition.get('component_kind') != 'project_component':
            continue
        identity = definition.get('identity') or {}
        name = definition['type']
        if any(a.matches(definition) for a in explicit):
            decisions.append({'definition_id':definition['id'], 'name':name, 'status':'explicit'})
            continue
        candidates = by_name.get(name, [])
        if not candidates:
            decisions.append({'definition_id':definition['id'], 'name':name, 'status':'not-found'})
            continue
        candidate = candidates[0]
        error = ('ambiguous same-name Harmony components: ' + name if len(candidates) != 1 else
                 '; '.join(candidate['errors']) or None)
        adapter = DiscoveredComponentAdapter('auto.' + definition['id'], identity['qualified_name'],
            candidate['module'], name, source=identity.get('source'), declaration_id=identity.get('declaration_id'),
            target_parameters=tuple(candidate['parameters']), error=error, call_style=candidate['call_style'])
        adapters.append(adapter)
        decisions.append({'definition_id':definition['id'], 'name':name,
            'status':'incompatible' if error else 'matched', 'reason':error,
            'target':candidate['path'], 'adapter_id':adapter.id})
    return adapters, decisions
