// ssf sync <change-dir> — merge delta specs into main specs with conflict detection
import { readFileSync, readdirSync, writeFileSync, existsSync, statSync, mkdirSync } from 'node:fs';
import { join, basename, dirname, resolve, sep } from 'node:path';
import { loadConfig } from './config-loader.mjs';

function findSpecFiles(dir) {
  const results = [];
  if (!existsSync(dir)) return results;
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) results.push(...findSpecFiles(full));
    else if (entry === 'spec.md') results.push(full);
  }
  return results;
}

function parseCanonicalTarget(content) {
  const section = content.match(/^##\s+Canonical Target\s*\n([\s\S]*?)(?=^##\s+|\s*$)/im);
  if (!section) return null;

  const body = section[1];
  const pathMatch =
    body.match(/^\s*-\s*Path:\s*`?([^`\n]+?)`?\s*$/im) ||
    body.match(/^\s*Path:\s*`?([^`\n]+?)`?\s*$/im);

  if (!pathMatch) return null;

  return pathMatch[1].trim().replace(/\\/g, '/').replace(/^\.\//, '');
}

function resolveSyncTarget({ content, fallbackRelative, mainSpecsDir, projectRoot }) {
  const canonicalTarget = parseCanonicalTarget(content);

  if (!canonicalTarget) {
    const capabilityDir = fallbackRelative.replace('/spec.md', '');
    return {
      targetFile: join(mainSpecsDir, capabilityDir, 'spec.md'),
      displayPath: `specs/${capabilityDir}/spec.md`,
      usedCanonicalTarget: false,
    };
  }

  const invalidReason =
    canonicalTarget.startsWith('/') ? 'must be relative' :
    !canonicalTarget.startsWith('specs/') ? 'must start with specs/' :
    !canonicalTarget.endsWith('/spec.md') ? 'must end with /spec.md' :
    canonicalTarget.split('/').includes('..') ? 'must not contain .. segments' :
    null;

  if (invalidReason) {
    throw new Error(`Invalid Canonical Target "${canonicalTarget}": ${invalidReason}`);
  }

  const targetFile = resolve(projectRoot, canonicalTarget);
  const specsRoot = resolve(mainSpecsDir);
  if (targetFile !== specsRoot && !targetFile.startsWith(specsRoot + sep)) {
    throw new Error(`Invalid Canonical Target "${canonicalTarget}": target escapes specs/`);
  }

  return {
    targetFile,
    displayPath: canonicalTarget,
    usedCanonicalTarget: true,
  };
}

export async function run(args) {
  if (args.length < 1) {
    console.error('Usage: ssf sync <change-dir>');
    process.exit(2);
  }

  const changeDir = args[0];
  if (!existsSync(changeDir)) {
    console.error(`Error: "${changeDir}" not found`);
    process.exit(2);
  }

  const config = loadConfig(process.cwd());
  const { Validator, parseDeltaSpec } = await import('../../dist/index.js');
  const validator = new Validator();

  // Collect all unsynced changes for conflict detection
  const changesDir = join(process.cwd(), 'changes');
  const allDeltas = [];

  if (existsSync(changesDir)) {
    for (const dir of readdirSync(changesDir)) {
      const dirPath = join(changesDir, dir);
      if (!statSync(dirPath).isDirectory()) continue;
      const specsPath = join(dirPath, 'specs');
      if (!existsSync(specsPath)) continue;

      for (const specFile of findSpecFiles(specsPath)) {
        const content = readFileSync(specFile, 'utf-8');
        allDeltas.push({ changeName: dir, content });
      }
    }
  }

  // Check for conflicts
  if (allDeltas.length > 0) {
    const conflictReport = validator.detectSyncConflicts(allDeltas);
    if (conflictReport.hasConflicts) {
      console.log('⚠️  Sync conflicts detected:\n');
      for (const conflict of conflictReport.conflicts) {
        console.log(`  Requirement: "${conflict.requirement}"`);
        console.log(`  Modified by: ${conflict.changes.join(', ')}\n`);
      }
      console.log('Resolve conflicts before syncing. Consider syncing changes one at a time.');
      process.exit(1);
    }
  }

  // Perform sync: copy delta specs to main specs/
  const changeSpecsDir = join(changeDir, 'specs');
  const projectRoot = process.cwd();
  const mainSpecsDir = join(projectRoot, 'specs');
  const changeName = basename(changeDir);

  if (!existsSync(changeSpecsDir)) {
    console.log('No specs/ found in change directory.');
    return;
  }

  if (!existsSync(mainSpecsDir)) {
    mkdirSync(mainSpecsDir, { recursive: true });
  }

  const specFiles = findSpecFiles(changeSpecsDir);
  let synced = 0;

  for (const specFile of specFiles) {
    const relative = specFile.replace(changeSpecsDir + '/', '');
    const content = readFileSync(specFile, 'utf-8');
    const { targetFile, displayPath, usedCanonicalTarget } = resolveSyncTarget({
      content,
      fallbackRelative: relative,
      mainSpecsDir,
      projectRoot,
    });
    const targetDir = dirname(targetFile);

    if (!existsSync(targetDir)) {
      mkdirSync(targetDir, { recursive: true });
    }

    writeFileSync(targetFile, content);
    console.log(`  📋 Synced: ${displayPath}${usedCanonicalTarget ? ' (Canonical Target)' : ''}`);
    synced++;
  }

  console.log(`\n✅ Synced ${synced} spec(s) from ${changeName} to specs/`);
}
