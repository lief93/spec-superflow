"""Render typed corner sizes from native measured dimensions, never reference bbox."""
from ui_migration.arkui.formatting import page_number


class CornerEmitter:
    def __init__(self):
        self.declarations = []
        self.count = 0

    def emit(self, sizes):
        name = f'pageCorners{self.count}'
        self.count += 1
        keys = ('top_left', 'top_right', 'bottom_right', 'bottom_left')
        properties = ('TopLeft', 'TopRight', 'BottomRight', 'BottomLeft')
        self.declarations.append([f'  @State private {name}{key}: number = 0' for key in properties] + [''])
        expressions = []
        for key in keys:
            size = sizes[key]
            number = page_number(size['value'])
            if size['unit'] == 'percent':
                expression = f'{name}Minimum * {page_number(size["value"] / 100)}'
            elif size['unit'] == 'px':
                expression = f'this.getUIContext().px2vp({number})'
            else:
                expression = number
            expressions.append(expression)
        updates = [f'const {name}Minimum = Math.min(Number(current.width), Number(current.height))']
        updates.extend(f'const {name}{key} = {value}' for key, value in zip(properties, expressions))
        # Compose scales each vertical corner pair against the shorter measured side.
        for pair, first, second in [('Left', 'TopLeft', 'BottomLeft'), ('Right', 'TopRight', 'BottomRight')]:
            updates.append(f'const {name}{pair}Scale = Math.min(1, {name}Minimum / ({name}{first} + {name}{second} || 1))')
        updates.extend(f'this.{name}{key} = {name}{key} * {name}{"Left" if key.endswith("Left") else "Right"}Scale'
                       for key in properties)
        expression = '{ ' + ', '.join(key[0].lower() + key[1:] + ': this.' + name + key for key in properties) + ' }'
        return expression, updates
