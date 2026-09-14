#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
mkdir -p "$HERE/.work"
WORK="$(mktemp -d "$HERE/.work/contract-XXXXXX")"
printf 'Evidence: %s\n' "$WORK"
bash "$ROOT/tests/stdlib/compiler.sh" "$ROOT"/src/target/*.kt "$ROOT/src/output/Modules.kt" \
  "$HERE/ModuleContract.kt" -d "$WORK/contract.jar" > "$WORK/compile.stdout" 2> "$WORK/compile.stderr"
CP="$(bash "$ROOT/tests/stdlib/compiler.sh" --classpath)"
java -cp "$CP:$WORK/contract.jar" dev.ets.ModuleContractKt | tee "$WORK/test.stdout"
