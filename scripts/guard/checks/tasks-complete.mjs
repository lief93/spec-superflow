// scripts/guard/checks/tasks-complete.mjs — verify all tasks in tasks.md are checked off
import fs from 'node:fs';
import path from 'node:path';
import { readState } from '../../lib/state-loader.mjs';

/**
 * Check that tasks.md has no unchecked items and at least one completed item.
 * Returns { pass, failures[] }.
 */
export function checkTasksComplete(changeDir) {
  const tasksPath = path.join(changeDir, 'tasks.md');
  if (!fs.existsSync(tasksPath)) {
    return { pass: false, failures: ['tasks.md: missing'] };
  }

  const content = fs.readFileSync(tasksPath, 'utf-8');
  const unchecked = content.match(/^[ \t]*- \[ \]/gm);

  if (unchecked && unchecked.length > 0) {
    return {
      pass: false,
      failures: [`tasks.md: ${unchecked.length} unchecked task(s) remaining`],
    };
  }

  const hasAny = content.match(/^[ \t]*- \[[xX]\]/gm);
  if (!hasAny) {
    return { pass: false, failures: ['tasks.md: no completed tasks found'] };
  }

  const batchNumbers = [...content.matchAll(/^## Batch (\d+):/gm)]
    .map(match => Number(match[1]));
  if (batchNumbers.length === 0) {
    return { pass: false, failures: ['tasks.md: no ## Batch N: headings found'] };
  }

  const expectedNumbers = batchNumbers.map((_, index) => index + 1);
  if (batchNumbers.some((number, index) => number !== expectedNumbers[index])) {
    return {
      pass: false,
      failures: [
        `tasks.md: Batch numbering must be sequential from 1; found ${batchNumbers.join(', ')}`,
      ],
    };
  }

  const { batches_completed: batchesCompleted } = readState(changeDir);
  if (batchesCompleted !== batchNumbers.length) {
    return {
      pass: false,
      failures: [
        `batches_completed is ${batchesCompleted}; tasks.md defines ${batchNumbers.length} Batch section(s)`,
      ],
    };
  }

  return { pass: true, failures: [] };
}
