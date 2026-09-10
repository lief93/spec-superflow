from __future__ import annotations
import copy
import re
from collections import defaultdict
from component_required_facts import build_required_facts, normalized_layout_rules, required_fact_gate
from generate_source_attribute_inventory import call_attributes
from pathlib import Path
from typing import Any
from ui_migration.frontend.bindings import bind_source_expression, bound_modifier_call
from ui_migration.frontend.definitions import component_definition, source_component_id, source_semantic_key
from ui_migration.frontend.model import MATERIAL3_TYPOGRAPHY, RealPageError, SOURCE_PAGE_SCHEMA
from ui_migration.frontend.relationships import source_layout_relationships
from ui_migration.frontend.resources import resource_values, runtime_asset_rules, safe_asset_indexes
from ui_migration.frontend.styles import static_style_for_call
from ui_migration.frontend.project_styles import build_style_definitions, validate_style_definitions
from ui_migration.frontend.function_inventory import source_functions
from ui_migration.frontend.ui_declarations import NATIVE_SLOTS
from ui_migration.frontend.source_symbols import SourceSymbolIndex
from ui_migration.frontend.source_symbols import function_identity
from ui_migration.semantics.syntax import call_from
from kotlin_psi import parse_expression, KotlinPsiSyntaxError


def build_source_page_spec(
    contract: dict[str, Any],
    root_source: str,
    root_composable: str,
    page_id: str,
    state_id: str,
    contract_sha256: str,
    source_root: Path | None = None,
    *,
    style_definitions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ui = contract.get("ui")
    semantic = ui.get("semantic_translation_candidates") if isinstance(ui, dict) else None
    graph = ui.get("custom_composable_call_graph") if isinstance(ui, dict) else None
    calls = semantic.get("calls") if isinstance(semantic, dict) else None
    closures = graph.get("transitive_closures") if isinstance(graph, dict) else None
    if not isinstance(calls, list) or not isinstance(closures, list):
        raise RealPageError("contract has no Compose semantic call graph")
    closure = next(
        (
            item
            for item in closures
            if isinstance(item, dict)
            and item.get("root") == {"source": root_source, "composable": root_composable}
        ),
        None,
    )
    if closure is None:
        raise RealPageError("exact root source/composable closure was not found")
    reached = closure.get("reached_definitions")
    if not isinstance(reached, list):
        raise RealPageError("selected closure has no reached definitions")
    reached_keys = {
        (item.get("source"), item.get("composable"))
        for item in reached
        if isinstance(item, dict)
    }
    dependency_index = SourceSymbolIndex.from_root(source_root, roots=[(root_source, root_composable)]) if source_root is not None else None
    from ui_migration.frontend.root_selection import select_root_declaration
    root_declaration = select_root_declaration(dependency_index, root_source, root_composable) if dependency_index else None
    functions = source_functions(source_root, dependency_index)
    from ui_migration.frontend.callable_inventory import lambda_functions
    raw_composables = ui.get('composables') or []
    callable_definitions = []
    dependency_trace = None
    dependency_gate = None
    if source_root is not None:
        dependency_trace = dependency_index.trace(root_source, root_composable)
        traced = {item['id'] for item in dependency_trace['definitions']}
        traced_sources = {item['source'] for item in dependency_trace['definitions']}
        for source in dependency_index.syntax:
            if source not in traced_sources:
                continue
            for function in lambda_functions(dependency_index, source, within=traced):
                if any(function_identity(f) in traced and f['start']<=function['start']<f['end']
                       for f in dependency_index.by_source[source]):
                    functions.append(function)
                    callable_definitions.append(function)
            for function in dependency_index.ui_functions(source):
                if function_identity(function) in traced:
                    callable_definitions.append(function)
        reached_keys.update((f['source'],f['name']) for f in callable_definitions)
        # Templates are inventoried, not treated as visible until a fixed-state call selects them.
        dependency_gate = dependency_index.reconcile_content(dependency_trace,
            [{'source':s,'composable':n} for s,n in reached_keys], calls)
    function_scopes = {(f['source'], f['name']): {
        '__source_file': f['source'], '__source_owner': f.get('owner'),
        '__source_imports': f.get('imports', {})} for f in functions}
    modifier_definitions = {(f['source'], f['name']) for f in functions
                            if f.get('receiver') == 'Modifier' and f.get('return_type') == 'Modifier'}
    non_ui_definitions = set(modifier_definitions)
    if dependency_index:
        declarations = defaultdict(list)
        for function in dependency_index.functions:
            declarations[(function['source'], function['name'])].append(function)
        non_ui_definitions.update(key for key, targets in declarations.items()
            if all(dependency_index.roles[function_identity(t)] in {'value', 'modifier'} for t in targets))
    non_ui_calls = []
    calls_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    selected_calls: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        key = (call.get("source"), call.get("composable"))
        if key not in reached_keys:
            continue
        targets = (call.get('custom_composable') or {}).get('definitions', [])
        if targets and all((t.get('source'), t.get('composable')) in non_ui_definitions for t in targets):
            non_ui_calls.append({'call_id': call['call_id'], 'source': call['source'], 'line': call['line'],
                                 'reason': 'PSI declaration produces a value/Modifier, not visual content'})
            continue
        calls_by_definition[key].append(call)
        selected_calls.append(call)
    for definition_calls in calls_by_definition.values():
        definition_calls.sort(key=lambda item: (int(item.get("line", 0)), item.get('source_order', 0)))
    values = resource_values(contract)
    raw_composables = ui.get("composables") if isinstance(ui, dict) else None
    parameters_by_definition = {
        (str(item["source"]), str(item["name"])): copy.deepcopy(item.get("parameters", []))
        for item in raw_composables or []
        if isinstance(item, dict)
        and isinstance(item.get("source"), str)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("parameters"), list)
    }
    parameters_by_declaration = {item['declaration_id']: copy.deepcopy(item.get('parameters', []))
                                for item in raw_composables or [] if item.get('declaration_id')}
    functions_by_declaration = {function_identity(f): f for f in functions}
    definitions = copy.deepcopy(validate_style_definitions(style_definitions)
                                if style_definitions is not None else build_style_definitions(contract))
    theme_inventory = definitions['sourceInventory']
    theme_tokens = theme_inventory.get("tokens") if isinstance(theme_inventory, dict) else None
    source_diagnostics = copy.deepcopy(definitions['diagnostics'])
    theme_text_styles = definitions['theme']['textStyles']
    theme_colors = definitions['theme']['colors']
    font_family_tokens = {
        str(token["name"])
        for token in theme_tokens or []
        if isinstance(token, dict)
        and token.get("kind") == "font_family"
        and isinstance(token.get("name"), str)
    }
    manifest_assets, scoped_assets = safe_asset_indexes(source_root, (source for source, _ in reached_keys))
    components: list[dict[str, Any]] = []
    component_definitions: dict[str, dict[str, Any]] = {}
    metadata_cache: dict[str, tuple[str | None, dict[str, str]]] = {}
    expansion_unresolved: list[dict[str, str]] = []
    for missing in (dependency_gate or {}).get('missing_content_definitions', []):
        expansion_unresolved.append({'path':'source_dependency_trace',
            'expression':missing['id'], 'reason':'reachable content definition missing from UI call closure'})
    for missing in (dependency_gate or {}).get('missing_native_controls', []):
        expansion_unresolved.append({'path':'source_dependency_gate',
            'expression':missing['source']+'#'+missing['function']+':'+missing['component'],
            'reason':f"native content calls missing: expected {missing['expected_count']}, inventoried {missing['inventoried_count']}"})
    semantic_key_counts: dict[str, int] = defaultdict(int)

    def expand_definition(
        definition: tuple[str, str],
        attach_parent: str | None,
        instance_path: str,
        stack: tuple[tuple[str, str], ...],
        parameter_bindings: dict[str, str],
        parameter_scopes: dict | None = None,
        declaration_id: str | None = None,
    ) -> dict[str, tuple[str, str | None]]:
        invocation_identity = (*definition, declaration_id)
        if invocation_identity in stack:
            expansion_unresolved.append(
                {"path": instance_path, "expression": f"{definition[0]}#{definition[1]}", "reason": "recursive composable cycle"}
            )
            return {}
        definition_calls = calls_by_definition.get(definition, [])
        if declaration_id:
            definition_calls = [call for call in definition_calls if call.get('declaration_id')==declaration_id]
        local_ids = {
            str(call["call_id"]): source_component_id(instance_path, str(call["call_id"]))
            for call in definition_calls
            if isinstance(call.get("call_id"), str)
        }
        created: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for call in definition_calls:
            custom = call.get('custom_composable')
            if dependency_index and custom and len(custom.get('definitions', [])) > 1:
                owner = functions_by_declaration.get(call.get('declaration_id'))
                arguments = ', '.join((a['name']+' = ' if a.get('name') else '')+a['expression']
                                      for a in custom.get('arguments', []))
                syntax_call = call_from(parse_expression(call['component']+'('+arguments+')'))
                targets = dependency_index.resolve(syntax_call, owner) if owner and syntax_call else []
                if len(targets)==1:
                    selected = targets[0]
                    call = {**call, 'custom_composable': {**custom, 'definitions': [{
                        'source':selected['source'], 'composable':selected['name'],
                        'declaration_id':function_identity(selected)}]}}
            if dependency_index is not None and not call.get('modifier_expression'):
                scope = next((f for f in dependency_index.by_source[definition[0]] if f['name']==definition[1]), None)
                candidates = []
                for argument in call.get('positional_arguments', []):
                    if not argument.get('expression', '').strip():
                        continue
                    try:
                        expression = call_from(parse_expression(argument['expression']))
                    except KotlinPsiSyntaxError as error:
                        expansion_unresolved.append({'path':call['call_id']+'.arguments',
                            'expression':argument['expression'], 'reason':str(error)})
                        continue
                    targets = dependency_index.resolve(expression, scope) if expression and scope else []
                    if targets and all(dependency_index.roles[function_identity(t)]=='modifier' for t in targets):
                        candidates.append(argument)
                if len(candidates)==1:
                    call = {**call, 'modifier_expression':candidates[0]['expression'],
                            'positional_arguments':[a for a in call['positional_arguments'] if a is not candidates[0]]}
            if call.get('modifier_expression') and not call.get('ordered_modifier_chain') and call['modifier_expression'].strip()!='Modifier':
                call = {**call, 'ordered_modifier_chain':[{'name':'sourceExpression',
                        'source_expression':call['modifier_expression'], 'arguments':''}]}
            call = bound_modifier_call(call, {**(call.get('file_values') or {}),
                **parameter_bindings, **(call.get('local_values') or {})})
            call_id = call.get("call_id")
            if not isinstance(call_id, str):
                continue
            raw_parent = call.get("parent_call_id")
            parent_id = local_ids.get(raw_parent) if isinstance(raw_parent, str) else attach_parent
            style, provenance, unresolved = static_style_for_call(
                call,
                values,
                source_root,
                {**(call.get('file_values') or {}), **parameter_bindings},
                font_family_tokens,
                theme_colors,
                scoped_assets.get(call.get('source'), manifest_assets),
                theme_text_styles,
            )
            custom = call.get("custom_composable")
            node_definition = component_definition(call, source_root, metadata_cache)
            if node_definition['component_kind'] == 'project_component':
                identity = node_definition['identity']
                key = (identity['source'], identity['symbol'])
                selected_id = identity.get('declaration_id')
                node_definition['parameters'] = copy.deepcopy(parameters_by_declaration.get(selected_id,
                    parameters_by_definition.get(key, [])))
                node_definition['ui_template'] = {
                    'stage': 'before-state-projection',
                    'calls': copy.deepcopy([c for c in calls_by_definition.get(key, [])
                                            if not selected_id or c.get('declaration_id')==selected_id]),
                }
            component_definitions.setdefault(node_definition["id"], node_definition)
            base_semantic_key = source_semantic_key(call)
            semantic_key_counts[base_semantic_key] += 1
            semantic_key = (
                base_semantic_key
                if semantic_key_counts[base_semantic_key] == 1
                else f"{base_semantic_key}__{semantic_key_counts[base_semantic_key]}"
            )
            component = {
                "id": local_ids[call_id],
                "type": str(call.get("component", "View")),
                "definition_id": node_definition["id"],
                "component_kind": node_definition["component_kind"],
                "semantic_key": semantic_key,
                "parent_id": parent_id,
                "children_ids": [],
                "sibling_index": 0,
                "source": {
                    "source": str(call.get("source", "")),
                    "composable": str(call.get("composable", "")),
                    "line": int(call.get("line", 0)),
                    "call_id": call_id,
                    "declaration_id": call.get('declaration_id'),
                    "attributes": call_attributes(call),
                    "custom_component": isinstance(custom, dict),
                    "trailing_lambda_parameters": copy.deepcopy(call.get('trailing_lambda_parameters') or []),
                },
                "arguments": {
                    "semantic": copy.deepcopy(call.get("semantic_arguments", {})),
                    "positional": copy.deepcopy(call.get("positional_arguments", [])),
                    "state_slots": copy.deepcopy(call.get("state_slots", [])),
                    "invocation": copy.deepcopy(custom.get("arguments", [])) if isinstance(custom, dict) else [],
                },
                "visibility_condition": copy.deepcopy(call.get("visibility_condition")),
                "ui_state_path": [
                    {**branch, "group_id": f"{instance_path}:{branch['group_id']}"}
                    for branch in copy.deepcopy(call.get("ui_state_path") or [])
                ],
                "list_item_context": copy.deepcopy(call.get("list_item_context")),
                "list_item_contexts": copy.deepcopy(call.get("list_item_contexts")),
                "local_values": copy.deepcopy(call.get("local_values", {})),
                "file_values": copy.deepcopy(call.get("file_values", {})),
                "modifiers": copy.deepcopy(call.get("ordered_modifier_chain", [])),
                "custom_draw_commands": [
                    {
                        "kind": str(command.get("kind")),
                        "arguments": {
                            str(name): re.sub(
                                r"MaterialTheme\.colorScheme\.([A-Za-z_][A-Za-z0-9_]*)",
                                lambda match: (theme_colors or {}).get(
                                    match.group(1), match.group(0)
                                ),
                                bind_source_expression(str(expression), parameter_bindings),
                            )
                            for name, expression in (command.get("arguments") or {}).items()
                        },
                    }
                    for command in call.get("custom_draw_commands") or []
                    if isinstance(command, dict)
                ],
                "slot_argument_name": (
                    str(call["slot_argument_name"])
                    if isinstance(call.get("slot_argument_name"), str)
                    else None
                ),
                "slot_invocation": (
                    copy.deepcopy(call["slot_invocation"])
                    if isinstance(call.get("slot_invocation"), dict)
                    else None
                ),
                "style": style,
                "provenance": provenance,
                "unresolved": unresolved,
                "parameter_bindings": copy.deepcopy(parameter_bindings),
                "parameter_scopes": copy.deepcopy(parameter_scopes or {}),
                "_parameter_bindings": copy.deepcopy(parameter_bindings),
            }
            component["layout_rules"] = normalized_layout_rules(component)
            if call.get('callable_definition_only'):
                component['source']['callable_definition_only'] = True
            if call.get('decoration_kind'):
                component['source']['decoration_kind'] = call['decoration_kind']
            components.append(component)
            created.append((component, call))
        slot_ids: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for component, call in created:
            custom = call.get("custom_composable")
            definitions = custom.get("definitions") if isinstance(custom, dict) else None
            if not isinstance(definitions, list) or len(definitions) != 1 or not isinstance(definitions[0], dict):
                continue
            target = (definitions[0].get("source"), definitions[0].get("composable"))
            if not all(isinstance(item, str) for item in target) or target not in reached_keys:
                continue
            target_declaration = definitions[0].get('declaration_id')
            parameters = parameters_by_declaration.get(target_declaration, parameters_by_definition.get(
                (str(target[0]), str(target[1])), []))
            # Defaults belong to the callee; explicit arguments belong to the caller.
            child_bindings = {
                str(parameter["name"]): str(parameter["default"])
                for parameter in parameters
                if isinstance(parameter, dict)
                and isinstance(parameter.get("name"), str)
                and isinstance(parameter.get("default"), str)
            }
            caller_bindings = {**parameter_bindings, **(call.get('local_values') or {})}
            child_scopes = {name: function_scopes.get((str(target[0]), str(target[1])), {})
                            for name in child_bindings}
            default_arguments = set(child_bindings)
            invocation_names = {}
            for argument_index, argument in enumerate(custom.get("arguments", [])):
                if not isinstance(argument, dict) or not isinstance(argument.get("expression"), str):
                    continue
                argument_name = argument.get("name")
                if not isinstance(argument_name, str):
                    if argument_index < len(parameters):
                        candidate_name = parameters[argument_index].get("name")
                        argument_name = candidate_name if isinstance(candidate_name, str) else None
                if isinstance(argument_name, str):
                    default_arguments.discard(argument_name)
                    argument_expression = str(argument['expression']).strip()
                    from .source_names import direct_reference_name
                    caller_name = direct_reference_name(argument_expression)
                    if caller_name:
                        invocation_names[argument_name] = caller_name
                    child_scopes[argument_name] = (parameter_scopes or {}).get(
                        argument_expression, function_scopes.get(definition, {}))
                    child_bindings[argument_name] = bind_source_expression(
                        str(argument["expression"]), caller_bindings
                    )
            slot_hosts = expand_definition(
                (str(target[0]), str(target[1])),
                component["id"],
                f"{instance_path}/{call['call_id']}",
                stack + (invocation_identity,),
                child_bindings,
                child_scopes,
                target_declaration,
            )
            component['invocation_bindings'] = copy.deepcopy(child_bindings)
            component['source']['invocation_scopes'] = copy.deepcopy(child_scopes)
            component['source']['invocation_defaults'] = sorted(default_arguments)
            if invocation_names:
                component['source']['invocation_names'] = invocation_names
            # Carry a forwarded slot's actual destination back through each business component.
            for argument in custom.get('arguments', []):
                destination = slot_hosts.get(argument.get('name'))
                expression = argument.get('expression', '').strip()
                if destination is not None and any(p.get('name') == expression and '@Composable' in str(p.get('type'))
                        for p in parameters_by_definition.get(definition, [])):
                    slot_ids[expression].append(destination)
            for child_component, child_call in created:
                if child_call.get("parent_call_id") != call.get("call_id"):
                    continue
                slot_name = child_call.get("slot_argument_name")
                if isinstance(slot_name, str):
                    component['source'].setdefault('caller_slot_roots', {}).setdefault(slot_name, []).append(child_component['id'])
                slot_host = slot_hosts.get(slot_name) if isinstance(slot_name, str) else None
                if slot_host is not None:
                    host_id, native_slot = slot_host
                    child_component["parent_id"] = host_id
                    if native_slot is not None:
                        child_component['slot_argument_name'] = native_slot
                    host = next(item for item in components if item['id'] == host_id)
                    if host.get('slot_invocation'):
                        expression = child_bindings.get(slot_name)
                        syntax = parse_expression(expression) if expression else {}
                        if syntax.get('kind') == 'lambda':
                            host['slot_invocation']['parameters'] = syntax.get('parameters') or ['it']
                        elif parameters and slot_name == parameters[-1].get('name'):
                            host['slot_invocation']['parameters'] = copy.deepcopy(call.get('trailing_lambda_parameters') or ['it'])
                elif isinstance(slot_name, str):
                    if slot_name in child_bindings:
                        child_component['source']['callable_definition_only'] = True
                        continue
                    expansion_unresolved.append({
                        "path": child_component["id"],
                        "expression": slot_name,
                        "reason": "custom component slot invocation was not uniquely resolved",
                    })

        for component, call in created:
            invocation = call.get("slot_invocation")
            slot_name = invocation.get("name") if isinstance(invocation, dict) else None
            if isinstance(slot_name, str):
                slot_ids[slot_name].append((component["id"], None))
            if not call.get('custom_composable') and call.get('component') in NATIVE_SLOTS:
                arguments = call.get('native_slot_arguments', {
                    name: argument.get('expression') for name, argument in (call.get('semantic_arguments') or {}).items()
                    if name in NATIVE_SLOTS[call['component']] and isinstance(argument, dict)})
                for argument_name, expression in arguments.items():
                    if isinstance(expression, str) and re.fullmatch(r'[A-Za-z_]\w*', expression.strip()):
                        if any(p.get('name') == expression.strip() and '@Composable' in str(p.get('type'))
                               for p in parameters_by_definition.get((str(call['source']), str(call['composable'])), [])):
                            slot_ids[expression.strip()].append((component['id'], argument_name))
        return {
            name: ids[0]
            for name, ids in slot_ids.items()
            if len(ids) == 1
        }

    root_parameters = root_declaration['parameters'] if root_declaration else parameters_by_definition.get((root_source, root_composable), [])
    root_defaults = {p['name']: p['default']
                     for p in root_parameters
                     if isinstance(p.get('default'), str)}
    root_id = function_identity(root_declaration) if root_declaration else None
    expand_definition((root_source, root_composable), None, "root", (), root_defaults, declaration_id=root_id)
    active_count = len(components)
    callable_templates = []
    for function in callable_definitions:
        if (function['source'],function['name']) == (root_source,root_composable):
            continue
        start = len(components)
        expand_definition((function['source'],function['name']), None,
                          'callable/'+function_identity(function), (), {}, declaration_id=function_identity(function))
        callable_templates.append({'source':function['source'],'name':function['name'],
            'expression':function.get('callable_expression'),
            'parameters':function.get('parameters', []),
            'component_ids':[n['id'] for n in components[start:]]})
    by_id = {item["id"]: item for item in components}
    children: dict[str | None, list[str]] = defaultdict(list)
    for component in components:
        children[component["parent_id"]].append(component["id"])
    for parent_id, child_ids in children.items():
        for index, child_id in enumerate(child_ids):
            by_id[child_id]["sibling_index"] = index
        if parent_id is not None and parent_id in by_id:
            by_id[parent_id]["children_ids"] = child_ids
    layout_relationships = source_layout_relationships(components)
    for component in components:
        component.pop("_parameter_bindings", None)
    for component in components:
        if component["type"] not in {"Text", "BasicText", "ClickableText"}:
            continue
        typography = component["style"]["typography"]
        if typography["font_size_sp"] is not None:
            continue
        parent = by_id.get(component["parent_id"] or "")
        token = "labelLarge" if parent is not None and parent["type"] in {"Button", "IconButton"} else "bodyLarge"
        unknown_theme = theme_text_styles.get(token, {}).get('unresolved_reason')
        if unknown_theme:
            for field, property_name in (('font_size_sp', 'fontSize'), ('line_height_sp', 'lineHeight'),
                                         ('font_weight', 'fontWeight')):
                if typography.get(field) is None:
                    component['unresolved'].append({'path': 'style.typography.' + field,
                        'expression': f'MaterialTheme.typography.{token}.{property_name}', 'reason': unknown_theme})
            continue
        font_size, line_height, font_weight = MATERIAL3_TYPOGRAPHY[token]
        from ui_migration.frontend.model import material3_text_metrics
        if not theme_text_styles.get(token):
            typography.update(material3_text_metrics(token))
        typography.update(
            {"font_size_sp": font_size, "line_height_sp": line_height, "font_weight": font_weight}
        )
        component["provenance"].append(
            {
                "paths": [
                    "style.typography.font_size_sp",
                    "style.typography.line_height_sp",
                    "style.typography.font_weight",
                ],
                "origin": "source_resolved",
                "source": f"Material3 {token} default selected from source component context",
            }
        )
    for component in components:
        component["required_facts"] = build_required_facts(component)
    selected_call_ids = {
        str(call["call_id"])
        for call in selected_calls
        if isinstance(call.get("call_id"), str)
    }
    emitted_call_ids = {
        str(component["source"]["call_id"])
        for component in components
        if isinstance(component.get("source"), dict)
        and isinstance(component["source"].get("call_id"), str)
    }
    from ui_migration.frontend.route_roots import find_page_host
    page_host = find_page_host(dependency_index, root_source, root_composable, root_id) if dependency_index else None
    return {
        "schema": SOURCE_PAGE_SCHEMA,
        "status": "candidate_requires_runtime_verification",
        "authoritative": False,
        "page": {"id": page_id, "state": state_id},
        "root": {"source": root_source, "composable": root_composable},
        **({'root_declaration_id': root_id} if root_id else {}),
        **({'page_host': page_host} if page_host else {}),
        "contract_sha256": contract_sha256,
        "style_definitions": definitions,
        "source_tokens": copy.deepcopy(theme_tokens or []),
        "source_string_resources": {f'R.string.{name}': text for (kind, name), text in sorted(values.items())
                                    if kind == 'string'},
        "source_text_styles": copy.deepcopy(theme_text_styles),
        "source_shape_sets": copy.deepcopy((theme_inventory or {}).get('shape_sets', [])),
        "source_theme_applications": copy.deepcopy((theme_inventory or {}).get('theme_applications', [])),
        "source_diagnostics": source_diagnostics,
        "source_extended_color_sets": copy.deepcopy((theme_inventory or {}).get('extended_color_sets', [])),
        "source_color_accessors": copy.deepcopy((theme_inventory or {}).get('color_accessors', [])),
        "source_value_inventory": {
            **copy.deepcopy(ui.get('kotlin_data_class_inventory') or {}),
            'classes': [*copy.deepcopy((ui.get('kotlin_data_class_inventory') or {}).get('classes', [])),
                *[record for syntax in (dependency_index.syntax.values() if dependency_index else [])
                  for record in syntax.get('recordClasses', [])
                  if record['name'] not in {c['name'] for c in (ui.get('kotlin_data_class_inventory') or {}).get('classes', [])}]]},
        "source_enum_inventory": copy.deepcopy(ui.get('kotlin_enum_inventory') or {}),
        "source_functions": functions,
        "source_properties": dependency_index.properties if dependency_index is not None else [],
        "source_dependency_trace": dependency_trace,
        "source_dependency_gate": dependency_gate,
        "non_ui_calls": non_ui_calls,
        "source_color_schemes": copy.deepcopy(
            theme_inventory.get("color_schemes", [])
            if isinstance(theme_inventory, dict)
            else []
        ),
        "scoped_source_assets": scoped_assets,
        "source_assets": [
            {
                "resource": resource,
                **{
                    key: value
                    for key, value in evidence.items()
                    if key in {"path", "sha256", "width_dp", "height_dp"}
                },
            }
            for resource, evidence in sorted(manifest_assets.items())
        ],
        "component_definitions": sorted(
            component_definitions.values(), key=lambda item: item["id"]
        ),
        "layout_relationships": layout_relationships,
        "runtime_asset_rules": runtime_asset_rules(source_root, values),
        "components": components[:active_count],
        "source_callable_templates": callable_templates,
        "source_callable_components": components[active_count:],
        "required_fact_gate": required_fact_gate(components[:active_count]),
        "coverage": {
            "source_call_count": len(selected_call_ids),
            "emitted_call_count": len(emitted_call_ids),
            "emitted_call_ratio": round(len(emitted_call_ids) / len(selected_call_ids), 6) if selected_call_ids else 1.0,
            "expanded_instance_count": active_count,
            "callable_template_instance_count": len(components)-active_count,
        },
        "unresolved": expansion_unresolved,
        "limitations": [
            "All calls in the selected closure are retained; runtime state decides which conditional branches are visible.",
            "Source expressions are retained verbatim. A null style value is not guessed from pixels.",
            "Runtime bounds, rendered colors, and rendered typography must come from a bound runtime capture.",
        ],
    }
