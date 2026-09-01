import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, realpath, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { evaluateGates } from "../src/gates.mjs";

const cli = path.resolve("bin/harmony-quality.mjs");

async function run(root) {
  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );
  const directory = path.join(root, ".harmony-quality/reports");
  return {
    result,
    json: JSON.parse(await readFile(path.join(directory, "quality-report.json"), "utf8")),
    markdown: await readFile(path.join(directory, "quality-report.md"), "utf8"),
  };
}

test("scores and a failing gate trace back to metrics and raw evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony gate report "));
  const source = "entry/src/main/ets/Page.ets";
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(path.join(root, source), "export function page(): number { return 1 }\n");
  await writeFile(
    path.join(root, "quality/tests.json"),
    JSON.stringify({ tests: [{ id: "page", status: "passed", durationMs: 1 }] }),
  );
  await writeFile(
    path.join(root, "quality/acceptance.json"),
    JSON.stringify({ criteria: [{ id: "AC-1", tests: ["unit:page"] }] }),
  );
  await writeFile(
    path.join(root, "quality/lcov.info"),
    `TN:\nSF:${source}\nFN:1,page\nFNDA:1,page\nDA:1,1\nDA:2,0\nBRDA:1,0,0,1\nBRDA:1,0,1,1\nend_of_record\n`,
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      evidence: {
        tests: [{ id: "unit", format: "test-json", path: "quality/tests.json" }],
        acceptance: { path: "quality/acceptance.json" },
        coverage: { format: "lcov", path: "quality/lcov.info" },
      },
      analysis: { duplicateWindow: 6 },
      qualityGates: [
        {
          id: "line-coverage-80",
          source: "metric",
          key: "line_coverage",
          operator: ">=",
          threshold: 80,
          required: true,
          remediation: "Add tests for uncovered changed lines.",
        },
        {
          id: "test-quality-minimum",
          source: "score",
          key: "test_quality",
          operator: ">=",
          threshold: 90,
          required: true,
          remediation: "Cover behavior branches and kill surviving mutants.",
        },
      ],
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const output = await run(root);

  assert.equal(output.result.status, 2, output.result.stderr);
  assert.equal(output.json.status, "FAIL");
  assert.deepEqual(
    output.json.scores.map(({ id, value }) => [id, value]),
    [
      ["functionality_suitability", 100],
      ["maintainability", 100],
      ["overall", 96.67],
      ["reliability", 100],
      ["test_quality", 83.33],
    ],
  );
  assert.deepEqual(output.json.gates.map(({ id, status, remediation }) => ({
    id,
    status,
    remediation,
  })), [
    {
      id: "line-coverage-80",
      status: "FAIL",
      remediation: "Add tests for uncovered changed lines.",
    },
    {
      id: "test-quality-minimum",
      status: "FAIL",
      remediation: "Cover behavior branches and kill surviving mutants.",
    },
  ]);
  const metric = output.json.metrics.find(({ id }) => id === "line_coverage");
  assert.deepEqual(metric.evidence, ["coverage:entry/src/main/ets/Page.ets"]);
  assert.ok(output.json.metrics.every(({ explanation }) =>
    typeof explanation === "string" && explanation.length > 0));
  assert.ok(output.json.evidence.some(
    ({ id }) => id === "coverage:entry/src/main/ets/Page.ets",
  ));
  assert.match(output.markdown, /Overall \| 96\.67 \| - \| NOT_GATED/);
  assert.match(output.markdown, /Test Quality \| 83\.33 \| >= 90 \| FAIL/);
  assert.match(output.markdown, /line_coverage \| 50 \| percent/);
  assert.match(output.markdown, /line-coverage-80 \| FAIL \| 50 >= 80/);
  assert.match(output.markdown, /Required Changes/);
  assert.match(output.markdown, /Add tests for uncovered changed lines\./);
  assert.match(output.markdown, /Remediation/);
  const sourceUri = `vscode:\/\/file\/${encodeURI(path.join(await realpath(root), source))}:2:1`;
  assert.ok(output.markdown.includes(sourceUri), output.markdown);
});

test("a required gate with no metric blocks instead of assuming a value", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony blocked gate "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      qualityGates: [{
        id: "mutation-required",
        source: "metric",
        key: "mutation_score",
        operator: ">=",
        threshold: 80,
        required: true,
      }],
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const output = await run(root);

  assert.equal(output.result.status, 3, output.result.stderr);
  assert.equal(output.json.status, "BLOCKED");
  assert.equal(output.json.gates[0].status, "BLOCKED");
  assert.equal(output.json.gates[0].actual, null);
  assert.deepEqual(output.json.gates[0].evidence, []);
});

test("all quality-gate operators and sources have deterministic boundaries", () => {
  const metric = { id: "value", value: 10, evidence: ["metric-evidence"] };
  const score = { id: "overall", value: 90, evidence: ["score-evidence"] };
  const issues = [{
    issue_id: "critical-bug",
    category: "reliability",
    severity: "critical",
  }];
  const qualityGates = [
    { id: "gte", source: "metric", key: "value", operator: ">=", threshold: 10 },
    { id: "gt", source: "metric", key: "value", operator: ">", threshold: 9 },
    { id: "lte", source: "metric", key: "value", operator: "<=", threshold: 10 },
    { id: "lt", source: "metric", key: "value", operator: "<", threshold: 11 },
    { id: "eq", source: "metric", key: "value", operator: "==", threshold: 10 },
    { id: "neq", source: "metric", key: "value", operator: "!=", threshold: 9 },
    { id: "score", source: "score", key: "overall", operator: ">=", threshold: 90 },
    {
      id: "issues",
      source: "issue-count",
      key: "critical_reliability_issues",
      filter: { category: "reliability", severity: ["blocker", "critical"] },
      operator: "==",
      threshold: 1,
    },
    { id: "fails", source: "metric", key: "value", operator: ">", threshold: 10 },
    { id: "optional", source: "metric", key: "missing", operator: ">=", threshold: 1, required: false },
  ];

  const results = evaluateGates({ qualityGates }, [metric], [score], issues);

  assert.deepEqual(
    results.map(({ id, status, actual }) => [id, status, actual]),
    [
      ["gte", "PASS", 10],
      ["gt", "PASS", 10],
      ["lte", "PASS", 10],
      ["lt", "PASS", 10],
      ["eq", "PASS", 10],
      ["neq", "PASS", 10],
      ["score", "PASS", 90],
      ["issues", "PASS", 1],
      ["fails", "FAIL", 10],
      ["optional", "SKIPPED", null],
    ],
  );
  assert.deepEqual(results[7].evidence, ["issue:critical-bug"]);
});

test("JSON and Markdown reports are byte-deterministic for the same inputs", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony deterministic report "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await writeFile(
    path.join(root, "entry/src/main/ets/Page.ets"),
    "export function page(): number { return 1 }\n",
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

  const first = await run(root);
  const firstJson = await readFile(
    path.join(root, ".harmony-quality/reports/quality-report.json"),
    "utf8",
  );
  const firstMarkdown = first.markdown;
  const second = await run(root);
  const secondJson = await readFile(
    path.join(root, ".harmony-quality/reports/quality-report.json"),
    "utf8",
  );

  assert.equal(first.result.status, 0, first.result.stderr);
  assert.equal(second.result.status, 0, second.result.stderr);
  assert.equal(secondJson, firstJson);
  assert.equal(second.markdown, firstMarkdown);
});
