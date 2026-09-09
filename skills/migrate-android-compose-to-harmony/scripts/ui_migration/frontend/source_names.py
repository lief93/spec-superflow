"""Retain small source naming hints without copying Kotlin bodies to the backend."""
from kotlin_psi import parse_expression, KotlinPsiSyntaxError
from ui_migration.semantics.syntax import qualified_name


def reference_name(expression):
    if not isinstance(expression, str):
        return None
    try:
        name = qualified_name(parse_expression(expression))
    except KotlinPsiSyntaxError:
        return None
    return name.rsplit('.', 1)[-1] if name else None


def direct_reference_name(expression):
    if not isinstance(expression, str):
        return None
    try:
        syntax = parse_expression(expression)
    except KotlinPsiSyntaxError:
        return None
    return syntax.get('name') if syntax.get('kind') == 'name' else None


def property_name_hints(node, direct_only=False):
    arguments = node.get('arguments') or {}
    semantic = arguments.get('semantic') or {}
    positional = arguments.get('positional') or []
    hints = {}
    candidates = {
        'style.content.text': semantic.get('text') or semantic.get('value'),
        'style.content.description': semantic.get('contentDescription'),
        'style.asset.resource': semantic.get('painter') or semantic.get('imageVector') or semantic.get('bitmap'),
    }
    if not candidates['style.content.text'] and node.get('type') in {'Text', 'BasicText', 'ClickableText'} and positional:
        candidates['style.content.text'] = positional[0]
    for path, argument in candidates.items():
        if not isinstance(argument, dict):
            continue
        expression = argument.get('original_expression') or argument.get('expression')
        name = direct_reference_name(expression) if direct_only else reference_name(expression)
        if name:
            hints[path] = name
    return hints
