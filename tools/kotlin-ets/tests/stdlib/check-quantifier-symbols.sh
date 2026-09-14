#!/usr/bin/env bash
set -euo pipefail
export JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'
tests=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$tests/../.." && pwd)
mkdir -p "$tests/.build"
run=$(mktemp -d "$tests/.build/quantifier-symbols.XXXXXX")
printf 'Quantifier isolated symbol evidence: %s\n' "$run"
bash "$tests/compiler.sh" -d "$run/probe.jar" \
  "$root/src/target/Tree.kt" "$root/src/core/Contract.kt" \
  "$root/src/stdlib/StandardLibraryRules.kt" "$root/src/stdlib/StandardLibrarySupport.kt" \
  "$root/src/stdlib/IterationRules.kt" "$tests/QuantifierSymbols.kt" > "$run/compiler.stdout" 2> "$run/compiler.stderr"
cp=$(bash "$tests/compiler.sh" --classpath)
java -cp "$cp:$run/probe.jar" dev.ets.tests.stdlib.QuantifierSymbolsKt \
  -no-stdlib -no-reflect -classpath "$cp" -d "$run/unused" \
  "$tests/fixtures/quantifiers/QuantifierLibrary.kt" "$tests/fixtures/quantifiers/QuantifierRejected.kt" \
  > "$run/probe.stdout" 2> "$run/probe.stderr"
cat "$run/probe.stdout"
