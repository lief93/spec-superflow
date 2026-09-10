"""Discover target declarations once and adapt compatible source signatures."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
from typing import ClassVar

from .component_reuse import ComponentAdapter
from ui_migration.contracts.component_interfaces import signature, value_matches


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


def source_type(parameter):
    text = ''.join((parameter.get('type') or '').split())
    if text == '@Composable()->Unit':
        return '()=>void', True
    base = text.removesuffix('?').rsplit('.', 1)[-1]
    if base in {'Color', 'Dp', 'TextUnit'}:
        result = 'ResourceColor' if base == 'Color' else 'number'
    else:
        p = signature([parameter])[0]
        if p['status'] != 'resolved':
            return None, False
        def canonical(tree):
            if tree['kind'] == 'scalar':
                return tree['target']
            if tree['kind'] == 'nullable':
                inner = canonical(tree['inner'])
                return '|'.join(sorted([inner, 'null'])) if inner else None
            if tree['kind'] == 'function' and not tree['arguments'] and tree['result'].get('target') == 'void':
                return '()=>void'
            return None
        return canonical(p['type']), False
    return ('|'.join(sorted([result, 'null'])) if text.endswith('?') else result), False


def mismatch(definition, candidate):
    reasons = list(candidate['errors'])
    source = {p['name']:p for p in definition.get('parameters', [])}
    target = {p['name']:p for p in candidate['parameters']}
    for name, p in source.items():
        kind, slot = source_type(p)
        q = target.get(name)
        if q is None:
            reasons.append('missing target parameter ' + name)
        elif kind is None or kind != q['type'] or (candidate['call_style'] == 'properties' and slot != q['slot']):
            reasons.append(name + ': incompatible types ' + str(p.get('type')) + ' -> ' + q['type'])
        elif q['optional']:
            reasons.append(name + ': optional target property adds undefined; use an explicit compatible type')
        elif slot and candidate['call_style'] == 'positional':
            reasons.append(name + ': positional builder content slot is not supported')
    for name, q in target.items():
        if name not in source and (q['required'] or candidate['call_style'] == 'positional'):
            reasons.append('extra target parameter ' + name)
    return reasons


@dataclass(frozen=True)
class DiscoveredComponentAdapter(ComponentAdapter):
    preserve_parameter_names: ClassVar[bool] = True
    specs: dict = field(default_factory=dict)
    error: str | None = None
    call_style: str = 'properties'

    def argument(self, name, expression, arguments, evaluate):
        if self.error:
            raise ValueError(self.error)
        if source_type(self.specs[name])[0] == '()=>void':
            from kotlin_psi import parse_expression
            tree = parse_expression(expression)
            if tree.get('kind') == 'lambda' and tree.get('body', {}).get('kind') == 'block' and not tree['body'].get('statements'):
                return {'kind':'empty_callback'}
        return evaluate(name, expression, arguments)

    def properties(self, arguments):
        if self.error:
            raise ValueError(self.error)
        result = {}
        for name in self.parameters:
            p, value = self.specs[name], arguments[name]
            kind, _ = source_type(p)
            base = ''.join(p['type'].split()).removesuffix('?').rsplit('.', 1)[-1]
            if value is None and p['type'].strip().endswith('?'):
                result[name] = value
                continue
            resource = isinstance(value, dict) and value.get('kind') == 'platform_resource_reference'
            if base in {'Dp','TextUnit'}:
                unit = 'dp' if base == 'Dp' else 'sp'
                if resource:
                    valid = value['reference']['kind'] == 'dimension' and value['reference'].get('sourceUnit') == unit
                else:
                    valid = getattr(value, 'unit', None) == unit
                    if valid:
                        value = value.value
            elif base == 'Color':
                import re
                valid = (resource and value['reference']['kind'] == 'color') or (isinstance(value, str) and bool(re.fullmatch(r'#[0-9A-Fa-f]{8}', value)))
            else:
                valid = value_matches(value, signature([p])[0]['type'])
            if not valid:
                raise ValueError('auto reuse argument does not match ' + name + ': ' + str(kind))
            result[name] = value
        return result


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
        compatible = [c for c in candidates if not mismatch(definition, c)]
        error = None
        if len(compatible) != 1:
            error = ('ambiguous same-name Harmony components: ' + name if len(compatible) > 1 else
                     'no compatible same-name Harmony component: ' + name + '; ' + '; '.join(
                         c['path'] + ': ' + ', '.join(mismatch(definition, c)) for c in candidates))
        candidate = compatible[0] if len(compatible) == 1 else candidates[0]
        specs = {p['name']:p for p in definition.get('parameters', [])}
        ordered = [p['name'] for p in candidate['parameters'] if p['name'] in specs]
        ordered.extend(n for n in specs if n not in ordered)
        slots = {n:n for n in ordered if source_type(specs[n])[1]}
        adapter = DiscoveredComponentAdapter('auto.' + definition['id'], identity['qualified_name'],
            candidate['module'], name, {n:n for n in ordered if n not in slots}, slots,
            identity.get('source'), identity.get('declaration_id'), specs, error, candidate['call_style'])
        adapters.append(adapter)
        decisions.append({'definition_id':definition['id'], 'name':name,
            'status':'incompatible' if error else 'matched', 'reason':error,
            'target':candidate['path'], 'adapter_id':adapter.id})
    return adapters, decisions
