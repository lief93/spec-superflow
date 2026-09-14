#!/usr/bin/env bash
set -euo pipefail
tests=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$tests/../.." && pwd)
mkdir -p "$tests/.build"
run=$(mktemp -d "$tests/.build/loop-symbols.XXXXXX")
printf 'Loop adapter symbol evidence: %s\n' "$run"
sources=()
while IFS= read -r file; do sources+=("$file"); done < <(find "$root/src" -name '*.kt' -type f | sort)
bash "$tests/compiler.sh" -d "$run/probe.jar" "${sources[@]}" "$tests/LoopAdapterSymbols.kt" \
  > "$run/compiler.stdout" 2> "$run/compiler.stderr"
cp=$(bash "$tests/compiler.sh" --classpath)
java -cp "$cp:$run/probe.jar" dev.ets.tests.stdlib.LoopAdapterSymbolsKt \
  "$tests/fixtures/LoopAdapters.kt" "$cp" > "$run/test.stdout" 2> "$run/test.stderr"
cat "$run/test.stdout"
