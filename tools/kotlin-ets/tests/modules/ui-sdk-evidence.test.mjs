import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { verifyModuleCoverage } from './ui-sdk-evidence.mjs';

assert.ok(process.argv[2], 'Pass existing SDK evidence; this test performs no SDK build or artifact edits');
const evidence = resolve(process.argv[2]);
const manifest = JSON.parse(readFileSync(join(evidence, 'manifest.json'), 'utf8'));
const cache = join(manifest.host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule');
const inputs = {
  modules: manifest.modules,
  ets: join(manifest.host, 'entry/src/main/ets'),
  records: readFileSync(join(cache, 'debug/filesInfo.txt'), 'utf8').split('\n'),
  buildInfoPath: join(cache, '.tsbuildinfo'),
  buildInfo: JSON.parse(readFileSync(join(cache, '.tsbuildinfo'), 'utf8')),
  checker: JSON.parse(readFileSync(join(cache, '.ts_checker_cache'), 'utf8')),
};
const coverage = verifyModuleCoverage(inputs);
assert.equal(coverage.length, manifest.modules.length);
const erased = coverage.filter(module => module.kind === 'interface-only');
const runtime = coverage.find(module => module.kind === 'runtime');
assert.ok(erased.length && runtime, 'Regression evidence must contain both erased interfaces and runtime modules');
let negatives = 0;
function rejects(mutate, expected) {
  const changed = structuredClone(inputs);
  mutate(changed);
  assert.throws(() => verifyModuleCoverage(changed), expected);
  negatives++;
}
rejects(value => { value.records = value.records.filter(record => record !== runtime.record); },
  /Missing runtime SDK input for non-interface-only module/);
for (const module of erased) {
  const erasedPath = join(inputs.ets, 'modules', module.name);
  const index = module.checkerFileId - 1;
  rejects(value => { value.buildInfo.program.fileNames[index] = 'missing.ets'; }, /Missing SDK checker input/);
  rejects(value => { value.buildInfo.program.fileInfos[index] = 'stale'; }, /SDK checker input hash differs/);
  rejects(value => {
    value.buildInfo.program.semanticDiagnosticsPerFile = value.buildInfo.program.semanticDiagnosticsPerFile
      .filter(item => item !== module.checkerFileId);
  }, /Missing clean SDK semantic result/);
  rejects(value => {
    value.buildInfo.program.semanticDiagnosticsPerFile = value.buildInfo.program.semanticDiagnosticsPerFile
      .map(item => item === module.checkerFileId ? [item, [{ code: 9999 }]] : item);
  }, /Missing clean SDK semantic result/);
  rejects(value => { delete value.checker.fileList[erasedPath]; }, /Missing clean SDK checker-cache result/);
  rejects(value => { value.checker.fileList[erasedPath].error = true; }, /Missing clean SDK checker-cache result/);
  rejects(value => { value.checker.fileList[erasedPath].parent = []; }, /Missing SDK checked dependency/);
  rejects(value => {
    for (const parent of value.checker.fileList[erasedPath].parent) {
      value.checker.fileList[parent].children = value.checker.fileList[parent].children.filter(path => path !== erasedPath);
    }
  }, /Missing SDK checked dependency/);
  rejects(value => {
    value.buildInfo.program.fileIdsList = value.buildInfo.program.fileIdsList.map(list => list.filter(id => id !== module.checkerFileId));
  }, /Missing SDK checked dependency/);
}
console.log(`PASS recorded SDK evidence: ${coverage.length} modules covered; erased ${erased.map(module => module.name).join(', ')}; ${negatives} missing/stale/errored evidence negatives rejected; no build`);
