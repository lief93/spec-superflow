import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const EXTENSION = join(ROOT, 'extensions', 'spec-superflow-companion');
const require = createRequire(import.meta.url);

describe('Spec Superflow companion VSIX probe', () => {
  it('contributes one local read-only probe tool with a fixed result', () => {
    const manifest = JSON.parse(readFileSync(join(EXTENSION, 'package.json'), 'utf8'));
    const source = readFileSync(join(EXTENSION, 'extension.cjs'), 'utf8');
    const implementation = require(join(EXTENSION, 'extension.cjs'));

    assert.deepEqual(manifest.activationEvents, [
      'onLanguageModelTool:spec_superflow_companion_probe',
    ]);
    assert.deepEqual(manifest.contributes.languageModelTools, [
      {
        name: 'spec_superflow_companion_probe',
        toolReferenceName: 'specSuperflowCompanionProbe',
        displayName: 'Spec Superflow Companion Probe',
        canBeReferencedInPrompt: true,
        modelDescription: 'Verify that this VS Code can invoke a local Spec Superflow companion tool.',
        userDescription: 'Verify local Spec Superflow companion tool access.',
        inputSchema: {
          type: 'object',
          properties: {},
          additionalProperties: false,
        },
      },
    ]);
    assert.deepEqual(implementation.probePayload(), {
      ok: true,
      source: 'spec-superflow-companion-vsix',
      networkUsed: false,
    });
    assert.deepEqual(manifest.dependencies, undefined);
    assert.doesNotMatch(source, /child_process|https?:|fetch\(|XMLHttpRequest|net\.|tls\./);
  });
});
