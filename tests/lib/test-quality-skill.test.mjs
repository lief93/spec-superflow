import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');
const read = path => readFileSync(join(root, path), 'utf8');

describe('test-quality skill', () => {
  it('is a reusable skill rather than another agent or workflow stage', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /^name: test-quality$/m);
    assert.match(skill, /does not own workflow state/i);
    assert.match(skill, /do not invoke another Agent/i);
    assert.match(skill, /do not create another planning artifact/i);
  });

  it('is loaded for both test planning and test implementation', () => {
    const writer = read('skills/spec-writer/SKILL.md');
    const executor = read('skills/build-executor/SKILL.md');

    assert.match(writer, /load the `test-quality` Skill before authoring or repairing `tasks\.md`/i);
    assert.match(executor, /load the `test-quality` Skill before writing or changing any planned test/i);
  });

  it('maps every observable AC clause to concrete test mechanics', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /WHEN, THEN, and AND/i);
    assert.match(skill, /precondition.*action.*assertion/is);
    assert.match(skill, /intermediate.*terminal/is);
    assert.match(skill, /new value.*old or stale value/is);
    assert.match(skill, /invariant/i);
  });

  it('covers evidenced alternative paths without inventing product behavior', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /alternative (entry|path)|entry paths/i);
    assert.match(skill, /same (business )?(rule|outcome|state)/i);
    assert.match(skill, /user intent|spec|existing (code|behavior)|repository evidence/i);
    assert.match(skill, /do not invent|never invent/i);
    assert.match(skill, /edge case|boundary value/i);
  });

  it('performs an aggregate AC coverage check after per-AC planning', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /aggregate AC coverage|whole-change coverage/i);
    assert.match(skill, /after.*(?:every|all).*AC|after.*per-AC/is);
    assert.match(skill, /end-to-end user journey|user journey/i);
    assert.match(skill, /empty (?:row|requirement)|uncovered|coverage gap/i);
    assert.match(skill, /duplicate.*proof|same test.*multiple AC/is);
    assert.match(skill, /compile|build success/i);
  });

  it('rejects common false proofs and requires controllable seams', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /rendered control/i);
    assert.match(skill, /no-op fake|inert fake/i);
    assert.match(skill, /callback count/i);
    assert.match(skill, /compile|build success/i);
    assert.match(skill, /Markdown|documentation/i);
    assert.match(skill, /lazy|scroll/i);
  });

  it('fails closed when the architecture seam is not decided', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /mutually\s+exclusive|alternative designs/i);
    assert.match(skill, /select neither|do not select.*either|plan neither/i);
    assert.match(skill, /decision gap|developer decision/i);
    assert.match(skill, /test obligation.*option|option.*test obligation/is);
  });

  it('covers reusable state, persistence, concurrency, and boundary patterns', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /persistence/i);
    assert.match(skill, /new owner|new instance|recreate/i);
    assert.match(skill, /concurrency/i);
    assert.match(skill, /barrier|deferred|controllable scheduler/i);
    assert.match(skill, /empty|zero/i);
    assert.match(skill, /success.*failure/is);
  });

  it('requires a real competing action before claiming concurrency suppression', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /competing (action|event).*(reach|invoke).*production seam/is);
    assert.match(skill, /control.*(?:disappears|absent).*does not prove.*(?:dedup|duplicate)/is);
    assert.match(skill, /same state owner|same production (?:entry|seam)/i);
    assert.match(skill, /cannot.*trigger.*competing.*planning (?:defect|gap)/is);
    assert.match(skill, /do not (?:weaken|rephrase|replace).*acceptance/i);
  });

  it('adds production semantics only when the acceptance outcome needs them', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /do not add.*(?:test tag|semantics).*unchanged.*(?:collection|content)/is);
    assert.match(skill, /existing.*(?:text|accessibility|semantics|scroll).*representative/is);
    assert.match(skill, /acceptance outcome.*(?:identity|location)|(?:identity|location).*acceptance outcome/is);
  });

  it('closes changed interfaces across production and test implementations', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /interface|contract/i);
    assert.match(skill, /all\s+implementations/i);
    assert.match(skill, /test doubles|fakes/i);
    assert.match(skill, /compile.*affected|affected.*compile/is);
    assert.match(skill, /record.*search (pattern|symbol).*matched paths/is);
    assert.match(skill, /reconcile.*File Changes/i);
  });

  it('keeps each test fixture within the production layer responsibility', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /layer.*responsib|responsib.*layer/is);
    assert.match(skill, /presentational|rendering layer/i);
    assert.match(skill, /already-derived|post-domain|filtered state/i);
    assert.match(skill, /callback.*dispatch|dispatch.*callback/is);
    assert.match(skill, /presentational.*must not.*filter.*fixture/is);
    assert.match(skill, /(?:real state owner|state owner).*full production integration/is);
    assert.match(skill, /missing.*integration seam|integration seam.*missing/is);
  });

  it('does not mistake a reused in-memory fake for process persistence', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /storage engine|backing file|serialized bytes/i);
    assert.match(skill, /same in-memory (object|fake)/i);
    assert.match(skill, /does not prove.*process|cannot prove.*process/is);
  });

  it('has explicit completion gates for interface and visible behavior proof', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /completion gate/i);
    assert.match(skill, /every concrete implementation/i);
    assert.match(skill, /every\s+test\s+double/i);
    assert.match(skill, /before\s+and\s+after rendered states/i);
    assert.match(skill, /do not reuse[\s\S]*different Scenario/i);
    assert.match(skill, /stateful.*host[\s\S]*must not[\s\S]*business/i);
    assert.match(skill, /real state owner|production integration seam/i);
    assert.match(skill, /each user-visible Scenario.*own UI row/i);
    assert.match(skill, /file-backed|new storage engine/i);
  });

  it('bounds repository research and stops when proof is sufficient', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /search budget/i);
    assert.match(skill, /stop researching/i);
    assert.match(skill, /do not decompile/i);
    assert.match(skill, /framework internals/i);
    assert.match(skill, /targeted symbol and path searches/i);
    assert.match(skill, /record any remaining narrow uncertainty/i);
  });

  it('requires executable commands with platform-correct test selection', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /exact command.*repository evidence|repository evidence.*exact command/is);
    assert.match(skill, /JVM.*instrumentation|instrumentation.*JVM/is);
    assert.match(skill, /do not invent.*task|do not invent.*flag/is);
    assert.match(skill, /module(?:-scoped| task)|target module/i);
    assert.match(skill, /task discovery|tasks --all|dry-run/i);
    assert.match(skill, /before (?:freezing|recording|returning).*command|verify.*command.*before/is);
  });

  it('does not label unverified test commands as exact', () => {
    const skill = read('skills/test-quality/SKILL.md');

    assert.match(skill, /task discovery.*dry-run.*cannot run/is);
    assert.match(skill, /do not record.*exact command/is);
    assert.match(skill, /candidate\s+command/i);
    assert.match(skill, /command verification.*blocked/i);
  });
});
