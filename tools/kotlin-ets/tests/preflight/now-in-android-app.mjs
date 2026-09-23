import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  collectAttributes, parseBounds, runHarmonyApplication,
} from './harmony-application.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const checkout = process.argv[2] && resolve(process.argv[2]);
assert.ok(checkout && existsSync(join(checkout, '.git')),
  'Usage: node now-in-android-app.mjs /absolute/path/to/nowinandroid-checkout');

runHarmonyApplication({
  checkout,
  evidenceName: 'now-in-android-app',
  preflightScript: join(here, 'now-in-android.mjs'),
  generatedFile: 'TagPreview.ets',
  generatedPage: 'pages/Index.ets',
  appName: 'Now in Android Tag Preview',
  component: 'TagPreview',
  label: 'NIA',
  devicePassMessage: 'install, launch, Topic click, process survival and screenshot capture',
  verifyGeneration({ diagnosis, source }) {
    assert.equal(diagnosis.blockingFailure, null);
    assert.equal(diagnosis.status, 'generated_with_degradations');
    assert.equal(diagnosis.degradations.length, 3);
    assert.match(source, /@Entry\s+@Component\s+export struct TagPreview/);
  },
  interactDevice({ run, hdc, target, bundleName, evidence, sha256 }) {
    const beforePid = run('pid-before-click', hdc, [...target, 'shell', 'pidof', bundleName]).stdout.trim();
    assert.match(beforePid, /^\d+$/);
    const remoteBefore = '/data/local/tmp/kotlin-ets-nia-before.json';
    run('layout-before', hdc, [...target, 'shell', 'uitest', 'dumpLayout', '-a', '-b', bundleName, '-p', remoteBefore]);
    const localBefore = join(evidence, 'layout-before.json');
    run('layout-before-recv', hdc, [...target, 'file', 'recv', remoteBefore, localBefore]);
    const beforeNodes = collectAttributes(JSON.parse(readFileSync(localBefore, 'utf8')));
    const topic = beforeNodes.find(node => String(node.text ?? '').toUpperCase() === 'TOPIC');
    assert.ok(topic, 'Launched application does not expose the generated Topic text');
    const [left, top, right, bottom] = parseBounds(topic.bounds);
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
    assert.ok(collectAttributes(JSON.parse(readFileSync(localAfter, 'utf8')))
      .some(node => String(node.text ?? '').toUpperCase() === 'TOPIC'));
    const remoteScreenshot = '/data/local/tmp/kotlin-ets-nia.png';
    run('screenshot', hdc, [...target, 'shell', 'uitest', 'screenCap', '-p', remoteScreenshot]);
    const screenshot = join(evidence, 'after-click.png');
    run('screenshot-recv', hdc, [...target, 'file', 'recv', remoteScreenshot, screenshot]);
    const image = readFileSync(screenshot);
    assert.equal(image.subarray(1, 4).toString(), 'PNG');
    return {
      pid: beforePid, interaction: 'Topic click dispatched; process and generated layout survived',
      layoutBefore: { path: localBefore, sha256: sha256(localBefore) },
      layoutAfter: { path: localAfter, sha256: sha256(localAfter) },
      screenshot: { path: screenshot, sha256: sha256(screenshot), bytes: image.length },
    };
  },
});
