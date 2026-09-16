import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-wrap-'));
console.log('Evidence: ' + work);
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json')).filter(existsSync);
writeFileSync(join(work,'classpath.txt'),cp.join('\n'));
for (const [entry,status] of [['Page',0],['Unbounded',2],['EffectfulAlignment',2]]) {
  const out=join(work,entry+'.ets');
  const args=[join(root,'kotlin-ets'),'--entry','wrapcontent.'+entry,'--classpath-file',join(work,'classpath.txt'),'--out',out,join(here,'Page.kt')];
  const result=spawnSync('bash',args,{encoding:'utf8',timeout:600000,env:{...process.env,JAVA_TOOL_OPTIONS:'-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
  writeFileSync(join(work,entry+'.json'),JSON.stringify({args,...result},null,2));
  assert.equal(result.status,status,result.stdout+result.stderr);
  assert.equal(existsSync(out),status===0);
  if(status) assert.match(result.stdout,entry==='Unbounded'?/unbounded=false/:/alignment requires a resolved enum value/);
  else { const code=readFileSync(out,'utf8'); assert.match(code,/Alignment.Center/); assert.match(code,/Alignment.TopEnd/); assert.doesNotMatch(code,/onMeasureSize/); }
}
console.log('PASS bounded wrap via native Stack and explicit unbounded rejection');
