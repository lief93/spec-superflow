#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/tests/backend"
JDK="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
export PATH="$JDK/bin:$PATH"
CP="$(bash "$ROOT/tests/stdlib/compiler.sh" --classpath)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/kotlin-ets-backend-tests.XXXXXX")"
printf 'Evidence: %s\n' "$WORK"
run() {
  local label="$1"
  shift
  printf '%q ' "$@" >> "$WORK/commands.log"
  printf '\n' >> "$WORK/commands.log"
  local status=0
  "$@" > "$WORK/$label.stdout" 2> "$WORK/$label.stderr" || status=$?
  printf '%s\n' "$status" > "$WORK/$label.exit"
  if [[ "$status" != 0 ]]; then cat "$WORK/$label.stdout" "$WORK/$label.stderr"; exit "$status"; fi
}
SOURCES=()
while IFS= read -r file; do SOURCES+=("$file"); done < <(find "$ROOT/src/core" "$ROOT/src/lower" "$ROOT/src/language" "$ROOT/src/stdlib" -name '*.kt' ! -name Main.kt | sort)
IFS=: read -r -a DEPENDENCIES <<< "$CP"
shasum -a 256 "${SOURCES[@]}" "$ROOT"/src/target/*.kt "$HERE"/* \
  "$ROOT/tests/stdlib/compiler.sh" "${DEPENDENCIES[@]}" > "$WORK/input-sha256.txt"
run java-version "$JDK/bin/java" -version
run node-version node --version
compile() {
  local label="$1"
  shift
  run "$label" "$JDK/bin/java" -Xmx2g -cp "$CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -no-reflect "$@"
}
# Neither compile-time nor runtime lower classpaths contain EtsPrinter or UI.
compile lower-compile -classpath "$CP" -d "$WORK/lower.jar" "${SOURCES[@]}" \
  "$ROOT/src/target/Tree.kt" "$ROOT/src/target/TypeSubstitution.kt" "$ROOT/src/target/Validator.kt" "$ROOT/src/target/Traversal.kt" "$HERE/BackendContract.kt"
run lower "$JDK/bin/java" -Xmx2g -cp "$CP:$WORK/lower.jar" dev.ets.tests.backend.BackendContractKt \
  "$CP" "$HERE/Original.kt" "$HERE/Renamed.kt"
# Printer.kt smart-casts `EtsCall.callee`; that is a public Tree API property, so
# split compilation against lower.jar cannot smart-cast it. Compile Tree with
# Printer in one module. Frozen Printer.kt is unchanged.
compile printer-compile -classpath "$CP:$WORK/lower.jar" -d "$WORK/printer.jar" \
  "$ROOT/src/target/Tree.kt" "$ROOT/src/target/Printer.kt" "$HERE/PrintContract.kt"
run printer "$JDK/bin/java" -Xmx2g -cp "$CP:$WORK/printer.jar:$WORK/lower.jar" dev.ets.tests.backend.PrintContractKt \
  "$CP" "$WORK" "$HERE/Original.kt" "$HERE/Renamed.kt"
compile jvm-compile -classpath "$CP" -d "$WORK/oracle.jar" "$HERE/Original.kt" "$HERE/Renamed.kt" "$HERE/JvmOracle.kt"
run jvm "$JDK/bin/java" -cp "$CP:$WORK/oracle.jar" dev.ets.tests.backend.JvmOracleKt
run differential node "$HERE/oracle.mjs" "$WORK"
run input-stability shasum -a 256 -c "$WORK/input-sha256.txt"
cat "$WORK/lower.stdout" "$WORK/printer.stdout" "$WORK/differential.stdout"
