"""Render Material's named slots in native flow, never screenshot coordinates."""


def material_item_lines(renderer, component, children, bounds, indent):
    prefix = ' ' * indent
    facts = component.get('source', {}).get('material_item')
    if not facts:
        renderer.add_page_json_unresolved(component, 'source.material_item', 'Material layout defaults have not been resolved')
        return []
    length = renderer.lengths.length
    slots = {}
    for child in children:
        slot = child.get('source', {}).get('slot_argument_name')
        slots.setdefault(slot, []).append(child)
    multiline_state = None
    supporting = slots.get('supportingContent', [])
    if component['type'] == 'ListItem' and len(supporting) == 1 and supporting[0]['type'] in {'Text', 'BasicText'}:
        line_height = supporting[0]['style']['typography'].get('line_height_sp')
        if type(line_height) in (int, float):
            multiline_state = f'materialItem{len(renderer._material_item_states)}Multiline'
            renderer._material_item_states[component['id']] = multiline_state
    lines = [prefix + 'Row() {']
    def emit(slot, depth):
        result = []
        for child in slots.get(slot, []):
            result.extend(renderer.page_snapshot_component_lines(child, bounds, 'Column', depth))
        if slot == 'supportingContent' and multiline_state and result:
            result.append(' ' * depth + f'  .onAreaChange((_old, area) => {{ this.{multiline_state} = this.getUIContext().vp2px(Number(area.height)) > Math.round(this.getUIContext().fp2px({line_height})) + 1 }})')
        return result
    is_list = component['type'] == 'ListItem'
    is_fab = component['type'] == 'ExtendedFloatingActionButton'
    if is_fab:
        body = emit('icon', indent + 2)
        if facts.get('expanded') is True:
            body += emit('text', indent + 2)
        elif facts.get('expanded') is None:
            renderer.add_page_json_unresolved(component, 'source.material_item.expanded', 'extended FAB requires a fixed expanded state')
        body += emit('content', indent + 2)
        renderer.record_page_paths(component, {'source.material_item'})
        return [prefix + f'Row({{ space: {length(facts["gap_dp"])} }}) {{', *body,
            prefix + '}', prefix + '  .alignItems(VerticalAlign.Center)',
            prefix + f'  .constraintSize({{ minHeight: {length(56)}, minWidth: {length(80 if facts.get("expanded") else 56)} }})',
            prefix + f'  .padding({{ left: {length(16)}, right: {length(20 if facts.get("expanded") else 16)} }})']
    for slot, main in ((('leadingContent' if is_list else 'leadingIcon'), False),
                       ('main', True), (('trailingContent' if is_list else 'trailingIcon'), False)):
        names = ('overlineContent', 'headlineContent', 'supportingContent') if is_list and main else ('label',) if main else (slot,)
        body = [line for name in names for line in emit(name, indent + 4)]
        if not body:
            continue
        lines.extend([prefix + '  Column() {', *body, prefix + '  }', prefix + '    .alignItems(HorizontalAlign.Start)'])
        if main and is_list:
            lines.append(prefix + '    .layoutWeight(1)')
        elif not main:
            edge = 'right' if slot.startswith('leading') else 'left'
            lines.append(prefix + f'    .margin({{ {edge}: {length(facts["gap_dp"])} }})')
    lines.extend([prefix + '}', prefix + '  .alignItems(VerticalAlign.Center)',
                  prefix + f'  .constraintSize({{ minHeight: {"this." + multiline_state + " ? " + length(88) + " : " if multiline_state else ""}{length(facts["min_height_dp"])} }})'])
    if is_list:
        lines.append(prefix + "  .width('100%')")
    start = facts.get('start_padding_dp', facts['horizontal_padding_dp'])
    end = facts.get('end_padding_dp', facts['horizontal_padding_dp'])
    left, right = (end, start) if component['style']['layout'].get('layout_direction') == 'rtl' else (start, end)
    vp = length(facts.get('vertical_padding_dp', 0))
    if multiline_state:
        vp = f'this.{multiline_state} ? {length(12)} : {vp}'
    lines.append(prefix + f'  .padding({{ left: {length(left)}, right: {length(right)}, top: {vp}, bottom: {vp} }})')
    renderer.record_page_paths(component, {'source.material_item'})
    return lines
