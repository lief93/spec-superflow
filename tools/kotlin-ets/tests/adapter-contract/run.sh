#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/kotlin-ets-adapter-contract.XXXXXX")"
printf 'Evidence: %s\n' "$WORK"
CP="$(bash "$ROOT/tests/stdlib/compiler.sh" --classpath)"
bash "$ROOT/tests/stdlib/compiler.sh" "$ROOT"/src/target/*.kt \
  "$ROOT/src/core/Contract.kt" "$ROOT/src/adapters/AdapterModules.kt" \
  "$ROOT/tests/adapter-contract/AdapterContractTest.kt" -d "$WORK/test.jar" \
  > "$WORK/compile.stdout" 2> "$WORK/compile.stderr"
java -cp "$CP:$WORK/test.jar" dev.ets.AdapterContractTestKt
