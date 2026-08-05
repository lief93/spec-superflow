#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  proposeMattVendorSync,
  synchronizeMattPlugin,
} from './lib/matt-plugin-vendor.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PLUGIN_ROOT = join(ROOT, 'extensions', 'spec-superflow-companion', 'matt-plugin');
const REPOSITORY = 'https://github.com/mattpocock/skills';

function parseArgs(args) {
  const options = { apply: false, source: null, commit: null };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--apply') options.apply = true;
    else if (arg === '--commit') options.commit = args[++index];
    else if (arg === '--source') options.source = resolve(args[++index]);
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!/^[0-9a-f]{40}$/i.test(options.commit || '')) {
    throw new Error('--commit requires an explicit 40-character Git commit.');
  }
  return options;
}

function runGit(cwd, args) {
  const result = spawnSync('git', args, { cwd, encoding: 'utf8' });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
}

function checkout(commit) {
  const root = mkdtempSync(join(tmpdir(), 'matt-plugin-sync-source-'));
  runGit(root, ['init', '-q']);
  runGit(root, ['remote', 'add', 'origin', REPOSITORY]);
  runGit(root, ['fetch', '--depth', '1', 'origin', commit]);
  runGit(root, ['checkout', '--detach', 'FETCH_HEAD']);
  return root;
}

let temporarySource = null;
try {
  const options = parseArgs(process.argv.slice(2));
  const sourceRoot = options.source || (temporarySource = checkout(options.commit));
  const input = {
    pluginRoot: PLUGIN_ROOT,
    sourceRoot,
    repository: REPOSITORY,
    commit: options.commit,
  };
  const proposal = options.apply
    ? synchronizeMattPlugin(input)
    : proposeMattVendorSync(input);
  process.stdout.write(`${JSON.stringify({
    applied: options.apply,
    repository: proposal.repository,
    previousCommit: proposal.previousCommit,
    proposedCommit: proposal.commit,
    previousCount: proposal.previousCount,
    proposedCount: proposal.proposedCount,
    added: proposal.added,
    removed: proposal.removed,
    renamed: proposal.renamed,
  }, null, 2)}\n`);
} finally {
  if (temporarySource) rmSync(temporarySource, { recursive: true, force: true });
}
