#!/usr/bin/env bash
set -euo pipefail
tests=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$tests/../.." && pwd)
mkdir -p "$tests/.build"
run=$(mktemp -d "$tests/.build/runtime-tree.XXXXXX")
printf 'Typed dependency evidence: %s\n' "$run"
bash "$tests/compiler.sh" -d "$run/test.jar" \
  "$root/src/target/Tree.kt" "$root/src/target/Traversal.kt" "$root/src/stdlib/StandardLibrarySupport.kt" \
  "$root/src/stdlib/StandardLibraryDependencies.kt" "$tests/RuntimeDependencies.kt" \
  "$root/src/target/TypeSubstitution.kt" "$root/src/target/Validator.kt" \
  "$root/src/target/Printer.kt" "$root/src/output/Modules.kt" \
  > "$run/compiler.stdout" 2> "$run/compiler.stderr"
cp=$(bash "$tests/compiler.sh" --classpath)
java -cp "$cp:$run/test.jar" dev.ets.tests.stdlib.RuntimeDependenciesKt | tee "$run/test.stdout"
