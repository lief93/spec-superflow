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
  mkdirSync(join(root, '.github'), { recursive: true });
  mkdirSync(join(root, 'docs/project'), { recursive: true });
  mkdirSync(join(root, 'src'), { recursive: true });
  writeFileSync(join(root, 'src/App.kt'), 'class App { fun load() = Unit }\n');
  writeFileSync(
    join(root, '.github/copilot-instructions.md'),
    '# Project\n\nRead `docs/project/project-guidelines.md`.\n',
  );
  writeFileSync(
    join(root, 'docs/project/project-guidelines.md'),
    `# 项目开发基线

## 技术与框架约束

| 实现问题 | 项目统一机制 | 开发时怎么做 | 适用范围 | 参考 |
|---|---|---|---|---|
| 加载 | Kotlin | 调用 load | app | \`src/App.kt#load\` |

## 架构与编码规则

| 要实现的改动 | 由谁负责 | 应该如何协作 | 不应该出现 | 参考 |
|---|---|---|---|---|
| 页面 | App | 调用 load | 重复实现 | \`src/App.kt#App\` |

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

  it('reports missing recipe fields and broken references', () => {
    const root = fixture();
    const guideline = join(root, 'docs/project/project-guidelines.md');
    writeFileSync(
      guideline,
      '# 项目开发基线\n\n## 技术与框架约束\n\n## 架构与编码规则\n\n## 经典实现索引\n\n### 新增页面\n\n- 适用条件：页面\n- 参考实现：`src/Missing.kt#load`\n',
    );
    const result = check(root);
    assert.ok(result.issues.some(issue => issue.includes('missing field: 实现顺序')));
    assert.ok(result.issues.some(issue => issue.includes('Missing referenced path')));
  });

  it('reports unresolved placeholders', () => {
    const root = fixture();
    const instructions = join(root, '.github/copilot-instructions.md');
    writeFileSync(instructions, 'Read `docs/project/project-guidelines.md`. <scope>\n');
    const result = check(root);
    assert.ok(result.issues.some(issue => issue.includes('Unresolved placeholder: <scope>')));
  });
});
