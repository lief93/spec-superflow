#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/kotlin-ets-reactive-builders.XXXXXX")"
printf 'Evidence: %s\n' "$WORK"
CP="$(bash "$ROOT/tests/stdlib/compiler.sh" --classpath)"
SOURCES=()
while IFS= read -r source; do SOURCES+=("$source"); done < <(find "$ROOT/src" -name '*.kt' -type f)
bash "$ROOT/tests/stdlib/compiler.sh" -d "$WORK/test.jar" "${SOURCES[@]}" \
  "$ROOT/tests/ui/async-request/ReactiveBuilderTest.kt" > "$WORK/compile.log" 2>&1 || { cat "$WORK/compile.log"; exit 1; }
java -cp "$WORK/test.jar:$CP" dev.ets.ReactiveBuilderTestKt | tee "$WORK/test.stdout"
