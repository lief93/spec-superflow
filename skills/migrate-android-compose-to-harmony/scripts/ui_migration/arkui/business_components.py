"""Source-identity UI builders; no added layout node and no source-file fallback."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from ui_migration.common import ArkUIPageError, pascal_identifier


@dataclass
class Argument:
    kind: str
    expression: str
    component_id: str
    path: str


@dataclass
class Invocation:
    name: str
    arguments: list[Argument]
    slots: list['Invocation']


@dataclass
class Frame:
    arguments: list[Argument] = field(default_factory=list)
    slots: list[Invocation] = field(default_factory=list)


class BusinessComponents:
    def __init__(self, definitions):
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

    def clear(self):
        self.frames.clear()
        self.builders.clear()
        self.instances.clear()

    def bind(self, component, path, expression, kind='string'):
        if not self.frames:
            return expression
        frame = self.frames[-1]
        index = len(frame.arguments)
        frame.arguments.append(Argument(kind, expression, component['id'], path))
        return f'props.v{index}'

    def capture(self, definition_id, symbol, render):
        frame = Frame()
        self.frames.append(frame)
        try:
            body = render()
        finally:
            self.frames.pop()
        # Fixed-state structure/style variants are explicit specializations of a
        # source definition, never aliases inferred from visually similar trees.
        key = json.dumps([definition_id, body, [a.kind for a in frame.arguments], len(frame.slots)])
        digest = hashlib.sha256(key.encode()).hexdigest()[:12]
        name = 'business' + pascal_identifier(symbol) + digest
        self.builders.setdefault(name, {
            'name': name, 'definition_id': definition_id, 'symbol': symbol,
            'body': body, 'argument_types': [a.kind for a in frame.arguments],
            'slot_count': len(frame.slots),
        })
        return Invocation(name, frame.arguments, frame.slots)

    def slot_value(self, invocation):
        slots = [b['name'] for b in self.builders.values() if b['definition_id'] is None]
        text, media = [], []
        for argument in invocation.arguments:
            value = self.bind({'id': argument.component_id}, argument.path,
                              argument.expression, argument.kind)
            (media if argument.kind == 'ResourceStr' else text).append(value)
        nested = [self.slot_value(s) for s in invocation.slots]
        return ('{ kind: ' + str(slots.index(invocation.name))
                + ', text: [' + ', '.join(text) + '], media: [' + ', '.join(media)
                + '], slots: [' + ', '.join(nested) + '] }')

    def call(self, invocation):
        arguments = []
        if invocation.arguments:
            properties = []
            for index, argument in enumerate(invocation.arguments):
                value = self.bind({'id': argument.component_id}, argument.path,
                                  argument.expression, argument.kind)
                properties.append(f'v{index}: {value}')
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
        return [' ' * indent + self.call(invocation)]

    def slot(self, component, render, indent):
        owner = self.frames[-1]
        slot = self.capture(None, 'Slot', render)
        index = len(owner.slots)
        owner.slots.append(slot)
        return [' ' * indent + f'this.renderBusinessSlot(slot{index})']

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
                    fields.append(f'v{field_index}: slot.{array}[{counts[kind]}]')
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
                    interfaces.append(f'  v{index}: {kind}')
                interfaces.extend(['}', ''])
                parameters.append('props: ' + interface)
            parameters.extend(f'slot{i}: BusinessSlot' for i in range(builder['slot_count']))
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
