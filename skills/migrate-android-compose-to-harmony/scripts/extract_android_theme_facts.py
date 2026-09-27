#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import gzip
import json
from pathlib import Path
import sys

from compose_theme_facts import validate_compose_theme_facts
from page_snapshot import COMMAND_SCHEMA, PageSnapshotError, write_new_json


MARKER = "ANDROID_THEME_FACTS:"
COMPRESSED_MARKER = "ANDROID_THEME_FACTS_GZIP_BASE64:"
MAX_INPUT_BYTES = 10 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract one validated Android Compose runtime-theme record from stdin."
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        print("input exceeds 10 MiB", file=sys.stderr)
        return 1
    try:
        log = raw.decode("utf-8")
        records = [
            ("plain", line.partition(MARKER)[2])
            for line in log.splitlines()
            if MARKER in line
        ] + [
            ("gzip-base64", line.partition(COMPRESSED_MARKER)[2])
            for line in log.splitlines()
            if COMPRESSED_MARKER in line
        ]
        if len(records) != 1:
            raise PageSnapshotError(
                f"expected exactly one {MARKER.rstrip(':')} record; found {len(records)}"
            )
        encoding, record = records[0]
        try:
            if encoding == "gzip-base64":
                decoded = gzip.decompress(base64.b64decode(record, validate=True))
                if len(decoded) > MAX_INPUT_BYTES:
                    raise PageSnapshotError("decompressed Android theme marker exceeds 10 MiB")
                record = decoded.decode("utf-8")
            payload = json.loads(record)
        except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PageSnapshotError("Android theme marker does not contain valid JSON") from error
        normalized = validate_compose_theme_facts(payload)
        output, digest = write_new_json(args.output, normalized)
    except (UnicodeDecodeError, OSError, PageSnapshotError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "schema": COMMAND_SCHEMA,
        "platform": "android",
        "theme_id": normalized["theme_id"],
        "output": str(output),
        "sha256": digest,
        "color_count": len(normalized["theme"]["colors"]),
        "typography_count": len(normalized["theme"]["typography"]),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
