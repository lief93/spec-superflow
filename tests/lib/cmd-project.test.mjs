import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { check } from '../../scripts/lib/cmd-project.mjs';

const roots = [];

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'ssf-project-'));
  roots.push(root);
  mkdirSync(join(root, '.github', 'instructions'), { recursive: true });
  mkdirSync(join(root, 'docs/project'), { recursive: true });
  mkdirSync(join(root, 'src'), { recursive: true });
  writeFileSync(join(root, 'src/App.kt'), 'class App { fun load() = Unit }\n');
  writeFileSync(
    join(root, '.github/instructions/spec-superflow.instructions.md'),
    `---
name: Spec Superflow Project Baseline
description: Apply the repository's generated development baseline.
applyTo: "**"
---

# Project

Read \`docs/project/project-guidelines.md\`.
`,
  );
  writeFileSync(
    join(root, 'docs/project/project-guidelines.md'),
    `# Project Development Baseline

## Technology And Framework Constraints

| Implementation Concern | Project-Standard Mechanism | How To Implement | Scope | Reference |
|---|---|---|---|---|
| Loading | Kotlin | Call load | app | \`src/App.kt#load\` |

## Architecture And Coding Rules

| Change Type | Owner | Required Collaboration | Must Not Occur | Reference |
|---|---|---|---|---|
| Page | App | Call load | Duplicate implementation | \`src/App.kt#App\` |

## Classic Implementation Index

### Add a page

- Applies when: Adding a page
- Create or modify: App
- Implementation order:
  1. Call load
- Must preserve: Single responsibility
- Done when: The page is visible
- Reference implementation: \`src/App.kt#load\`
`,
  );
  return root;
}

afterEach(() => {
  while (roots.length > 0) rmSync(roots.pop(), { recursive: true, force: true });
});

describe('ssf project check', () => {
  it('accepts a complete baseline and verifies source references', () => {
    const result = check(fixture());
    assert.deepEqual(result.issues, []);
    assert.equal(result.checkedPaths, 3);
    assert.equal(result.checkedSymbols, 3);
  });

  it('continues to accept an existing Chinese baseline', () => {
    const root = fixture();
    writeFileSync(
      join(root, 'docs/project/project-guidelines.md'),
      `# 项目开发基线

## 技术与框架约束

## 架构与编码规则

## 经典实现索引

### 新增页面

- 适用条件：新增页面
- 新建或修改：App
- 实现顺序：
  1. 调用 load
- 必须保持：单一职责
- 完成标准：页面可见
- 参考实现：\`src/App.kt#load\`
`,
    );

    const result = check(root);
    assert.deepEqual(result.issues, []);
    assert.equal(result.checkedPaths, 1);
    assert.equal(result.checkedSymbols, 1);
  });

  it('reports missing recipe fields and broken references', () => {
    const root = fixture();
    const guideline = join(root, 'docs/project/project-guidelines.md');
    writeFileSync(
      guideline,
      '# Project Development Baseline\n\n## Technology And Framework Constraints\n\n## Architecture And Coding Rules\n\n## Classic Implementation Index\n\n### Add a page\n\n- Applies when: Page\n- Reference implementation: `src/Missing.kt#load`\n',
    );
    const result = check(root);
    assert.ok(result.issues.some(issue => issue.includes('missing field: Implementation order')));
    assert.ok(result.issues.some(issue => issue.includes('Missing referenced path')));
  });

  it('reports unresolved placeholders', () => {
    const root = fixture();
    const instructions = join(root, '.github/instructions/spec-superflow.instructions.md');
    writeFileSync(instructions, `---
applyTo: "**"
---

Read \`docs/project/project-guidelines.md\`. <scope>
`);
    const result = check(root);
    assert.ok(result.issues.some(issue => issue.includes('Unresolved placeholder: <scope>')));
  });

  it('rejects project instructions without frontmatter', () => {
    const root = fixture();
    writeFileSync(
      join(root, '.github/instructions/spec-superflow.instructions.md'),
      '# Project\n\nRead `docs/project/project-guidelines.md`.\n',
    );

    const result = check(root);

    assert.ok(result.issues.some(issue => issue.includes('frontmatter')));
  });

  it('rejects project instructions with a non-global applyTo value', () => {
    const root = fixture();
    writeFileSync(
      join(root, '.github/instructions/spec-superflow.instructions.md'),
      `---
applyTo: "src/**"
---

Read \`docs/project/project-guidelines.md\`.
`,
    );

    const result = check(root);

    assert.ok(result.issues.some(issue => issue.includes('applyTo: "**"')));
  });
});
