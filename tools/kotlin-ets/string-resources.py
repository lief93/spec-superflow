#!/usr/bin/env python3
"""Materialize a bounded string-resource input pack, without reading Kotlin text."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def properties(values):
    def escape(value):
        return (value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
                .replace("\t", "\\t").replace("=", "\\=").replace(":", "\\:"))
    return "".join(f"{escape(key)}={escape(value)}\n" for key, value in sorted(values.items()))


def materialize(source, namespace, output):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", namespace):
        raise ValueError("namespace must be a Java package name")
    if not source.is_dir() or source.is_symlink():
        raise ValueError("res-dir must be a real directory")
    if source == output or source in output.parents:
        raise ValueError("out must not be inside res-dir")
    packs, errors = {}, {}
    seen = set()
    for directory in sorted(source.glob("values*")):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Invalid resource directory: {directory}")
        qualifier = "base" if directory.name == "values" else None
        match = re.fullmatch(r"values-([a-z]{2})(?:-r([A-Z]{2}))?", directory.name)
        if match:
            qualifier = match[1] + ("_" + match[2] if match[2] else "")
        for file in sorted(directory.glob("*.xml")):
            if file.is_symlink():
                raise ValueError(f"Symlink resource file: {file}")
            root = ET.parse(file).getroot()
            if root.tag != "resources":
                raise ValueError(f"Expected resources XML: {file}")
            for item in root:
                if item.tag != "string" and not (item.tag == "item" and item.get("type") == "string"):
                    continue
                name = item.get("name", "")
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                    raise ValueError(f"Invalid string name {name}: {file}")
                symbol = f"{namespace}.R.string.{name}"
                identity = (directory.name, symbol)
                if identity in seen:
                    raise ValueError(f"Conflicting string resource {symbol}: {directory}")
                seen.add(identity)
                value = item.text or ""
                reason = None
                if qualifier is None:
                    reason = f"unsupported qualifier {directory.name}"
                elif len(item) or any(char in value for char in "\\\"'%") or value.startswith(("@", "?")):
                    reason = "requires styled, escaped, formatted or referenced string semantics"
                elif value != value.strip() or re.search(r"\s{2,}|[\n\r\t]", value):
                    reason = "requires Android whitespace normalization"
                if reason:
                    errors[symbol] = f"{reason}: {file}"
                else:
                    packs.setdefault(qualifier, {})[symbol] = value
    if not packs.get("base"):
        raise ValueError("No plain default strings in selected resource directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    for qualifier, values in packs.items():
        (output / f"{qualifier}.properties").write_text(properties(values), encoding="utf-8")
    (output / "unsupported.properties").write_text(properties(errors), encoding="utf-8")
    return {"output": str(output), "defaultCount": len(packs["base"]), "unsupportedCount": len(errors)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--res-dir", required=True, type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(materialize(args.res_dir.absolute(), args.namespace, args.out.absolute())))
