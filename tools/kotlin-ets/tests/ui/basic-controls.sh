#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/kotlin-ets-basic-controls.XXXXXX")"
printf 'Evidence: %s\n' "$WORK"
SOURCES=()
while IFS= read -r file; do SOURCES+=("$file"); done < <(find "$ROOT/src" -name '*.kt' ! -name Main.kt ! -path '*/output/*' | sort)
CP="$(bash "$ROOT/tests/stdlib/compiler.sh" --classpath)"
UI_CP="$(node -e 'console.log(require(process.argv[1]).join(":"))' "${KOTLIN_ETS_PROBE:-/tmp/kotlin-official-frontend-probe-06}/classpath.json")"
bash "$ROOT/tests/stdlib/compiler.sh" "${SOURCES[@]}" "$HERE/BasicControlsProbe.kt" -d "$WORK/lower.jar" > "$WORK/compile.stdout" 2> "$WORK/compile.stderr"
java -cp "$CP:$WORK/lower.jar" ui.test.BasicControlsProbeKt "$UI_CP" "$HERE/BasicControls.kt" "$WORK" "$HERE/UnsupportedBasicControls.kt" > "$WORK/test.stdout" 2> "$WORK/test.stderr"
cat "$WORK/test.stdout"
node "$HERE/basic-controls-callbacks.mjs" "$WORK"
