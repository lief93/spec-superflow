"""Kotlin literal values; interpolations are PSI nodes, never text substitutions."""
import json


def display_value(value):
    if value is None:
        return 'null'
    if type(value) is bool:
        return 'true' if value else 'false'
    return str(value)


def literal_value(node, evaluate):
    if 'parts' in node:
        return ''.join(part['value'] if part['kind'] == 'text' else display_value(evaluate(part['value']))
                       for part in node['parts'])
    token = node['text'].replace('_', '')
    if token in ('true', 'false', 'null'):
        return {'true': True, 'false': False, 'null': None}[token]
    if token.startswith("'") and token.endswith("'"):
        return json.loads('"' + token[1:-1] + '"')
    if token.lower().startswith(('0x', '0b')):
        return int(token.rstrip('uUlL'), 0)
    if any(mark in token.lower() for mark in ('.', 'e')) or token[-1:] in ('f', 'F'):
        return float(token.rstrip('fFdD'))
    return int(token.rstrip('uUlL'))
