#!/usr/bin/env bash
set -euo pipefail
stdlib_tests=$(cd "$(dirname "$0")" && pwd)
stdlib_root=$(cd "$stdlib_tests/../.." && pwd)
mkdir -p "$stdlib_tests/.build"
bash "$stdlib_tests/compiler.sh" -d "$stdlib_tests/.build/probe.jar" \
  "$stdlib_root/src/target/Tree.kt" "$stdlib_root/src/target/Traversal.kt" \
  "$stdlib_root/src/target/TypeSubstitution.kt" "$stdlib_root/src/target/Validator.kt" \
  "$stdlib_root/src/core/Contract.kt" "$stdlib_root/src/stdlib/StandardLibraryRules.kt" \
  "$stdlib_root/src/stdlib/StandardLibrarySupport.kt" \
  "$stdlib_root/src/stdlib/IterationRules.kt" \
  "$stdlib_tests/ResolvedCalls.kt"
stdlib_cp=$(bash "$stdlib_tests/compiler.sh" --classpath)
java -cp "${stdlib_cp}:${stdlib_tests}/.build/probe.jar" dev.ets.tests.stdlib.ResolvedCallsKt 0 \
  -no-stdlib -no-reflect -classpath "$stdlib_cp" -d "$stdlib_tests/.build/unused" \
  "$stdlib_tests/fixtures/Scalars.kt" "$stdlib_tests/fixtures/Lists.kt" "$stdlib_tests/fixtures/FilterSymbols.kt"
java -cp "${stdlib_cp}:${stdlib_tests}/.build/probe.jar" dev.ets.tests.stdlib.ResolvedCallsKt 6 \
  -no-stdlib -no-reflect -classpath "$stdlib_cp" -d "$stdlib_tests/.build/unused" \
  "$stdlib_tests/fixtures/Unsupported.kt"
