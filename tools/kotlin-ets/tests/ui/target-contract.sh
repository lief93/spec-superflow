#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/kotlin-ets-target-ui.XXXXXX")"
printf 'Evidence: %s\n' "$WORK"
bash "$ROOT/tests/stdlib/compiler.sh" "$ROOT"/src/target/*.kt "$ROOT/src/output/Modules.kt" \
  "$HERE/TargetUiContract.kt" -d "$WORK/test.jar" > "$WORK/compile.stdout" 2> "$WORK/compile.stderr"
CP="$(bash "$ROOT/tests/stdlib/compiler.sh" --classpath)"
java -cp "$CP:$WORK/test.jar" dev.ets.TargetUiContractKt | tee "$WORK/test.stdout"
