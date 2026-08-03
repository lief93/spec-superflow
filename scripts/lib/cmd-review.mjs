import { randomUUID } from 'node:crypto';
import {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  realpathSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { parseArgs } from 'node:util';

import {
  computeReviewCandidate,
  REVIEW_STAGES,
} from './review-candidate.mjs';
import {
  checkCurrentReview,
  currentReviewRelativePath,
  parseCurrentReview,
  pendingReviewReportRelativePath,
  readRegularFileNoFollow,
  requireReviewStagePrerequisites,
  resolveFinalReviewBase,
} from './review-evidence.mjs';

const REVIEW_COMMANDS = ['candidate', 'record', 'check'];

export function run(args) {
  const { positionals, values } = parseArgs({
    args,
    options: {
      json: { type: 'boolean', default: false },
      base: { type: 'string' },
    },
    allowPositionals: true,
  });
  const [subcommand, changeDir, stage] = positionals;
  if (
    positionals.length !== 3
    || !REVIEW_COMMANDS.includes(subcommand)
    || !changeDir
    || !REVIEW_STAGES.includes(stage)
  ) {
    printUsage();
    process.exit(2);
  }
  if (stage !== 'final' && values.base) {
    console.error('--base is supported only for final review.');
    process.exit(2);
  }

  const base = stage === 'final'
    ? resolveFinalReviewBase(changeDir, values.base)
    : undefined;

  const common = {
    changeDir,
    stage,
    repoRoot: process.cwd(),
    base,
  };
  if (subcommand === 'candidate') {
    const prerequisiteIdentities = requireReviewStagePrerequisites(common);
    printResult(computeReviewCandidate({
      ...common,
      prerequisiteIdentities,
    }), values.json);
    return;
  }
  if (subcommand === 'record') {
    const result = recordCurrentReview(common);
    printResult(result, values.json);
    return;
  }

  const result = checkCurrentReview(common);
  printResult(result, values.json);
  if (!result.pass) process.exit(1);
}

export function recordCurrentReview({ changeDir, stage, repoRoot, base }) {
  const prerequisiteIdentities = requireReviewStagePrerequisites({
    changeDir,
    stage,
    repoRoot,
  });
  const candidate = computeReviewCandidate({
    changeDir,
    stage,
    repoRoot,
    base,
    prerequisiteIdentities,
  });
  const changePath = realpathSync(resolve(changeDir));
  const reviewsPath = ensureSafeReviewsDirectory(changePath);
  const pendingPath = join(changePath, pendingReviewReportRelativePath(stage));
  const report = parseCurrentReview(
    readRegularFileNoFollow(pendingPath, 'Pending review report'),
    {
      expectedStage: stage,
      expectedIdentity: candidate.identity,
      expectedBase: candidate.review_base,
      allowedFindingPaths: candidate.allowed_finding_paths,
    },
  );

  try {
    chmodSync(pendingPath, 0o600);
  } catch {
    // Permissions are hygiene, not a second semantic acceptance gate.
  }

  const currentPath = join(changePath, currentReviewRelativePath(stage));
  const temporary = join(
    reviewsPath,
    `.${stage}-current.${process.pid}.${randomUUID()}.tmp`,
  );
  try {
    writeFileSync(temporary, `${JSON.stringify(report)}\n`, {
      flag: 'wx',
      mode: 0o600,
    });
    renameSync(temporary, currentPath);
  } finally {
    rmSync(temporary, { force: true });
  }
  rmSync(pendingPath, { force: true });
  return {
    ok: true,
    stage,
    verdict: report.verdict,
    candidate_identity: candidate.identity,
    path: currentReviewRelativePath(stage),
  };
}

function ensureSafeReviewsDirectory(changePath) {
  const reviewsPath = join(changePath, 'reviews');
  if (!existsSync(reviewsPath)) mkdirSync(reviewsPath, { mode: 0o700 });
  const stat = lstatSync(reviewsPath);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error('reviews must be a real directory');
  }
  const canonical = realpathSync(reviewsPath);
  if (!canonical.startsWith(`${changePath}${sep}`)) {
    throw new Error('reviews directory escapes the Change directory');
  }
  return canonical;
}

function printResult(result, json) {
  if (json) console.log(JSON.stringify(result));
  else if (result.pass === false) console.error(result.failures.join('; '));
  else console.log(result.path ?? `${result.stage} ${result.identity ?? result.verdict}`);
}

function printUsage() {
  console.error('Usage: ssf review candidate <change-dir> <proposal-specs|design-tasks|final> [--base <git-ref>] [--json]');
  console.error('       ssf review record <change-dir> <proposal-specs|design-tasks|final> [--base <git-ref>] [--json]');
  console.error('       ssf review check <change-dir> <proposal-specs|design-tasks|final> [--base <git-ref>] [--json]');
}
