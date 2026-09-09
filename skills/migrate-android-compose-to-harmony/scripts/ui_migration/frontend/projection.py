"""Project selected PSI facts through source framework adapters, never target code."""
from dataclasses import dataclass
from kotlin_psi import KotlinPsiSyntaxError, parse_expression
from pathlib import Path
from typing import Mapping, Protocol
from ui_migration.semantics.expressions import LAYOUT_ARGUMENT_FIELDS, LayoutDimension, LayoutExpressionError
from ui_migration.frontend.values import value_resolver
from ui_migration.frontend.bindings import bind_source_expression
from ui_migration.semantics.syntax import call_from


class ModifierSerializer(Protocol):
    def __call__(self, selected_operation: str) -> list[dict]: ...


class StaticStyleResolver(Protocol):
    def __call__(self, call: dict, values: dict, source_root: Path | None,
                 parameter_bindings: dict, *, font_family_tokens: set[str] | None = None
                 ) -> tuple[dict, list[dict], list[dict]]: ...


@dataclass(frozen=True)
class SourceStyleAdapters:
    serialize_modifier: ModifierSerializer
    resolve_style: StaticStyleResolver
    typography_defaults: Mapping[str, tuple[float, float, int]]


def selected_modifiers(modifiers, resolver):
    output, failures, names = [], [], set()
    def collect(node):
        if node.get('kind') == 'call' and node.get('callee', {}).get('kind') == 'name':
            names.add(node['callee']['name'])
        for value in node.values():
            if isinstance(value, dict):
                collect(value)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, dict):
                        collect(child)
    for modifier in modifiers:
        operation = modifier.get('syntax_expression')
        expression = modifier.get('source_expression') or (
            'Modifier.' + operation if operation else f"Modifier.{modifier['name']}({modifier.get('arguments') or ''})")
        try:
            tree = parse_expression(expression)
            collect(tree)
            operations = resolver.chain(tree)
            names.update(m['name'] for m in operations)
            output.extend(operations)
        except (LayoutExpressionError, KotlinPsiSyntaxError) as error:
            output.append({'name': 'unresolvedExpression', 'arguments': expression})
            failures.append({'path': 'source.modifiers.unresolvedexpression', 'expression': expression, 'reason': str(error)})
    return output, failures, names


class SourceStyleProjector:
    def __init__(self, adapters: SourceStyleAdapters):
        self.adapters = adapters

    def project(self, node, values, theme_styles, font_families):
        bindings = {**(node.get('file_values') or {}), **(node.get('parameter_bindings') or {}),
                    **(node.get('local_values') or {})}
        resolver = value_resolver(bindings, values, self.adapters.serialize_modifier)
        self.project_modifier_styles(node, resolver)
        self.project_text_styles(node, resolver, theme_styles, font_families)
        self.project_control_arguments(node, resolver)
        self.project_surface_arguments(node, resolver)

    def project_surface_arguments(self, node, resolver):
        if node['type'] not in {'Card', 'Button', 'TextButton', 'OutlinedButton'}:
            return
        semantic = (node.get('arguments') or {}).get('semantic') or {}
        argument = semantic.get('colors') or {}
        expression = argument.get('expression')
        if not isinstance(expression, str):
            return
        try:
            colors = resolver.value(parse_expression(expression))
        except (LayoutExpressionError, KotlinPsiSyntaxError):
            return
        if not isinstance(colors, dict) or colors.get('kind') != 'material_colors':
            return
        node['source']['resolved_material_colors'] = {'expression': expression, 'values': colors['values']}
        enabled = node['style']['state'].get('enabled')
        if type(enabled) is not bool:
            return
        resolved = []
        for key, group, field in [('ContainerColor', 'surface', 'background'), ('ContentColor', 'typography', 'color')]:
            value = colors['values'].get(key[0].lower() + key[1:] if enabled else 'disabled' + key)
            if not isinstance(value, str):
                continue
            node['style'][group][field] = {'type': 'solid', 'color': value} if field == 'background' else value
            resolved.append('style.' + group + '.' + field)
        if resolved:
            node['unresolved'] = [u for u in node.get('unresolved', []) if u.get('path') not in resolved]
            node.setdefault('provenance', []).append({'paths': resolved, 'origin': 'source_resolved',
                'source': ' '.join(expression.split())})

    def project_control_arguments(self, node, resolver):
        from page_native_controls import CONTROL_TYPES, arguments_for, parse_argument
        if node['type'] not in CONTROL_TYPES:
            return
        semantic = (node.get('arguments') or {}).get('semantic') or {}
        for name in arguments_for(node['type']):
            argument = semantic.get(name)
            if not isinstance(argument, dict) or not isinstance(argument.get('expression'), str):
                continue
            expression = argument['expression']
            try:
                selected = resolver.render(parse_expression(expression))
            except (LayoutExpressionError, KotlinPsiSyntaxError):
                continue
            fields = parse_argument(name, selected)
            if fields is None:
                continue
            argument.update(expression=selected, original_expression=expression)
            node['style']['control'].update(fields)
            path = 'source.arguments.' + name.lower()
            node['unresolved'] = [u for u in node.get('unresolved', []) if u.get('path') != path]
            node.setdefault('provenance', []).append({
                'paths': ['style.control.' + field for field in fields],
                'origin': 'source_resolved', 'source': expression})

    def project_modifier_styles(self, node, resolver):
        modifiers = node.get('modifiers') or []
        chain, failures, names = selected_modifiers(modifiers, resolver)
        semantic = (node.get('arguments') or {}).get('semantic') or {}
        selected_arguments = {}
        for name, field in LAYOUT_ARGUMENT_FIELDS.items():
            argument = semantic.get(name)
            if not isinstance(argument, dict) or not isinstance(argument.get('expression'), str):
                continue
            expression = argument['expression']
            try:
                resolved = resolver.render(parse_expression(expression))
                argument.update(expression=resolved, original_expression=expression)
                selected_arguments[name] = argument
            except (LayoutExpressionError, KotlinPsiSyntaxError) as error:
                failures.append({'path': 'style.layout.' + field, 'expression': expression, 'reason': str(error)})
        call = {'component': node['type'], 'ordered_modifier_chain': chain,
                'semantic_arguments': selected_arguments,
                'source': node.get('source', {}).get('source', ''), 'line': node.get('source', {}).get('line', 0)}
        style, _, errors = self.adapters.resolve_style(call, {}, None, {})
        fields = {
            'padding': [('layout', 'padding_dp')], 'absolutePadding': [('layout', 'padding_dp')],
            'width': [('layout', 'width_dp')], 'height': [('layout', 'height_dp')],
            'size': [('layout', 'width_dp'), ('layout', 'height_dp')],
            'aspectRatio': [('layout', 'aspect_ratio')],
            'background': [('surface', 'background')], 'alpha': [('surface', 'alpha')],
            'clip': [('surface', 'clip'), ('surface', 'corner_radius_dp'), ('surface', 'corner_sizes')],
            'border': [('surface', 'border'), ('surface', 'corner_radius_dp'), ('surface', 'corner_sizes')],
            'shadow': [('surface', 'shadows')],
            'rotate': [('transform', 'rotation_degrees')],
            'scale': [('transform', 'scale_x'), ('transform', 'scale_y')],
            'offset': [('transform', 'translation_x_dp'), ('transform', 'translation_y_dp')],
        }
        updated = {field for name in names for field in fields.get(name, [])}
        updated.update(('layout', field) for name, field in LAYOUT_ARGUMENT_FIELDS.items() if name in semantic)
        for group, key in updated:
            node['style'][group][key] = style[group][key]
        paths = {'style.' + '.'.join(field) for field in updated}
        node['unresolved'] = [item for item in node.get('unresolved', []) if item.get('path') not in paths]
        node['unresolved'].extend([e for e in errors if e.get('path') in paths or str(e.get('path', '')).startswith('source.modifiers.')] + failures)
        node['modifiers'] = chain
        node['modifier_projection'] = {'parser': 'kotlin-psi-1.9.22', 'input': modifiers, 'failures': failures}


    def project_text_styles(self, node, resolver, theme_styles, font_families):
        if node['type'] not in {'Text', 'BasicText', 'ClickableText', 'TextField', 'BasicTextField', 'OutlinedTextField'}:
            return
        fields = {'fontSize': 'font_size_sp', 'fontWeight': 'font_weight', 'fontStyle': 'font_style',
                  'fontFamily': 'font_family', 'letterSpacing': 'letter_spacing_sp', 'lineHeight': 'line_height_sp',
                  'textAlign': 'text_align', 'color': 'color', 'textDecoration': 'decoration',
                  'baselineShift': 'baseline_shift'}

        uses_theme_style = False
        def properties(tree, seen=()):
            nonlocal uses_theme_style
            try:
                resolved = resolver.value(tree, seen)
                if isinstance(resolved, dict) and resolved.get('kind') == 'text_style':
                    return {name: parse_expression(expression) for name, expression in resolved['properties'].items()}
            except LayoutExpressionError:
                pass
            if tree['kind'] == 'name':
                bound, path = resolver.bound(tree['name'], seen)
                return properties(bound, path)
            if tree['kind'] in ('if', 'when'):
                return properties(resolver.branch(tree, seen), seen)
            if tree['kind'] == 'block' and len(tree['statements']) == 1:
                return properties(tree['statements'][0], seen)
            role = tree.get('text', '').removeprefix('MaterialTheme.typography.')
            if tree.get('text') == 'MaterialTheme.typography.' + role:
                uses_theme_style = True
                expression = theme_styles.get(role, {}).get('expression')
                if not expression and role in self.adapters.typography_defaults and not theme_styles.get(role, {}).get('unresolved_reason'):
                    size, height, weight = self.adapters.typography_defaults[role]
                    expression = f'TextStyle(fontSize = {size}.sp, lineHeight = {height}.sp, fontWeight = FontWeight({weight}))'
                if expression:
                    return properties(parse_expression(expression), seen)
            base = {}
            if tree['kind'] == 'qualified' and tree['selector']['kind'] == 'call' and tree['selector']['callee'].get('name') == 'copy':
                try:
                    base = properties(tree['receiver'], seen)
                except LayoutExpressionError as error:
                    node.setdefault('unresolved', []).append({'path': 'source.arguments.style.base',
                        'expression': tree['receiver'].get('text'), 'reason': str(error)})
                call = tree['selector']
            elif tree['kind'] == 'call' and tree['callee'].get('name') == 'TextStyle':
                call = tree
            else:
                invocation = call_from(tree)
                functions = [function for function in resolver.values.get('__source_functions', [])
                             if invocation and function['name'] == invocation.name
                             and function.get('receiver') == 'TextStyle']
                if len(functions) == 1 and invocation.receiver is not None:
                    function = functions[0]
                    identity = 'style:' + function['source'] + ':' + str(function['line'])
                    if identity in seen:
                        raise LayoutExpressionError('recursive TextStyle extension')
                    bindings = {**resolver.bindings, 'this': invocation.receiver['text']}
                    for index, parameter in enumerate(function['parameters']):
                        argument = invocation.argument(parameter['name'], index)
                        expression = argument['text'] if argument else parameter.get('default')
                        if expression is None:
                            raise LayoutExpressionError('missing TextStyle extension argument: ' + parameter['name'])
                        bindings[parameter['name']] = bind_source_expression(expression, resolver.bindings)
                    expanded = bind_source_expression(function['body']['text'], bindings)
                    return properties(parse_expression(expanded), seen + (identity,))
                raise LayoutExpressionError('unsupported text style expression: ' + tree.get('text', ''))
            for argument in call['arguments']:
                if not argument.get('name'):
                    raise LayoutExpressionError('text style positional overload is unresolved')
                base[argument['name']] = argument['value']
            return base

        semantic = (node.get('arguments') or {}).get('semantic') or {}
        selected = {}
        style_arg = semantic.get('style') or semantic.get('textStyle')
        if style_arg is None and node['type'] in {'TextField', 'OutlinedTextField'}:
            style_arg = {'expression': 'MaterialTheme.typography.bodyLarge'}
        if isinstance(style_arg, dict) and isinstance(style_arg.get('expression'), str):
            node['unresolved'] = [e for e in node.get('unresolved', [])
                                  if not str(e.get('path', '')).startswith('source.arguments.style')]
            try:
                selected = properties(parse_expression(style_arg['expression']))
                # An explicitly supplied TextStyle replaces LocalTextStyle, it does not
                # implicitly inherit Material bodyLarge. Resolve unspecified span defaults.
                for name, field, default in [('fontSize', 'font_size_sp', 14),
                                              ('lineHeight', 'line_height_sp', None),
                                              ('letterSpacing', 'letter_spacing_sp', 0),
                                              ('fontWeight', 'font_weight', 400)]:
                    if not uses_theme_style and name not in selected and name not in semantic:
                        node['style']['typography'][field] = default
            except (LayoutExpressionError, KotlinPsiSyntaxError) as error:
                node.setdefault('unresolved', []).append({'path': 'source.arguments.style',
                    'expression': style_arg['expression'], 'reason': str(error)})
        # Explicit Text arguments win over the selected TextStyle properties.
        for name in fields:
            argument = semantic.get(name)
            if isinstance(argument, dict) and isinstance(argument.get('expression'), str):
                selected[name] = parse_expression(argument['expression'])
        for name, tree in selected.items():
            path = 'style.typography.' + fields[name] if name in fields else 'source.arguments.style.' + name
            try:
                if name == 'textIndent':
                    invocation = call_from(tree)
                    if invocation is None or invocation.name != 'TextIndent':
                        raise LayoutExpressionError('text indent requires the source TextIndent value')
                    first = invocation.argument('firstLine', 0)
                    rest = invocation.argument('restLine', 1)
                    first = resolver.value(first) if first else LayoutDimension(0, 'sp')
                    rest = resolver.value(rest) if rest else LayoutDimension(0, 'sp')
                    scale = resolver.values.get('LocalDensity.current', {}).get('fontScale')
                    if not (isinstance(first, LayoutDimension) and first.unit == 'sp'
                            and isinstance(rest, LayoutDimension) and rest.value == 0
                            and type(scale) in (int, float)):
                        raise LayoutExpressionError('only fixed first-line indent with known font scale is supported')
                    node['source']['first_line_indent_dp'] = first.value * scale
                    node['unresolved'] = [e for e in node.get('unresolved', []) if e.get('path') != path]
                    continue
                if name in {'platformStyle', 'lineHeightStyle', 'lineBreak'}:
                    from ui_migration.frontend.text_metrics import text_metric_properties
                    metrics = text_metric_properties(name, tree, resolver)
                    node['style']['typography'].update(metrics)
                    node.setdefault('provenance', []).append({'paths': ['style.typography.' + key for key in metrics],
                        'origin': 'source_resolved', 'source': tree['text']})
                    continue
                if name == 'baselineShift':
                    invocation = call_from(tree)
                    if invocation is None or invocation.qualified_name != 'BaselineShift' or len(invocation.arguments) != 1:
                        raise LayoutExpressionError('baseline shift requires a known multiplier')
                    value = resolver.value(invocation.arguments[0]['value'])
                    if type(value) not in (int, float):
                        raise LayoutExpressionError('baseline shift multiplier is unresolved')
                    node['style']['typography']['baseline_shift'] = value
                    node['unresolved'] = [e for e in node.get('unresolved', []) if e.get('path') != path]
                    continue
                rendered = resolver.render(tree)
                if name == 'color':
                    value = resolver.value(tree)
                    if isinstance(value, str) and len(value) == 9 and value.startswith('#'):
                        rendered = 'Color(0x' + value[1:] + ')'
                elif name in {'fontSize', 'lineHeight', 'letterSpacing'}:
                    value = resolver.value(tree)
                    if isinstance(value, LayoutDimension) and value.unit == 'sp':
                        rendered = f'{value.value:g}.sp'
                    elif type(value) in (int, float):
                        rendered = f'{value:g}.sp'
                if name not in fields:
                    raise LayoutExpressionError('unsupported TextStyle property: ' + name)
                call = {'component': node['type'], 'semantic_arguments': {name: {'expression': rendered}},
                        'source': node.get('source', {}).get('source', ''), 'line': node.get('source', {}).get('line', 0)}
                projected, _, _ = self.adapters.resolve_style(call, {}, None, {}, font_family_tokens=font_families)
                result = projected['typography'][fields[name]]
                if result is None:
                    raise LayoutExpressionError('unresolved selected TextStyle property')
                node['style']['typography'][fields[name]] = result
                node['unresolved'] = [e for e in node.get('unresolved', []) if e.get('path') != path]
                node.setdefault('provenance', []).append({'paths': [path], 'origin': 'source_resolved',
                                                         'source': tree['text']})
            except (LayoutExpressionError, KotlinPsiSyntaxError) as error:
                if name in fields:
                    node['style']['typography'][fields[name]] = None
                node.setdefault('unresolved', []).append({'path': path, 'expression': tree['text'], 'reason': str(error)})
