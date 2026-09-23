import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
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
  generatedPage: 'pages/TagPreview.ets',
  mainPage: 'pages/Index.ets',
  hostSource: `import { TagPreview } from './TagPreview';

@Entry
@Component
struct NiaEntry {
  @State interactionCount: number = 0;

  build() {
    Column() {
      Text('INTERACTIONS: ' + this.interactionCount).id('interaction-state')
      Button('ADVANCE').id('interaction-probe').onClick(() => { this.interactionCount += 1; })
      TagPreview()
    }.width('100%').height('100%')
  }
}
`,
  copyGeneratedResources: true,
  appName: 'Now in Android Tag Preview',
  component: 'TagPreview',
  label: 'NIA',
  devicePassMessage: 'install, launch, Topic render, state-changing interaction, process survival and screenshot capture',
  verifyGeneration({ diagnosis, source }) {
    assert.equal(diagnosis.blockingFailure, null);
    assert.equal(diagnosis.status, 'generated_with_degradations');
    assert.equal(diagnosis.degradations.length, 3);
    assert.match(source, /@Entry\s+@Component\s+export struct TagPreview/);
  },
  interactDevice({ run, hdc, target, bundleName, evidence, sha256 }) {
    let beforePid = '';
    for (let attempt = 1; attempt <= 5 && !beforePid; attempt += 1) {
      beforePid = run(`pid-after-launch-${attempt}`, hdc,
        [...target, 'shell', 'pidof', bundleName], { check: false }).stdout.trim();
      if (!beforePid && attempt < 5) spawnSync('sleep', ['1']);
    }
    assert.match(beforePid, /^\d+$/);
    const remoteBefore = '/data/local/tmp/kotlin-ets-nia-before.json';
    run('layout-before', hdc, [...target, 'shell', 'uitest', 'dumpLayout', '-a', '-b', bundleName, '-p', remoteBefore]);
    const localBefore = join(evidence, 'layout-before.json');
    run('layout-before-recv', hdc, [...target, 'file', 'recv', remoteBefore, localBefore]);
    const beforeNodes = collectAttributes(JSON.parse(readFileSync(localBefore, 'utf8')));
    const topic = beforeNodes.find(node => String(node.text ?? '').toUpperCase() === 'TOPIC');
    assert.ok(topic, 'Launched application does not expose the generated Topic text');
    assert.ok(beforeNodes.some(node => node.text === 'INTERACTIONS: 0'));
    const advance = beforeNodes.find(node => node.text === 'ADVANCE');
    assert.ok(advance, 'Interaction probe is missing from the generated-page host');
    const [left, top, right, bottom] = parseBounds(advance.bounds);
    assert.ok([left, top, right, bottom].every(Number.isFinite) && left < right && top < bottom,
      `Invalid interaction bounds: ${JSON.stringify(advance.bounds)}`);
    run('click-advance', hdc, [...target, 'shell', 'uitest', 'uiInput', 'click',
      String(Math.round((left + right) / 2)), String(Math.round((top + bottom) / 2))]);
    const afterPid = run('pid-after-click', hdc, [...target, 'shell', 'pidof', bundleName]).stdout.trim();
    assert.equal(afterPid, beforePid, 'Application process did not survive the generated onClick event');
    const remoteAfter = '/data/local/tmp/kotlin-ets-nia-after.json';
    run('layout-after', hdc, [...target, 'shell', 'uitest', 'dumpLayout', '-a', '-b', bundleName, '-p', remoteAfter]);
    const localAfter = join(evidence, 'layout-after.json');
    run('layout-after-recv', hdc, [...target, 'file', 'recv', remoteAfter, localAfter]);
    const afterNodes = collectAttributes(JSON.parse(readFileSync(localAfter, 'utf8')));
    assert.ok(afterNodes.some(node => String(node.text ?? '').toUpperCase() === 'TOPIC'));
    assert.ok(afterNodes.some(node => node.text === 'INTERACTIONS: 1'),
      'ArkUI state did not change after the interaction');
    const remoteScreenshot = '/data/local/tmp/kotlin-ets-nia.png';
    run('screenshot', hdc, [...target, 'shell', 'uitest', 'screenCap', '-p', remoteScreenshot]);
    const screenshot = join(evidence, 'after-click.png');
    run('screenshot-recv', hdc, [...target, 'file', 'recv', remoteScreenshot, screenshot]);
    const image = readFileSync(screenshot);
    assert.equal(image.subarray(1, 4).toString(), 'PNG');
    return {
      pid: beforePid, interaction: 'Advance click changed INTERACTIONS: 0 to INTERACTIONS: 1; generated Topic remained visible',
      layoutBefore: { path: localBefore, sha256: sha256(localBefore) },
      layoutAfter: { path: localAfter, sha256: sha256(localAfter) },
      screenshot: { path: screenshot, sha256: sha256(screenshot), bytes: image.length },
    };
  },
});
