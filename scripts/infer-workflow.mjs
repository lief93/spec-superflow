#!/usr/bin/env node
// scripts/infer-workflow.mjs — infer hotfix/tweak/full from change artifacts
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { readState } from './lib/state-loader.mjs';

const CODE_EXTS = new Set([
  'mjs', 'js', 'ts', 'jsx', 'tsx', 'cjs',
]);
const CONFIG_DOC_EXTS = new Set([
  'md', 'json', 'yaml', 'yml', 'toml', 'ini',
  'txt', 'html', 'css',
]);

const FILE_RE = /\b\/?(?:[\w-]+\/)*[\w-]+\.(mjs|js|ts|jsx|tsx|cjs|md|json|yaml|yml|toml|ini|txt|html|css)\b/gi;

function readText(dir, name) {
  const p = join(dir, name);
  return existsSync(p) ? readFileSync(p, 'utf-8') : '';
}

function countTasks(tasks) {
  return (tasks.match(/^- \[([ x])\]/gm) || []).length;
}

function collectFiles(text) {
  const matches = text.match(FILE_RE) || [];
  return [...new Set(matches.map(m => m.trim()))];
}

function hasKeyword(text, patterns) {
  const lower = text.toLowerCase();
  return patterns.some(p => lower.includes(p.toLowerCase()));
}

function inferCapability(changeDir) {
  const state = readState(changeDir);
  if (state.capability && state.capability !== 'auto' && state.capability !== 'null') {
    return {
      capability: state.capability,
      explicit: true,
      reason: `capability explicitly set to '${state.capability}' in .spec-superflow.yaml; skipping auto-detection`,
    };
  }

  const proposal = readText(changeDir, 'proposal.md');
  const tasks = readText(changeDir, 'tasks.md');
  const combined = `${state.dp_0_decisions ?? ''}\n${proposal}\n${tasks}`;
  const lower = combined.toLowerCase();

  const hasAndroidSource = /\b(android|compose|jetpack compose|kotlin|gradle)\b/.test(lower)
    || /安卓/.test(combined);
  const hasHarmonyTarget = /\b(harmonyos|harmony|arkui|arkts|ohos)\b/.test(lower)
    || /鸿蒙/.test(combined);
  const hasMigrationIntent = /\b(migrate|migration|convert|port|translat(?:e|ion))\b/.test(lower)
    || /迁移|转换|转成|转鸿蒙|转到鸿蒙/.test(combined);

  if (hasAndroidSource && hasHarmonyTarget && hasMigrationIntent) {
    return {
      capability: 'android-to-harmony',
      explicit: false,
      reason: 'Android source, HarmonyOS target, and migration intent detected → android-to-harmony',
    };
  }

  return {
    capability: null,
    explicit: false,
    reason: 'no scoped optional capability detected',
  };
}

function inferMode(changeDir) {
  const state = readState(changeDir);
  const capability = inferCapability(changeDir);

  if (capability.capability === 'android-to-harmony') {
    return {
      mode: 'full',
      explicit: false,
      capability: capability.capability,
      capability_reason: capability.reason,
      reason: 'android-to-harmony capability detected → full workflow with migration-scoped gates',
    };
  }

  // Explicit override: honor any non-auto, non-null workflow value
  if (state.workflow && state.workflow !== 'auto') {
    const valid = ['hotfix', 'tweak', 'full'];
    if (valid.includes(state.workflow)) {
      return {
        mode: state.workflow,
        explicit: true,
        capability: capability.capability,
        capability_reason: capability.reason,
        reason: `workflow explicitly set to '${state.workflow}' in .spec-superflow.yaml; skipping auto-detection`,
      };
    }
  }

  const proposal = readText(changeDir, 'proposal.md');
  const tasks = readText(changeDir, 'tasks.md');
  const combined = `${proposal}\n${tasks}`;

  const taskCount = countTasks(tasks);
  const files = collectFiles(combined);
  const fileCount = files.length;

  const hasSchemaChange = hasKeyword(combined, [
    'schema', 'api', 'interface', '接口', 'validator', '类型',
    'type definition', 'protobuf', 'openapi', 'json schema',
  ]);
  const hasNewModule = hasKeyword(combined, [
    'new module', '新增模块', '新模块', '新增 skill', '新目录',
    '新增 capability', 'new capability',
  ]);

  const allExts = files.map(f => {
    const parts = f.split('.');
    return parts[parts.length - 1].toLowerCase();
  });
  const codeFileCount = allExts.filter(e => CODE_EXTS.has(e)).length;
  const configDocOnly = codeFileCount === 0 && allExts.every(e => CONFIG_DOC_EXTS.has(e));

  // No artifacts → safe default to full
  if (taskCount === 0 && fileCount === 0) {
    return {
      mode: 'full',
      explicit: false,
      capability: capability.capability,
      capability_reason: capability.reason,
      reason: 'no planning artifacts detected → full (safe default)',
    };
  }

  // Hotfix: very small, no schema/api, no new module
  if (taskCount <= 2 && fileCount <= 2 && !hasSchemaChange && !hasNewModule) {
    return {
      mode: 'hotfix',
      explicit: false,
      capability: capability.capability,
      capability_reason: capability.reason,
      reason: `≤2 tasks, ≤2 files, no schema/API/new-module keywords → hotfix`,
    };
  }

  // Tweak: small config/doc change
  if (taskCount <= 4 && configDocOnly && !hasSchemaChange && !hasNewModule) {
    return {
      mode: 'tweak',
      explicit: false,
      capability: capability.capability,
      capability_reason: capability.reason,
      reason: `≤4 tasks, only config/doc files, no schema/API/new-module keywords → tweak`,
    };
  }

  // Default
  return {
    mode: 'full',
    explicit: false,
    capability: capability.capability,
    capability_reason: capability.reason,
    reason: `${taskCount} tasks, ${fileCount} files${codeFileCount > 0 ? ` (${codeFileCount} code files)` : ''}${hasSchemaChange ? ', schema/API change detected' : ''}${hasNewModule ? ', new module detected' : ''} → full`,
  };
}

function main() {
  const changeDir = process.argv[2];
  if (!changeDir) {
    console.error('Usage: node scripts/infer-workflow.mjs <change-dir>');
    process.exit(2);
  }

  const result = inferMode(changeDir);
  console.log(JSON.stringify(result, null, 2));
}

export { inferMode, inferCapability };

if (import.meta.filename === process.argv[1] || import.meta.url === `file://${process.argv[1]}`) {
  main();
}
