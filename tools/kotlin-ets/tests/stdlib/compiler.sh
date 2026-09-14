#!/usr/bin/env bash
set -euo pipefail

# Test-only entry to the installed official compiler; never downloads dependencies.
stdlib_cache="${HOME}/.gradle/caches/modules-2/files-2.1"
stdlib_cp=""
for artifact in \
  org.jetbrains.kotlin/kotlin-compiler-embeddable/2.1.20 \
  org.jetbrains.kotlin/kotlin-stdlib/2.1.20 \
  org.jetbrains.kotlin/kotlin-script-runtime/2.1.20 \
  org.jetbrains.kotlin/kotlin-reflect/1.6.10 \
  org.jetbrains.kotlin/kotlin-daemon-embeddable/2.1.20 \
  org.jetbrains.intellij.deps/trove4j/1.0.20200330 \
  org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm/1.8.0 \
  org.jetbrains/annotations/13.0; do
  stdlib_name="${artifact%/*}"
  stdlib_name="${stdlib_name##*/}"
  stdlib_jar=$(find "${stdlib_cache}/${artifact}" -name "${stdlib_name}-${artifact##*/}.jar" -print -quit)
  test -n "$stdlib_jar"
  stdlib_cp="${stdlib_cp:+${stdlib_cp}:}${stdlib_jar}"
done
if [[ "${1:-}" == --classpath ]]; then
  printf '%s\n' "$stdlib_cp"
  exit 0
fi
exec java -cp "$stdlib_cp" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -no-stdlib -no-reflect -classpath "$stdlib_cp" "$@"
