import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
const source = fileURLToPath(new URL('./Page.kt', import.meta.url));
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-arrangement-'));
assert.ok(process.argv[2], 'Pass real Compose classpath.txt');
function run(entry) {
  const output = join(root, entry + '.ets');
  const result = spawnSync('bash', [launcher, '--entry', 'arrangement.' + entry,
    '--classpath-file', process.argv[2], '--out', output, source], {
    encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'},
  });
  writeFileSync(output + '.log', result.stdout + result.stderr);
  return {result, output, report: JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'))};
}
const page = run('Page');
assert.equal(page.result.status, 0, page.result.stdout + page.result.stderr);
assert.equal(page.report.degradationCount, 0);
const code = readFileSync(page.output, 'utf8');
assert.match(code, /Row\(\{ space: /);
assert.match(code, /Column\(\{ space: /);
const unsupported = run('UnsupportedAlignment');
assert.equal(unsupported.result.status, 2);
assert.match(unsupported.report.blockingFailure.message, /spacedBy|alignment/);
console.log(JSON.stringify({ok: true, root, page: page.output}));
