import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = path.resolve("bin/harmony-quality.mjs");

async function fixture(testScript) {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony mutation "));
  const relativeSource = "entry/src/main/ets/Predicate.ets";
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "quality"), { recursive: true });
  const original = "export function isOne(value: number): boolean {\n  return value === 1\n}\n";
  await writeFile(path.join(root, relativeSource), original);
  await writeFile(path.join(root, "quality/mutation-test.mjs"), testScript);
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry"] },
      commands: {},
      mutation: {
        enabled: true,
        maxMutants: 1,
        command: {
          argv: [process.execPath, "quality/mutation-test.mjs"],
          timeoutMs: 5_000,
          compileExitCodes: [2],
        },
      },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );
  return { root, relativeSource, original };
}

async function runAndRead(root) {
  const result = spawnSync(
    process.execPath,
    [cli, "check", "--project", root, "--scope", "full"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );
  const report = JSON.parse(await readFile(
    path.join(root, ".harmony-quality/reports/quality-report.json"),
    "utf8",
  ));
  return { result, report };
}

test("mutation runs in an isolated copy and records a killed mutant", async () => {
  const { root, relativeSource, original } = await fixture(`
    import { readFileSync } from "node:fs";
    const source = readFileSync("entry/src/main/ets/Predicate.ets", "utf8");
    process.exit(source.includes("!==") ? 1 : 0);
  `);

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(report.mutation.summary, {
    total: 1,
    killed: 1,
    survived: 0,
    timeout: 0,
    compileError: 0,
    score: 100,
  });
  assert.equal(report.mutation.mutants[0].operator, "strict-equality-negation");
  assert.equal(report.mutation.mutants[0].status, "killed");
  assert.equal(report.mutation.sourceHashUnchanged, true);
  assert.equal(await readFile(path.join(root, relativeSource), "utf8"), original);
});

test("mutation exposes a survived mutant as a traceable test-quality issue", async () => {
  const { root } = await fixture("process.exit(0)\n");

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(report.mutation.summary.score, 0);
  assert.equal(report.mutation.mutants[0].status, "survived");
  const issue = report.issues.find(({ rule_id }) => rule_id === "mutant-must-be-killed");
  assert.equal(issue.file, "entry/src/main/ets/Predicate.ets");
  assert.deepEqual(issue.evidence, ["mutation:M-001"]);
});

test("mutation uses Hypium result evidence when the runner exits zero", async () => {
  const { root } = await fixture(`
    import { mkdirSync, writeFileSync } from "node:fs";
    mkdirSync("quality", { recursive: true });
    const mutated = process.env.HARMONY_QUALITY_MUTANT_ID !== "baseline";
    const summary = mutated
      ? "Tests run: 1, Failure: 1, Error: 0, Pass: 0, Ignore: 0\\n"
      : "Tests run: 1, Failure: 0, Error: 0, Pass: 1, Ignore: 0\\n";
    writeFileSync("quality/test_result.txt", summary);
    process.exit(0);
  `);
  const configPath = path.join(root, "harmony-quality.config.json");
  const config = JSON.parse(await readFile(configPath, "utf8"));
  config.mutation.command.hypiumResultPath = "quality/test_result.txt";
  await writeFile(configPath, JSON.stringify(config));

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(report.mutation.summary.score, 100);
  assert.equal(report.mutation.mutants[0].status, "killed");
  assert.equal(report.mutation.mutants[0].exitCode, 0);
});

test("mutation does not award 100 when no valid mutant exists", async () => {
  const { root, relativeSource } = await fixture("process.exit(0)\n");
  await writeFile(
    path.join(root, relativeSource),
    "export function constant(): number { return 1 }\n",
  );

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(report.mutation.summary.total, 0);
  assert.equal(report.mutation.summary.score, null);
  assert.equal(report.metrics.some(({ id }) => id === "mutation_score"), false);
});

test("mutation excludes compile errors from the score denominator", async () => {
  const { root } = await fixture(`
    process.exit(process.env.HARMONY_QUALITY_MUTANT_ID === "baseline" ? 0 : 2);
  `);

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(report.mutation.summary, {
    total: 1,
    killed: 0,
    survived: 0,
    timeout: 0,
    compileError: 1,
    score: null,
  });
  assert.equal(report.metrics.some(({ id }) => id === "mutation_score"), false);
});

test("mutation timeout blocks instead of being counted as killed", async () => {
  const { root } = await fixture(`
    if (process.env.HARMONY_QUALITY_MUTANT_ID === "baseline") process.exit(0);
    setTimeout(() => {}, 1_000);
  `);
  const configPath = path.join(root, "harmony-quality.config.json");
  const config = JSON.parse(await readFile(configPath, "utf8"));
  config.mutation.command.timeoutMs = 200;
  await writeFile(configPath, JSON.stringify(config));

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 3, result.stderr);
  assert.equal(report.status, "BLOCKED");
  assert.equal(report.mutation.summary.timeout, 1);
  assert.equal(report.mutation.summary.score, null);
});

test("mutation blocks when the unmodified baseline test fails", async () => {
  const { root } = await fixture("process.exit(1)\n");

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 3, result.stderr);
  assert.equal(report.status, "BLOCKED");
  assert.equal(report.mutation.summary.total, 0);
  assert.equal(
    report.issues.some(({ rule_id }) => rule_id === "mutation-baseline-must-pass"),
    true,
  );
});

test("mutation baseline also runs in isolation when its command writes source", async () => {
  const { root, relativeSource, original } = await fixture(`
    import { appendFileSync } from "node:fs";
    appendFileSync("entry/src/main/ets/Predicate.ets", "// side effect\\n");
    process.exit(process.env.HARMONY_QUALITY_MUTANT_ID === "baseline" ? 0 : 1);
  `);

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(report.mutation.sourceHashUnchanged, true);
  assert.equal(await readFile(path.join(root, relativeSource), "utf8"), original);
});

test("mutation isolation preserves installed project dependencies", async () => {
  const { root } = await fixture(`
    import { existsSync } from "node:fs";
    process.exit(existsSync("oh_modules/dependency.marker") ? 0 : 1);
  `);
  await mkdir(path.join(root, "oh_modules"), { recursive: true });
  await writeFile(path.join(root, "oh_modules/dependency.marker"), "installed\n");

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(report.mutation.summary.total, 1);
  assert.equal(report.mutation.mutants[0].status, "survived");
});

test("mutation isolation preserves relative dependency symlinks", async () => {
  const { root } = await fixture(`
    import { readlinkSync } from "node:fs";
    process.exit(readlinkSync("oh_modules/active") === "package" ? 0 : 1);
  `);
  await mkdir(path.join(root, "oh_modules/package"), { recursive: true });
  await symlink("package", path.join(root, "oh_modules/active"));

  const { result, report } = await runAndRead(root);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(report.mutation.summary.total, 1);
});
