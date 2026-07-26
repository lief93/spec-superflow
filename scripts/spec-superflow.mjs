#!/usr/bin/env node
// spec-superflow CLI — zero-dependency CLI for spec management
// Usage: ssf <command> [options]

import { parseArgs } from 'node:util';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const COMMANDS = {
  list:           () => import('./lib/cmd-list.mjs'),
  validate:       () => import('./lib/cmd-validate.mjs'),
  doctor:         () => import('./lib/cmd-doctor.mjs'),
  version:        () => import('./lib/cmd-version.mjs'),
  sync:           () => import('./lib/cmd-sync.mjs'),
  config:         () => import('./lib/cmd-config.mjs'),
  state:          () => import('./lib/cmd-state.mjs'),
  inject:         () => import('./lib/cmd-inject.mjs'),
  audit:          () => import('./lib/cmd-audit.mjs'),
  memories:       () => import('./lib/cmd-memories.mjs'),
  project:        () => import('./lib/cmd-project.mjs'),
  'install-cursor': () => import('./lib/cmd-install-cursor.mjs'),
  'install-workbuddy': () => import('./lib/cmd-install-workbuddy.mjs'),
};

const BUNDLED_HELPERS = {
  'check-update': { path: './check-update.mjs', runner: 'node' },
  'infer-workflow': { path: './infer-workflow.mjs', runner: 'node' },
  guard: { path: './guard/guard.mjs', runner: 'node' },
  'task-brief': { path: './task-brief', runner: 'bash' },
  'review-package': { path: './review-package', runner: 'bash' },
};

const HELP = `spec-superflow (ssf) — Spec-first workflow CLI

Usage: ssf <command> [options]

Commands:
  list                  List all changes and their status
  validate <dir>        Validate artifacts in a change directory
  doctor                Source-checkout maintenance check
  version <semver>      Sync version to all manifest files
  sync <change-dir>     Merge delta specs into main specs
  config [options]      Display or modify configuration
  state <sub> <dir>     Manage .spec-superflow.yaml state (init|check|transition|get|rebuild)
  inject <dir>          Generate phase-guard artifacts for Claude/Cursor/Copilot/Gemini
  audit <dir>           Generate decision-point-audit.md from .spec-superflow.yaml
  memories <sub> [root] Manage Claude-style shared auto memory (init|list|check)
  project check [root]  Validate project development baseline documents
  check-update          Check for a newer spec-superflow release
  infer-workflow <dir>  Infer hotfix, tweak, or full workflow mode
  guard check ...       Validate a workflow state transition
  task-brief ...        Extract one task or AC into a brief file
  review-package ...    Generate a bounded review package
  install-cursor        Deploy skills/scripts/docs to .cursor/ (local Cursor setup)
  install-workbuddy     Deploy skills to WorkBuddy marketplace and enable them

Options:
  --help, -h            Show this help message
  --version, -v         Show CLI version

Examples:
  ssf list
  ssf validate changes/v0.4.0-platform-evolution/
  ssf doctor
  ssf version 0.4.0
  ssf sync changes/v0.3.0-workflow-enhancements/
  ssf config --get execution.inlineThreshold
  ssf config --set verification.language=zh
  ssf state init changes/my-change/
  ssf state check changes/my-change/
  ssf state transition changes/my-change/ approved-for-build
  ssf state get changes/my-change/ batches_completed
  ssf infer-workflow changes/my-change/
  ssf guard check changes/my-change/ specifying bridging --json
  ssf task-brief changes/my-change/tasks.md 1
  ssf review-package HEAD~1 HEAD
  ssf memories init
  ssf memories check
  ssf project check
  ssf install-cursor
  ssf install-workbuddy
`;

function runBundledHelper(helper, args) {
  const script = fileURLToPath(new URL(helper.path, import.meta.url));
  const command = helper.runner === 'bash' ? 'bash' : process.execPath;
  const result = spawnSync(command, [script, ...args], { stdio: 'inherit' });

  if (result.error) {
    console.error(`Failed to run helper: ${result.error.message}`);
    process.exit(1);
  }
  process.exit(result.status ?? 1);
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    console.log(HELP);
    process.exit(0);
  }

  if (args.includes('--version') || args.includes('-v')) {
    const pkg = JSON.parse(
      (await import('node:fs')).readFileSync(
        new URL('../package.json', import.meta.url), 'utf-8'
      )
    );
    console.log(pkg.version);
    process.exit(0);
  }

  const command = args[0];
  const commandArgs = args.slice(1);

  if (BUNDLED_HELPERS[command]) {
    runBundledHelper(BUNDLED_HELPERS[command], commandArgs);
  }

  if (!COMMANDS[command]) {
    console.error(`Unknown command: ${command}`);
    console.error(`Run "ssf --help" for available commands.`);
    process.exit(2);
  }

  const mod = await COMMANDS[command]();
  await mod.run(commandArgs);
}

main().catch(err => {
  console.error(`Error: ${err.message}`);
  process.exit(1);
});
