// scripts/lib/hash.mjs — SHA256 artifact hashing for fast staleness detection
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

// Compute a joint SHA256 hash of all 4 planning artifacts.
// Input: proposal.md + specs/*/spec.md (sorted) + design.md + tasks.md
export function computeArtifactsHash(changeDir) {
  const hash = crypto.createHash('sha256');
  let hasContent = false;

  // proposal.md
  const proposal = path.join(changeDir, 'proposal.md');
  if (fs.existsSync(proposal)) {
    hash.update(fs.readFileSync(proposal, 'utf-8'));
    hasContent = true;
  }

  // specs/*/spec.md (sorted for deterministic output)
  // Only hash spec.md files — exclude README.md, design-notes.md, etc.
  const specsDir = path.join(changeDir, 'specs');
  if (fs.existsSync(specsDir)) {
    const specFiles = [];
    walkDir(specsDir, specFiles);
    specFiles.sort();
    for (const f of specFiles) {
      if (path.basename(f) === 'spec.md') {
        hash.update(fs.readFileSync(f, 'utf-8'));
        hasContent = true;
      }
    }
  }

  // design.md
  const design = path.join(changeDir, 'design.md');
  if (fs.existsSync(design)) {
    hash.update(fs.readFileSync(design, 'utf-8'));
    hasContent = true;
  }

  // tasks.md
  const tasks = path.join(changeDir, 'tasks.md');
  if (fs.existsSync(tasks)) {
    hash.update(fs.readFileSync(tasks, 'utf-8'));
    hasContent = true;
  }

  return hasContent ? `sha256:${hash.digest('hex')}` : null;
}

// Compute SHA256 hash of execution-contract.md alone.
export function computeContractHash(changeDir) {
  const contract = path.join(changeDir, 'execution-contract.md');
  if (!fs.existsSync(contract)) return null;
  const hash = crypto.createHash('sha256');
  hash.update(fs.readFileSync(contract, 'utf-8'));
  return `sha256:${hash.digest('hex')}`;
}

// Fast staleness check: compare stored artifacts_hash against current.
export function isContractFresh(changeDir, stateLoader) {
  const stateFile = path.join(changeDir, '.spec-superflow.yaml');
  if (!fs.existsSync(stateFile)) return false;

  const raw = fs.readFileSync(stateFile, 'utf-8');
  const storedHash = extractYamlField(raw, 'artifacts_hash');
  if (!storedHash || storedHash === 'null') return false;

  const currentHash = computeArtifactsHash(changeDir);
  return storedHash === currentHash;
}

function walkDir(dir, result) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walkDir(full, result);
    else result.push(full);
  }
}

function extractYamlField(content, field) {
  for (const line of content.split('\n')) {
    const match = line.match(new RegExp(`^${field}:\\s*(.*)`));
    if (match) {
      const val = match[1].trim();
      return val === 'null' || val === '' ? null : val;
    }
  }
  return null;
}
