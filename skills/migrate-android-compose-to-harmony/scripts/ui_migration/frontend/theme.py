from __future__ import annotations
import copy
from generate_harmony_theme_resources import MATERIAL3_LIGHT_COLOR_DEFAULTS, color_from_semantics
from typing import Any
from ui_migration.frontend.model import RealPageError


def resolve_theme_environment(payload, environment):
    from kotlin_psi import parse_expression, KotlinPsiSyntaxError
    from ui_migration.frontend.values import value_resolver
    from ui_migration.frontend.page_model import UNRESOLVED
    from ui_migration.semantics.expressions import LayoutExpressionError
    styles = copy.deepcopy(payload.get('source_text_styles') or {})
    values, typography = {}, {}
    for role, style in styles.items():
        scope = style.get('source_scope') or {}
        resolver = value_resolver(scope.get('bindings', {}), {
            **environment, '__source_file': scope.get('source'),
            '__source_imports': scope.get('imports', {})})
        expression = style.get('expression')
        if not isinstance(expression, str):
            continue
        try:
            value = resolver.value(parse_expression(expression))
            if isinstance(value, dict) and value.get('kind') == 'text_style':
                typography[role] = value
                style['expression'] = resolver.value_syntax(value)
        except (LayoutExpressionError, KotlinPsiSyntaxError):
            continue
    if typography:
        values['MaterialTheme.typography'] = typography
        values.update({'MaterialTheme.typography.' + role: value for role, value in typography.items()})
    colors = page_theme_colors(payload)
    if colors:
        values['MaterialTheme.colorScheme'] = colors
    shape_names = {a.get('arguments', {}).get('shapes', {}).get('expression')
                   for a in payload.get('source_theme_applications', [])} - {None}
    candidates = [s for s in payload.get('source_shape_sets', []) if s.get('name') in shape_names]
    if len(candidates) == 1:
        shapes = {}
        resolver = value_resolver({}, environment)
        for role, fact in candidates[0].get('roles', {}).items():
            try:
                value = resolver.value(parse_expression(fact['expression']))
                if value is not UNRESOLVED:
                    shapes[role] = value
            except (LayoutExpressionError, KotlinPsiSyntaxError):
                continue
        values['MaterialTheme.shapes'] = shapes
    return values, styles


def page_theme_colors(payload: dict) -> dict[str, str]:
    definitions = payload.get('style_definitions')
    if definitions is not None:
        return copy.deepcopy(definitions['theme']['colors'])
    return selected_theme_colors({'color_schemes': payload.get('source_color_schemes', [])})


def selected_theme_colors(inventory: dict[str, Any] | None) -> dict[str, str]:
    selected = next((scheme for scheme in (inventory or {}).get('color_schemes', [])
                     if isinstance(scheme, dict) and scheme.get('variant') == 'light'), None)
    if selected is None:
        return {}
    roles = selected.get('roles') or {}
    colors = {role: value for role, value in MATERIAL3_LIGHT_COLOR_DEFAULTS.items()
              if selected.get('constructor') == 'lightColorScheme' and role not in roles}
    for role, semantics in roles.items():
        value = color_from_semantics(semantics)
        if value is not None:
            colors[str(role)] = value
    return colors


def selected_theme_text_styles(inventory: dict[str, Any] | None, diagnostics: list | None = None) -> dict[str, Any]:
    if not inventory:
        return {}
    names = {
        item.get("arguments", {}).get("typography", {}).get("expression")
        for item in inventory.get("theme_applications", [])
        if isinstance(item, dict)
    } - {None}
    if not names:
        return {}
    matches = [item for item in inventory.get("typography_sets", []) if item.get("name") in names]
    if len(names) != 1 or len(matches) != 1:
        reason = ("multiple project typography providers require an explicit page theme" if len(names) != 1
                  else "project typography provider is unresolved or ambiguous")
        if diagnostics is None:
            raise RealPageError(reason)
        diagnostics.append({'path': 'source.theme.typography', 'expression': ', '.join(sorted(names)),
                            'reason': reason, 'candidates': copy.deepcopy(inventory.get('theme_applications', []))})
        from ui_migration.frontend.model import MATERIAL3_TYPOGRAPHY
        return {role: {'expression': None, 'unresolved_reason': reason} for role in MATERIAL3_TYPOGRAPHY}
    return copy.deepcopy(matches[0].get("styles", {}))
