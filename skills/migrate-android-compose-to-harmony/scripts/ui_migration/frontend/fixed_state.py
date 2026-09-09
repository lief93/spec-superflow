from __future__ import annotations
import copy
import re
from collections import defaultdict
from component_required_facts import build_required_facts, is_preview_only_placeholder_expression, normalized_layout_rules, required_fact_gate
from typing import Any
from ui_migration.frontend.lanhu_export import source_assets
from ui_migration.frontend.image_projection import project_image
from page_native_controls import CONTROL_TYPES
from ui_migration.frontend.page_model import TEXT_TYPES, UNRESOLVED, call_arguments, clean_number, component_dimensions, nested_modifier_arguments, semantic_expression, split_top_level, style_group
from ui_migration.frontend.shapes import shape_surface
from ui_migration.frontend.material_items import project_material_item, material_content_color, material_text_defaults


from ui_migration.frontend.values import evaluate_expression

# Compatibility names retain the one structured evaluator, not independent parsers.
evaluate_value_leaf = evaluate_expression
evaluate_static_call = evaluate_expression

def stroke_width(expression: str, environment: dict[str, Any]) -> float | None:
    match = re.fullmatch(r"Stroke\s*\(\s*(.+?)\s*\)", expression.strip())
    if match is None:
        return None
    width_expression = re.sub(r"\.toPx\(\)\s*$", "", match.group(1).strip())
    resolved = evaluate_expression(width_expression, environment)
    if isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved > 0:
        return float(resolved)
    return None


def project_progress_ring(
    component: dict[str, Any], environment: dict[str, Any]
) -> bool:
    commands = component.get("custom_draw_commands")
    if not isinstance(commands, list) or len(commands) != 2:
        return False
    resolved: list[dict[str, Any]] = []
    for command in commands:
        arguments = command.get("arguments") if isinstance(command, dict) else None
        if (
            not isinstance(command, dict)
            or command.get("kind") != "arc"
            or not isinstance(arguments, dict)
        ):
            return False
        required = {"color", "startAngle", "sweepAngle", "useCenter", "style"}
        if not required.issubset(arguments):
            return False
        color = evaluate_expression(str(arguments["color"]), environment)
        start = evaluate_expression(str(arguments["startAngle"]), environment)
        sweep = evaluate_expression(str(arguments["sweepAngle"]), environment)
        use_center = evaluate_expression(str(arguments["useCenter"]), environment)
        width = stroke_width(str(arguments["style"]), environment)
        if (
            not isinstance(color, str)
            or re.fullmatch(r"#[0-9A-F]{8}", color) is None
            or not isinstance(start, (int, float))
            or not isinstance(sweep, (int, float))
            or use_center is not False
            or width is None
        ):
            return False
        resolved.append(
            {
                "color": color,
                "start": float(start),
                "sweep": float(sweep),
                "width": width,
            }
        )
    track, active = resolved
    if (
        abs(track["sweep"] - 360.0) > 0.001
        or abs(track["start"] - active["start"]) > 0.001
        or abs(track["width"] - active["width"]) > 0.001
        or active["sweep"] < 0
        or active["sweep"] > 360
    ):
        return False
    value = round(active["sweep"] / 3.6)
    component["type"] = "ProgressRing"
    style_group(component, "content")["text"] = f"{value}%"
    component["custom_draw"] = {
        "kind": "ring_progress",
        "value": value,
        "total": 100,
        "start_angle_degrees": clean_number(track["start"]),
        "stroke_width_dp": clean_number(track["width"]),
        "track_color": track["color"],
        "active_color": active["color"],
    }
    component["unresolved"] = [
        item
        for item in component.get("unresolved") or []
        if not isinstance(item, dict) or item.get("path") != "style.custom_draw"
    ]
    return True


def set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def resolve_input_decoration(node: dict[str, Any], environment: dict[str, Any]) -> None:
    source = node.get('source') or {}
    if source.get('decoration_kind') != 'material3-outlined':
        return
    expression = semantic_expression(node, 'supportingText').strip()
    if not expression or expression == 'null':
        present = False
    elif expression.startswith('{') and expression.endswith('}'):
        # A non-null composable lambda reserves space even when its body emits nothing.
        present = True
    else:
        value = evaluate_expression(expression, environment)
        present = False if value is None else None
    source['input_decoration'] = {
        'kind': 'material3-outlined', 'text_min_height_dp': 24,
        'supporting_text': present, 'supporting_min_height_dp': 16,
        'supporting_padding_dp': dict(left=16, right=16, top=4, bottom=0),
    }
    if present is None:
        node.setdefault('unresolved', []).append({
            'path': 'source.input_decoration.supporting_text', 'expression': expression,
            'reason': 'supporting slot nullability is unresolved; no empty-slot assumption',
        })


def project_source_page(
    payload: dict[str, Any], fixture: dict[str, Any], *, allow_unresolved: bool = False, api_registry=None
) -> tuple[dict[str, Any], dict[str, Any]]:
    from analyze_compose_project import ordered_modifier_chain
    from ui_migration.frontend.model import MATERIAL3_TYPOGRAPHY
    from ui_migration.frontend.styles import static_style_for_call
    from ui_migration.frontend.projection import SourceStyleAdapters, SourceStyleProjector

    styles = SourceStyleProjector(SourceStyleAdapters(
        ordered_modifier_chain, static_style_for_call, MATERIAL3_TYPOGRAPHY,
    ))
    from ui_migration.frontend.component_defaults import ComponentStyleDefaults
    component_defaults = ComponentStyleDefaults(payload.get('style_definitions') or {})
    from ui_migration.frontend.style_tokens import StyleTokenProjector
    style_tokens = StyleTokenProjector(payload.get('style_definitions') or {})
    from ui_migration.frontend.component_reuse import ComponentReuse
    component_reuse = ComponentReuse(getattr(api_registry, 'component_adapters', ()),
                                     payload.get('component_definitions', []))
    from ui_migration.frontend.component_interfaces import project_interface
    if fixture.get("schema") != "android-to-harmony.page-state-fixture.v1":
        raise ValueError(f"unsupported state fixture schema: {fixture.get('schema')!r}")
    if fixture.get("page") != payload.get("page"):
        raise ValueError("state fixture page/state must match source page")
    if allow_unresolved:
        from ui_migration.frontend.source_tree import SourceTree
        SourceTree(payload, allow_multiple_roots=True)
    preview = None
    if fixture.get('ui_preview') is not None:
        from ui_migration.frontend.preview import PreviewPolicy
        preview = PreviewPolicy(payload, fixture['ui_preview'])
    original = {
        component["id"]: component
        for component in payload.get("components") or []
        if isinstance(component, dict) and isinstance(component.get("id"), str)
    }
    children: dict[str, list[str]] = defaultdict(list)
    root_ids: list[str] = []
    for component in original.values():
        parent_id = component.get("parent_id")
        if isinstance(parent_id, str):
            children[parent_id].append(component["id"])
        else:
            root_ids.append(component["id"])
    for child_ids in children.values():
        child_ids.sort(key=lambda item: original[item].get("sibling_index", 0))
    root_ids.sort(key=lambda item: original[item].get("sibling_index", 0))
    for component in payload.get('source_callable_components', []):
        original[component['id']] = component
        if component.get('parent_id'):
            children[component['parent_id']].append(component['id'])

    token_values = defaultdict(set)
    for token in payload.get('source_tokens') or []:
        if token.get('kind') == 'color' and token.get('name') and token.get('argb_hex'):
            token_values[token['name']].add(token['argb_hex'])
    base_environment = {name: next(iter(colors)) for name, colors in token_values.items() if len(colors) == 1}
    from ui_migration.frontend.theme import page_theme_colors
    from generate_harmony_theme_resources import color_from_semantics
    base_environment.update({'MaterialTheme.colorScheme.' + name: color for name, color in
        page_theme_colors(payload).items()})
    for accessor in payload.get('source_color_accessors', []):
        candidates = [s for s in payload.get('source_extended_color_sets', [])
                      if s.get('constructor') == accessor['type'] and s.get('variant') == 'light']
        if len(candidates) == 1:
            for name, semantics in candidates[0].get('roles', {}).items():
                color = color_from_semantics(semantics)
                if color:
                    base_environment[accessor['expression'] + '.' + name] = color
    base_environment.update(payload.get('source_string_resources') or {})
    for enum in payload.get('source_enum_inventory', {}).get('classes', []):
        for entry in enum['values']:
            key = enum['name'] + '.' + entry
            base_environment[key] = key
    base_environment.update(fixture.get("values") or {})
    base_environment.update(fixture.get("symbols") or {})
    if api_registry is not None:
        base_environment['__api_registry'] = api_registry
    base_environment['__source_value_inventory'] = payload.get('source_value_inventory') or {}
    base_environment['__source_functions'] = payload.get('source_functions') or []
    base_environment['__source_properties'] = payload.get('source_properties') or []
    root_function = next((function for function in base_environment['__source_functions']
                          if function.get('source') == payload.get('root', {}).get('source')
                          and function.get('name') == payload.get('root', {}).get('composable')), None)
    if root_function:
        base_environment.update(__source_file=root_function['source'],
                                __source_owner=root_function.get('owner'),
                                __source_imports=root_function.get('imports', {}))
    base_environment['__source_tokens'] = payload.get('source_tokens') or []
    from ui_migration.frontend.theme import resolve_theme_environment
    theme_values, resolved_theme_styles = resolve_theme_environment(payload, base_environment)
    for name, value in theme_values.items():
        base_environment.setdefault(name, value)
    ambient_bindings = fixture.get('source_bindings') or {}
    if not isinstance(ambient_bindings, dict) or not all(isinstance(value, str) for value in ambient_bindings.values()):
        raise ValueError('source_bindings must map names to bounded source expressions')
    for name, expression in ambient_bindings.items():
        base_environment[name] = evaluate_expression(expression, base_environment, preserve_units=True)
    source_assets = {
        item["resource"]: item
        for item in payload.get("source_assets") or []
        if isinstance(item, dict) and isinstance(item.get("resource"), str)
    }
    for name in source_assets:
        base_environment['R.drawable.' + name] = name
        base_environment['R.mipmap.' + name] = name
    emitted: list[dict[str, Any]] = []
    inactive: list[str] = []
    expanded_count = 0
    deferred = []
    functions_by_source = {function['source']: function for function in payload.get('source_functions', [])}
    functions_by_identity = {(function['source'], function['name']): function
                             for function in payload.get('source_functions', [])}
    for parameter in (root_function or {}).get('parameters', []):
        parameter_type = parameter.get('type') or ''
        if '->' in parameter_type and not parameter_type.endswith('?'):
            base_environment.setdefault(parameter['name'], {'kind': 'function_reference',
                                                           'expression': parameter['name']})

    def inactive_subtree(component_id: str) -> None:
        inactive.append(component_id)
        for child_id in children.get(component_id, []):
            inactive_subtree(child_id)

    def resolve_environment(node: dict[str, Any], environment: dict[str, Any]) -> dict[str, Any]:
        local = dict(environment)
        parent = original.get(node.get('parent_id'), {})
        color = material_content_color(parent, node.get('slot_argument_name') or node.get('source', {}).get('slot_argument_name'), environment) if parent else None
        if color is not None:
            local['LocalContentColor.current'] = color
        defaults = material_text_defaults(parent, node.get('slot_argument_name') or node.get('source', {}).get('slot_argument_name'))
        if defaults:
            local['__material_text_defaults'] = defaults
        source_file = node.get('source', {}).get('source')
        from ui_migration.frontend.source_symbols import function_identity
        declaration = node.get('source', {}).get('declaration_id')
        function = next((f for f in payload.get('source_functions', [])
                         if declaration and function_identity(f)==declaration), None)
        if function is None:
            function = functions_by_identity.get((source_file, node.get('source', {}).get('composable')), {})
        local.update(__source_file=source_file,
                     __source_owner=function.get('owner'),
                     __source_imports=functions_by_source.get(source_file, {}).get('imports', {}))
        pending_file = {**function.get('global_values', {}), **(node.get('file_values') or {})}
        for _ in range(len(pending_file) + 1):
            progressed = False
            for name, expression in list(pending_file.items()):
                if name in function.get('global_values', {}) and payload.get('source_properties'):
                    local[name] = UNRESOLVED
                    resolved = evaluate_expression(name, local, preserve_units=True)
                else:
                    resolved = evaluate_expression(str(expression), local, preserve_units=True)
                local[name] = resolved
                if resolved is not UNRESOLVED:
                    del pending_file[name]
                    progressed = True
            if not progressed:
                break
        for name, expression in (node.get("parameter_bindings") or {}).items():
            if (source_file == payload.get('root', {}).get('source')
                    and node.get('source', {}).get('composable') == payload.get('root', {}).get('composable')
                    and name in (fixture.get('values') or {})):
                local[name] = fixture['values'][name]
                continue
            scope = (node.get('parameter_scopes') or {}).get(name, {})
            resolved = evaluate_expression(str(expression), {**local, **scope}, preserve_units=True)
            local[str(name)] = resolved
            if resolved is not UNRESOLVED:
                local[str(expression)] = resolved
        pending = dict(node.get("local_values") or {})
        if node.get('source', {}).get('composable') == payload.get('root', {}).get('composable'):
            supplied_values = fixture.get('values') or {}
            for name in set(pending) & supplied_values.keys():
                if name not in (node.get('parameter_bindings') or {}):
                    local[name] = supplied_values[name]
                    del pending[name]
        for _ in range(len(pending) + 1):
            progressed = False
            for name, expression in list(pending.items()):
                resolved = evaluate_expression(str(expression), local, preserve_units=True)
                if resolved is UNRESOLVED:
                    local[str(name)] = UNRESOLVED
                    continue
                local[str(name)] = resolved
                del pending[name]
                progressed = True
            if not progressed:
                break
        return local

    def visibility_value(node: dict[str, Any], environment: dict[str, Any]) -> Any:
        condition = node.get("visibility_condition")
        expression = condition.get("expression") if isinstance(condition, dict) else None
        result = evaluate_expression(expression, environment) if isinstance(expression, str) else True
        if result is True and node.get('type') == 'AnimatedVisibility':
            argument = ((node.get('arguments') or {}).get('semantic') or {}).get('visible', {})
            expression = argument.get('expression')
            return evaluate_expression(expression, environment) if isinstance(expression, str) else UNRESOLVED
        return result

    def resolve_node(node: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(node)
        styles.project(result, local,
                            resolved_theme_styles,
                            {t['name'] for t in payload.get('source_tokens', []) if t.get('kind') == 'font_family'} |
                            {f['family'] for f in payload.get('runtime_font_faces', [])})
        direction = local.get('LocalLayoutDirection.current')
        if result['style']['layout'].get('layout_direction') is None and direction in ('ltr', 'rtl'):
            result['style']['layout']['layout_direction'] = direction
        project_progress_ring(result, local)
        padding_expressions = [semantic_expression(node, 'contentPadding')]
        padding_expressions.extend(m.get('arguments') for m in node.get('modifiers', [])
                                   if m.get('name') == 'padding')
        for expression in padding_expressions:
            if not expression:
                continue
            padding = evaluate_expression(expression, local, preserve_units=True)
            if isinstance(padding, dict) and '__scaffold_padding_owner' in padding:
                result['source']['scaffold_padding'] = {
                    'owner_id': padding['__scaffold_padding_owner'],
                    'edges': {'top': 'topBar', 'bottom': 'bottomBar'}}
                if result['style']['layout'].get('padding_dp') is None:
                    result['style']['layout']['padding_dp'] = dict.fromkeys(('left', 'right', 'top', 'bottom'), 0)
                result['unresolved'] = [u for u in result.get('unresolved', [])
                                        if u.get('path') != 'style.layout.padding_dp']
        unresolved = []
        for item in result.get("unresolved") or []:
            if not isinstance(item, dict):
                unresolved.append(item)
                continue
            expression = str(item.get("expression") or "")
            path = item.get("path")
            expression_parts = split_top_level(expression, ",")
            value_expression = (
                expression_parts[0]
                if path == "style.surface.background" and expression_parts
                else expression
            )
            resolved = evaluate_expression(value_expression, local)
            if path == 'style.surface.border' and isinstance(resolved, dict) and resolved.get('kind') == 'border_stroke':
                resolved = {k: v for k, v in resolved.items() if k != 'kind'}
            if path == 'style.asset.resource' and (not isinstance(resolved, str) or not resolved.strip()):
                resolved = UNRESOLVED
            if path in {'style.surface.clip', 'style.surface.corner_radius_dp'} and isinstance(resolved, dict):
                shape = shape_surface(resolved, style_group(result, 'layout').get('layout_direction'), component_dimensions(result))
                if shape is not None:
                    style_group(result, 'surface').update(shape)
                    if path == 'style.surface.clip':
                        style_group(result, 'surface')['clip'] = True
                    continue
                resolved = UNRESOLVED
            if resolved is UNRESOLVED or not isinstance(item.get("path"), str):
                unresolved.append(item)
            else:
                if path == 'style.content.text' and isinstance(resolved, dict) and resolved.get('kind') == 'annotated_string':
                    result['source']['text_spans'] = resolved['span_styles']
                    if resolved['span_styles']:
                        unresolved.append({'path': 'source.text_spans', 'expression': expression,
                                           'reason': 'inline range styling requires target Span rendering'})
                    resolved = resolved['text']
                projected_value = (
                    {"type": "solid", "color": resolved}
                    if path == "style.surface.background"
                    and isinstance(resolved, str)
                    and re.fullmatch(r"#[0-9A-Fa-f]{8}", resolved)
                    else resolved
                )
                set_path(result, item["path"], projected_value)
                if path == 'style.surface.background' and len(expression_parts) == 2:
                    shape = shape_surface(evaluate_expression(expression_parts[1], local),
                                          style_group(result, 'layout').get('layout_direction'), component_dimensions(result))
                    if shape is not None:
                        style_group(result, 'surface').update(shape)
        result["unresolved"] = [
            item
            for item in unresolved
            if not (
                item.get("path") == "style.content.placeholder"
                and is_preview_only_placeholder_expression(item.get("expression"))
            )
        ]
        surface = style_group(result, "surface")
        for arguments in nested_modifier_arguments(result, "background"):
            positional, named = call_arguments(arguments)
            applied = False
            color_expression = named.get("color") or (positional[0] if positional else None)
            if surface.get("background") is None and isinstance(color_expression, str):
                color_value = evaluate_expression(color_expression, local)
                if (
                    isinstance(color_value, str)
                    and re.fullmatch(r"#[0-9A-Fa-f]{8}", color_value)
                ):
                    surface["background"] = {"type": "solid", "color": color_value}
                    applied = True
            shape_expression = named.get("shape") or (
                positional[1] if len(positional) > 1 else None
            )
            shape_value = (
                evaluate_expression(shape_expression, local)
                if isinstance(shape_expression, str)
                else None
            )
            if surface.get('corner_radius_dp') is None and surface.get('corner_sizes') is None:
                shape = shape_surface(shape_value, style_group(result, 'layout').get('layout_direction'), component_dimensions(result))
                if shape is not None:
                    surface.update(shape)
                    applied = True
            if applied:
                break
        content = style_group(result, "content")
        if result.get("type") in TEXT_TYPES:
            semantic = (result.get("arguments") or {}).get("semantic") or {}
            candidates = [semantic.get("text")]
            candidates.extend((result.get("arguments") or {}).get("positional") or [])
            for candidate in candidates:
                expression = candidate.get("expression") if isinstance(candidate, dict) else None
                if not isinstance(expression, str):
                    continue
                resolved = evaluate_expression(expression, local)
                if isinstance(resolved, dict) and resolved.get('kind') == 'annotated_string':
                    result['source']['text_spans'] = resolved['span_styles']
                    resolved = resolved['text']
                if resolved is not UNRESOLVED:
                    if isinstance(resolved, (str, int, float, bool)):
                        result["style"]["content"]["text"] = str(resolved)
                    break
        typography = style_group(result, "typography")
        semantic = (result.get("arguments") or {}).get("semantic") or {}
        if result['type'] in TEXT_TYPES and not semantic.get('style'):
            names = {'font_size_sp': 'fontSize', 'line_height_sp': 'lineHeight', 'font_weight': 'fontWeight', 'letter_spacing_sp': 'letterSpacing'}
            for field, value in local.get('__material_text_defaults', {}).items():
                if names[field] not in semantic:
                    typography[field] = value
        if result['type'] in TEXT_TYPES and typography.get('font_family') is None:
            family = local.get('LocalTextStyle.current.fontFamily')
            if isinstance(family, str) and not semantic.get('fontFamily'):
                typography['font_family'] = family
        color_argument = semantic.get('contentColor' if result['type'] == 'Surface' else 'color')
        if result['type'] in CONTROL_TYPES:
            color_argument = None
        color_expression = (
            color_argument.get("resolved_local_expression")
            or color_argument.get("expression")
            if isinstance(color_argument, dict)
            else None
        )
        if isinstance(color_expression, str):
            resolved_color = evaluate_expression(color_expression, local)
            if (
                isinstance(resolved_color, str)
                and re.fullmatch(r"#[0-9A-Fa-f]{8}", resolved_color)
            ):
                typography["color"] = resolved_color.upper()
        elif result['type'] in TEXT_TYPES and typography.get('color') is None:
            ambient = local.get('LocalContentColor.current')
            if isinstance(ambient, str) and re.fullmatch(r'#[0-9A-Fa-f]{8}', ambient):
                typography['color'] = ambient.upper()
        project_image(result, local, {**source_assets, **payload.get('scoped_source_assets', {}).get(
            node.get('source', {}).get('source'), {})})
        project_material_item(result, local, [original[c].get('slot_argument_name') or
            original[c].get('source', {}).get('slot_argument_name') for c in children.get(node['id'], [])])
        from ui_migration.frontend.material_defaults import project_material_defaults
        project_material_defaults(result, local, [original[c] for c in children.get(node['id'], [])])
        component_defaults.apply(result, local)
        style_tokens.apply(node, result, local)
        result["layout_rules"] = normalized_layout_rules(result)
        resolve_input_decoration(result, local)
        for modifier in result.get('modifiers', []):
            if modifier.get('name') == 'alignBy':
                expression = modifier.get('arguments', '').strip()
                baseline = {'kind': 'first_baseline'} if expression == 'FirstBaseline' else None
                if baseline is None:
                    value = evaluate_expression(expression, local)
                    density = local.get('LocalDensity.current', {}).get('density')
                    if type(value) in (int, float) and type(density) in (int, float) and density > 0:
                        baseline = {'kind': 'offset', 'offset_dp': value / density}
                if baseline:
                    result['source']['baseline_alignment'] = baseline
                    result['unresolved'] = [u for u in result.get('unresolved', []) if u.get('path') != 'source.modifiers.alignby']
        result["required_facts"] = build_required_facts(result)
        return result

    def emit_deferred(component_id, parent_id, environment, suffix, selection):
        source = original[component_id]
        local = resolve_environment(source, environment)
        node = resolve_node(source, local)
        node.update(id=component_id + suffix, source_component_id=component_id,
                    parent_id=parent_id, children_ids=[], sibling_index=0)
        node.setdefault('source', {})['state_resolution'] = copy.deepcopy(selection)
        node['unresolved'].append({'path': 'source.state_resolution', 'expression': selection['expression'],
            'reason': 'state selection is unresolved; source template retained, not selected for rendering'})
        emitted.append(node)
        deferred.append(node['id'])
        for child_id in children.get(component_id, []):
            emit_deferred(child_id, node['id'], local, suffix, selection)
        return node['id']

    def emit_single(
        component_id: str,
        parent_id: str | None,
        environment: dict[str, Any],
        suffix: str,
    ) -> str | None:
        source = original[component_id]
        local = resolve_environment(source, environment)
        if source.get('source', {}).get('callable_definition_only'):
            inactive_subtree(component_id)
            return None
        visible = visibility_value(source, local)
        if visible is False:
            inactive_subtree(component_id)
            return None
        if visible is not True:
            expression = (source.get("visibility_condition") or {}).get("expression")
            if source.get('type') == 'AnimatedVisibility' and not expression:
                expression = semantic_expression(source, 'visible')
            if allow_unresolved:
                return emit_deferred(component_id, parent_id, environment, suffix,
                    {'status': 'unresolved', 'kind': 'condition', 'expression': expression or 'visible',
                     'owner_id': component_id + suffix})
            raise ValueError(
                f"state condition requires a resolved boolean for {component_id}: {expression}"
            )
        reuse_error = None
        try:
            def reuse_argument(name, expression, arguments):
                metadata = source.get('source') or {}
                scoped = {**local, **metadata.get('invocation_scopes', {}).get(name, {})}
                if name in metadata.get('invocation_defaults', []):
                    scoped.update(arguments)
                return evaluate_expression(expression, scoped, preserve_units=True)
            reuse = component_reuse.resolve(source, reuse_argument)
        except ValueError as error:
            reuse, reuse_error = None, str(error)
        if reuse is not None:
            node = copy.deepcopy(source)
            node['source']['component_reuse'] = reuse
            # The selected target library owns the internals; do not replay its
            # Android implementation or infer target sizes from that implementation.
            node['style'], node['modifiers'], node['unresolved'] = {}, [], []
            node['required_facts'] = build_required_facts(node)
        else:
            node = resolve_node(source, local)
            definition = component_reuse.definitions.get(source.get('definition_id'), {})
            if definition.get('component_kind') == 'project_component':
                node['source']['component_interface'] = project_interface(source, definition, reuse_argument)
            if reuse_error:
                node['unresolved'].append({'path': 'source.component_reuse',
                    'expression': source.get('type'), 'reason': reuse_error})
        if preview is not None and reuse is None:
            preview.content(node, suffix)
            node['required_facts'] = build_required_facts(node)
        new_id = component_id + suffix
        node["id"] = new_id
        if suffix and isinstance(node.get("semantic_key"), str):
            match = re.fullmatch(r"(.+?)(?:__(\d+))?", node["semantic_key"])
            base_key = match.group(1) if match else node["semantic_key"]
            static_instance = match.group(2) if match else None
            instance_parts = [
                part
                for part in (static_instance, suffix.lstrip("_").replace("__", "-"))
                if part
            ]
            node["semantic_key"] = (
                f"{base_key}__instance_{'-'.join(instance_parts)}"
            )
        node["source_component_id"] = component_id
        node["parent_id"] = parent_id
        node["children_ids"] = []
        node["sibling_index"] = 0
        emitted.append(node)
        if reuse is not None:
            for name, roots in reuse['slots'].items():
                reuse['slots'][name] = emit_children(roots, new_id, local, suffix)
                for child_id in reuse['slots'][name]:
                    child = next(item for item in emitted if item['id'] == child_id)
                    child.pop('slot_argument_name', None)
                    child.get('source', {}).pop('slot_argument_name', None)
            return new_id
        consumed_insets = dict(local.get('__consumed_window_insets', {}))
        for modifier in node.get('modifiers', []):
            for edge, value in modifier.get('consumed_insets_dp', {}).items():
                consumed_insets[edge] = max(consumed_insets.get(edge, 0), value)
        if consumed_insets:
            local = {**local, '__consumed_window_insets': consumed_insets}
        if source['type'] == 'AnimatedContent':
            expression = semantic_expression(source, 'targetState')
            parameters = (source.get('source') or {}).get('trailing_lambda_parameters') or ['it']
            local = dict(local)
            local[parameters[0]] = evaluate_expression(expression, local)
        if source['type'] == 'Scaffold':
            parameters = (source.get('source') or {}).get('trailing_lambda_parameters') or ['it']
            local = {**local, parameters[0]: {'__scaffold_padding_owner': new_id}}
        from ui_migration.frontend.pager import PAGER_TYPES, project_pager
        if source['type'] in PAGER_TYPES:
            pager = project_pager(node, local)
            node['required_facts'] = build_required_facts(node)
            if pager is None:
                for child in children.get(component_id, []):
                    emit_deferred(child, new_id, local, suffix, {'status': 'unresolved',
                        'kind': 'pager', 'expression': semantic_expression(source, 'state'), 'owner_id': new_id})
                return new_id
            parameters = source.get('source', {}).get('trailing_lambda_parameters') or ['it']
            for page in range(pager['page_count']):
                roots = emit_children(children.get(component_id, []), new_id,
                    {**local, parameters[0]: page}, suffix + '__page' + str(page))
                pager['pages'].append(roots)
            return new_id
        invocation = source.get('slot_invocation') or {}
        if invocation and (invocation.get('expression') or not children.get(component_id)):
            from ui_migration.frontend.callable_expansion import select_template
            selected, slot_environment, error = select_template(payload, invocation, local)
            if selected is not None:
                stack = environment.get('__callable_stack', ())
                key = (selected['source'], selected['name'])
                if key not in stack and len(stack)<32:
                    slot_environment['__callable_stack'] = (*stack, key)
                    roots = [i for i in selected['component_ids'] if not original[i].get('parent_id')]
                    emit_children(roots, new_id, slot_environment, suffix+'__slot'+str(len(emitted)))
                    return new_id
                error = 'recursive or over-deep content invocation'
            node['unresolved'].append({'path':'source.callable',
                'expression':invocation.get('expression',invocation['name']), 'reason':error})
            return new_id
        if invocation.get('parameters'):
            arguments = [evaluate_expression(expression, local, preserve_units=True)
                         for expression in invocation.get('arguments', [])]
            local = {**local, **dict(zip(invocation['parameters'], arguments))}
        emit_children(children.get(component_id, []), new_id, local, suffix)
        return new_id

    def pending_context(source, environment):
        contexts = source.get('list_item_contexts') or ([source['list_item_context']]
                    if source.get('list_item_context') else [])
        return next((context for context in contexts
                     if context not in environment.get('__active_list_contexts', [])), None)

    def emit_children(component_ids, parent_id, environment, suffix):
        """Expand a lexical iteration around all sibling statements, not each leaf."""
        nonlocal expanded_count
        ids = []
        cursor = 0
        while cursor < len(component_ids):
            component_id = component_ids[cursor]
            source = original[component_id]
            context = pending_context(source, environment)
            if context is None:
                node_id = emit_single(component_id, parent_id, environment, suffix)
                if node_id is not None:
                    ids.append(node_id)
                cursor += 1
                continue
            end = cursor + 1
            while end < len(component_ids) and pending_context(original[component_ids[end]], environment) == context:
                end += 1
            group = component_ids[cursor:end]
            cursor = end
            local = resolve_environment(source, environment)
            if visibility_value(source, local) is False:
                for node_id in group:
                    inactive_subtree(node_id)
                continue
            collection_expression = context['collection']
            collection = evaluate_expression(collection_expression, local)
            if preview is not None and not allow_unresolved:
                collection = preview.collection(source, collection, UNRESOLVED)
            if isinstance(collection, dict):
                collection = [{'key': key, 'value': value} for key, value in collection.items()]
            if not isinstance(collection, list):
                if allow_unresolved:
                    ids.extend(emit_deferred(node_id, parent_id, environment, suffix,
                        {'status': 'unresolved', 'kind': 'collection', 'expression': collection_expression,
                         'owner_id': component_id + suffix}) for node_id in group)
                    continue
                raise ValueError(
                    f"state collection requires a resolved list for {component_id}: {collection_expression}"
                )
            if not collection:
                for node_id in group:
                    inactive_subtree(node_id)
            for index, item in enumerate(collection, start=1):
                item_environment = dict(local)
                item_environment['__active_list_contexts'] = [*environment.get('__active_list_contexts', []), context]
                parameter = context['item_parameter']
                if isinstance(parameter, list):
                    from ui_migration.frontend.source_values import SourceRecord
                    values = (list(item.values()) if isinstance(item, SourceRecord) else
                              [item['key'], item['value']] if isinstance(item, dict) and set(item) == {'key', 'value'} else item)
                    for position, name in enumerate(parameter):
                        item_environment[name] = (values[position] if isinstance(values, (list, tuple))
                                                  and position < len(values) else UNRESOLVED)
                else:
                    item_environment[parameter] = item
                if context.get('index_parameter'):
                    item_environment[context['index_parameter']] = index - 1
                item_suffix = f"{suffix}__item{index}"
                ids.extend(emit_children(group, parent_id, item_environment, item_suffix))
                expanded_count += 1
        return ids

    # Source siblings can belong to different states. Select the state before
    # requiring the single, layout-owned tree consumed by the renderer.
    active_roots = []
    for root_id in root_ids:
        if preview is not None and root_id != preview.root_id:
            inactive_subtree(root_id)
            continue
        active_roots.extend(emit_children([root_id], None, base_environment, ""))
    if not active_roots:
        raise ValueError("selected page state has no active root")
    if len(active_roots) != 1:
        raise ValueError(
            "selected page state has multiple active roots; an explicit source parent layout "
            f"is required: {', '.join(active_roots)}"
        )
    emitted_by_id = {component["id"]: component for component in emitted}
    emitted_children: dict[str, list[str]] = defaultdict(list)
    for component in emitted:
        parent_id = component.get("parent_id")
        if isinstance(parent_id, str):
            emitted_children[parent_id].append(component["id"])
    for parent_id, child_ids in emitted_children.items():
        emitted_by_id[parent_id]["children_ids"] = child_ids
        for index, child_id in enumerate(child_ids):
            emitted_by_id[child_id]["sibling_index"] = index
    projected = copy.deepcopy(payload)
    projected["components"] = emitted
    inactive_only = set(original) - {node["source_component_id"] for node in emitted}
    projected["layout_relationships"] = [
        relationship for relationship in payload.get("layout_relationships") or []
        if relationship.get("container_id") not in inactive_only
    ]
    projected["required_fact_gate"] = required_fact_gate(emitted)
    projected["state_projection"] = {
        "fixture_schema": fixture["schema"],
        "source_component_count": len(original),
        "active_component_count": len(emitted),
        "active_root_id": active_roots[0],
        "inactive_source_ids": sorted(set(inactive)),
        "expanded_list_instances": expanded_count,
        "deferred_component_ids": deferred,
        "selection_complete": not deferred,
        "api_extensions": list(api_registry.identities) if api_registry is not None else [],
    }
    if preview is not None:
        projected['state_projection']['ui_preview'] = preview.report()
    return projected, projected["state_projection"]
