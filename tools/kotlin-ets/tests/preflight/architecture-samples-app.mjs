import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runHarmonyApplication } from './harmony-application.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const checkout = process.argv[2] && resolve(process.argv[2]);
assert.ok(checkout && existsSync(join(checkout, '.git')),
  'Usage: node architecture-samples-app.mjs /absolute/path/to/architecture-samples-checkout');

runHarmonyApplication({
  checkout,
  evidenceName: 'architecture-samples-app',
  preflightScript: join(here, 'architecture-samples.mjs'),
  generatedFile: 'StatisticsScreen.ets',
  generatedPage: 'pages/StatisticsScreen.ets',
  mainPage: 'pages/Index.ets',
  hostSource: `import {
  EtsSnackbarHostState, EtsStateFlow, StatisticsScreen,
  StatisticsUiState, StatisticsViewModelBridge
} from './StatisticsScreen';

class StatisticsHostViewModel implements StatisticsViewModelBridge {
  readonly uiState: EtsStateFlow<StatisticsUiState> = new EtsStateFlow<StatisticsUiState>({
    isEmpty: false,
    isLoading: false,
    activeTasksPercent: 50,
    completedTasksPercent: 50
  } as StatisticsUiState);

  refresh(): void {}
}

@Entry
@Component
struct StatisticsEntry {
  private readonly viewModel: StatisticsHostViewModel = new StatisticsHostViewModel();
  private readonly snackbarHostState: EtsSnackbarHostState = new EtsSnackbarHostState();

  build() {
    Column() {
      StatisticsScreen({
        openDrawer: () => {},
        viewModel: this.viewModel,
        snackbarHostState: this.snackbarHostState
      })
    }.width('100%').height('100%')
  }
}
`,
  copyGeneratedResources: true,
  appName: 'Architecture Statistics',
  component: 'StatisticsEntry',
  label: 'Architecture Samples',
  devicePassMessage: 'install, launch, generated statistics layout and stable process',
  verifyGeneration({ diagnosis, source }) {
    assert.equal(diagnosis.blockingFailure, null);
    assert.deepEqual(diagnosis.degradations.map(value => value.action), ['dimension_qualifier_fallback']);
    assert.match(source, /@Component\s+export struct StatisticsScreen/);
    assert.match(source, /Refresh\(\{ refreshing: loading \}\)/);
  },
  interactDevice({ run, hdc, target, bundleName, evidence, sha256 }) {
    let pid = '';
    for (let attempt = 1; attempt <= 5 && !pid; attempt += 1) {
      pid = run(`pid-after-launch-${attempt}`, hdc,
        [...target, 'shell', 'pidof', bundleName], { check: false }).stdout.trim();
      if (!pid && attempt < 5) spawnSync('sleep', ['1']);
    }
    assert.match(pid, /^\d+$/);
    const remoteBefore = '/data/local/tmp/kotlin-ets-architecture-before.json';
    run('layout-before', hdc, [...target, 'shell', 'uitest', 'dumpLayout', '-a', '-b', bundleName, '-p', remoteBefore]);
    const layoutBefore = join(evidence, 'layout-before.json');
    run('layout-before-recv', hdc, [...target, 'file', 'recv', remoteBefore, layoutBefore]);
    const before = readFileSync(layoutBefore, 'utf8');
    assert.match(before, /Statistics|Active tasks|Completed tasks/);
    const button = JSON.parse(before);
    const queue = [button];
    let bounds;
    while (queue.length && !bounds) {
      const value = queue.shift();
      if (Array.isArray(value)) queue.push(...value);
      else if (value && typeof value === 'object') {
        if (value.attributes?.type === 'Button' && value.attributes?.clickable === 'true') bounds = value.attributes.bounds;
        queue.push(...Object.values(value));
      }
    }
    const coordinates = [...String(bounds).matchAll(/-?\d+/g)].map(match => Number(match[0]));
    assert.equal(coordinates.length, 4);
    const remoteScreenshot = '/data/local/tmp/kotlin-ets-architecture-statistics.png';
    run('screenshot', hdc, [...target, 'shell', 'uitest', 'screenCap', '-p', remoteScreenshot]);
    const screenshot = join(evidence, 'statistics.png');
    run('screenshot-recv', hdc, [...target, 'file', 'recv', remoteScreenshot, screenshot]);
    const image = readFileSync(screenshot);
    assert.equal(image.subarray(1, 4).toString(), 'PNG');
    return { pid, interaction: 'Generated statistics state rendered without host-only visual probes',
      layoutBefore: { path: layoutBefore, sha256: sha256(layoutBefore) },
      screenshot: { path: screenshot, sha256: sha256(screenshot), bytes: image.length } };
  },
});
