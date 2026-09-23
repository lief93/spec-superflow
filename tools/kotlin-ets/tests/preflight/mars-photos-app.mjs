import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { collectAttributes, runHarmonyApplication } from './harmony-application.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const checkout = process.argv[2] && resolve(process.argv[2]);
assert.ok(checkout && existsSync(join(checkout, '.git')),
  'Usage: node mars-photos-app.mjs /absolute/path/to/mars-photos-checkout');

runHarmonyApplication({
  checkout,
  evidenceName: 'mars-photos-app',
  preflightScript: join(here, 'mars-photos.mjs'),
  generatedFile: 'HomeScreen.ets',
  generatedPage: 'pages/HomeScreen.ets',
  mainPage: 'pages/Index.ets',
  hostSource: `import { HomeScreen, Loading } from './HomeScreen';

@Entry
@Component
struct MarsPhotosEntry {
  build() {
    Column() {
      HomeScreen({
        marsUiState: Loading.__etsGetInstance(),
        retryAction: () => {}
      })
    }
  }
}
`,
  copyGeneratedResources: true,
  appName: 'Mars Photos',
  component: 'MarsPhotosEntry',
  label: 'Mars Photos',
  devicePassMessage: 'install, launch, loading layout, process survival and screenshot capture',
  verifyGeneration({ diagnosis, source }) {
    assert.equal(diagnosis.blockingFailure, null);
    assert.equal(diagnosis.status, 'generated');
    assert.equal(diagnosis.degradationCount, 0);
    assert.match(source, /@Component\s+export struct HomeScreen/);
    assert.doesNotMatch(source, /@Entry\s+@Component\s+export struct HomeScreen/);
    for (const declaration of ['HomeScreen', 'Loading', 'Success', 'Error_0']) {
      assert.match(source, new RegExp(`export (?:struct|class) ${declaration}`));
    }
    assert.match(source, /static __etsGetInstance\(\): Loading/);
  },
  interactDevice({ run, hdc, target, bundleName, evidence, sha256 }) {
    let pid = '';
    for (let attempt = 1; attempt <= 5 && !pid; attempt += 1) {
      pid = run(`pid-after-launch-${attempt}`, hdc,
        [...target, 'shell', 'pidof', bundleName], { check: false }).stdout.trim();
      if (!pid && attempt < 5) spawnSync('sleep', ['1']);
    }
    assert.match(pid, /^\d+$/);
    const remoteLayout = '/data/local/tmp/kotlin-ets-mars-photos.json';
    run('layout', hdc, [...target, 'shell', 'uitest', 'dumpLayout',
      '-a', '-b', bundleName, '-p', remoteLayout]);
    const layout = join(evidence, 'layout.json');
    run('layout-recv', hdc, [...target, 'file', 'recv', remoteLayout, layout]);
    const nodes = collectAttributes(JSON.parse(readFileSync(layout, 'utf8')));
    assert.ok(nodes.some(node => node.bundleName === bundleName && node.pagePath === 'pages/Index'),
      'Launched application does not expose the Mars Photos entry page');
    for (const type of ['Column', 'Image']) {
      assert.ok(nodes.some(node => node.type === type && node.visible === 'true'),
        `Launched Mars Photos loading layout does not contain a visible ${type}`);
    }
    const remoteScreenshot = '/data/local/tmp/kotlin-ets-mars-photos.png';
    run('screenshot', hdc, [...target, 'shell', 'uitest', 'screenCap', '-p', remoteScreenshot]);
    const screenshot = join(evidence, 'loading.png');
    run('screenshot-recv', hdc, [...target, 'file', 'recv', remoteScreenshot, screenshot]);
    const image = readFileSync(screenshot);
    assert.equal(image.subarray(1, 4).toString(), 'PNG');
    const afterPid = run('pid-after-evidence', hdc, [...target, 'shell', 'pidof', bundleName]).stdout.trim();
    assert.equal(afterPid, pid, 'Application process did not survive layout and screenshot capture');
    return {
      pid, interaction: 'Generated loading layout rendered and process survived evidence capture',
      layout: { path: layout, sha256: sha256(layout) },
      screenshot: { path: screenshot, sha256: sha256(screenshot), bytes: image.length },
    };
  },
});
