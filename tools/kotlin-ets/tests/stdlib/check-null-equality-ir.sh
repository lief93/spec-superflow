#!/usr/bin/env bash
set -euo pipefail
export JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'
tests=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$tests/../.." && pwd)
mkdir -p "$tests/.build"
run=$(mktemp -d "$tests/.build/null-equality-ir.XXXXXX")
printf 'Full actual IR null-equality evidence: %s\n' "$run"
sources=()
while IFS= read -r file; do sources+=("$file"); done < <(find "$root/src" -name '*.kt' -type f | sort)
bash "$tests/compiler.sh" -d "$run/probe.jar" "${sources[@]}" "$tests/NullEqualityProbe.kt" \
  > "$run/compiler.stdout" 2> "$run/compiler.stderr"
cp=$(bash "$tests/compiler.sh" --classpath)
java -cp "$cp:$run/probe.jar" dev.ets.tests.stdlib.NullEqualityProbeKt "$run" \
  -no-stdlib -no-reflect -classpath "$cp" \
  "$tests/fixtures/quantifiers/QuantifierLibrary.kt" "$tests/fixtures/quantifiers/QuantifierCases.kt" \
  "$tests/fixtures/quantifiers/NullEquality.kt" > "$run/probe.stdout" 2> "$run/probe.stderr"
cat "$run/probe.stdout"
