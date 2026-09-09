"""Preserve selected source references independently from their resolved values."""
import copy

from kotlin_psi import KotlinPsiSyntaxError, parse_expression
from ui_migration.semantics.syntax import qualified_name, call_from
from ui_migration.semantics.expressions import LayoutExpressionError
from ui_migration.contracts.style_tokens import validate_token_mappings, validate_property_token
from ui_migration.contracts.resource_values import is_resource_value, validate_resource_value
from .component_defaults import has_source_owner
from .values import value_resolver


TEXT_ARGUMENTS = {'fontSize': 'font_size_sp', 'color': 'color', 'fontWeight': 'font_weight',
                  'fontFamily': 'font_family', 'lineHeight': 'line_height_sp', 'letterSpacing': 'letter_spacing_sp'}


class StyleTokenProjector:
    def __init__(self, definitions):
        self.mappings = validate_token_mappings(definitions.get('tokenMappings', {}))
        self.defaults = definitions.get('componentDefaults', {})

    def apply(self, original, result, environment):
        bindings = {**original.get('file_values', {}), **original.get('parameter_bindings', {}),
                    **original.get('local_values', {})}
        imports = environment.get('__source_imports') or {}
        references = {}
        environment = {**environment, 'componentState': result['style']['state']}
        resolver = value_resolver(bindings, environment)

        def select(tree, seen=()):
            name = qualified_name(tree)
            if name in bindings and name not in seen:
                return select(parse_expression(str(bindings[name])), (*seen, name))
            if tree.get('kind') in {'if', 'when'}:
                try:
                    return select(resolver.branch(tree, seen), seen)
                except LayoutExpressionError:
                    return tree
            return tree

        def bind_resource(path, value, name, expression):
            group, field = path.split('.', 1)
            result['style'][group][field] = None
            try:
                spec = validate_resource_value(value)
                validate_property_token(path, spec)
            except ValueError as error:
                result.setdefault('unresolved', []).append({'path':'style.' + path,
                    'expression':expression, 'reason':str(error)})
                return
            references[path] = {'android':name, 'key':value['key'], **copy.deepcopy(spec)}

        def bind(path, tree):
            references.pop(path, None)
            tree = select(tree)
            name = qualified_name(tree)
            try:
                value = resolver.value(tree)
            except LayoutExpressionError:
                value = None
            if is_resource_value(value):
                call = call_from(tree)
                name = name or (call.qualified_name if call else 'resource')
                head, *tail = name.split('.')
                if isinstance(imports.get(head), str):
                    name = '.'.join([imports[head], *tail])
                bind_resource(path, value, name, tree.get('text') or name)
                return
            if not name:
                def contains_mapping(value):
                    if isinstance(value, dict):
                        name = qualified_name(value)
                        if name in self.mappings:
                            return True
                        return any(contains_mapping(child) for child in value.values())
                    return isinstance(value, list) and any(contains_mapping(child) for child in value)
                if contains_mapping(tree):
                    result.setdefault('unresolved', []).append({'path': 'source.style_token_references.' + path,
                        'expression': tree.get('text', ''),
                        'reason': 'mapped token is inside an unselected or composite expression; reference was not substituted'})
                return
            head, *tail = name.split('.')
            imported = imports.get(head)
            if isinstance(imported, str):
                name = '.'.join([imported, *tail])
            spec = self.mappings.get(name)
            if spec is None:
                return
            try:
                validate_property_token(path, spec)
            except ValueError as error:
                result.setdefault('unresolved', []).append({'path': 'style.' + path,
                    'expression': tree['text'], 'reason': str(error)})
                return
            references[path] = {'android': name, **copy.deepcopy(spec)}

        def shape(tree):
            call = call_from(select(tree))
            if call and call.name == 'RoundedCornerShape' and len(call.arguments) == 1:
                bind('surface.corner_radius_dp', call.arguments[0]['value'])

        def modifiers(tree):
            tree = select(tree)
            call = call_from(tree)
            if not call:
                return
            if call.receiver:
                modifiers(call.receiver)
            if call.name == 'background':
                color = call.argument('color')
                if color:
                    bind('surface.background', color)
                corner = call.argument('shape', 1)
                if corner:
                    shape(corner)
            elif call.name == 'clip' and call.argument('shape'):
                shape(call.argument('shape'))
            elif call.name == 'then' and call.arguments:
                modifiers(call.arguments[0]['value'])

        semantic = (original.get('arguments') or {}).get('semantic') or {}
        try:
            if original['type'] in {'Text', 'BasicText', 'ClickableText'}:
                positional = (original.get('arguments') or {}).get('positional') or []
                spec = semantic.get('text') or (positional[0] if positional else None)
                if spec:
                    bind('content.text', parse_expression(spec.get('original_expression') or spec['expression']))
            for name in ('style', 'textStyle'):
                if not semantic.get(name):
                    continue
                call = call_from(select(parse_expression(semantic[name]['expression'])))
                if call and call.name == 'TextStyle':
                    for argument, field in TEXT_ARGUMENTS.items():
                        value = next((a['value'] for a in call.arguments if a.get('name') == argument), None)
                        if value:
                            bind('typography.' + field, value)
            for argument, field in TEXT_ARGUMENTS.items():
                spec = semantic.get(argument)
                if spec and original['type'] in {'Text', 'BasicText', 'ClickableText', 'TextField', 'BasicTextField', 'OutlinedTextField'}:
                    bind('typography.' + field, parse_expression(spec.get('original_expression') or spec['expression']))
            if original['type'] == 'Surface' and semantic.get('color'):
                bind('surface.background', parse_expression(semantic['color']['expression']))
            if original['type'] in {'Icon', 'Image', 'AsyncImage'} and semantic.get('tint'):
                bind('asset.tint', parse_expression(semantic['tint']['expression']))
            if original['type'] in {'CircularProgressIndicator', 'LinearProgressIndicator',
                                    'Divider', 'HorizontalDivider', 'VerticalDivider'}:
                for argument, field in [('color', 'active_color'), ('trackColor', 'inactive_color')]:
                    if semantic.get(argument):
                        bind('control.' + field, parse_expression(semantic[argument]['expression']))
            if semantic.get('colors') and original['type'] in {'Button', 'TextButton', 'OutlinedButton', 'Card'}:
                call = call_from(select(parse_expression(semantic['colors']['expression'])))
                enabled = result['style']['state'].get('enabled')
                if call and call.name in {'buttonColors', 'textButtonColors', 'outlinedButtonColors', 'cardColors'} and type(enabled) is bool:
                    for argument, path in [('containerColor', 'surface.background'), ('contentColor', 'typography.color')]:
                        argument = argument if enabled else 'disabled' + argument[0].upper() + argument[1:]
                        value = next((a['value'] for a in call.arguments if a.get('name') == argument), None)
                        if value:
                            bind(path, value)
            if semantic.get('shape'):
                shape(parse_expression(semantic['shape']['expression']))
            for modifier in original.get('modifiers', []):
                if modifier['name'] == 'unresolvedExpression':
                    # Already diagnosed by modifier projection; this is not an API call.
                    continue
                expression = modifier.get('source_expression') or ('Modifier.' + (modifier.get('syntax_expression') or
                    f"{modifier['name']}({modifier.get('arguments') or ''})"))
                modifiers(parse_expression(expression))
            for path, spec in self.defaults.get(original['type'], {}).items():
                if not has_source_owner(original, path) and 'expression' in spec:
                    bind(path, parse_expression(spec['expression']))
        except KotlinPsiSyntaxError as error:
            result.setdefault('unresolved', []).append({'path': 'source.style_token_references',
                'expression': error.expression, 'reason': str(error)})
        # Values may arrive through arbitrary callee parameters, not direct API syntax.
        for group, fields in result['style'].items():
            if not isinstance(fields, dict):
                continue
            for field, value in fields.items():
                if is_resource_value(value):
                    bind_resource(group + '.' + field, value, 'resource', str(value.get('key') or field))
        result.setdefault('source', {})['style_token_references'] = references
        reference_paths = {'style.' + path for path in references}
        result['unresolved'] = [u for u in result.get('unresolved', []) if u.get('path') not in reference_paths]
