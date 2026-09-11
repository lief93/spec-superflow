"""Source-file output planning from page definitions, without reopening Android."""
import json
import hashlib
from pathlib import Path, PurePosixPath
import subprocess

from ui_migration.arkts_sdk import parser_runtime
from ui_migration.contracts.identity import require_safe_relative_source
from ui_migration.target_access import checked_path, check_manifest_outputs
from ui_migration.arkui.project import validate_previous
from ui_migration.common import ArkUIPageError
from ui_migration.naming import source_identifier


def source_file(source):
    source = require_safe_relative_source(source)
    path = PurePosixPath(source)
    if path.suffix not in ('.kt', '.kts') or path.parts[0] == '_migration':
        raise ArkUIPageError('unsupported source module path: ' + source)
    return path.with_suffix('.ets').name


def page_file(root, output, target, manifest):
    candidate = output / source_file(root['source'])
    if manifest.is_file():
        previous = json.loads(manifest.read_text(encoding='utf-8'))
        entries = [target / path for path, record in previous.get('outputs', {}).items()
                   if record.get('root_component')]
        if len(entries) == 1 and entries[0].is_relative_to(output):
            candidate = output / entries[0].name
    return candidate


def render_modules(code, root, business, output, page):
    owners, mapping, preferred_names = {}, [], {}
    destinations = {page.relative_to(output).as_posix().casefold():root['source']}
    for definition in business.definitions.values():
        reached = [b['name'] for b in business.builders.values() if b['definition_id'] == definition['id']]
        entry = business.interfaces.entries.get(definition['id']) or business.ui_states.entries.get(definition['id'])
        if entry:
            reached.append(entry['name'])
        elif len(reached) == 1:
            preferred_names[reached[0]] = source_identifier(definition['type'])
        if not reached:
            continue
        source = (definition.get('identity') or {}).get('source')
        if not source:
            raise ArkUIPageError('component source identity missing; regenerate version JSON: ' + definition['type'])
        relative = page.relative_to(output).as_posix() if source == root['source'] else source_file(source)
        previous = destinations.setdefault(relative.casefold(), source)
        if previous != source:
            raise ArkUIPageError('source files map to the same ETS output: ' + previous + ', ' + source)
        owners.update({name:relative for name in reached})
        mapping.append({'definition_id':definition['id'], 'source':source,
                        'symbol':definition['type'], 'output':relative, 'methods':reached})
    node, compiler = parser_runtime()
    script = Path(__file__).resolve().parents[2] / 'arkts_source_modules.cjs'
    result = subprocess.run([node, str(script), compiler], input=json.dumps({
        'code':code, 'page':page.relative_to(output).as_posix(), 'owners':owners,
        'preferred_names':preferred_names,
        'preferred_imports':{alias:source_identifier(symbol) for alias, symbol in business.preferred_imports.items()},
        'local_slot_builders':[b['name'] for b in business.builders.values() if b['direct_slot']],
        'facades': {entry['name']:entry['variants'][0]['invocation'].name
                    for entry in business.interfaces.entries.values() if len(entry['variants']) == 1},
    }), capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ArkUIPageError('source module generation failed: ' + result.stderr[-2000:])
    result = json.loads(result.stdout)
    for item in mapping:
        item['methods'] = list(dict.fromkeys(result['method_names'][name] for name in item['methods']))
    files, case_paths = {}, {}
    for relative, content in result['files'].items():
        destination = checked_path(output, output / relative)
        folded = relative.casefold()
        if folded in case_paths:
            raise ArkUIPageError('case-insensitive source module collision: ' + relative)
        case_paths[folded] = relative
        files[destination] = content.encode('utf-8')
    return files, {'representation':'source-file-builders', 'definitions':mapping,
                   'renamed_methods':{name:target for name,target in result['method_names'].items()
                                      if name != target and name not in result['inlined_methods']},
                   'inlined_methods':result['inlined_methods'],
                   'slot_lowerings':business.slot_lowerings,
                   'context_parameter':result['context_parameter'],
                   'shared_cross_page_modules':'identical-owned-modules-only',
                   'scope':'selected-page-ui; business callbacks and domain types are not synthesized'}


def validate_outputs(target, module, page, manifest, root, force, payloads):
    check_manifest_outputs(target, module, manifest)
    previous = json.loads(manifest.read_text(encoding='utf-8')).get('outputs', {}) if manifest.is_file() else {}
    old_entries = [target / path for path, entry in previous.items() if entry.get('root_component')]
    old_page = page
    if len(old_entries) == 1 and old_entries[0].name == page.name and old_entries[0].is_relative_to(page.parent):
        old_page = old_entries[0]
    validate_previous(target, old_page, manifest, root, module, force)
    shared = {}
    for other in manifest.parent.glob('*.json'):
        if other == manifest:
            continue
        if other.is_symlink():
            raise ArkUIPageError('generation manifest must not be a symbolic link')
        record = json.loads(other.read_text(encoding='utf-8'))
        if not isinstance(record, dict) or record.get('generator') != 'migrate-android-compose-to-harmony' or record.get('module') != module:
            continue
        check_manifest_outputs(target, module, other)
        for relative, entry in record['outputs'].items():
            shared.setdefault(target / relative, set()).add(entry.get('sha256'))
    for destination in payloads:
        checked_path(target / module / 'src/main', destination)
        if destination in shared:
            digest = hashlib.sha256(payloads[destination]).hexdigest()
            if shared[destination] != {digest} or not destination.is_file() or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise ArkUIPageError('shared generated module differs between pages; use an explicit reusable component: ' + str(destination))
            continue
        if destination.exists() and destination.relative_to(target).as_posix() not in previous:
            raise ArkUIPageError('refusing to replace an unowned generated output: ' + str(destination))
    # validate_previous verified every old hash before any output can be removed.
    return {target / path for path in previous if target / path not in payloads and target / path not in shared}


def prune_obsolete_directories(output, deletions):
    for deleted in deletions:
        directory = deleted.parent
        while directory != output and directory.is_relative_to(output):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent
