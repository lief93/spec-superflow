from __future__ import annotations
import hashlib
import re
from typing import Any
from ui_migration.frontend.bindings import resolve_constraint_branch, resolved_dp_expression


def source_layout_relationships(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {component["id"]: component for component in components}
    relationships: list[dict[str, Any]] = []
    link_pattern = re.compile(
        r"\b(start|end|top|bottom|baseline)\.linkTo\(\s*"
        r"([A-Za-z_][A-Za-z0-9_]*)\.(start|end|top|bottom|baseline)"
        r"(?:\s*,\s*margin\s*=\s*([^)]+?))?\s*\)"
    )
    center_pattern = re.compile(
        r"\bcenterAround\(\s*([A-Za-z_][A-Za-z0-9_]*)\."
        r"(start|end|top|bottom|baseline)\s*\)"
    )
    for container in components:
        if container["type"] != "ConstraintLayout":
            continue
        constrained: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
        for child_id in container["children_ids"]:
            child = by_id[child_id]
            modifier = next(
                (
                    item
                    for item in child.get("modifiers", [])
                    if isinstance(item, dict) and item.get("name") == "constrainAs"
                ),
                None,
            )
            reference = str(modifier.get("arguments", "")).strip() if modifier else ""
            if modifier is not None and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference):
                constrained.append((child, reference, modifier))
        target_ids = {reference: child["id"] for child, reference, _modifier in constrained}
        target_ids["parent"] = container["id"]
        for child, reference, modifier in constrained:
            raw_expression = modifier.get("trailing_lambda")
            unresolved: list[dict[str, str]] = []
            active_constraints: list[dict[str, Any]] = []
            branch_resolution = "missing_constraint_body"
            active_expression = ""
            bindings = child.get("_parameter_bindings", {})
            if isinstance(raw_expression, str) and raw_expression.strip():
                active_expression, branch_resolution = resolve_constraint_branch(
                    raw_expression,
                    bindings if isinstance(bindings, dict) else {},
                )
                matches: list[tuple[int, dict[str, Any]]] = []
                for match in link_pattern.finditer(active_expression):
                    target_reference = match.group(2)
                    target_id = target_ids.get(target_reference)
                    if target_id is None:
                        unresolved.append({
                            "expression": match.group(0),
                            "reason": "constraint target reference is not a sibling or parent",
                        })
                        continue
                    margin_expression = match.group(4).strip() if match.group(4) else None
                    margin_dp = (
                        resolved_dp_expression(margin_expression, bindings)
                        if margin_expression is not None and isinstance(bindings, dict)
                        else 0.0
                    )
                    if margin_expression is not None and margin_dp is None:
                        unresolved.append({
                            "expression": margin_expression,
                            "reason": "constraint margin is not a resolved dp value",
                        })
                    matches.append((match.start(), {
                        "kind": "link_to",
                        "subject_anchor": match.group(1),
                        "target_id": target_id,
                        "target_reference": target_reference,
                        "target_anchor": match.group(3),
                        "margin_expression": margin_expression,
                        "margin_dp": margin_dp,
                    }))
                for match in center_pattern.finditer(active_expression):
                    target_reference = match.group(1)
                    target_id = target_ids.get(target_reference)
                    if target_id is None:
                        unresolved.append({
                            "expression": match.group(0),
                            "reason": "constraint target reference is not a sibling or parent",
                        })
                        continue
                    matches.append((match.start(), {
                        "kind": "center_around",
                        "subject_anchor": "center",
                        "target_id": target_id,
                        "target_reference": target_reference,
                        "target_anchor": match.group(2),
                        "margin_expression": None,
                        "margin_dp": 0.0,
                    }))
                active_constraints = [item for _position, item in sorted(matches)]
                if not active_constraints:
                    unresolved.append({
                        "expression": raw_expression,
                        "reason": "no supported active ConstraintLayout relationship was resolved",
                    })
            else:
                unresolved.append({
                    "expression": f"constrainAs({reference})",
                    "reason": "constraint body is missing from the source contract",
                })
            overlays_sibling = any(
                constraint["target_id"] != container["id"]
                and (
                    constraint["kind"] == "center_around"
                    or (
                        isinstance(constraint.get("margin_dp"), (int, float))
                        and constraint["margin_dp"] < 0
                    )
                )
                for constraint in active_constraints
            )
            relationships.append({
                "id": "layout-" + hashlib.sha256(
                    f"{container['id']}\0{child['id']}\0{reference}".encode("utf-8")
                ).hexdigest()[:20],
                "container_id": container["id"],
                "container_type": "ConstraintLayout",
                "subject_id": child["id"],
                "subject_reference": reference,
                "composition": "overlay" if overlays_sibling else "constraint",
                "draw_order": child["sibling_index"],
                "source_expression": raw_expression or "",
                "branch_resolution": branch_resolution,
                "active_constraints": active_constraints,
                "unresolved": unresolved,
            })
    return relationships


def select_most_specific_surface_owner(
    owner_matches: list[tuple[int, int, str, list[dict[str, Any]]]],
) -> tuple[int, int, str, list[dict[str, Any]]]:
    return max(owner_matches, key=lambda item: (item[1], item[0], item[2]))


def surface_height_matches_source(
    candidate_height_px: int,
    density: float,
    fixed_heights_dp: set[float],
) -> bool:
    if not fixed_heights_dp:
        return True
    candidate_height_dp = candidate_height_px / density
    return min(
        abs(candidate_height_dp - fixed_height_dp)
        for fixed_height_dp in fixed_heights_dp
    ) <= 2.0
