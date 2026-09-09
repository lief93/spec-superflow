from __future__ import annotations
import json
import re
from typing import Any
from ui_migration.frontend.model import QUOTED_STRING_PATTERN, STRING_RESOURCE_PATTERN


def decode_literal(expression: str) -> str | None:
    match = QUOTED_STRING_PATTERN.fullmatch(expression.strip())
    if match is None:
        return None
    try:
        return json.loads(expression.strip())
    except json.JSONDecodeError:
        return match.group(1)


def resolve_text(expression: str, values: dict[tuple[str, str], str]) -> str | None:
    literal = decode_literal(expression)
    if literal is not None:
        return literal
    match = STRING_RESOURCE_PATTERN.search(expression)
    if match is not None:
        return values.get(("string", match.group(1)))
    return None


def bind_source_expression(expression: str, parameter_bindings: dict[str, str] | None) -> str:
    """Expand arguments through the same PSI scope used for selected page values."""
    if not parameter_bindings:
        return expression
    from kotlin_psi import KotlinPsiSyntaxError, parse_expression
    from ui_migration.frontend.values import value_resolver
    from ui_migration.semantics.expressions import LayoutExpressionError

    try:
        return value_resolver(parameter_bindings, {}).render(parse_expression(expression))
    except (LayoutExpressionError, KotlinPsiSyntaxError):
        # Preserve the unknown expression for the selected-state diagnostic pass.
        return expression


bind_modifier_sizes = bind_source_expression


def resolved_dp_expression(expression: str, parameter_bindings: dict[str, str]) -> float | None:
    from kotlin_psi import KotlinPsiSyntaxError, parse_expression
    from ui_migration.frontend.values import value_resolver
    from ui_migration.semantics.expressions import LayoutDimension, LayoutExpressionError

    try:
        value = value_resolver(parameter_bindings, {}).value(parse_expression(expression))
        return value.value if isinstance(value, LayoutDimension) and value.unit == 'dp' else None
    except (LayoutExpressionError, KotlinPsiSyntaxError):
        return None


def resolved_shadow_elevation(
    expression: str,
    parameter_bindings: dict[str, str] | None,
) -> float | None:
    if re.search(r"(?:shadow|elevation)", expression, re.IGNORECASE) is None:
        return None
    value_pattern = r"(-?[0-9]+(?:\.[0-9]+)?\.dp|[A-Za-z_][A-Za-z0-9_]*)"
    patterns = [rf"\belevation\s*=\s*{value_pattern}"]
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*Elevation\s*\(", expression):
        patterns.append(rf"\brequiredSize\s*=\s*{value_pattern}")
    patterns.append(rf"\.shadow\s*\(\s*{value_pattern}")
    for pattern in patterns:
        match = re.search(pattern, expression)
        if match is None:
            continue
        value = resolved_dp_expression(match.group(1), parameter_bindings or {})
        if value is not None and value >= 0:
            return round(value, 3)
    return None


def resolve_constraint_branch(
    expression: str,
    parameter_bindings: dict[str, str],
) -> tuple[str, str]:
    body = expression.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1].strip()
    branch_pattern = re.compile(
        r"if\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=)\s*null\s*\)\s*"
        r"\{([^{}]*)\}\s*else\s*\{([^{}]*)\}"
    )
    resolved_any = False
    while True:
        match = branch_pattern.search(body)
        if match is None:
            break
        binding = parameter_bindings.get(match.group(1))
        if binding is None:
            return body, "unresolved_condition"
        is_null = binding.strip() == "null"
        condition = is_null if match.group(2) == "==" else not is_null
        selected = match.group(3) if condition else match.group(4)
        body = body[:match.start()] + selected.strip() + body[match.end():]
        resolved_any = True
    if re.search(r"\bif\s*\(", body):
        return body, "unresolved_condition"
    return body, "resolved_condition" if resolved_any else "not_conditional"


def semantic_expression(call: dict[str, Any], name: str) -> str | None:
    semantic = call.get("semantic_arguments")
    value = semantic.get(name) if isinstance(semantic, dict) else None
    expression = value.get("expression") if isinstance(value, dict) else None
    return expression if isinstance(expression, str) and expression.strip() else None


def first_positional_expression(call: dict[str, Any]) -> str | None:
    return positional_expression(call, 0)


def positional_expression(call: dict[str, Any], index: int) -> str | None:
    positional = call.get("positional_arguments")
    if (
        not isinstance(positional, list)
        or index < 0
        or index >= len(positional)
        or not isinstance(positional[index], dict)
    ):
        return None
    expression = positional[index].get("expression")
    return expression if isinstance(expression, str) and expression.strip() else None


def number(value: str) -> float:
    return round(float(value), 3)


def modifier_dimensions(modifier: dict[str, Any]) -> list[tuple[float, str]]:
    raw = modifier.get("dimensions")
    if not isinstance(raw, list):
        return []
    result: list[tuple[float, str]] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("unit") not in {"dp", "sp"}:
            continue
        value = item.get("value")
        if isinstance(value, str) and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
            result.append((number(value), item["unit"]))
    return result


def direct_padding(arguments: str, dimensions: list[tuple[float, str]]) -> dict[str, float] | None:
    dp_values = [value for value, unit in dimensions if unit == "dp"]
    if not dp_values:
        return None
    named: dict[str, float] = {}
    for name, value in re.findall(
        r"(start|end|left|right|top|bottom|horizontal|vertical|all)\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)\.dp",
        arguments,
    ):
        named[name] = number(value)
    if not named:
        if len(dp_values) == 1:
            return {edge: dp_values[0] for edge in ("left", "top", "right", "bottom")}
        return None
    all_value = named.get("all", 0.0)
    horizontal = named.get("horizontal", all_value)
    vertical = named.get("vertical", all_value)
    return {
        "left": named.get("left", named.get("start", horizontal)),
        "top": named.get("top", vertical),
        "right": named.get("right", named.get("end", horizontal)),
        "bottom": named.get("bottom", vertical),
    }


def bound_modifier_call(call: dict[str, Any], bindings: dict[str, str] | None) -> dict[str, Any]:
    expression = call.get('modifier_expression')
    if not bindings:
        return call
    if not expression:
        candidates = []
        for argument in call.get('positional_arguments') or []:
            candidate = argument.get('expression', '')
            receiver = re.match(r'^([A-Za-z_]\w*)(?:\.|$)', candidate)
            if receiver and re.match(r'^Modifier\b', bind_source_expression(receiver.group(1), bindings)):
                candidates.append(argument)
        if len(candidates) != 1:
            return call
        expression = candidates[0]['expression']
        call = {**call, 'positional_arguments': [a for a in call.get('positional_arguments', []) if a is not candidates[0]]}
    if not isinstance(expression, str):
        return call
    match = re.match(r'^\s*([A-Za-z_]\w*)\b', expression)
    if match is None or match.group(1) not in bindings:
        return call
    receiver = bind_source_expression(match.group(1), bindings)
    if not re.match(r'^Modifier\b', receiver):
        return call
    from analyze_compose_project import ordered_modifier_chain
    resolved = receiver + expression[match.end():]
    return {**call, 'modifier_expression': resolved, 'ordered_modifier_chain': ordered_modifier_chain(resolved)}
