#!/usr/bin/env python3
"""Materialize one explicitly selected module resource directory's local fonts."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil


def materialize(resources: Path, namespace: str, output: Path):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", namespace):
        raise ValueError("Invalid Android resource namespace")
    if not resources.is_dir():
        raise ValueError("Resource directory does not exist")
    if any(resources.glob("font-*")):
        raise ValueError("Qualified font directories require explicit variant selection")
    entries = {}
    for file in sorted((resources / "font").glob("*")):
        if not file.is_file():
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", file.stem):
            raise ValueError(f"Invalid font resource name: {file.name}")
        symbol = f"{namespace}.R.font.{file.stem}"
        if symbol in entries:
            raise ValueError(f"Duplicate font resource: {symbol}")
        entries[symbol] = file
    output.mkdir(parents=True, exist_ok=False)
    (output / "fonts").mkdir()
    mappings = []
    for symbol, file in entries.items():
        name = hashlib.sha256(symbol.encode()).hexdigest() + file.suffix.lower()
        shutil.copyfile(file, output / "fonts" / name)
        mappings.append(f"{symbol}=fonts/{name}\n")
    (output / "fonts.properties").write_text("".join(mappings), encoding="utf-8")
    return output / "fonts.properties"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--res-dir", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(materialize(args.res_dir, args.namespace, args.out))
