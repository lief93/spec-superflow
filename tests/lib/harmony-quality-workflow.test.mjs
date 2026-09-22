import assert from 'node:assert/strict';
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { after, before, describe, it } from 'node:test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '../..');
const CLI = join(ROOT, 'scripts/spec-superflow.mjs');
let tempRoot;

function read(relativePath) {
  return readFileSync(join(ROOT, relativePath), 'utf8');
}

function runSsf(args, cwd = tempRoot) {
  return spawnSync(process.execPath, [CLI, ...args], {
    cwd,
    encoding: 'utf8',
  });
}

function writeQualityConfig(projectRoot, commands) {
  writeFileSync(
    join(projectRoot, 'harmony-quality.config.json'),
    `${JSON.stringify({
      schemaVersion: 1,
      project: { root: '.', modules: ['entry'] },
      commands,
      qualityGates: [],
      scope: { default: 'full' },
      reports: { directory: '.harmony-quality/reports' },
    }, null, 2)}\n`,
  );
}

function verifiedCommand(source) {
  return {
    status: 'verified',
    required: true,
    argv: [process.execPath, '-e', source],
  };
}

describe('Harmony Quality workflow integration', () => {
  before(() => {
    tempRoot = mkdtempSync(join(tmpdir(), 'ssf-harmony-quality-'));
  });

  after(() => {
    rmSync(tempRoot, { recursive: true, force: true });
  });

  it('exposes quality init and check through ssf', () => {
    const help = runSsf(['--help']);

    assert.equal(help.status, 0, help.stderr);
    assert.match(help.stdout, /quality init --project/);
    assert.match(help.stdout, /quality check --project/);
  });

  it('initializes a Harmony project once and preserves an existing configuration', () => {
    const project = join(tempRoot, 'init-project');
    mkdirSync(join(project, 'entry/src/main/ets'), { recursive: true });
    const wrapper = join(project, 'hvigorw');
    writeFileSync(wrapper, '#!/bin/sh\nprintf "%s\\n" assembleHap test codeLinter\n');
    chmodSync(wrapper, 0o755);

    const first = runSsf(['quality', 'init', '--project', project]);
    assert.equal(first.status, 0, first.stderr);
    assert.match(first.stdout, /CONFIGURED/);

    const configPath = join(project, 'harmony-quality.config.json');
    const config = JSON.parse(readFileSync(configPath, 'utf8'));
    config.project.marker = 'developer-owned';
    writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`);

    const second = runSsf(['quality', 'init', '--project', project]);
    assert.equal(second.status, 0, second.stderr);
    assert.match(second.stdout, /ALREADY_CONFIGURED/);
    assert.equal(
      JSON.parse(readFileSync(configPath, 'utf8')).project.marker,
      'developer-owned',
    );
  });

  it('preserves Harmony Quality PASS, FAIL, and BLOCKED exit codes', () => {
    const cases = [
      {
        name: 'pass',
        expected: 0,
        commands: { build: verifiedCommand('process.exit(0)') },
      },
      {
        name: 'fail',
        expected: 2,
        commands: { build: verifiedCommand('process.exit(1)') },
      },
      {
        name: 'blocked',
        expected: 3,
        commands: { build: { status: 'unresolved', required: true, argv: [] } },
      },
    ];

    for (const testCase of cases) {
      const project = join(tempRoot, `check-${testCase.name}`);
      mkdirSync(join(project, 'entry/src/main/ets'), { recursive: true });
      writeFileSync(join(project, 'entry/src/main/ets/Main.ets'), 'export const value = 1;\n');
      writeQualityConfig(project, testCase.commands);

      const result = runSsf([
        'quality',
        'check',
        '--project',
        project,
        '--scope',
        'full',
      ]);

      assert.equal(result.status, testCase.expected, `${testCase.name}: ${result.stderr}`);
    }
  });

  it('initializes quality only during Project Init for detected Harmony projects', () => {
    const projectInit = read('skills/project-init/SKILL.md');

    assert.match(projectInit, /src\/main\/ets/);
    assert.match(projectInit, /ssf quality init --project <project-root>/);
    assert.match(projectInit, /harmony-quality\.config\.json.*absent/is);
    assert.match(projectInit, /existing.*harmony-quality\.config\.json.*unchanged/is);
    assert.match(projectInit, /ALREADY_CONFIGURED.*success/is);
    assert.match(projectInit, /unresolved.*immediately/is);
    assert.match(projectInit, /non-Harmony.*skip/is);
  });

  it('checks configured Harmony projects before final review without initializing in Closing', () => {
    const release = read('skills/release-archivist/SKILL.md');
    const preReview = /### Pre-review preparation([\s\S]*?)(?=### Post-approval state progression)/
      .exec(release)?.[1] || '';

    assert.match(
      preReview,
      /ssf state get <change-dir> execution_base_commit[\s\S]*ssf quality check[\s\S]*--project <project-root>[\s\S]*--scope changed[\s\S]*--base <returned-execution-base-commit>/i,
    );
    assert.match(preReview, /exact immutable `execution_base_commit` returned by the state command/i);
    assert.match(preReview, /Closing must never run `ssf quality init`/i);
    assert.match(preReview, /PASS.*continues/is);
    assert.match(preReview, /FAIL.*BLOCKED.*prevents closing/is);
    assert.match(preReview, /exact report path/is);
    assert.match(preReview, /Harmony.*configuration.*missing.*BLOCKED/is);
    assert.match(preReview, /non-Harmony.*skip/is);
    assert.match(
      preReview,
      /--mutation --max-mutants <N>.*Specs or tasks\.md.*explicitly require/is,
    );
    assert.match(
      release,
      /Lightweight Closure[\s\S]*Harmony Quality gate[\s\S]*before the lightweight closure guard/i,
    );
  });
});
