import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = path.resolve("bin/harmony-quality.mjs");

async function qualityReport(root) {
  return JSON.parse(await readFile(
    path.join(root, ".harmony-quality/reports/quality-report.json"),
    "utf8",
  ));
}

test("check traces ArkTS lint, architecture, complexity, CRAP, and empty catch findings", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony static analysis "));
  const relativeSource = "entry/src/main/ets/pages/Home.ets";
  const source = path.join(root, relativeSource);
  await mkdir(path.dirname(source), { recursive: true });
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(
    source,
    [
      "import { Repository } from '../../data/Repository'",
      "export function classify(value: boolean, alternate: boolean): number {",
      "  try {",
      "    if (value && alternate) {",
      "      return 1",
      "    }",
      "  } catch (error) {}",
      "  return 0",
      "}",
      "",
    ].join("\n"),
  );
  await writeFile(
    path.join(root, "quality/lint.json"),
    JSON.stringify({
      issues: [{
        ruleId: "arkts-no-any",
        type: "code-smell",
        severity: "major",
        file: relativeSource,
        line: 2,
        message: "Avoid any",
      }],
    }),
  );
  await writeFile(
    path.join(root, "quality/lcov.info"),
    `TN:\nSF:${relativeSource}\nFN:2,classify\nFNDA:0,classify\nDA:2,0\nDA:3,0\nDA:4,0\nDA:5,0\nDA:6,0\nDA:8,0\nDA:9,0\nend_of_record\n`,
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      evidence: {
        coverage: { format: "lcov", path: "quality/lcov.info" },
        linter: { format: "arkts-json", path: "quality/lint.json" },
      },
      analysis: {
        maxFunctionLines: 40,
        maxComplexity: 10,
        maxNesting: 4,
        duplicateWindow: 6,
        architectureRules: [{
          id: "ui-must-not-import-data",
          from: "entry/src/main/ets/pages/",
          forbiddenImports: ["/data/"],
        }],
      },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  assert.equal(report.status, "PASS");
  assert.deepEqual(report.functions, [{
    file: relativeSource,
    name: "classify",
    startLine: 2,
    endLine: 9,
    complexity: 4,
    coverage: 0,
    crap: 20,
    maxNesting: 2,
  }]);
  assert.deepEqual(
    report.issues.map(({ rule_id, source }) => [rule_id, source]).sort(),
    [
      ["arkts-no-any", "arkts-linter"],
      ["empty-catch", "harmony-quality"],
      ["line-must-be-covered", "lcov"],
      ["line-must-be-covered", "lcov"],
      ["line-must-be-covered", "lcov"],
      ["line-must-be-covered", "lcov"],
      ["line-must-be-covered", "lcov"],
      ["line-must-be-covered", "lcov"],
      ["line-must-be-covered", "lcov"],
      ["ui-must-not-import-data", "architecture-rule"],
    ].sort(),
  );
  assert.equal(
    report.metrics.find(({ id }) => id === "max_crap").value,
    20,
  );
  assert.equal(
    report.metrics.find(({ id }) => id === "max_complexity").value,
    4,
  );
  const evidenceIds = new Set(report.evidence.map(({ id }) => id));
  for (const issue of report.issues) {
    for (const evidence of issue.evidence) assert.equal(evidenceIds.has(evidence), true, evidence);
  }
  for (const metric of report.metrics) {
    for (const evidence of metric.evidence) assert.equal(evidenceIds.has(evidence), true, evidence);
  }
});

test("functions have unknown coverage and CRAP when coverage evidence is absent", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony no coverage "));
  const relativeSource = "entry/src/main/ets/Plain.ets";
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await writeFile(
    path.join(root, relativeSource),
    "export function plain(value: boolean): number { return value ? 1 : 0 }\n",
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      analysis: { duplicateWindow: 6 },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  assert.equal(report.functions[0].coverage, null);
  assert.equal(report.functions[0].crap, null);
  assert.equal(report.metrics.some(({ id }) => id === "max_crap"), false);
});

test("function size complexity and nesting rules honor exact thresholds", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony static thresholds "));
  const relativeSource = "entry/src/main/ets/Thresholds.ets";
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await writeFile(
    path.join(root, relativeSource),
    [
      "export function atBoundary(flag: boolean): number {",
      "  if (flag) {",
      "    return 1;",
      "  }",
      "  return 0;",
      "}",
      "export function overBoundary(first: boolean, second: boolean): number {",
      "  if (first) {",
      "    if (second) {",
      "      return 1;",
      "    }",
      "  }",
      "  return 0;",
      "}",
      "",
    ].join("\n"),
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      analysis: {
        maxFunctionLines: 6,
        maxComplexity: 2,
        maxNesting: 1,
        duplicateWindow: 6,
      },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  assert.deepEqual(
    report.functions.map(({ name, endLine, startLine, complexity, maxNesting }) => ({
      name,
      lines: endLine - startLine + 1,
      complexity,
      maxNesting,
    })),
    [
      { name: "atBoundary", lines: 6, complexity: 2, maxNesting: 1 },
      { name: "overBoundary", lines: 8, complexity: 3, maxNesting: 2 },
    ],
  );
  assert.deepEqual(
    report.issues.filter(({ file }) => file === relativeSource).map(({ rule_id }) => rule_id).sort(),
    ["cyclomatic-complexity", "function-length", "maximum-nesting"],
  );
});

test("allowed imports and handled catches do not create architecture or reliability issues", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony clean static "));
  const relativeSource = "entry/src/main/ets/pages/Clean.ets";
  await mkdir(path.dirname(path.join(root, relativeSource)), { recursive: true });
  await writeFile(
    path.join(root, relativeSource),
    [
      "import { Formatter } from '../../presentation/Formatter'",
      "export function clean(): number {",
      "  try {",
      "    return 1",
      "  } catch (error) {",
      "    return 0",
      "  }",
      "}",
      "",
    ].join("\n"),
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      analysis: {
        duplicateWindow: 6,
        architectureRules: [{
          id: "ui-must-not-import-data",
          from: "entry/src/main/ets/pages/",
          forbiddenImports: ["/data/"],
        }],
      },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  assert.equal(report.issues.some(({ rule_id }) => rule_id === "empty-catch"), false);
  assert.equal(report.issues.some(({ source }) => source === "architecture-rule"), false);
});

test("changed scope excludes pre-existing static findings on unchanged lines", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony changed static "));
  const relativeSource = "entry/src/main/ets/Legacy.ets";
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await writeFile(
    path.join(root, relativeSource),
    "try {} catch (error) {}\nconst changed = 1\n",
  );
  const gitEnv = {
    ...process.env,
    GIT_AUTHOR_NAME: "Harmony Quality Test",
    GIT_AUTHOR_EMAIL: "quality@example.invalid",
    GIT_COMMITTER_NAME: "Harmony Quality Test",
    GIT_COMMITTER_EMAIL: "quality@example.invalid",
  };
  for (const args of [["init", "-q"], ["add", "."], ["commit", "-qm", "baseline"]]) {
    const git = spawnSync("git", args, { cwd: root, encoding: "utf8", env: gitEnv });
    assert.equal(git.status, 0, git.stderr);
  }
  await writeFile(
    path.join(root, relativeSource),
    "try {} catch (error) {}\nconst changed = 2\n",
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      analysis: { duplicateWindow: 6 },
      scope: { default: "changed", base: "HEAD" },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "changed"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  assert.equal(report.issues.some(({ rule_id }) => rule_id === "empty-catch"), false);
});

test("duplicate ArkTS blocks produce a metric and traceable issue", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony duplicate "));
  for (const module of ["entry", "feature"]) {
    const directory = path.join(root, module, "src/main/ets");
    await mkdir(directory, { recursive: true });
    await writeFile(
      path.join(directory, "Shared.ets"),
      "const first = load()\nconst second = map(first)\nconst third = save(second)\n",
    );
  }
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry", "feature"] },
      commands: {},
      analysis: { duplicateWindow: 3 },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  assert.equal(report.metrics.find(({ id }) => id === "duplication_percent").value, 100);
  const issue = report.issues.find(({ rule_id }) => rule_id === "duplicate-code-block");
  assert.deepEqual(issue.evidence, [
    "source:entry/src/main/ets/Shared.ets:1",
    "source:feature/src/main/ets/Shared.ets:1",
  ]);
});

test("generated BuildProfile files are excluded from source quality findings", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony generated profile "));
  for (const module of ["entry", "feature"]) {
    const directory = path.join(root, module);
    await mkdir(directory, { recursive: true });
    await writeFile(
      path.join(directory, "BuildProfile.ets"),
      "const first = generated()\nconst second = generated()\nconst third = generated()\n",
    );
  }
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry", "feature"] },
      commands: {},
      analysis: { duplicateWindow: 3 },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  assert.equal(report.functions.length, 0);
  assert.equal(report.issues.length, 0);
  assert.equal(report.metrics.find(({ id }) => id === "duplication_percent").value, 0);
});

test("DevEco generated and test source trees are excluded from production findings", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony generated test tree "));
  for (const relative of [
    "feature/main/.test/cache/Generated.ts",
    "feature/main/src/test/LocalUnit.test.ets",
    "feature/main/src/ohosTest/ets/test/Ability.test.ets",
  ]) {
    const generated = path.join(root, relative);
    await mkdir(path.dirname(generated), { recursive: true });
    await writeFile(generated, "try {} catch (error) {}\n");
  }
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["feature/main"] },
      commands: {},
      analysis: { duplicateWindow: 3 },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  assert.equal(report.functions.length, 0);
  assert.equal(report.issues.length, 0);
});

test("overlapping duplicate windows are reported as one contiguous block", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony duplicate block "));
  for (const module of ["entry", "feature"]) {
    const directory = path.join(root, module, "src/main/ets");
    await mkdir(directory, { recursive: true });
    await writeFile(
      path.join(directory, "Shared.ets"),
      [
        "const first = load()",
        "const second = map(first)",
        "const third = validate(second)",
        "const fourth = save(third)",
        "const fifth = publish(fourth)",
        "",
      ].join("\n"),
    );
  }
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry", "feature"] },
      commands: {},
      analysis: { duplicateWindow: 3 },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const report = await qualityReport(root);
  const issues = report.issues.filter(({ rule_id }) => rule_id === "duplicate-code-block");
  assert.equal(issues.length, 1);
  assert.match(issues[0].message, /5-line/);
  assert.equal(report.metrics.find(({ id }) => id === "duplication_percent").value, 100);
});
