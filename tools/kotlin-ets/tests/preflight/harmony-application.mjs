import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync,
} from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const sdk = '/Applications/DevEco-Studio.app/Contents';

export function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

export function collectAttributes(value, output = []) {
  if (Array.isArray(value)) value.forEach(item => collectAttributes(item, output));
  else if (value && typeof value === 'object') {
    if (value.attributes) output.push(value.attributes);
    Object.entries(value).forEach(([key, item]) => key === 'attributes' || collectAttributes(item, output));
  }
  return output;
}

export function parseBounds(value) {
  if (typeof value === 'string') return [...value.matchAll(/-?\d+/g)].map(match => Number(match[0]));
  if (value && typeof value === 'object') return ['left', 'top', 'right', 'bottom'].map(key => value[key]);
  return [];
}

function json5(path) {
  const source = readFileSync(path, 'utf8').replace(/,(\s*[}\]])/g, '$1');
  return JSON.parse(source);
}

function filesBelow(root, current = root) {
  return readdirSync(current, { withFileTypes: true }).flatMap(entry => {
    const path = join(current, entry.name);
    return entry.isDirectory() ? filesBelow(root, path) : [path.slice(root.length + 1)];
  });
}

function copyResourceBundle(source, target) {
  for (const relative of filesBelow(source)) {
    if (!relative.includes('/')) continue;
    const from = join(source, relative);
    const to = join(target, relative);
    mkdirSync(dirname(to), { recursive: true });
    if (relative.includes('/element/') && relative.endsWith('.json') && existsSync(to)) {
      const generated = JSON.parse(readFileSync(from, 'utf8'));
      const host = JSON.parse(readFileSync(to, 'utf8'));
      for (const [kind, entries] of Object.entries(generated)) {
        assert.ok(Array.isArray(entries), `Generated element resource group must be an array: ${relative}:${kind}`);
        const previous = host[kind] ?? [];
        assert.ok(Array.isArray(previous), `Host element resource group must be an array: ${relative}:${kind}`);
        const names = new Set(previous.map(entry => entry.name));
        host[kind] = [...previous, ...entries.filter(entry => !names.has(entry.name))];
      }
      writeFileSync(to, JSON.stringify(host, null, 2) + '\n');
    } else cpSync(from, to);
  }
}

export function runHarmonyApplication(config) {
  const checkout = resolve(config.checkout);
  assert.ok(existsSync(join(checkout, '.git')), `Checkout is not a Git worktree: ${checkout}`);
  const seed = process.env.KOTLIN_ETS_SDK_SEED;
  assert.ok(seed && existsSync(join(seed, 'oh-package.json5')),
    'KOTLIN_ETS_SDK_SEED must name a complete Harmony application seed');
  const signingSource = process.env.KOTLIN_ETS_SIGNING_PROFILE;
  const bundleName = process.env.KOTLIN_ETS_BUNDLE_NAME ?? config.defaultBundleName ?? 'dev.ets.widgetproof';
  const device = process.env.KOTLIN_ETS_DEVICE;
  mkdirSync(join(here, '.work'), { recursive: true });
  const evidence = mkdtempSync(join(here, `.work/${config.evidenceName}-`));
  const host = join(evidence, 'harmony-app');
  const hdc = join(sdk, 'sdk/default/openharmony/toolchains/hdc');
  const result = { checkout, seed, host, bundleName, commands: [], passed: false };
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

  const preflight = run('project-preflight', 'node', [config.preflightScript, checkout], {
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' },
  });
  const match = preflight.stdout.match(/^Evidence: (.+)$/m);
  assert.ok(match, preflight.stdout);
  const projectEvidence = resolve(match[1]);
  const generated = join(projectEvidence, config.generatedFile);
  const diagnosisPath = generated + '.diagnosis.json';
  const diagnosis = JSON.parse(readFileSync(diagnosisPath, 'utf8'));
  config.verifyGeneration({ diagnosis, generated, source: readFileSync(generated, 'utf8') });

  const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
  cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
  const ets = join(host, 'entry/src/main/ets');
  rmSync(ets, { recursive: true, force: true });
  mkdirSync(join(ets, 'pages'), { recursive: true });
  mkdirSync(join(ets, 'entryability'), { recursive: true });
  const generatedPage = join(ets, config.generatedPage);
  mkdirSync(dirname(generatedPage), { recursive: true });
  cpSync(generated, generatedPage);
  const mainPage = join(ets, config.mainPage ?? config.generatedPage);
  if (config.hostSource) writeFileSync(mainPage, config.hostSource);
  cpSync(join(here, '../language/SdkEntryAbility.ets'), join(ets, 'entryability/EntryAbility.ets'));
  writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'),
    JSON.stringify({ src: [(config.mainPage ?? config.generatedPage).replace(/\.ets$/, '')] }, null, 2) + '\n');

  let generatedResources;
  if (config.copyGeneratedResources) {
    generatedResources = generated + '.resources';
    assert.ok(existsSync(join(generatedResources, 'base')), 'Generated ETS resource bundle is missing');
    copyResourceBundle(generatedResources, join(host, 'entry/src/main/resources'));
  }

  const appPath = join(host, 'AppScope/app.json5');
  const app = json5(appPath);
  app.app.bundleName = bundleName;
  writeFileSync(appPath, JSON.stringify(app, null, 2) + '\n');
  const stringsPath = join(host, 'AppScope/resources/base/element/string.json');
  const strings = JSON.parse(readFileSync(stringsPath, 'utf8'));
  const appName = strings.string.find(value => value.name === 'app_name');
  assert.ok(appName);
  appName.value = config.appName;
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

  assert.equal(sha256(generated), sha256(generatedPage), 'Generated ETS changed while staging the application');
  const filesInfo = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt');
  for (const page of new Set([config.generatedPage, config.mainPage ?? config.generatedPage])) {
    assert.match(readFileSync(filesInfo, 'utf8'), new RegExp(page.replace(/\.ets$/, '\\.ts').replaceAll('/', '\\/') + ';'));
  }
  const hapDirectory = join(host, 'entry/build/default/outputs/default');
  const haps = readdirSync(hapDirectory).filter(name => name.endsWith('.hap'));
  assert.ok(haps.length > 0, 'SDK did not produce a HAP');
  const preferred = haps.find(name => name.endsWith('-signed.hap')) ?? haps[0];
  const hap = join(hapDirectory, preferred);
  if (signed) assert.match(preferred, /-signed\.hap$/);
  const abc = join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
  result.projectEvidence = projectEvidence;
  result.generated = { path: generated, sha256: sha256(generated), diagnosis: diagnosisPath };
  result.application = {
    ability: 'EntryAbility', page: (config.mainPage ?? config.generatedPage).replace(/\.ets$/, ''),
    component: config.component, stagedPath: generatedPage, stagedSha256: sha256(generatedPage),
    signingRequested: Boolean(signingSource), signed,
  };
  if (generatedResources) {
    const stagedResources = join(host, 'entry/src/main/resources');
    const files = filesBelow(generatedResources).filter(path => path.includes('/')).sort().map(path => {
      const sourceFile = join(generatedResources, path);
      const stagedFile = join(stagedResources, path);
      const sourceSha256 = sha256(sourceFile);
      const stagedSha256 = sha256(stagedFile);
      if (sourceSha256 !== stagedSha256) {
        assert.ok(path.includes('/element/') && path.endsWith('.json'),
          `Only element resources may merge with the host: ${path}`);
        const generated = JSON.parse(readFileSync(sourceFile, 'utf8'));
        const staged = JSON.parse(readFileSync(stagedFile, 'utf8'));
        for (const [kind, entries] of Object.entries(generated)) {
          for (const entry of entries) {
            assert.deepEqual(staged[kind]?.find(value => value.name === entry.name), entry,
              `Generated resource changed while staging: ${path}:${entry.name}`);
          }
        }
      }
      return { path, sourceSha256, stagedSha256, merged: sourceSha256 !== stagedSha256 };
    });
    result.resources = { source: generatedResources, staged: stagedResources, files };
  }
  result.hap = { path: hap, sha256: sha256(hap), bytes: readFileSync(hap).length };
  result.abc = { path: abc, sha256: sha256(abc), bytes: readFileSync(abc).length };
  record();

  if (device) {
    const target = ['-t', device];
    const availability = run('device-availability', hdc,
      [...target, 'shell', 'param', 'get', 'const.product.software.version'], { check: false });
    const softwareVersion = availability.stdout.trim();
    if (availability.status !== 0 || !softwareVersion || /\[Fail\]/i.test(softwareVersion + availability.stderr)) {
      result.device = { target: device, status: 'unavailable',
        blocker: `Authorized Harmony device ${device} is not connected` };
    } else {
      run('uninstall', hdc, [...target, 'uninstall', bundleName], { check: false });
      const install = run('install', hdc, [...target, 'install', '-r', hap]);
      assert.match(install.stdout + install.stderr, /successfully|success/i);
      run('launch', hdc, [...target, 'shell', 'aa', 'start', '-a', 'EntryAbility', '-b', bundleName]);
      result.device = { target: device, status: 'pass', softwareVersion,
        ...config.interactDevice?.({ run, hdc, target, bundleName, evidence, sha256 }) };
      run('force-stop', hdc, [...target, 'shell', 'aa', 'force-stop', bundleName], { check: false });
    }
  }

  result.buildPassed = true;
  result.passed = !device || result.device?.status === 'pass';
  record();
  console.log(`PASS ${config.label} project entry -> wired Harmony application -> ${signed ? 'signed ' : ''}HAP`);
  if (result.device?.status === 'pass') console.log(`PASS ${config.devicePassMessage}`);
  else if (result.device) console.log(`DEVICE BLOCKER: ${result.device.blocker}`);
  return { evidence, result };
}
