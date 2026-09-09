from __future__ import annotations
from typing import Any
from ui_migration.contracts.runtime_overlay import nested_value
from ui_migration.contracts.requirements import merge_requirement_facts, requirement_context


def target_fact_phase(path: str) -> str:
    if path == 'style.input.single_line':
        return 'measure'
    if path in {
        'style.content.text', 'style.content.placeholder',
        'style.typography.font_size_sp', 'style.typography.font_weight',
        'style.typography.font_style', 'style.typography.font_family',
        'style.typography.letter_spacing_sp', 'style.typography.line_height_sp',
        'style.typography.max_lines', 'style.typography.overflow',
        'style.typography.min_lines', 'style.typography.soft_wrap',
        'style.typography.include_font_padding', 'style.typography.line_height_alignment',
        'style.typography.line_height_trim',
        'style.typography.line_break',
    }:
        return 'measure'
    if path == 'style.typography.text_align':
        return 'layout'
    if path.startswith("source.modifiers.") and path.rsplit(".", 1)[-1] in {"fillmaxwidth", "fillmaxheight", "fillmaxsize", "matchparentsize", "wrapcontentwidth", "wrapcontentheight", "wrapcontentsize", "width", "height", "size", "widthin", "heightin", "sizein", "weight", "padding", "absolutepadding", "aspectratio", "defaultminsize", "verticalscroll", "horizontalscroll"}:
        return "measure"
    if path in {"source.modifiers.zindex", "style.layout.z_index"} or (
        path.startswith('source.modifiers.') and path.rsplit('.', 1)[-1] in {
            'background', 'border', 'clip', 'alpha', 'shadow', 'rotate', 'scale'
        }
    ):
        return "draw"
    if path in {"style.layout.alignment", "style.layout.horizontal_arrangement", "style.layout.vertical_arrangement", "style.layout.layout_direction", "style.layout.margin_dp"}:
        return "layout"
    if path.startswith("style.layout.") or path in {
        "style.asset.width_dp", "style.asset.height_dp"
    }:
        return "measure"
    if path.startswith("structure.") or path.startswith("source.modifiers."):
        return "layout"
    return "draw"


def build_target_phase_consumption_gate(
    page_input: dict[str, Any] | None,
    processed_component_ids: set[str],
    processed_call_ids: set[str],
    applied_paths: dict[str, set[str]],
    applied_component_paths: dict[str, set[str]] | None = None,
    layout_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if page_input is None:
        return None
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    layout_decisions = layout_decisions or []
    nodes = {c.get('id'): c for c in page_input.get('components') or []}
    for component in page_input.get("components") or []:
        source = component.get("source")
        call_id = source.get("call_id") if isinstance(source, dict) else None
        rendered = component.get("id") in processed_component_ids
        # A shared source call may have several differently configured instances.
        # Another instance's emitted field is not evidence for this component.
        call_paths: set[str] = set()
        if applied_component_paths is not None:
            call_paths.update(applied_component_paths.get(str(component.get("id")), set()))
        candidate_facts: dict[str, dict[str, Any]] = {}
        for fact in merge_requirement_facts(component, nodes):
            if not isinstance(fact, dict) or (fact.get("status") == "not_applicable" and fact.get('origin') != 'semantic_contract'):
                continue
            path = fact.get("path")
            if not isinstance(path, str):
                continue
            candidate_facts[path] = {
                "path": path,
                "expression": fact.get("expression"),
                "origin": "required_fact",
                "source_status": fact.get("status"),
                "resolved": fact.get("status") in {"resolved", "default_resolved", "not_applicable"},
                "semantic_not_applicable": fact.get('status') == 'not_applicable',
                "reason": fact.get('reason'),
            }
        style = component.get("style")
        if isinstance(style, dict):
            for section_name, section in style.items():
                if not isinstance(section, dict):
                    continue
                for field_name, value in section.items():
                    if value is None or value == [] or value == {}:
                        continue
                    path = f"style.{section_name}.{field_name}"
                    candidate_facts.setdefault(path, {
                        "path": path,
                        "expression": None,
                        "origin": "resolved_style",
                    })
        for fact in candidate_facts.values():
            path = fact["path"]
            phase = target_fact_phase(path)
            decisions = [d for d in layout_decisions if d['component_id'] == component.get('id') and d['path'] == path]
            not_applicable = fact.get('semantic_not_applicable', False) or (
                path == "style.content.content_description"
                and fact.get("expression") == "null"
            ) or (
                path in {"style.state.selected", "style.state.checked"}
                and nested_value(component, path) is False
                and rendered
            ) or (
                path == "style.state.clickable"
                and rendered
                # The page renderer owns visuals, not the behavior contract.
                # Keep this boundary in the report instead of dropping the field.
            ) or (
                path == "style.asset.sha256"
                and "style.asset.resource" in call_paths
            ) or (
                path in {"style.asset.width_dp", "style.asset.height_dp"}
                and fact["origin"] == "resolved_style"
                and "style.asset.resource" in call_paths
                and all(
                    f"style.layout.{axis}_dp" in call_paths
                    or any(
                        f"source.modifiers.{name}" in call_paths
                        for name in (f"fillmax{axis}", "fillmaxsize", "matchparentsize")
                    )
                    for axis in ("width", "height")
                )
            ) or (
                path == "style.surface.clip"
                and nested_value(component, path) is False
                and rendered
            ) or (
                path == "style.surface.alpha"
                and nested_value(component, path) == 1
                and rendered
            ) or (
                path == "style.state.visible"
                and nested_value(component, path) is True
                and rendered
            ) or (
                path == "style.transform.rotation_degrees"
                and nested_value(component, path) == 0
                and rendered
            ) or (
                path == "style.content.role"
                and rendered
            )
            consumed = ((rendered and path in call_paths) or not_applicable) and fact.get("resolved", True)
            if any(d['outcome'] == 'unresolved' for d in decisions):
                consumed = False
            check = {
                "component_id": component.get("id"),
                "component_type": component.get("type"),
                "context": requirement_context(component, nodes),
                "call_id": call_id,
                "phase": phase,
                "path": path,
                "origin": fact["origin"],
                "source_status": fact.get("source_status", "resolved_style"),
                "expression": fact.get("expression"),
                "reason": fact.get('reason'),
                "status": "not_applicable" if not_applicable else (
                    "consumed" if consumed else "unconsumed"
                ),
            }
            if decisions:
                check['decisions'] = decisions
            if path == "style.state.clickable":
                check["reason"] = "interaction metadata only; click handlers require the separate behavior contract"
            checks.append(check)
            if not consumed:
                failures.append(check)
    return {
        "schema": "android-to-harmony.target-phase-gate.v1",
        "verdict": "pass" if not failures else "fail",
        "phase_order": ["measure", "layout", "draw"],
        "check_count": len(checks),
        "failure_count": len(failures),
        "status_counts": {
            status: sum(item["status"] == status for item in checks)
            for status in ("consumed", "not_applicable", "unconsumed")
        },
        "failures": failures,
        "checks": checks,
        "layout_decisions": layout_decisions,
    }
