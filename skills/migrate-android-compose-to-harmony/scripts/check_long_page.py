#!/usr/bin/env python3
"""Capture/compare a configured page state. Exit 0 pass, 1 fail, 2 invalid evidence."""
import argparse
import json
import subprocess
from pathlib import Path

from ui_migration.verification.long_page import evaluate
from ui_migration.verification.scroll_capture import capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    for command in ('capture','compare'):
        p = sub.add_parser(command)
        p.add_argument('--config',type=Path,required=True)
        p.add_argument('--output',type=Path,required=True)
        if command == 'capture':
            p.add_argument('--platform',choices=['android','harmony'],required=True)
        else:
            p.add_argument('--android',type=Path,required=True)
            p.add_argument('--harmony',type=Path,required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
        if args.command == 'capture':
            result = capture(config,args.platform,args.output)
            passed = all(s=='end_observed' for s in result['stream_status'].values())
            summary = {'acquisition_complete':passed,'visual_acceptance':'not_evaluated','streams':result['stream_status']}
        else:
            result = evaluate(config,args.android,args.harmony,args.output)
            passed = result['verdict']=='pass'
            summary = {k:result[k] for k in ('verdict','expected','complete','passed')}
        print(json.dumps(summary))
        return 0 if passed else 1
    except (ValueError,KeyError,OSError,TypeError,subprocess.SubprocessError) as error:
        print(json.dumps({'verdict':'fail','invalid_evidence':True,'error':str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
