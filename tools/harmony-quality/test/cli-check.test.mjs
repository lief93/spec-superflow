import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, readFile, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = path.resolve("bin/harmony-quality.mjs");

async function createProject(commands) {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony quality check "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    `${JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands,
      scope: { default: "changed" },
      reports: { directory: ".harmony-quality/reports" },
    }, null, 2)}\n`,
  );
  return root;
}

function command(script, { required = true, timeoutMs = 5_000 } = {}) {
  return {
    status: "verified",
    required,
    timeoutMs,
    argv: [process.execPath, "-e", script],
  };
}

function runCheck(root, scope = "full") {
  return spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", scope],
    { cwd: path.resolve("."), encoding: "utf8" },
  );
}

async function readReport(root) {
  return JSON.parse(
    await readFile(
      path.join(root, ".harmony-quality/reports/quality-report.json"),
      "utf8",
    ),
  );
}

test("check executes configured argv and emits a deterministic PASS report", async () => {
  const root = await createProject({
    build: command("console.log('built')"),
    unitTest: command("console.log('2 tests passed')"),
    lint: command("console.log('clean')"),
    uiTest: { status: "unresolved", required: false, argv: [] },
  });

  const result = runCheck(root);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /PASS/);
  const report = await readReport(root);
  assert.equal(report.schemaVersion, 1);
  assert.equal(report.status, "PASS");
  assert.equal(report.scope.mode, "full");
  assert.deepEqual(
    report.commands.map(({ id, outcome }) => [id, outcome]),
    [
      ["build", "pass"],
      ["lint", "pass"],
      ["unitTest", "pass"],
      ["uiTest", "skipped"],
    ],
  );
  assert.equal(report.issues.length, 0);
});

test("check reports a required missing executable as BLOCKED", async () => {
  const root = await createProject({
    build: {
      status: "verified",
      required: true,
      timeoutMs: 5_000,
      argv: [path.join(rootPlaceholder(), "missing-hvigorw")],
    },
  });

  const result = runCheck(root);

  assert.equal(result.status, 3, result.stderr);
  const report = await readReport(root);
  assert.equal(report.status, "BLOCKED");
  assert.equal(report.commands[0].outcome, "infrastructure-error");
  assert.equal(report.commands[0].reason, "executable-not-found");
});

test("check reports a unit test command failure as FAIL, not infrastructure failure", async () => {
  const root = await createProject({
    unitTest: command("process.exit(7)"),
  });

  const result = runCheck(root);

  assert.equal(result.status, 2, result.stderr);
  const report = await readReport(root);
  assert.equal(report.status, "FAIL");
  assert.equal(report.commands[0].outcome, "test-failure");
  assert.equal(report.commands[0].exitCode, 7);
});

test("check reports a build failure as FAIL", async () => {
  const root = await createProject({ build: command("process.exit(9)") });

  const result = runCheck(root);

  assert.equal(result.status, 2, result.stderr);
  const report = await readReport(root);
  assert.equal(report.commands[0].outcome, "command-failure");
  assert.equal(report.commands[0].exitCode, 9);
});

test("check reads Hypium failure evidence when Hvigor exits zero", async () => {
  const root = await createProject({
    unitTest: {
      ...command(`
        const { mkdirSync, writeFileSync } = require("node:fs");
        mkdirSync("quality", { recursive: true });
        writeFileSync("quality/test_result.txt", "Tests run: 2, Failure: 1, Error: 0, Pass: 1, Ignore: 0\\n");
      `),
      hypiumResultPath: "quality/test_result.txt",
    },
  });

  const result = runCheck(root);

  assert.equal(result.status, 2, result.stderr);
  const report = await readReport(root);
  assert.equal(report.status, "FAIL");
  assert.equal(report.commands[0].outcome, "test-failure");
  assert.equal(report.commands[0].reason, "hypium-test-failure");
  assert.equal(report.commands[0].exitCode, 0);
});

test("check blocks when configured Hypium result evidence is missing", async () => {
  const root = await createProject({
    unitTest: {
      ...command("process.exit(0)"),
      hypiumResultPath: "quality/missing-test_result.txt",
    },
  });

  const result = runCheck(root);

  assert.equal(result.status, 3, result.stderr);
  const report = await readReport(root);
  assert.equal(report.commands[0].outcome, "infrastructure-error");
  assert.equal(report.commands[0].reason, "hypium-result-missing");
});

test("check records a passing UI Hypium result separately", async () => {
  const root = await createProject({
    uiTest: {
      ...command(`
        const { mkdirSync, writeFileSync } = require("node:fs");
        mkdirSync("quality", { recursive: true });
        writeFileSync("quality/ui_result.txt", "Tests run: 1, Failure: 0, Error: 0, Pass: 1, Ignore: 0\\n");
      `),
      hypiumResultPath: "quality/ui_result.txt",
    },
  });

  const result = runCheck(root);

  assert.equal(result.status, 0, result.stderr);
  const report = await readReport(root);
  assert.deepEqual(report.commands[0].hypium, {
    total: 1,
    failures: 0,
    errors: 0,
    passed: 1,
    ignored: 0,
  });
});

test("check rejects a Hypium result path outside the project", async () => {
  const root = await createProject({
    unitTest: {
      ...command("process.exit(0)"),
      hypiumResultPath: "../outside-result.txt",
    },
  });

  const result = runCheck(root);

  assert.equal(result.status, 4);
  assert.match(result.stderr, /Hypium result path escapes project root/);
});

test("check reports command timeout as BLOCKED", async () => {
  const root = await createProject({
    unitTest: command("setTimeout(() => {}, 1_000)", { timeoutMs: 20 }),
  });

  const result = runCheck(root);

  assert.equal(result.status, 3, result.stderr);
  const report = await readReport(root);
  assert.equal(report.commands[0].outcome, "infrastructure-error");
  assert.equal(report.commands[0].reason, "timeout");
});

test("check uses configured infrastructure exit codes for unavailable devices", async () => {
  const root = await createProject({
    uiTest: {
      ...command("process.exit(42)"),
      infrastructureExitCodes: { "42": "device-unavailable" },
    },
  });

  const result = runCheck(root);

  assert.equal(result.status, 3, result.stderr);
  const report = await readReport(root);
  assert.equal(report.commands[0].outcome, "infrastructure-error");
  assert.equal(report.commands[0].reason, "device-unavailable");
});

test("check rejects a report directory outside the project", async () => {
  const root = await createProject({});
  const outside = path.join(path.dirname(root), `${path.basename(root)}-outside`);
  const configPath = path.join(root, "harmony-quality.config.json");
  const config = JSON.parse(await readFile(configPath, "utf8"));
  config.reports.directory = `../${path.basename(outside)}`;
  await writeFile(configPath, JSON.stringify(config));

  const result = runCheck(root);

  assert.equal(result.status, 4, result.stderr);
  await assert.rejects(access(path.join(outside, "quality-report.json")));
});

test("check reports an unexpected report filesystem failure as internal error", async () => {
  const root = await createProject({});
  await writeFile(path.join(root, ".harmony-quality"), "not a directory\n");

  const result = runCheck(root);

  assert.equal(result.status, 5);
  assert.match(result.stderr, /^INTERNAL_ERROR:/);
});

test("check accepts native coverage paths through a symlinked project root", async () => {
  const root = await createProject({});
  const source = path.join(root, "entry/src/main/ets/Feature.ets");
  await writeFile(source, "export const enabled = true;\n");
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(
    path.join(root, "quality/coverage.json"),
    JSON.stringify({
      files: [{
        path: source,
        summary: { lines: { executedLineCount: [1] } },
        functions: [],
      }],
    }),
  );
  const configPath = path.join(root, "harmony-quality.config.json");
  const config = JSON.parse(await readFile(configPath, "utf8"));
  config.evidence = {
    coverage: { format: "harmony-coverage-json", path: "quality/coverage.json" },
  };
  await writeFile(configPath, JSON.stringify(config));
  const alias = `${root}-alias`;
  await symlink(root, alias, "dir");

  const result = runCheck(alias);

  assert.equal(result.status, 0, result.stderr);
  const report = await readReport(root);
  assert.equal(report.coverage.files[0].path, "entry/src/main/ets/Feature.ets");
});

function rootPlaceholder() {
  return path.join(os.tmpdir(), "harmony-quality-definitely-absent");
}
