import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { it } from 'node:test';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const CHANGE_DIR = join(ROOT, 'changes', 'android-to-harmony-54-benchmark');
const RUN_ROOT = join(CHANGE_DIR, 'run-root');
const TARGET = '/Users/lief123/harmonyos-learning/projects/android-to-harmony-codex54-benchmark-20260820';

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function readLatestGateEvidence(gate) {
  const evidenceDir = join(TARGET, '.migration', 'evidence');
  const records = readdirSync(evidenceDir)
    .filter((file) => file.endsWith('.json'))
    .map((file) => ({ file, record: readJson(join(evidenceDir, file)) }))
    .filter(({ record }) => record.gate === gate)
    .sort((left, right) => {
      const leftStarted = left.record.started_at ?? '';
      const rightStarted = right.record.started_at ?? '';
      return leftStarted.localeCompare(rightStarted);
    });

  assert.notEqual(records.length, 0, gate);
  return records.at(-1);
}

it('starts benchmark intake from workflow-owned fixed source and isolated target', () => {
  const agentState = readJson(join(RUN_ROOT, 'agent-state.json'));
  const buildProfile = readJson(join(TARGET, 'build-profile.json5'));

  assert.equal(agentState.paths.source.endsWith('/sources/modular-mobile-banking'), true);
  assert.equal(agentState.paths.target, TARGET);
  assert.equal(agentState.project.sdk_version, '6.1.1(24)');
  assert.equal(
    agentState.artifacts.snapshot_manifest_sha256,
    'd735a5287ae179193917bce581c9f0e1e51d8711a2c526fc32d4aadfaf6f5b66'
  );
  assert.deepEqual(
    buildProfile.modules.map((module) => module.name),
    ['entry', 'common', 'core', 'feature']
  );
});

it('keeps protected assets out of model-visible snapshot', () => {
  const contract = readJson(join(RUN_ROOT, 'migration-contract.json'));
  const safeManifest = readJson(join(RUN_ROOT, 'snapshot', '.android-to-harmony-safe.json'));

  assert.equal(contract.privacy.local_only_asset_count, 16);
  assert.equal(contract.privacy.blocked_file_count, 2);
  assert.equal(contract.privacy.known_image_paths_copied, false);
  assert.equal(safeManifest.schema, 'android-to-harmony.safe-snapshot.v1');
});

it('converts referenced auth and splash drawables into target media assets', () => {
  const safeManifest = readJson(join(RUN_ROOT, 'snapshot', '.android-to-harmony-safe.json'));
  const localAssetPaths = safeManifest.local_only_assets.map((asset) => asset.path);
  const loginPage = readFileSync(join(TARGET, 'entry', 'src', 'main', 'ets', 'pages', 'LoginPage.ets'), 'utf8');
  const registerPage = readFileSync(join(TARGET, 'entry', 'src', 'main', 'ets', 'pages', 'RegisterPage.ets'), 'utf8');
  const splashPage = readFileSync(join(TARGET, 'entry', 'src', 'main', 'ets', 'pages', 'SplashPage.ets'), 'utf8');

  for (const asset of [
    'features/src/main/res/drawable/bg_only_dark.xml',
    'features/src/main/res/drawable/bg_only_light.xml',
    'features/src/main/res/drawable/logo_app.xml',
    'features/src/main/res/drawable/logo_light.xml',
  ]) {
    assert.equal(localAssetPaths.includes(asset), true, asset);
  }

  for (const file of [
    'bg_only_dark.svg',
    'bg_only_light.svg',
    'logo_app.svg',
    'logo_light.svg',
  ]) {
    assert.equal(
      existsSync(join(TARGET, 'entry', 'src', 'main', 'resources', 'base', 'media', file)),
      true,
      file
    );
  }

  assert.match(loginPage, /\$r\('app\.media\.bg_only_dark'\)/);
  assert.match(loginPage, /\$r\('app\.media\.bg_only_light'\)/);
  assert.match(loginPage, /\$r\('app\.media\.logo_app'\)/);
  assert.match(loginPage, /\$r\('app\.media\.logo_light'\)/);
  assert.match(registerPage, /\$r\('app\.media\.bg_only_dark'\)/);
  assert.match(registerPage, /\$r\('app\.media\.bg_only_light'\)/);
  assert.match(registerPage, /\$r\('app\.media\.logo_app'\)/);
  assert.match(registerPage, /\$r\('app\.media\.logo_light'\)/);
  assert.match(splashPage, /\$r\('app\.media\.bg_only_dark'\)/);
  assert.match(splashPage, /\$r\('app\.media\.bg_only_light'\)/);
  assert.match(splashPage, /\$r\('app\.media\.logo_app'\)/);
  assert.match(splashPage, /\$r\('app\.media\.logo_light'\)/);
});

it('records full migration inventory accounting', () => {
  const slicesDir = join(TARGET, '.migration', 'slices');
  const authSlice = readJson(join(slicesDir, 'auth-flow.json'));
  const dashboardSlice = readJson(join(slicesDir, 'main-dashboard.json'));
  const notificationsSlice = readJson(join(slicesDir, 'notifications-init.json'));
  const reconciliation = readJson(join(TARGET, '.migration', 'inventory-reconciliation.json'));

  assert.equal(authSlice.schema, 'android-to-harmony.slice-ledger.v1');
  assert.equal(dashboardSlice.schema, 'android-to-harmony.slice-ledger.v1');
  assert.equal(notificationsSlice.schema, 'android-to-harmony.slice-ledger.v1');
  assert.equal(reconciliation.schema, 'android-to-harmony.inventory-reconciliation.v1');
  assert.equal(reconciliation.status, 'authoritative');
  assert.equal(reconciliation.all_snapshot_files_reviewed, true);
});

it('records executed harmony verification into .migration evidence ledgers', () => {
  for (const file of ['build.json', 'unit_tests.json', 'ui_tests.json']) {
    assert.equal(existsSync(join(TARGET, '.migration', 'evidence', file)), true, file);
  }

  const latestUiEvidence = readLatestGateEvidence('ui_tests');
  assert.equal(latestUiEvidence.record.status, 'passed');
  assert.equal(latestUiEvidence.record.tests.passed, 3);
  assert.equal(latestUiEvidence.record.tests.failed, 0);
  assert.equal(latestUiEvidence.record.device.id, '127.0.0.1:5555');
});

it('marks missing manual verification as pending instead of passed', () => {
  const statusSnapshot = readJson(join(CHANGE_DIR, 'evidence', 'migration-status.json'));
  const deviceEvidencePath = join(TARGET, '.migration', 'evidence', 'device_test.json');
  const deviceRetryEvidencePath = join(TARGET, '.migration', 'evidence', 'device_test_retry.json');
  const visualEvidencePath = join(TARGET, '.migration', 'evidence', 'visual_review.json');
  const runtimeEvidence = readFileSync(join(CHANGE_DIR, 'runtime-evidence.md'), 'utf8');
  const prSummary = readFileSync(join(CHANGE_DIR, 'pr-summary.md'), 'utf8');
  const pendingGates = statusSnapshot.pending_gates.map((item) => item.gate);

  assert.equal(existsSync(deviceEvidencePath), true);
  assert.equal(existsSync(deviceRetryEvidencePath), true);
  assert.equal(existsSync(visualEvidencePath), false);
  assert.equal(statusSnapshot.latest_evidence.ui_tests, 'passed');
  assert.deepEqual(pendingGates, [
    'visual_review',
    'slice_verification',
    'slice_verification',
    'slice_verification',
    'slice_verification',
    'slice_verification',
  ]);
  assert.equal(statusSnapshot.verified_slices.length, 0);
  assert.equal(statusSnapshot.implemented_slices.length, 5);
  assert.equal(statusSnapshot.complete, false);
  assert.match(runtimeEvidence, /ui_tests`: PASS/);
  assert.match(runtimeEvidence, /device_test`: PASS/);
  assert.match(runtimeEvidence, /visual_review`: PENDING/);
  assert.match(runtimeEvidence, /no `visual_review\.json` was created/);
  assert.match(runtimeEvidence, /selects the latest current-revision record for each gate/);
  assert.doesNotMatch(runtimeEvidence, /contains only the current gate records/);
  assert.match(prSummary, /\| Runtime acceptance \| `Pass` \|/);
  assert.match(prSummary, /\| Device Test \| `Required` \| `Pass` \|/);
});
