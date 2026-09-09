#!/usr/bin/env python3
"""Extract project styles once from the analyzed contract, or explicitly refresh."""
import argparse
import json

from pathlib import Path
from ui_migration.frontend.project_styles import prepare_style_definitions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--refresh', action='store_true', help='Replace existing styles from the current contract.')
    args = parser.parse_args()
    reused = args.output.exists() and not args.refresh
    try:
        styles = prepare_style_definitions(args.contract, args.output, refresh=args.refresh)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')
    print(json.dumps({'status': 'reused' if reused else 'written', 'output': str(args.output.resolve()),
                      'colors': len(styles['theme']['colors']), 'textStyles': len(styles['theme']['textStyles']),
                      'diagnostics': styles['diagnostics']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
