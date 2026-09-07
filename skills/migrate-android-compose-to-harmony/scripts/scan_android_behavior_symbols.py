#!/usr/bin/env python3
"""Check configured Kotlin behavior symbols against a source inventory."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def signature(text: str, declaration: str) -> str:
    match = re.search(declaration, text)
    if match is None:
        raise ValueError(f"declaration not found: {declaration}")
    opening = text.find("{", match.start())
    if opening < 0:
        raise ValueError(f"opening brace not found: {declaration}")
    return text[match.start() : opening]


def class_body(text: str, class_name: str) -> str:
    match = re.search(rf"\bclass\s+{re.escape(class_name)}\b", text)
    if match is None:
        raise ValueError(f"class not found: {class_name}")
    opening = text.find("{", match.end())
    if opening < 0:
        raise ValueError(f"class body not found: {class_name}")
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise ValueError(f"class body is not balanced: {class_name}")


def extract(group: dict[str, Any], source_root: Path) -> list[str]:
    source = source_root / group["file"]
    text = source.read_text(encoding="utf-8")
    kind = group["kind"]
    symbol = group["symbol"]
    if kind == "function_parameters":
        block = signature(text, rf"\bfun\s+{re.escape(symbol)}\s*\(")
        names = re.findall(r"^\s*([A-Za-z_]\w*)\s*:", block, re.MULTILINE)
    elif kind == "class_public_functions":
        block = class_body(text, symbol)
        names = re.findall(r"^\s{4}fun\s+([A-Za-z_]\w*)\s*\(", block, re.MULTILINE)
    elif kind == "data_class_fields":
        block = signature(text, rf"\bdata\s+class\s+{re.escape(symbol)}\s*\(")
        names = re.findall(r"^\s*val\s+([A-Za-z_]\w*)\s*:", block, re.MULTILINE)
    else:
        raise ValueError(f"unsupported extractor kind: {kind}")
    pattern = re.compile(group["name_pattern"])
    return sorted({name for name in names if pattern.search(name)})


def scan(
    config: dict[str, Any], source_root: Path, inventory: dict[str, Any]
) -> dict[str, Any]:
    discovered = sorted(
        f"{group['id']}:{name}"
        for group in config["groups"]
        for name in extract(group, source_root)
    )
    mapping = config["mapping"]
    inventory_ids = {item["id"] for item in inventory["items"]}
    unmapped = sorted(set(discovered) - mapping.keys())
    stale = sorted(mapping.keys() - set(discovered))
    unknown_inventory_refs = sorted(
        {
            inventory_id
            for references in mapping.values()
            for inventory_id in references
            if inventory_id not in inventory_ids
        }
    )
    return {
        "schema": "android-to-harmony.behavior-symbol-scan.v1",
        "verdict": "pass"
        if not unmapped and not stale and not unknown_inventory_refs
        else "fail",
        "scope_id": inventory.get("scope_id"),
        "source_revision": inventory.get("source_revision"),
        "symbol_count": len(discovered),
        "mapped_symbol_count": len(discovered) - len(unmapped),
        "symbols": discovered,
        "unmapped_symbols": unmapped,
        "stale_mappings": stale,
        "unknown_inventory_refs": unknown_inventory_refs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = scan(config, args.source_root, inventory)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as error:
        result = {
            "schema": "android-to-harmony.behavior-symbol-scan.v1",
            "verdict": "fail",
            "error": str(error),
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
