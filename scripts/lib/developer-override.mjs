import { randomUUID } from 'node:crypto';
import {
  appendFileSync,
  chmodSync,
  closeSync,
  constants,
  existsSync,
  fstatSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { join, resolve, sep } from 'node:path';

const SHA256 = /^sha256:[a-f0-9]{64}$/;
const WAIVER_FIELDS = [
  'action',
  'actor',
  'candidate_identity',
  'reason',
  'stage',
  'timestamp',
];

export function waiverRelativePath(stage) {
  return `reviews/${stage}-developer-waiver.json`;
}

export function writeDeveloperWaiver(changeDir, waiver) {
  const changePath = requireChangeDirectory(changeDir);
  const reviewsPath = ensureRealChildDirectory(changePath, 'reviews');
  const target = join(changePath, waiverRelativePath(waiver.stage));
  const temporary = join(
    reviewsPath,
    `.${waiver.stage}-developer-waiver.${process.pid}.${randomUUID()}.tmp`,
  );
  try {
    writeFileSync(temporary, `${JSON.stringify(waiver)}\n`, {
      flag: 'wx',
      mode: 0o600,
    });
    renameSync(temporary, target);
  } finally {
    rmSync(temporary, { force: true });
  }
  return waiverRelativePath(waiver.stage);
}

export function readDeveloperWaiver(changeDir, stage) {
  const path = join(changeDir, waiverRelativePath(stage));
  let value;
  try {
    value = JSON.parse(
      readRegularFileNoFollow(path, 'Developer review waiver').toString('utf8'),
    );
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw new Error(`Developer review waiver is invalid: ${error.message}`);
  }
  requirePlainObject(value);
  if (JSON.stringify(Object.keys(value).sort()) !== JSON.stringify([...WAIVER_FIELDS].sort())) {
    throw new Error('Developer review waiver fields are invalid');
  }
  if (value.action !== 'waive-review' || value.actor !== 'developer') {
    throw new Error('Developer review waiver authority is invalid');
  }
  if (value.stage !== stage) throw new Error(`Developer review waiver stage must be ${stage}`);
  if (!SHA256.test(value.candidate_identity ?? '')) {
    throw new Error('Developer review waiver candidate identity is invalid');
  }
  requireText(value.reason, 'Developer review waiver reason');
  if (Number.isNaN(Date.parse(value.timestamp))) {
    throw new Error('Developer review waiver timestamp is invalid');
  }
  return value;
}

export function appendDeveloperOverride(changeDir, record) {
  const changePath = requireChangeDirectory(changeDir);
  const path = join(changePath, 'developer-overrides.jsonl');
  if (existsSync(path)) {
    const stat = lstatSync(path);
    if (stat.isSymbolicLink() || !stat.isFile()) {
      throw new Error('developer-overrides.jsonl must be a regular file');
    }
  }
  appendFileSync(path, `${JSON.stringify(record)}\n`, {
    encoding: 'utf8',
    mode: 0o600,
    flag: constants.O_APPEND | constants.O_CREAT | constants.O_WRONLY | (constants.O_NOFOLLOW ?? 0),
  });
  try {
    chmodSync(path, 0o600);
  } catch {
    // Audit content is authoritative; stricter permissions are best-effort portability hygiene.
  }
}

export function requireChangeDirectory(changeDir) {
  const requested = resolve(changeDir);
  const stat = lstatSync(requested);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error('Change path must be a real directory');
  }
  return realpathSync(requested);
}

function ensureRealChildDirectory(changePath, name) {
  const requested = join(changePath, name);
  if (!existsSync(requested)) mkdirSync(requested, { mode: 0o700 });
  const stat = lstatSync(requested);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(`${name} must be a real directory`);
  }
  const canonical = realpathSync(requested);
  if (!canonical.startsWith(`${changePath}${sep}`)) {
    throw new Error(`${name} directory escapes the Change directory`);
  }
  return canonical;
}

function requirePlainObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Developer review waiver must be an object');
  }
}

function requireText(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} must be non-empty text`);
  }
}

function readRegularFileNoFollow(path, label) {
  const before = lstatSync(path);
  if (before.isSymbolicLink() || !before.isFile()) {
    throw new Error(`${label} must be a regular file, not a symbolic link`);
  }
  const descriptor = openSync(
    path,
    constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0),
  );
  try {
    const stat = fstatSync(descriptor);
    if (!stat.isFile() || before.dev !== stat.dev || before.ino !== stat.ino) {
      throw new Error(`${label} changed while it was opened`);
    }
    return readFileSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}
