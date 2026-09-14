#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
JDK="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
MAVEN="${GRADLE_USER_HOME:-$HOME/.gradle}/caches/modules-2/files-2.1"
jar() { find "$MAVEN/$1/$2/$3" -name "$2-$3.jar" -print -quit; }
STDLIB="$(jar org.jetbrains.kotlin kotlin-stdlib 2.1.20)"
CP="$(jar org.jetbrains.kotlin kotlin-compiler-embeddable 2.1.20):$STDLIB"
CP="$CP:$(jar org.jetbrains.kotlin kotlin-script-runtime 2.1.20):$(jar org.jetbrains.kotlin kotlin-reflect 1.6.10)"
CP="$CP:$(jar org.jetbrains.kotlin kotlin-daemon-embeddable 2.1.20):$(jar org.jetbrains.intellij.deps trove4j 1.0.20200330)"
CP="$CP:$(jar org.jetbrains.kotlinx kotlinx-coroutines-core-jvm 1.8.0):$(jar org.jetbrains annotations 13.0)"
BUILD="$(mktemp -d "${TMPDIR:-/tmp}/kotlin-ets-target-tests.XXXXXX")"
printf 'Evidence: %s\n' "$BUILD"
# Compile and run target nodes without the Kotlin compiler on their own classpath.
"$JDK/bin/java" -Xmx1g -cp "$CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -no-stdlib -no-reflect -classpath "$STDLIB:$(jar org.jetbrains annotations 13.0)" \
  -d "$BUILD/test.jar" "$ROOT"/src/target/*.kt "$ROOT"/tests/target/*.kt \
  > "$BUILD/compile.stdout" 2> "$BUILD/compile.stderr" || { cat "$BUILD/compile.stderr"; exit 1; }
"$JDK/bin/java" -cp "$STDLIB:$BUILD/test.jar" dev.ets.TargetTreeTestKt
