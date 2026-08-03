import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  lstatSync,
  readFileSync,
  readlinkSync,
  realpathSync,
} from 'node:fs';
import {
  relative,
  resolve,
  sep,
} from 'node:path';

const MAX_GIT_OUTPUT = 128 * 1024 * 1024;

export function collectWorktreeReviewCandidate({
  repoRoot,
  changeDir,
  base,
}) {
  const canonicalRepo = realpathSync(resolve(repoRoot));
  const canonicalChange = realpathSync(resolve(changeDir));
  const changeRelative = toPosix(relative(canonicalRepo, canonicalChange));
  if (
    !changeRelative
    || changeRelative === '..'
    || changeRelative.startsWith('../')
  ) {
    throw new Error('Change directory must be inside the repository');
  }

  const reviewBase = gitText(
    canonicalRepo,
    ['rev-parse', '--verify', '--end-of-options', `${base}^{commit}`],
    'review base',
  ).trim();
  const pathspec = [
    '--',
    '.',
    `:(exclude)${changeRelative}`,
    `:(exclude)${changeRelative}/**`,
  ];
  const diff = gitText(canonicalRepo, [
    'diff',
    '--binary',
    '--full-index',
    '--no-ext-diff',
    '--find-renames',
    reviewBase,
    ...pathspec,
  ], 'worktree diff');
  const status = gitBuffer(canonicalRepo, [
    'status',
    '--porcelain=v2',
    '-z',
    '--untracked-files=all',
    ...pathspec,
  ], 'worktree status');
  const trackedFiles = parseTrackedFiles(gitBuffer(canonicalRepo, [
    'diff',
    '--name-status',
    '-z',
    '--find-renames',
    reviewBase,
    ...pathspec,
  ], 'changed files'));
  const untrackedPaths = nulFields(gitBuffer(canonicalRepo, [
    'ls-files',
    '--others',
    '--exclude-standard',
    '-z',
    ...pathspec,
  ], 'untracked files')).sort(compareUtf8);
  const trackedMetadata = trackedFiles.map(file => {
    if (file.status.startsWith('D')) return file;
    const metadata = readTrackedWorktreeMetadata(canonicalRepo, file.path);
    return { ...file, ...metadata };
  });
  const untrackedFiles = untrackedPaths.map(path => (
    readWorktreeFile(canonicalRepo, path)
  ));
  const changedFiles = [
    ...trackedMetadata.map(({
      gitlink_object_id: _gitlinkObjectId,
      ...file
    }) => file),
    ...untrackedFiles.map(({
      bytes: _bytes,
      text: _text,
      ...file
    }) => ({
      status: 'untracked',
      ...file,
    })),
  ].sort((left, right) => compareUtf8(left.path, right.path));
  const identity = hashWorktree({
    reviewBase,
    status,
    diff,
    gitlinks: trackedMetadata.filter(file => file.gitlink_object_id),
    untrackedFiles,
  });

  return {
    reviewBase,
    identity,
    diff,
    changedFiles,
    untrackedFiles: untrackedFiles.map(({ bytes: _bytes, ...file }) => file),
  };
}

function readTrackedWorktreeMetadata(repoRoot, relativePath) {
  const indexEntry = readIndexEntry(repoRoot, relativePath);
  if (indexEntry?.mode === '160000') {
    const objectId = readGitlinkCommit(repoRoot, relativePath, indexEntry.objectId);
    const bytes = Buffer.from(objectId, 'utf8');
    return {
      path: relativePath,
      mode: '160000',
      byte_length: bytes.length,
      content_hash: hashBytes(bytes),
      gitlink_object_id: objectId,
    };
  }

  const {
    bytes: _bytes,
    text: _text,
    ...metadata
  } = readWorktreeFile(repoRoot, relativePath);
  return metadata;
}

function readIndexEntry(repoRoot, relativePath) {
  const output = gitText(
    repoRoot,
    ['ls-files', '--stage', '-z', '--', relativePath],
    'tracked file metadata',
  );
  const headerEnd = output.indexOf('\t');
  if (headerEnd === -1) return null;
  const [mode, objectId, stage] = output.slice(0, headerEnd).split(' ');
  if (
    !/^\d{6}$/.test(mode ?? '')
    || !/^[a-f0-9]{40,64}$/.test(objectId ?? '')
    || stage !== '0'
  ) {
    return null;
  }
  return { mode, objectId };
}

function readGitlinkCommit(repoRoot, relativePath, fallbackObjectId) {
  const absolutePath = resolve(repoRoot, relativePath);
  const result = spawnSync('git', [
    '-C',
    absolutePath,
    'rev-parse',
    '--show-toplevel',
    '--verify',
    'HEAD^{commit}',
  ], {
    encoding: 'utf8',
    maxBuffer: MAX_GIT_OUTPUT,
  });
  if (result.status !== 0) return fallbackObjectId;

  const lines = result.stdout.trim().split('\n');
  const objectId = lines.at(-1);
  const topLevel = lines.slice(0, -1).join('\n');
  if (
    !/^[a-f0-9]{40,64}$/.test(objectId ?? '')
    || !topLevel
  ) {
    return fallbackObjectId;
  }
  try {
    return realpathSync(topLevel) === realpathSync(absolutePath)
      ? objectId
      : fallbackObjectId;
  } catch {
    return fallbackObjectId;
  }
}

function readWorktreeFile(repoRoot, relativePath) {
  const absolutePath = resolve(repoRoot, relativePath);
  if (
    absolutePath !== repoRoot
    && !absolutePath.startsWith(`${repoRoot}${sep}`)
  ) {
    throw new Error(`Untracked path escapes the repository: ${relativePath}`);
  }
  const stat = lstatSync(absolutePath);
  if (stat.isSymbolicLink()) {
    const target = readlinkSync(absolutePath, { encoding: 'buffer' });
    return {
      path: relativePath,
      mode: '120000',
      byte_length: target.length,
      content_hash: hashBytes(target),
      text: target.toString('utf8'),
      bytes: target,
    };
  }
  if (!stat.isFile()) {
    throw new Error(`Untracked path is not a regular file: ${relativePath}`);
  }
  const bytes = readFileSync(absolutePath);
  return {
    path: relativePath,
    mode: stat.mode & 0o111 ? '100755' : '100644',
    byte_length: bytes.length,
    content_hash: hashBytes(bytes),
    text: readableText(bytes),
    bytes,
  };
}

function readableText(bytes) {
  if (bytes.includes(0)) return null;
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

function parseTrackedFiles(output) {
  const fields = nulFields(output);
  const files = [];
  for (let index = 0; index < fields.length;) {
    const status = fields[index++];
    if (/^[RC]\d+$/.test(status)) {
      const from = fields[index++];
      const path = fields[index++];
      if (from === undefined || path === undefined) {
        throw new Error('Changed-file list is malformed');
      }
      files.push({ status, path, from });
    } else {
      const path = fields[index++];
      if (path === undefined) throw new Error('Changed-file list is malformed');
      files.push({ status, path });
    }
  }
  return files;
}

function nulFields(output) {
  const fields = output.toString('utf8').split('\0');
  if (fields.at(-1) === '') fields.pop();
  return fields;
}

function hashWorktree({ reviewBase, status, diff, gitlinks, untrackedFiles }) {
  const hash = createHash('sha256');
  hash.update('spec-superflow-worktree-review-v3\0', 'utf8');
  updateFramed(hash, 'review-base', Buffer.from(reviewBase, 'utf8'));
  updateFramed(hash, 'status-porcelain-v2', status);
  updateFramed(hash, 'base-to-worktree-diff', Buffer.from(diff, 'utf8'));
  for (const file of [...gitlinks].sort((left, right) => compareUtf8(left.path, right.path))) {
    updateFramed(
      hash,
      `gitlink/${file.mode}/${file.path}`,
      Buffer.from(file.gitlink_object_id, 'utf8'),
    );
  }
  for (const file of untrackedFiles) {
    updateFramed(hash, `untracked/${file.mode}/${file.path}`, file.bytes);
  }
  return `sha256:${hash.digest('hex')}`;
}

function updateFramed(hash, label, content) {
  hash.update(`${Buffer.byteLength(label)}:${label}:${content.length}:`, 'utf8');
  hash.update(content);
}

function hashBytes(content) {
  return `sha256:${createHash('sha256').update(content).digest('hex')}`;
}

function toPosix(path) {
  return sep === '/' ? path : path.split(sep).join('/');
}

function compareUtf8(left, right) {
  return Buffer.compare(Buffer.from(left), Buffer.from(right));
}

function gitText(cwd, args, label) {
  return gitBuffer(cwd, args, label).toString('utf8');
}

function gitBuffer(cwd, args, label) {
  const result = spawnSync('git', ['-C', cwd, ...args], {
    encoding: null,
    maxBuffer: MAX_GIT_OUTPUT,
  });
  if (result.status !== 0) {
    throw new Error(
      `${label} is invalid: ${result.stderr?.toString('utf8').trim() || 'Git command failed'}`,
    );
  }
  return result.stdout;
}
