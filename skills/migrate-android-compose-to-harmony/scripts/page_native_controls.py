"""Constant visual arguments shared by source extraction and its fact gate."""
from __future__ import annotations

import re

SELECTION_FIELDS = {'Checkbox': 'checked', 'Switch': 'checked', 'RadioButton': 'selected'}
PROGRESS_TYPES = {'LinearProgressIndicator', 'CircularProgressIndicator'}
DIVIDER_TYPES = {'Divider', 'HorizontalDivider', 'VerticalDivider'}
CONTROL_TYPES = set(SELECTION_FIELDS) | PROGRESS_TYPES | DIVIDER_TYPES | {'Slider'}
CONTROL_ARGUMENTS = {'value', 'valueRange', 'steps', 'progress', 'color', 'trackColor', 'thickness', 'strokeWidth'}


def arguments_for(kind):
    if kind == 'Slider':
        return {'value', 'valueRange', 'steps'}
    if kind in PROGRESS_TYPES:
        return {'progress', 'color', 'trackColor', 'strokeWidth'}
    if kind in DIVIDER_TYPES:
        return {'thickness', 'color'}
    return set()


def numeric(expression):
    match = re.fullmatch(r'(-?(?:\d+(?:\.\d*)?|\.\d+))[fF]?', expression.strip())
    return float(match[1]) if match else None


def parse_argument(name, expression):
    from component_required_facts import constant_color, number_expression
    expression = expression.strip()
    if name in {'color', 'trackColor'}:
        value = constant_color(expression)
        return {('active_color' if name == 'color' else 'inactive_color'): value} if value else None
    if name in {'thickness', 'strokeWidth'}:
        value = number_expression(expression, 'dp')
        return {'stroke_width_dp': value} if value is not None and value >= 0 else None
    if name == 'valueRange':
        parts = expression.split('..')
        values = [numeric(p) for p in parts]
        if len(values) == 2 and all(v is not None for v in values) and values[0] < values[1]:
            return dict(zip(('minimum', 'maximum'), values))
        return None
    if name == 'progress' and expression.startswith('{') and expression.endswith('}'):
        expression = expression[1:-1].strip()
    value = numeric(expression)
    if value is None:
        return None
    if name == 'steps':
        return {'steps': int(value)} if value >= 0 and value.is_integer() else None
    return {'value': value}


def defaults_for(kind):
    if kind == 'Slider':
        return {'minimum': 0, 'maximum': 1, 'steps': 0}
    if kind in PROGRESS_TYPES:
        return {'minimum': 0, 'maximum': 1}
    if kind in DIVIDER_TYPES:
        return {'stroke_width_dp': 1}
    return {}
