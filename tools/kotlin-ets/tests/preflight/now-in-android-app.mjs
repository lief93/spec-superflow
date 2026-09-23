import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync,
} from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const checkout = process.argv[2] && resolve(process.argv[2]);
assert.ok(checkout && existsSync(join(checkout, '.git')),
  'Usage: node now-in-android-app.mjs /absolute/path/to/nowinandroid-checkout');

const seed = process.env.KOTLIN_ETS_SDK_SEED;
assert.ok(seed && existsSync(join(seed, 'oh-package.json5')),
  'KOTLIN_ETS_SDK_SEED must name a complete Harmony application seed');
const signingSource = process.env.KOTLIN_ETS_SIGNING_PROFILE;
const bundleName = process.env.KOTLIN_ETS_BUNDLE_NAME ?? 'dev.ets.widgetproof';
const device = process.env.KOTLIN_ETS_DEVICE;
const sdk = '/Applications/DevEco-Studio.app/Contents';
const hdc = join(sdk, 'sdk/default/openharmony/toolchains/hdc');
const evidence = mkdtempSync(join(here, '.work/now-in-android-app-'));
const host = join(evidence, 'harmony-app');
const result = { checkout, seed, host, bundleName, commands: [], passed: false };
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const record = () => writeFileSync(join(evidence, 'result.json'), JSON.stringify(result, null, 2) + '\n');
console.log(`Evidence: ${evidence}`);
record();

function run(label, command, args, options = {}) {
  const commandResult = spawnSync(command, args, {
    encoding: options.binary ? null : 'utf8', timeout: options.timeout ?? 600000,
    maxBuffer: 32 * 1024 * 1024, cwd: options.cwd, env: options.env ?? process.env,
  });
  if (!options.binary) {
    writeFileSync(join(evidence, `${label}.stdout`), commandResult.stdout ?? '');
    writeFileSync(join(evidence, `${label}.stderr`), commandResult.stderr ?? '');
  }
  result.commands.push({ label, command, args, cwd: options.cwd,
    status: commandResult.status, error: commandResult.error?.message });
  record();
  if (commandResult.error) throw commandResult.error;
  if (options.check !== false) assert.equal(commandResult.status, options.expected ?? 0,
    String(commandResult.stdout ?? '') + String(commandResult.stderr ?? ''));
  return commandResult;
}

function json5(path) {
  const source = readFileSync(path, 'utf8').replace(/,(\s*[}\]])/g, '$1');
  return JSON.parse(source);
}

function attributes(value, output = []) {
  if (Array.isArray(value)) value.forEach(item => attributes(item, output));
  else if (value && typeof value === 'object') {
    if (value.attributes) output.push(value.attributes);
    Object.entries(value).forEach(([key, item]) => key === 'attributes' || attributes(item, output));
  }
  return output;
}

function bounds(value) {
  if (typeof value === 'string') return [...value.matchAll(/-?\d+/g)].map(match => Number(match[0]));
  if (value && typeof value === 'object') return ['left', 'top', 'right', 'bottom'].map(key => value[key]);
  return [];
}

const preflight = run('project-preflight', 'node', [join(here, 'now-in-android.mjs'), checkout],
  { env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
const match = preflight.stdout.match(/^Evidence: (.+)$/m);
assert.ok(match, preflight.stdout);
const projectEvidence = resolve(match[1]);
const generated = join(projectEvidence, 'TagPreview.ets');
const diagnosisPath = generated + '.diagnosis.json';
const diagnosis = JSON.parse(readFileSync(diagnosisPath, 'utf8'));
assert.equal(diagnosis.blockingFailure, null);
assert.equal(diagnosis.status, 'generated_with_degradations');
assert.equal(diagnosis.degradations.length, 3);
assert.match(readFileSync(generated, 'utf8'), /@Entry\s+@Component\s+export struct TagPreview/);

const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
const ets = join(host, 'entry/src/main/ets');
rmSync(ets, { recursive: true, force: true });
mkdirSync(join(ets, 'pages'), { recursive: true });
mkdirSync(join(ets, 'entryability'), { recursive: true });
const page = join(ets, 'pages/Index.ets');
cpSync(generated, page);
cpSync(join(here, '../language/SdkEntryAbility.ets'), join(ets, 'entryability/EntryAbility.ets'));
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'),
  JSON.stringify({ src: ['pages/Index'] }, null, 2) + '\n');

const appPath = join(host, 'AppScope/app.json5');
const app = json5(appPath);
app.app.bundleName = bundleName;
writeFileSync(appPath, JSON.stringify(app, null, 2) + '\n');
const stringsPath = join(host, 'AppScope/resources/base/element/string.json');
const strings = JSON.parse(readFileSync(stringsPath, 'utf8'));
const appName = strings.string.find(value => value.name === 'app_name');
assert.ok(appName);
appName.value = 'Now in Android Tag Preview';
writeFileSync(stringsPath, JSON.stringify(strings, null, 2) + '\n');

const profilePath = join(host, 'build-profile.json5');
const unsignedProfile = readFileSync(profilePath, 'utf8');
let signed = false;
if (signingSource) {
  const sourceProfile = json5(resolve(signingSource));
  assert.ok(sourceProfile.app?.signingConfigs?.length, 'Signing source has no signingConfigs');
  const profile = json5(profilePath);
  profile.app.signingConfigs = sourceProfile.app.signingConfigs;
  profile.app.products[0].signingConfig = sourceProfile.app.products[0].signingConfig ??
    sourceProfile.app.signingConfigs[0].name;
  writeFileSync(profilePath, JSON.stringify(profile, null, 2) + '\n');
  signed = true;
}

const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
run('ohpm-install', join(sdk, 'tools/ohpm/bin/ohpm'), ['install'], { cwd: host, env });
const assembleArgs =
  ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon'];
const assembly = run('assemble-hap', join(sdk, 'tools/hvigor/bin/hvigorw'), assembleArgs,
  { cwd: host, env, check: !signed });
if (signed && assembly.status !== 0) {
  const failure = assembly.stdout + assembly.stderr;
  assert.match(failure, /certificate has expired/i,
    'Signed application build failed for a reason other than the configured certificate expiry');
  const expiry = failure.match(/certificate has expired! NotAfter: ([^\n\r]+)/i)?.[1];
  result.signingBlocker = { code: 'SIGNING_CERTIFICATE_EXPIRED', expiresAt: expiry,
    message: `The configured Harmony signing certificate has expired${expiry ? `: ${expiry}` : ''}` };
  writeFileSync(profilePath, unsignedProfile);
  signed = false;
  run('assemble-hap-unsigned', join(sdk, 'tools/hvigor/bin/hvigorw'), assembleArgs, { cwd: host, env });
}
assert.equal(hash(generated), hash(page), 'Generated ETS changed while staging the application');
const filesInfo = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt');
assert.match(readFileSync(filesInfo, 'utf8'), /pages\/Index\.ts;/);
const hapDirectory = join(host, 'entry/build/default/outputs/default');
const haps = readdirSync(hapDirectory).filter(name => name.endsWith('.hap'));
assert.ok(haps.length > 0, 'SDK did not produce a HAP');
const preferred = haps.find(name => name.endsWith('-signed.hap')) ?? haps[0];
const hap = join(hapDirectory, preferred);
if (signed) assert.match(preferred, /-signed\.hap$/);
result.projectEvidence = projectEvidence;
result.generated = { path: generated, sha256: hash(generated), diagnosis: diagnosisPath };
result.application = {
  ability: 'EntryAbility', page: 'pages/Index', component: 'TagPreview', stagedSha256: hash(page),
  signingRequested: Boolean(signingSource), signed,
};
result.hap = { path: hap, sha256: hash(hap), bytes: readFileSync(hap).length };
result.abc = { path: join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc'),
  sha256: hash(join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc')) };
record();

if (device) {
  const target = ['-t', device];
  const availability = run('device-availability', hdc,
    [...target, 'shell', 'param', 'get', 'const.product.software.version'], { check: false });
  if (availability.status !== 0 || !availability.stdout.trim()) {
    result.device = { target: device, status: 'unavailable',
      blocker: `Authorized Harmony device ${device} is not connected` };
  } else if (!signed) {
    result.device = { target: device, status: 'not-installed',
      blocker: result.signingBlocker?.message ?? 'The built HAP is unsigned' };
  } else {
    run('uninstall', hdc, [...target, 'uninstall', bundleName], { check: false });
    const install = run('install', hdc, [...target, 'install', '-r', hap]);
    assert.match(install.stdout + install.stderr, /successfully|success/i);
    run('launch', hdc, [...target, 'shell', 'aa', 'start', '-a', 'EntryAbility', '-b', bundleName]);
    const beforePid = run('pid-before-click', hdc, [...target, 'shell', 'pidof', bundleName]).stdout.trim();
    assert.match(beforePid, /^\d+$/);
    const remoteBefore = '/data/local/tmp/kotlin-ets-nia-before.json';
    run('layout-before', hdc, [...target, 'shell', 'uitest', 'dumpLayout', '-a', '-b', bundleName, '-p', remoteBefore]);
    const localBefore = join(evidence, 'layout-before.json');
    run('layout-before-recv', hdc, [...target, 'file', 'recv', remoteBefore, localBefore]);
    const beforeNodes = attributes(JSON.parse(readFileSync(localBefore, 'utf8')));
    const topic = beforeNodes.find(node => String(node.text ?? '').toUpperCase() === 'TOPIC');
    assert.ok(topic, 'Launched application does not expose the generated Topic text');
    const [left, top, right, bottom] = bounds(topic.bounds);
    assert.ok([left, top, right, bottom].every(Number.isFinite) && left < right && top < bottom,
      `Invalid Topic bounds: ${JSON.stringify(topic.bounds)}`);
    run('click-topic', hdc, [...target, 'shell', 'uitest', 'uiInput', 'click',
      String(Math.round((left + right) / 2)), String(Math.round((top + bottom) / 2))]);
    const afterPid = run('pid-after-click', hdc, [...target, 'shell', 'pidof', bundleName]).stdout.trim();
    assert.equal(afterPid, beforePid, 'Application process did not survive the generated onClick event');
    const remoteAfter = '/data/local/tmp/kotlin-ets-nia-after.json';
    run('layout-after', hdc, [...target, 'shell', 'uitest', 'dumpLayout', '-a', '-b', bundleName, '-p', remoteAfter]);
    const localAfter = join(evidence, 'layout-after.json');
    run('layout-after-recv', hdc, [...target, 'file', 'recv', remoteAfter, localAfter]);
    assert.ok(attributes(JSON.parse(readFileSync(localAfter, 'utf8')))
      .some(node => String(node.text ?? '').toUpperCase() === 'TOPIC'));
    const remoteScreenshot = '/data/local/tmp/kotlin-ets-nia.png';
    run('screenshot', hdc, [...target, 'shell', 'uitest', 'screenCap', '-p', remoteScreenshot]);
    const screenshot = join(evidence, 'after-click.png');
    run('screenshot-recv', hdc, [...target, 'file', 'recv', remoteScreenshot, screenshot]);
    const image = readFileSync(screenshot);
    assert.equal(image.subarray(1, 4).toString(), 'PNG');
    result.device = { target: device, status: 'pass', softwareVersion: availability.stdout.trim(),
      pid: beforePid, interaction: 'Topic click dispatched; process and generated layout survived',
      layoutBefore: { path: localBefore, sha256: hash(localBefore) },
      layoutAfter: { path: localAfter, sha256: hash(localAfter) },
      screenshot: { path: screenshot, sha256: hash(screenshot), bytes: image.length } };
    run('force-stop', hdc, [...target, 'shell', 'aa', 'force-stop', bundleName], { check: false });
  }
}

result.buildPassed = true;
result.passed = !device || result.device?.status === 'pass';
record();
console.log(`PASS NIA project entry -> wired Harmony application -> ${signed ? 'signed ' : ''}HAP`);
if (result.device?.status === 'pass') console.log('PASS install, launch, Topic click, process survival and screenshot capture');
else if (result.device) console.log(`DEVICE BLOCKER: ${result.device.blocker}`);
