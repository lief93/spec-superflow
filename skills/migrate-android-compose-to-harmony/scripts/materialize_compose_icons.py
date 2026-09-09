"""Convert selected, version-pinned AndroidX Material paths without viewing images."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from contextlib import ExitStack

from kotlin_psi import parse_declarations
from ui_migration.contracts.material_icons import material_icon_identity
from ui_migration.frontend.values import evaluate_expression
from ui_migration.semantics.syntax import call_from


COMMANDS = {
    'moveTo': ('M', 2), 'moveToRelative': ('m', 2),
    'lineTo': ('L', 2), 'lineToRelative': ('l', 2),
    'horizontalLineTo': ('H', 1), 'horizontalLineToRelative': ('h', 1),
    'verticalLineTo': ('V', 1), 'verticalLineToRelative': ('v', 1),
    'curveTo': ('C', 6), 'curveToRelative': ('c', 6),
    'reflectiveCurveTo': ('S', 4), 'reflectiveCurveToRelative': ('s', 4),
    'quadTo': ('Q', 4), 'quadToRelative': ('q', 4),
    'reflectiveQuadTo': ('T', 2), 'reflectiveQuadToRelative': ('t', 2),
    'arcTo': ('A', 7), 'arcToRelative': ('a', 7),
    'close': ('Z', 0),
}


def syntax_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from syntax_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from syntax_nodes(child)


def convert(source):
    factories = [call_from(n) for n in syntax_nodes(parse_declarations(source)['propertyGetters'])]
    factories = [c for c in factories if c and c.qualified_name == 'materialIcon']
    if len(factories) != 1:
        raise ValueError('expected exactly one Material icon factory')
    factory = factories[0]
    # materialIcon defaults to a 24dp / 24-unit viewport in this API.
    if any(a.get('name') not in (None, 'name', 'autoMirror') for a in factory.arguments):
        raise ValueError('unsupported Material icon factory argument')
    bodies = [a['value'] for a in factory.arguments if a['value']['kind'] == 'lambda']
    root = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg', 'width': '24', 'height': '24', 'viewBox': '0 0 24 24'})
    for statement in bodies[0]['body']['statements']:
        path = call_from(statement)
        if path is None or path.qualified_name != 'materialPath':
            raise ValueError('unsupported Material vector body')
        attributes = {'fill': '#000000', 'fill-rule': 'nonzero'}
        path_bodies = []
        for argument in path.arguments:
            if argument['value']['kind'] == 'lambda':
                path_bodies.append(argument['value'])
            elif argument.get('name') in ('fillAlpha', 'strokeAlpha'):
                alpha = evaluate_expression(argument['value']['text'], {})
                if type(alpha) not in (int, float) or not 0 <= alpha <= 1:
                    raise ValueError('unknown vector alpha')
                attributes['fill-opacity' if argument['name'] == 'fillAlpha' else 'stroke-opacity'] = str(alpha)
            else:
                raise ValueError('unsupported Material path argument')
        if len(path_bodies) != 1:
            raise ValueError('missing Material path body')
        commands = []
        for statement in path_bodies[0]['body']['statements']:
            call = call_from(statement)
            if call is None or call.name not in COMMANDS:
                raise ValueError('unsupported vector path command')
            command, count = COMMANDS[call.name]
            values = [evaluate_expression(a['value']['text'], {}) for a in call.arguments]
            if command in ('A', 'a'):
                if len(values) != 7 or any(type(values[i]) is not bool for i in (3, 4)):
                    raise ValueError('unresolved vector arc flags')
                values[3:5] = [int(v) for v in values[3:5]]
            if len(values) != count or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise ValueError('unresolved vector path coordinates')
            commands.append(command + ' '.join(format(v, 'g') for v in values))
        attributes['d'] = ' '.join(commands)
        ET.SubElement(root, 'path', attributes)
    if not len(root):
        raise ValueError('empty icon')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def materialize(jars, target, icons):
    output = target / 'entry/src/main/resources/base/media'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    with ExitStack() as stack:
        archives = [(jar, stack.enter_context(zipfile.ZipFile(jar))) for jar in jars]
        for expression in icons:
            identity = material_icon_identity(expression)
            if identity is None:
                raise ValueError('invalid Material icon identity')
            path, resource = identity
            matches = [(jar, archive, p) for jar, archive in archives for p in archive.namelist()
                       if p.endswith('/androidx/compose/material/icons/' + path)]
            if len(matches) != 1:
                raise ValueError('missing or ambiguous icon source: ' + path)
            jar, archive, source_path = matches[0]
            source = archive.read(source_path)
            svg = convert(source.decode('utf-8'))
            destination = output / (resource + '.svg')
            if destination.exists() and destination.read_bytes() != svg:
                raise ValueError('refusing to replace a different resource')
            destination.write_bytes(svg)
            records.append({'expression': expression, 'source': source_path, 'source_jar_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(), 'source_sha256': hashlib.sha256(source).hexdigest(),
                            'output': str(destination.relative_to(target)), 'sha256': hashlib.sha256(svg).hexdigest()})
    manifest = target / '.migration/compose-material-icons.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({'icons': records}, indent=2) + '\n')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-jar', type=Path, action='append', required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--icon', action='append', required=True)
    args = parser.parse_args()
    print(json.dumps(materialize(args.source_jar, args.target, args.icon), indent=2))
