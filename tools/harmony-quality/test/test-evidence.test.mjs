import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = path.resolve("bin/harmony-quality.mjs");

async function createFixture({ tests, acceptance, lcov }) {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony evidence "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(path.join(root, "quality/tests.json"), JSON.stringify(tests));
  await writeFile(
    path.join(root, "quality/acceptance.json"),
    JSON.stringify(acceptance),
  );
  await writeFile(path.join(root, "quality/lcov.info"), lcov);
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    `${JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {
        unitTest: {
          status: "verified",
          required: true,
          argv: [process.execPath, "-e", "process.exit(0)"],
        },
      },
      evidence: {
        tests: [{ id: "unit", format: "test-json", path: "quality/tests.json" }],
        acceptance: { path: "quality/acceptance.json" },
        coverage: { format: "lcov", path: "quality/lcov.info" },
      },
      reports: { directory: ".harmony-quality/reports" },
    }, null, 2)}\n`,
  );
  return root;
}

function run(root) {
  return spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );
}

async function report(root) {
  return JSON.parse(await readFile(
    path.join(root, ".harmony-quality/reports/quality-report.json"),
    "utf8",
  ));
}

async function createHypiumFixture(text, acceptance) {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony hypium evidence "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(path.join(root, "quality/test_result.txt"), text);
  await writeFile(
    path.join(root, "quality/acceptance.json"),
    JSON.stringify(acceptance),
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      evidence: {
        tests: [{ id: "unit", format: "hypium-text", path: "quality/test_result.txt" }],
        acceptance: { path: "quality/acceptance.json" },
      },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );
  return root;
}

const completeLcov = `TN:\nSF:entry/src/main/ets/Page.ets\nFN:1,loadPage\nFNDA:1,loadPage\nFNF:1\nFNH:1\nDA:1,1\nDA:2,1\nLF:2\nLH:2\nBRDA:2,0,0,1\nBRDA:2,0,1,1\nBRF:2\nBRH:2\nend_of_record\n`;

test("check traces passing tests, acceptance criteria, and coverage metrics", async () => {
  const root = await createFixture({
    tests: {
      tests: [
        { id: "loads-page", name: "loads page", status: "passed", durationMs: 12 },
        { id: "shows-error", name: "shows error", status: "passed", durationMs: 8 },
      ],
    },
    acceptance: {
      criteria: [
        { id: "AC-1", tests: ["unit:loads-page"] },
        { id: "AC-2", tests: ["unit:shows-error"] },
      ],
    },
    lcov: completeLcov,
  });

  const result = run(root);

  assert.equal(result.status, 0, result.stderr);
  const output = await report(root);
  assert.equal(output.status, "PASS");
  assert.deepEqual(output.tests.summary, {
    total: 2,
    passed: 2,
    failed: 0,
    skipped: 0,
    durationMs: 20,
  });
  assert.deepEqual(
    output.metrics.map(({ id, value }) => [id, value]),
    [
      ["acceptance_coverage", 100],
      ["branch_coverage", 100],
      ["function_coverage", 100],
      ["line_coverage", 100],
      ["test_pass_rate", 100],
    ],
  );
  assert.deepEqual(output.acceptance.criteria, [
    { id: "AC-1", status: "passed", tests: ["unit:loads-page"] },
    { id: "AC-2", status: "passed", tests: ["unit:shows-error"] },
  ]);
});

test("check reads native DevEco Harmony coverage JSON", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony native coverage "));
  const source = path.join(root, "entry/src/main/ets/Page.ets");
  await mkdir(path.dirname(source), { recursive: true });
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(source, "export function loadPage() { return true; }\n");
  await writeFile(
    path.join(root, "quality/coverageReport.json"),
    JSON.stringify({
      summary: {},
      files: [{
        path: source,
        functions: [
          {
            name: "loadPage",
            count: 1,
            ignored: 0,
            regions: [],
            branches: [{
              startLoc: { line: 2, col: 1 },
              endLoc: { line: 2, col: 10 },
              trueCount: 1,
              falseCount: 0,
              group: [],
              ignored: 0,
            }],
          },
          { name: "showError", count: 0, ignored: 0, regions: [], branches: [] },
          { name: "ignored", count: 0, ignored: 1, regions: [], branches: [] },
        ],
        summary: {
          lines: { executedLineCount: [-1, 1, 0, 2] },
        },
      }],
    }),
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    `${JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      evidence: {
        coverage: {
          format: "harmony-coverage-json",
          path: "quality/coverageReport.json",
        },
      },
      reports: { directory: ".harmony-quality/reports" },
    }, null, 2)}\n`,
  );

  const result = run(root);

  assert.equal(result.status, 0, result.stderr);
  const output = await report(root);
  assert.deepEqual(
    output.metrics.map(({ id, value }) => [id, value]),
    [
      ["branch_coverage", 50],
      ["function_coverage", 50],
      ["line_coverage", 66.67],
    ],
  );
  assert.deepEqual(output.coverage.files, [{
    path: "entry/src/main/ets/Page.ets",
    lines: [
      { line: 1, hits: 1 },
      { line: 2, hits: 0 },
      { line: 3, hits: 2 },
    ],
    branches: [
      { line: 2, block: 0, branch: 0, hits: 1 },
      { line: 2, block: 0, branch: 1, hits: 0 },
    ],
    functions: [
      { name: "loadPage", hits: 1 },
      { name: "showError", hits: 0 },
    ],
  }]);
});

test("check rejects malformed native coverage instead of inventing zero", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony malformed coverage "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(
    path.join(root, "quality/coverageReport.json"),
    JSON.stringify({ files: [{ path: "entry/src/main/ets/Page.ets", summary: {} }] }),
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      evidence: {
        coverage: { format: "harmony-coverage-json", path: "quality/coverageReport.json" },
      },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = run(root);

  assert.equal(result.status, 4);
  assert.match(result.stderr, /missing executed lines/);
});

test("check rejects native coverage whose source escapes the project", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony escaping coverage "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(
    path.join(root, "quality/coverageReport.json"),
    JSON.stringify({
      files: [{
        path: path.join(path.dirname(root), "Outside.ets"),
        functions: [],
        summary: { lines: { executedLineCount: [-1, 1] } },
      }],
    }),
  );
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      evidence: {
        coverage: { format: "harmony-coverage-json", path: "quality/coverageReport.json" },
      },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );

  const result = run(root);

  assert.equal(result.status, 4);
  assert.match(result.stderr, /coverage source path escapes project root/);
});

test("check normalizes native Hypium cases for acceptance traceability", async () => {
  const root = await createHypiumFixture(
    [
      "class=Eligibility",
      "test=acceptsBoundary",
      "result=Success",
      "test=rejectsInactive",
      "result=Success",
      "Tests run: 2, Failure: 0, Error: 0, Pass: 2, Ignore: 0",
      "",
    ].join("\n"),
    { criteria: [{ id: "AC-1", tests: ["unit:Eligibility/acceptsBoundary"] }] },
  );

  const result = run(root);

  assert.equal(result.status, 0, result.stderr);
  const output = await report(root);
  assert.deepEqual(output.tests.cases, [
    {
      id: "unit:Eligibility/acceptsBoundary",
      name: "Eligibility/acceptsBoundary",
      status: "passed",
      durationMs: 0,
      source: "unit",
    },
    {
      id: "unit:Eligibility/rejectsInactive",
      name: "Eligibility/rejectsInactive",
      status: "passed",
      durationMs: 0,
      source: "unit",
    },
  ]);
  assert.equal(output.acceptance.criteria[0].status, "passed");
  assert.equal(output.metrics.find(({ id }) => id === "test_pass_rate").value, 100);
});

test("check reports a native Hypium failed case and linked AC as failed", async () => {
  const root = await createHypiumFixture(
    [
      "class=Eligibility",
      "test=acceptsBoundary",
      "Error in acceptsBoundary, expect true, actualValue is false",
      "    at expect (/workspace/oh_modules/@ohos/hypium/index.js:20:4)",
      "    at evaluate (entry/src/main/ets/Eligibility.ets:7:3)",
      "    at anonymous (entry/src/test/Eligibility.test.ets:12:5)",
      "result=Failure",
      "Tests run: 1, Failure: 1, Error: 0, Pass: 0, Ignore: 0",
      "",
    ].join("\n"),
    { criteria: [{ id: "AC-1", tests: ["unit:Eligibility/acceptsBoundary"] }] },
  );

  const result = run(root);

  assert.equal(result.status, 2, result.stderr);
  const output = await report(root);
  assert.equal(output.tests.cases[0].status, "failed");
  assert.deepEqual(output.tests.cases[0].stack, [
    {
      file: "/workspace/oh_modules/@ohos/hypium/index.js",
      line: 20,
      column: 4,
      function: "expect",
      external: true,
    },
    { file: "entry/src/main/ets/Eligibility.ets", line: 7, column: 3, function: "evaluate" },
    { file: "entry/src/test/Eligibility.test.ets", line: 12, column: 5, function: "anonymous" },
  ]);
  assert.equal(output.acceptance.criteria[0].status, "failed");
  assert.equal(output.metrics.find(({ id }) => id === "test_pass_rate").value, 0);
  const testIssue = output.issues.find(({ rule_id }) => rule_id === "test-case-must-pass");
  assert.deepEqual(
    {
      file: testIssue.file,
      line: testIssue.line,
      column: testIssue.column,
      stack: testIssue.stack,
    },
    {
      file: "entry/src/main/ets/Eligibility.ets",
      line: 7,
      column: 3,
      stack: output.tests.cases[0].stack,
    },
  );
  const markdown = await readFile(
    path.join(root, ".harmony-quality/reports/quality-report.md"),
    "utf8",
  );
  assert.match(markdown, /vscode:\/\/file\/.*Eligibility\.ets:7:3/);
  assert.match(markdown, /vscode:\/\/file\/.*Eligibility\.test\.ets:12:5/);
  assert.doesNotMatch(markdown, /oh_modules/);
});

test("check rejects Hypium evidence whose summary does not match its cases", async () => {
  const root = await createHypiumFixture(
    [
      "class=Eligibility",
      "test=acceptsBoundary",
      "result=Success",
      "Tests run: 2, Failure: 0, Error: 0, Pass: 2, Ignore: 0",
      "",
    ].join("\n"),
    { criteria: [] },
  );

  const result = run(root);

  assert.equal(result.status, 4);
  assert.match(result.stderr, /Hypium result summary does not match parsed cases/);
});

test("check fails with a traceable issue when an acceptance criterion has no test", async () => {
  const root = await createFixture({
    tests: { tests: [{ id: "loads-page", status: "passed", durationMs: 1 }] },
    acceptance: {
      criteria: [
        { id: "AC-1", tests: ["unit:loads-page"] },
        { id: "AC-2", tests: [] },
      ],
    },
    lcov: completeLcov,
  });

  const result = run(root);

  assert.equal(result.status, 2, result.stderr);
  const output = await report(root);
  assert.equal(output.status, "FAIL");
  assert.deepEqual(output.acceptance.criteria[1], {
    id: "AC-2",
    status: "missing-test",
    tests: [],
  });
  const issue = output.issues.find(
    ({ rule_id }) => rule_id === "acceptance-criterion-must-have-executable-test",
  );
  assert.equal(issue.issue_id, "acceptance-AC-2-missing-test");
  assert.deepEqual(issue.evidence, ["acceptance:AC-2"]);
});

test("an acceptance criterion is not passed when one required linked test is skipped", async () => {
  const root = await createFixture({
    tests: {
      tests: [
        { id: "unit-path", status: "passed", durationMs: 1 },
        { id: "ui-path", status: "skipped", durationMs: 0 },
      ],
    },
    acceptance: {
      criteria: [{ id: "AC-1", tests: ["unit:unit-path", "unit:ui-path"] }],
    },
    lcov: completeLcov,
  });

  const result = run(root);

  assert.equal(result.status, 2, result.stderr);
  const output = await report(root);
  assert.equal(output.acceptance.criteria[0].status, "not-executed");
});

test("acceptance evidence preserves optional Given When Then behavior", async () => {
  const root = await createFixture({
    tests: { tests: [{ id: "offline", status: "passed", durationMs: 1 }] },
    acceptance: {
      criteria: [{
        id: "AC-1",
        given: "the device is offline",
        when: "the user refreshes",
        then: "cached content remains visible",
        tests: ["unit:offline"],
      }],
    },
    lcov: completeLcov,
  });

  const result = run(root);

  assert.equal(result.status, 0, result.stderr);
  const output = await report(root);
  assert.deepEqual(output.acceptance.criteria[0], {
    id: "AC-1",
    given: "the device is offline",
    when: "the user refreshes",
    then: "cached content remains visible",
    status: "passed",
    tests: ["unit:offline"],
  });
});

test("all-skipped test evidence does not claim a 100 percent pass rate", async () => {
  const root = await createFixture({
    tests: { tests: [{ id: "device", status: "skipped", durationMs: 0 }] },
    acceptance: { criteria: [] },
    lcov: completeLcov,
  });

  const result = run(root);

  assert.equal(result.status, 0, result.stderr);
  const output = await report(root);
  assert.equal(output.metrics.some(({ id }) => id === "test_pass_rate"), false);
});
