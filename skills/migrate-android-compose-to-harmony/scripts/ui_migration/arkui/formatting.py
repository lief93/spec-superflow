from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from ui_migration.common import decimal_literal


def page_number(value: int | float) -> str:
    rounded = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return decimal_literal(rounded)


class LayoutLengths:
    """One rounding policy and helper requirement shared by all node emitters."""

    def __init__(self):
        self.used = False

    def length(self, value: float) -> str:
        self.used = True
        return f"this.layoutPx({page_number(value)})"

    def edges(self, values: dict) -> str:
        rendered = {edge: self.length(values[edge]) for edge in ('left', 'right', 'top', 'bottom')}
        if len(set(rendered.values())) == 1:
            return rendered['left']
        return '{ ' + ', '.join(f'{edge}: {value}' for edge, value in rendered.items()) + ' }'
