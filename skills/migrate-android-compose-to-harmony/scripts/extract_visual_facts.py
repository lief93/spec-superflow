#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from page_snapshot import (
    COMMAND_SCHEMA,
    PageSnapshotError,
    validate_visual_facts_payload,
    write_new_json,
)


MAX_INPUT_BYTES = 10 * 1024 * 1024


def extract(log: str, marker: str, platform: str) -> dict[str, object]:
    records = [line.partition(marker)[2] for line in log.splitlines() if marker in line]
    if len(records) != 1:
        raise PageSnapshotError(f"expected exactly one {marker} record; found {len(records)}")
    try:
        payload = json.loads(records[0])
    except json.JSONDecodeError as error:
        raise PageSnapshotError("visual facts marker does not contain valid JSON") from error
    validate_visual_facts_payload(payload, platform)
    return payload


def main_for_platform(platform: str, marker: str) -> int:
    parser = argparse.ArgumentParser(
        description=f"Extract one validated {platform} component visual-facts inventory from stdin."
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        print("input exceeds 10 MiB", file=sys.stderr)
        return 1
    try:
        payload = extract(raw.decode("utf-8"), marker, platform)
        output, digest = write_new_json(args.output, payload)
    except (UnicodeDecodeError, OSError, PageSnapshotError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema": COMMAND_SCHEMA,
                "platform": platform,
                "output": str(output),
                "sha256": digest,
                "component_count": len(payload["components"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0
