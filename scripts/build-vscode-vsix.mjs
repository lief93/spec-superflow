#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const EXTENSION_SOURCE = join(ROOT, 'extensions', 'spec-superflow-companion');

function copy(source, destination) {
  mkdirSync(dirname(destination), { recursive: true });
  copyFileSync(source, destination);
}

function npmPackageFiles() {
  const packed = spawnSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], {
    cwd: ROOT,
    encoding: 'utf8',
    maxBuffer: 20 * 1024 * 1024,
  });
  if (packed.status !== 0) throw new Error(packed.stderr || packed.stdout);
  const result = JSON.parse(packed.stdout)[0];
  if (!result?.files?.length) throw new Error('npm pack did not return Plugin files.');
  return result.files.map(file => file.path);
}

function stageAgentPlugin(extensionRoot) {
  const pluginRoot = join(extensionRoot, 'agent-plugin');
  for (const path of npmPackageFiles()) copy(join(ROOT, path), join(pluginRoot, path));

  rmSync(join(pluginRoot, '.mcp.json'), { force: true });
  rmSync(join(pluginRoot, 'servers', 'token-example-mcp.mjs'), { force: true });
  rmSync(join(pluginRoot, 'examples', 'mcp', 'token-auth'), { recursive: true, force: true });
  for (const manifestPath of [
    join(pluginRoot, 'plugin.json'),
    join(pluginRoot, '.plugin', 'plugin.json'),
  ]) {
    if (!existsSync(manifestPath)) continue;
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
    delete manifest.mcpServers;
    writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  }

  cpSync(join(EXTENSION_SOURCE, 'agent-plugin-additions'), pluginRoot, {
    recursive: true,
    force: true,
  });
}

function xml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function stageVsix(root) {
  const extensionRoot = join(root, 'extension');
  rmSync(extensionRoot, { recursive: true, force: true });
  mkdirSync(extensionRoot, { recursive: true });

  for (const file of ['package.json', 'extension.cjs']) {
    copy(join(EXTENSION_SOURCE, file), join(extensionRoot, file));
  }
  copy(join(EXTENSION_SOURCE, 'README.md'), join(extensionRoot, 'readme.md'));
  copy(join(EXTENSION_SOURCE, 'LICENSE'), join(extensionRoot, 'LICENSE.txt'));
  stageAgentPlugin(extensionRoot);

  const manifest = JSON.parse(readFileSync(join(EXTENSION_SOURCE, 'package.json'), 'utf8'));
  writeFileSync(join(root, 'extension.vsixmanifest'), `<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="${xml(manifest.name)}" Version="${xml(manifest.version)}" Publisher="${xml(manifest.publisher)}" />
    <DisplayName>${xml(manifest.displayName)}</DisplayName>
    <Description xml:space="preserve">${xml(manifest.description)}</Description>
    <Tags>agent-plugin,language-model-tools,offline</Tags>
    <Categories>AI</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="${xml(manifest.engines.vscode)}" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
      <Property Id="Microsoft.VisualStudio.Code.ExecutesCode" Value="true" />
      <Property Id="Microsoft.VisualStudio.Services.GitHubFlavoredMarkdown" Value="true" />
      <Property Id="Microsoft.VisualStudio.Services.Content.Pricing" Value="Free" />
    </Properties>
    <License>extension/LICENSE.txt</License>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code" /></Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/readme.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true" />
  </Assets>
</PackageManifest>
`);
  writeFileSync(join(root, '[Content_Types].xml'), `<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="cjs" ContentType="application/octet-stream" />
  <Default Extension="cmd" ContentType="application/octet-stream" />
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="md" ContentType="text/markdown" />
  <Default Extension="mjs" ContentType="application/javascript" />
  <Default Extension="txt" ContentType="text/plain" />
  <Default Extension="vsixmanifest" ContentType="text/xml" />
</Types>
`);
  return extensionRoot;
}

function buildVsix(output) {
  const stage = mkdtempSync(join(tmpdir(), 'spec-superflow-vsix-'));
  try {
    stageVsix(stage);
    mkdirSync(dirname(output), { recursive: true });
    rmSync(output, { force: true });
    const zipped = spawnSync('zip', ['-X', '-q', '-r', output, '.'], {
      cwd: stage,
      encoding: 'utf8',
    });
    if (zipped.status !== 0) throw new Error(zipped.stderr || zipped.stdout);
  } finally {
    rmSync(stage, { recursive: true, force: true });
  }
}

const rootPackage = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const [mode, argument] = process.argv.slice(2);
if (mode === '--stage-only') {
  if (!argument) throw new Error('--stage-only requires an output directory.');
  stageVsix(resolve(argument));
  process.stdout.write(`${JSON.stringify({ stage: resolve(argument) })}\n`);
} else {
  const output = resolve(
    mode || join(ROOT, 'release-assets', 'vscode', `spec-superflow-${rootPackage.version}.vsix`),
  );
  buildVsix(output);
  process.stdout.write(`${JSON.stringify({ output, version: rootPackage.version })}\n`);
}

export { stageVsix };
