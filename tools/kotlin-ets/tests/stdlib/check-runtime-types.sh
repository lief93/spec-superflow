#!/usr/bin/env bash
set -euo pipefail
export JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'
tests=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$tests/../.." && pwd)
mkdir -p "$tests/.build"
run=$(mktemp -d "$tests/.build/runtime-types.XXXXXX")
printf 'Runtime type evidence: %s\n' "$run"
bash "$tests/compiler.sh" -d "$run/probe.jar" "$root/src/target/Tree.kt" "$root/src/target/Traversal.kt" \
  "$root/src/stdlib/StandardLibrarySupport.kt" "$root/src/stdlib/StandardLibraryDependencies.kt" \
  "$tests/RuntimeTypes.kt" > "$run/compiler.stdout" 2> "$run/compiler.stderr"
cp=$(bash "$tests/compiler.sh" --classpath)
java -cp "$cp:$run/probe.jar" dev.ets.tests.stdlib.RuntimeTypesKt > "$run/test.stdout" 2> "$run/test.stderr"
cat "$run/test.stdout"
