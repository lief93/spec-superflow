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


class BusinessComponents:
    def __init__(self, definitions, root_name=None):
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
        self.clear()

    def clear(self):
        self.frames.clear()
        self.builders.clear()
        self.instances.clear()
        self.keys = {}
        self.names = NameScope({'renderBusinessSlot', 'renderAndroidPageSnapshot', 'layoutPx',
                                'nativeFontSize', 'nativeLineHeight', self.root_name})

    def bind(self, component, path, expression, kind='string'):
        if not self.frames:
            return expression
        frame = self.frames[-1]
        source_name = (component.get('source') or {}).get('property_names', {}).get(path)
        fallbacks = {'semantic_key': 'viewId', 'style.content.text': 'text',
                     'style.content.placeholder': 'placeholder', 'style.asset.resource': 'image',
                     'style.content.description': 'contentDescription'}
        name = frame.names.allocate(source_name or fallbacks.get(path, 'value'))
        frame.arguments.append(Argument(kind, expression, component['id'], path, name, source_name or ''))
        return f'props.{name}'

    def capture(self, definition_id, symbol, render):
        frame = Frame()
        self.frames.append(frame)
        try:
            body = render()
        finally:
            self.frames.pop()
        # Fixed-state structure/style variants are explicit specializations of a
        # source definition, never aliases inferred from visually similar trees.
        key = json.dumps([definition_id, body, [(a.name, a.kind) for a in frame.arguments], frame.slot_names])
        if key in self.keys:
            return Invocation(self.keys[key], frame.arguments, frame.slots)
        preferred = symbol
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
        }
        return Invocation(name, frame.arguments, frame.slots)

    def slot_value(self, invocation):
        slots = [b['name'] for b in self.builders.values() if b['definition_id'] is None]
        text, media = [], []
        for argument in invocation.arguments:
            value = self.bind({'id': argument.component_id, 'source': {'property_names': {argument.path: argument.source_name}}}, argument.path,
                              argument.expression, argument.kind)
            (media if argument.kind == 'ResourceStr' else text).append(value)
        nested = [self.slot_value(s) for s in invocation.slots]
        return ('{ kind: ' + str(slots.index(invocation.name))
                + ', text: [' + ', '.join(text) + '], media: [' + ', '.join(media)
                + '], slots: [' + ', '.join(nested) + '] }')

    def call(self, invocation, component=None):
        arguments = []
        if invocation.arguments:
            properties = []
            for argument in invocation.arguments:
                preferred = argument.source_name
                preferred = ((component or {}).get('source') or {}).get('invocation_names', {}).get(preferred, preferred)
                value = self.bind({'id': argument.component_id, 'source': {'property_names': {argument.path: preferred}}}, argument.path,
                                  argument.expression, argument.kind)
                properties.append(f'{argument.name}: {value}')
            arguments.append('{ ' + ', '.join(properties) + ' }')
        for slot in invocation.slots:
            arguments.append(self.slot_value(slot))
        return f"this.{invocation.name}({', '.join(arguments)})"

    def render(self, component, render, indent):
        definition_id = component.get('definition_id')
        definition = self.definitions.get(definition_id)
        if not definition or definition.get('component_kind') != 'project_component':
            raise ArkUIPageError('missing project component definition: ' + str(definition_id))
        invocation = self.capture(definition_id, definition['type'], render)
        self.instances[component['id']] = {
            'id': component['id'], 'definition_id': definition_id,
            'builder': invocation.name, 'invocation_bindings': component.get('invocation_bindings') or {},
            'render_arguments': [vars(a) for a in invocation.arguments],
            'slots': [s.name for s in invocation.slots],
        }
        return [' ' * indent + self.call(invocation, component)]

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
        slots = [b for b in self.builders.values() if b['definition_id'] is None]
        if slots:
            interfaces.extend(['interface BusinessSlot {', '  kind: number',
                '  text: string[]', '  media: ResourceStr[]', '  slots: BusinessSlot[]', '}', ''])
            # Defunctionalize fixed-state UI lambdas. Arbitrary () => void calls
            # are not ArkUI builder syntax. Dispatch has no layout node of its own.
            methods.extend(['  @Builder', '  private renderBusinessSlot(slot: BusinessSlot) {'])
            for index, slot in enumerate(slots):
                fields, counts = [], {'string': 0, 'ResourceStr': 0}
                for field_index, kind in enumerate(slot['argument_types']):
                    array = 'media' if kind == 'ResourceStr' else 'text'
                    fields.append(f"{slot['argument_names'][field_index]}: slot.{array}[{counts[kind]}]")
                    counts[kind] += 1
                args = ['{ ' + ', '.join(fields) + ' }'] if fields else []
                args.extend(f'slot.slots[{i}]' for i in range(slot['slot_count']))
                methods.extend([f"    {'if' if index == 0 else 'else if'} (slot.kind === {index}) {{",
                    f"      this.{slot['name']}({', '.join(args)})", '    }'])
            methods.extend(['  }', ''])
        for builder in self.builders.values():
            name = builder['name']
            parameters = []
            if builder['argument_types']:
                interface = name + 'Props'
                interfaces.append(f'interface {interface} {{')
                for index, kind in enumerate(builder['argument_types']):
                    interfaces.append(f"  {builder['argument_names'][index]}: {kind}")
                interfaces.extend(['}', ''])
                parameters.append('props: ' + interface)
            parameters.extend(f'{name}: BusinessSlot' for name in builder['slot_names'])
            methods.extend(['  @Builder', f"  private {name}({', '.join(parameters)}) {{",
                            *builder['body'], '  }', ''])
        return interfaces, methods

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
                'definition_count': len(definitions), 'instance_count': len(self.instances),
                'builder_count': sum(d['builder_count'] for d in definitions),
                'definitions': definitions, 'instances': list(self.instances.values())}
