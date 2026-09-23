import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runHarmonyApplication } from './harmony-application.mjs';

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
  knownSigningBlocker: {
    code: 'SIGNING_CERTIFICATE_EXPIRED',
    expiresAt: 'Sun Aug 30 03:33:22 CST 2026',
    message: 'The configured Harmony signing certificate expired Sun Aug 30 03:33:22 CST 2026',
  },
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
});
