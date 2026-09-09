"""Reusable project theme definitions; refresh is explicit, never fingerprint-driven."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from ui_migration.frontend.theme import selected_theme_colors, selected_theme_text_styles


SCHEMA = 'android-to-harmony.project-style-definitions.v1'
INVENTORY_FIELDS = ('tokens', 'color_schemes', 'typography_sets', 'shape_sets',
                    'theme_applications', 'extended_color_sets', 'color_accessors')


def build_style_definitions(contract: dict) -> dict:
    inventory = (contract.get('ui') or {}).get('compose_theme_token_inventory') or {}
    diagnostics = []
    text_styles = selected_theme_text_styles(inventory, diagnostics)
    return {
        'schema': SCHEMA,
        'theme': {
            'variant': 'light',
            'colors': selected_theme_colors(inventory),
            'textStyles': text_styles,
        },
        # Preserve provider scopes for fixed-state expression evaluation, not a second source scan.
        'sourceInventory': {key: copy.deepcopy(inventory.get(key) or []) for key in INVENTORY_FIELDS},
        'diagnostics': diagnostics,
        'componentDefaults': {},
        'tokenMappings': {},
    }


def validate_style_definitions(value: dict) -> dict:
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise ValueError('unsupported project style definitions schema')
    theme = value.get('theme')
    if (not isinstance(theme, dict) or theme.get('variant') != 'light'
            or not isinstance(theme.get('colors'), dict) or not isinstance(theme.get('textStyles'), dict)):
        raise ValueError('style definitions require a light theme with colors and textStyles')
    inventory = value.get('sourceInventory')
    if not isinstance(inventory, dict) or any(not isinstance(inventory.get(key), list) for key in INVENTORY_FIELDS):
        raise ValueError('style definitions require source provider inventories')
    if not isinstance(value.get('diagnostics'), list):
        raise ValueError('style definitions require diagnostics')
    from .component_defaults import validate_component_defaults
    validate_component_defaults(value.get('componentDefaults', {}))
    from ui_migration.contracts.style_tokens import validate_token_mappings
    validate_token_mappings(value.get('tokenMappings', {}))
    return value


def load_style_definitions(path: Path) -> dict:
    return validate_style_definitions(json.loads(path.read_text(encoding='utf-8')))


def prepare_style_definitions(contract_path: Path, output: Path, *, refresh: bool = False) -> dict:
    if output.exists() and not refresh:
        return load_style_definitions(output)
    previous = load_style_definitions(output) if output.exists() else None
    value = build_style_definitions(json.loads(contract_path.read_text(encoding='utf-8')))
    if previous:
        value['componentDefaults'] = copy.deepcopy(previous.get('componentDefaults', {}))
        value['tokenMappings'] = copy.deepcopy(previous.get('tokenMappings', {}))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return value
