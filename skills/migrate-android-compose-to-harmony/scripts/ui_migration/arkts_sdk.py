"""Locate the shared, read-only ArkTS syntax parser runtime."""
import os
from pathlib import Path
import shutil


def parser_runtime():
    home = Path(os.environ.get('DEVECO_HOME', '/Applications/DevEco-Studio.app'))
    contents = home/'Contents' if (home/'Contents').is_dir() else home
    node = os.environ.get('ARKTS_NODE') or shutil.which('node') or str(contents/'tools/node/bin/node')
    explicit = os.environ.get('ARKTS_TYPESCRIPT_PATH')
    candidates = [Path(explicit)] if explicit else [
        contents/'sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript',
    ]
    if not explicit and os.environ.get('DEVECO_SDK_HOME'):
        sdk = Path(os.environ['DEVECO_SDK_HOME'])
        candidates = [sdk/'ets/build-tools/ets-loader/node_modules/typescript',
            sdk/'openharmony/ets/build-tools/ets-loader/node_modules/typescript',
            sdk/'default/openharmony/ets/build-tools/ets-loader/node_modules/typescript', *candidates]
    compiler = next((p for p in candidates if p.exists()), None)
    if compiler is None or not (shutil.which(node) or Path(node).is_file()):
        raise ValueError('ArkTS output/discovery needs the SDK parser: set ARKTS_TYPESCRIPT_PATH and ARKTS_NODE (or DEVECO_HOME)')
    return node, str(compiler)
