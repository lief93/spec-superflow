#!/usr/bin/env bash
set -euo pipefail
stdlib_tests=$(cd "$(dirname "$0")" && pwd)
stdlib_root=$(cd "$stdlib_tests/../.." && pwd)
mkdir -p "$stdlib_tests/.build"
stdlib_run=$(mktemp -d "$stdlib_tests/.build/cli.XXXXXX")
printf 'Evidence directory: %s\n' "$stdlib_run"
bash "$stdlib_tests/compiler.sh" -d "$stdlib_run/oracle.jar" \
  "$stdlib_tests/fixtures/Scalars.kt" "$stdlib_tests/fixtures/Lists.kt" "$stdlib_tests/JvmOracle.kt"
stdlib_cp=$(bash "$stdlib_tests/compiler.sh" --classpath)
java -cp "${stdlib_cp}:${stdlib_run}/oracle.jar" stdlibcases.JvmOracleKt > "$stdlib_run/jvm-oracle.jsonl"
"$stdlib_root/kotlin-ets" --mode language --out "$stdlib_run/generated.ets" \
  "$stdlib_tests/fixtures/Scalars.kt" "$stdlib_tests/fixtures/Lists.kt" \
  > "$stdlib_run/cli.stdout" 2> "$stdlib_run/cli.stderr"
node "$stdlib_tests/oracle.mjs" "$stdlib_run/generated.ets" "$stdlib_run/jvm-oracle.jsonl"
if "$stdlib_root/kotlin-ets" --mode language --out "$stdlib_run/rejected.ets" \
  "$stdlib_tests/fixtures/UnknownApi.kt" > "$stdlib_run/rejected.stdout" 2> "$stdlib_run/rejected.stderr"; then
  printf 'ERROR: unknown library API was accepted\n' >&2
  exit 1
else
  test "$?" -eq 2
fi
test ! -e "$stdlib_run/rejected.ets"
node - "$stdlib_run/rejected.stdout" <<'NODE'
const assert = require('node:assert/strict');
const fs = require('node:fs');
const diagnostic = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(diagnostic.ok, false);
assert.equal(diagnostic.code, 'UNSUPPORTED');
assert.ok(diagnostic.message.includes('kotlin.text.lowercase'));
assert.ok(diagnostic.source.file.endsWith('UnknownApi.kt'));
assert.ok(diagnostic.source.start >= 0);
assert.ok(diagnostic.source.end > diagnostic.source.start);
console.log('PASS: unknown API rejected with call-site diagnostic and no target artifact');
NODE
