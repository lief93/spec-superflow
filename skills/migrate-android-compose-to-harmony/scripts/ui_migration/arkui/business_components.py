"""Source-identity UI builders; no added layout node and no source-file fallback."""
from __future__ import annotations

from dataclasses import dataclass, field
import json

from ui_migration.common import ArkUIPageError, pascal_identifier
from ui_migration.naming import NameScope


@dataclass
class Argument:
    kind: str
    expression: str
    component_id: str
    path: str
    name: str
    source_name: str


@dataclass
class Invocation:
    name: str
    arguments: list[Argument]
    slots: list['Invocation']


@dataclass
class Frame:
    arguments: list[Argument] = field(default_factory=list)
    slots: list[Invocation] = field(default_factory=list)
    names: NameScope = field(default_factory=NameScope)
    slot_names: list[str] = field(default_factory=list)
    preserve_literals: bool = False
    source_parameters: set[str] = field(default_factory=set)


class BusinessComponents:
    def __init__(self, definitions, root_name=None, diagnostic=None, value_emitter=None):
        if not isinstance(definitions, list):
            raise ArkUIPageError('componentDefinitions must be a list')
        self.definitions = {}
        for definition in definitions:
            if not isinstance(definition, dict) or not isinstance(definition.get('id'), str):
                raise ArkUIPageError('component definition requires a stable id')
            if definition['id'] in self.definitions:
                raise ArkUIPageError('duplicate component definition: ' + definition['id'])
            self.definitions[definition['id']] = definition
        self.frames = []
        self.builders = {}
        self.instances = {}
        self.root_name = root_name
        self.diagnostic = diagnostic or (lambda *args: None)
        from ui_migration.arkui.component_interfaces import literal
        self.value = value_emitter or literal
        self.clear()

    def clear(self):
        self.preferred_imports = {}
        self.frames.clear()
        self.builders.clear()
        self.instances.clear()
        self.keys = {}
        self.names = NameScope({'renderBusinessSlot', 'renderAndroidPageSnapshot', 'layoutPx',
                                'nativeFontSize', 'nativeLineHeight', self.root_name})
        from ui_migration.arkui.component_interfaces import ComponentInterfaces
        self.interfaces = ComponentInterfaces(self, self.diagnostic)
        from ui_migration.arkui.component_ui_states import ComponentUiStates
        self.ui_states = ComponentUiStates(self)
        self.slot_fields = {'string':'text', 'ResourceStr':'media'}

    def slot_field(self, kind):
        if kind not in self.slot_fields:
            self.slot_fields[kind] = 'values' + str(len(self.slot_fields))
        return self.slot_fields[kind]

    def bind(self, component, path, expression, kind='string'):
        if not self.frames:
            return expression
        frame = self.frames[-1]
        source = component.get('source') or {}
        source_name = source.get('property_bindings', {}).get(path)
        if frame.preserve_literals and source_name not in frame.source_parameters:
            return expression
        hint = source.get('property_names', {}).get(path)
        fallbacks = {'semantic_key': 'viewId', 'style.content.text': 'text',
                     'style.content.placeholder': 'placeholder', 'style.asset.resource': 'image',
                     'style.content.description': 'contentDescription'}
        name = frame.names.allocate(hint or source_name or fallbacks.get(path, 'value'))
        frame.arguments.append(Argument(kind, expression, component['id'], path, name, source_name or ''))
        return name if frame.preserve_literals else f'props.{name}'

    def capture(self, definition_id, symbol, render, prefix='', *, direct_slot=False):
        frame = Frame(preserve_literals=direct_slot)
        frame.source_parameters = ({p['name'] for p in self.definitions.get(definition_id, {}).get('parameters', [])}
                                   if not direct_slot else set().union(*(f.source_parameters for f in self.frames)))
        self.frames.append(frame)
        try:
            body = render()
        finally:
            self.frames.pop()
        # Fixed-state structure/style variants are explicit specializations of a
        # source definition, never aliases inferred from visually similar trees.
        key = json.dumps([definition_id, body, [(a.name, a.kind) for a in frame.arguments], frame.slot_names, direct_slot])
        if key in self.keys:
            return Invocation(self.keys[key], frame.arguments, frame.slots)
        preferred = prefix + symbol
        peers = [d for d in self.definitions.values() if d.get('type') == symbol and d.get('component_kind') == 'project_component']
        if len(peers) > 1 and definition_id:
            parameters = self.definitions[definition_id].get('parameters') or []
            preferred += 'By' + ''.join(pascal_identifier(p['name']) for p in parameters) if parameters else 'WithoutArguments'
        if any(b['definition_id'] == definition_id for b in self.builders.values()) and definition_id:
            preferred += 'Variant'
        name = self.names.allocate(preferred, 'Component')
        self.keys[key] = name
        self.builders[name] = {
            'name': name, 'definition_id': definition_id, 'symbol': symbol,
            'body': body, 'argument_types': [a.kind for a in frame.arguments],
            'argument_names': [a.name for a in frame.arguments],
            'slot_count': len(frame.slots),
            'slot_names': frame.slot_names,
            'direct_slot': direct_slot,
        }
        return Invocation(name, frame.arguments, frame.slots)

    def slot_value(self, invocation):
        slots = [b['name'] for b in self.builders.values() if b['definition_id'] is None and not b['direct_slot']]
        arrays = {}
        for argument in invocation.arguments:
            value = self.bind({'id': argument.component_id, 'source': {'property_bindings': {argument.path: argument.source_name}}}, argument.path,
                              argument.expression, argument.kind)
            arrays.setdefault(self.slot_field(argument.kind), []).append(value)
        nested = [self.slot_value(s) for s in invocation.slots]
        return ('{ kind: ' + str(slots.index(invocation.name))
                + ''.join(', ' + field + ': [' + ', '.join(values) + ']' for field, values in arrays.items())
                + ', slots: [' + ', '.join(nested) + '] }')

    def call(self, invocation, component=None):
        arguments = []
        direct_slot = self.builders[invocation.name]['direct_slot']
        if invocation.arguments:
            properties = []
            for argument in invocation.arguments:
                preferred = argument.source_name
                preferred = ((component or {}).get('source') or {}).get('invocation_names', {}).get(preferred, preferred)
                value = self.bind({'id': argument.component_id, 'source': {'property_bindings': {argument.path: preferred}}}, argument.path,
                                  argument.expression, argument.kind)
                properties.append(value if direct_slot else f'{argument.name}: {value}')
            if direct_slot:
                arguments.extend(properties)
            else:
                arguments.append('{ ' + ', '.join(properties) + ' }')
        for slot in invocation.slots:
            arguments.append(self.slot_value(slot))
        return f"this.{invocation.name}({', '.join(arguments)})"

    def render(self, component, render, indent):
        definition_id = component.get('definition_id')
        definition = self.definitions.get(definition_id)
        if not definition or definition.get('component_kind') != 'project_component':
            raise ArkUIPageError('missing project component definition: ' + str(definition_id))
        record = self.interfaces.contract(component, definition)
        invocation = self.capture(definition_id, definition['type'], render, 'render' if record is not None else 'preview')
        self.instances[component['id']] = {
            'id': component['id'], 'definition_id': definition_id,
            'builder': invocation.name, 'invocation_bindings': component.get('invocation_bindings') or {},
            'render_arguments': [vars(a) for a in invocation.arguments],
            'slots': [s.name for s in invocation.slots],
            'interface': component.get('source', {}).get('component_interface'),
        }
        call = self.interfaces.call(component, definition, invocation, record) if record is not None else self.call(invocation, component)
        return [' ' * indent + call]

    def slot(self, component, render, indent):
        owner = self.frames[-1]
        source_name = (component.get('source') or {}).get('slot_invocation', {}).get('name') or 'content'
        slot = self.capture(None, 'render' + pascal_identifier(source_name), render)
        name = NameScope(['props', *owner.slot_names]).allocate(source_name)
        owner.slots.append(slot)
        owner.slot_names.append(name)
        return [' ' * indent + f'this.renderBusinessSlot({name})']

    def declarations(self):
        interfaces, methods = [], []
        declared_methods = self.interfaces.declarations()
        ui_interfaces, ui_methods = self.ui_states.declarations()
        interfaces.extend(ui_interfaces)
        slots = [b for b in self.builders.values() if b['definition_id'] is None and not b['direct_slot']]
        if slots:
            for slot in slots:
                for kind in slot['argument_types']:
                    self.slot_field(kind)
            interfaces.extend(['interface BusinessSlot {', '  kind: number',
                *['  ' + field + '?: Array<' + kind + '>' for kind, field in self.slot_fields.items()],
                '  slots: BusinessSlot[]', '}', ''])
            # Defunctionalize fixed-state UI lambdas. Arbitrary () => void calls
            # are not ArkUI builder syntax. Dispatch has no layout node of its own.
            methods.extend(['  @Builder', '  private renderBusinessSlot(slot: BusinessSlot) {'])
            for index, slot in enumerate(slots):
                fields, counts = [], {kind:0 for kind in self.slot_fields}
                for field_index, kind in enumerate(slot['argument_types']):
                    array = self.slot_field(kind)
                    fields.append(f"{slot['argument_names'][field_index]}: slot.{array}![{counts[kind]}]")
                    counts[kind] += 1
                args = ['{ ' + ', '.join(fields) + ' }'] if fields else []
                args.extend(f'slot.slots[{i}]' for i in range(slot['slot_count']))
                methods.extend([f"    {'if' if index == 0 else 'else if'} (slot.kind === {index}) {{",
                    f"      this.{slot['name']}({', '.join(args)})", '    }'])
            methods.extend(['  }', ''])
        for builder in self.builders.values():
            name = builder['name']
            parameters = []
            if builder['direct_slot']:
                parameters.extend(f'{name}: {kind}' for name, kind in zip(builder['argument_names'], builder['argument_types']))
            elif builder['argument_types']:
                interface = name + 'Props'
                interfaces.append(f'interface {interface} {{')
                for index, kind in enumerate(builder['argument_types']):
                    interfaces.append(f"  {builder['argument_names'][index]}: {kind}")
                interfaces.extend(['}', ''])
                parameters.append('props: ' + interface)
            parameters.extend(f'{name}: BusinessSlot' for name in builder['slot_names'])
            methods.extend(['  @Builder', f"  private {name}({', '.join(parameters)}) {{",
                            *builder['body'], '  }', ''])
        return interfaces, methods + declared_methods + ui_methods

    def report(self):
        reached = {instance['definition_id'] for instance in self.instances.values()}
        definitions = []
        for key in sorted(reached):
            definition = self.definitions[key]
            builders = [b['name'] for b in self.builders.values() if b['definition_id'] == key]
            definitions.append({'id': key, 'symbol': definition['type'],
                'identity': definition.get('identity'), 'builders': builders,
                'builder_count': len(builders), 'specialization_count': len(builders),
                'parameters': definition.get('parameters') or []})
        return {'scope': 'fixed-state-ui', 'representation': 'page-local-builders',
                'shared_cross_page_modules': False,
                'parameterized_facts': ['style.content.text', 'style.content.placeholder',
                    'style.asset.resource', 'semantic_key', 'style.content.description'],
                'style_policy': 'explicit fixed-state specializations',
                'declared_interfaces': self.interfaces.report(),
                'component_ui_states': self.ui_states.report(),
                'definition_count': len(definitions), 'instance_count': len(self.instances),
                'builder_count': sum(d['builder_count'] for d in definitions),
                'definitions': definitions, 'instances': list(self.instances.values())}
