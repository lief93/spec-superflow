import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = path.resolve("bin/harmony-quality.mjs");

function git(root, args) {
  const result = spawnSync("git", args, {
    cwd: root,
    encoding: "utf8",
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: "Harmony Quality Test",
      GIT_AUTHOR_EMAIL: "quality@example.invalid",
      GIT_COMMITTER_NAME: "Harmony Quality Test",
      GIT_COMMITTER_EMAIL: "quality@example.invalid",
    },
  });
  assert.equal(result.status, 0, result.stderr);
}

async function configure(root, lcov) {
  await mkdir(path.join(root, "quality"), { recursive: true });
  await writeFile(path.join(root, "quality/lcov.info"), lcov);
  await writeFile(
    path.join(root, "harmony-quality.config.json"),
    JSON.stringify({
      schemaVersion: 1,
      project: { root: ".", modules: ["entry", "feature"] },
      commands: {},
      evidence: { coverage: { format: "lcov", path: "quality/lcov.info" } },
      scope: { default: "changed", base: "HEAD" },
      reports: { directory: ".harmony-quality/reports" },
    }),
  );
}

function check(root, args) {
  return spawnSync(
    process.execPath,
    [cli, "check", "--project", root, ...args],
    { cwd: path.resolve("."), encoding: "utf8" },
  );
}

async function report(root) {
  return JSON.parse(await readFile(
    path.join(root, ".harmony-quality/reports/quality-report.json"),
    "utf8",
  ));
}

test("changed scope calculates coverage and gaps only for changed lines", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony changed scope "));
  const source = path.join(root, "entry/src/main/ets/Page.ets");
  await mkdir(path.dirname(source), { recursive: true });
  await writeFile(source, "const stable = 1;\nconst value = 1;\n");
  git(root, ["init", "-q"]);
  git(root, ["add", "."]);
  git(root, ["commit", "-qm", "baseline"]);
  await writeFile(source, "const stable = 1;\nconst value = 2;\nconst added = 3;\n");
  await configure(
    root,
    "TN:\nSF:entry/src/main/ets/Page.ets\nDA:1,0\nDA:2,1\nDA:3,0\nend_of_record\n",
  );

  const result = check(root, ["--scope", "changed", "--base", "HEAD"]);

  assert.equal(result.status, 0, result.stderr);
  const output = await report(root);
  assert.deepEqual(output.scope, {
    mode: "changed",
    base: "HEAD",
    files: ["entry/src/main/ets/Page.ets"],
  });
  assert.equal(
    output.metrics.find(({ id }) => id === "line_coverage").value,
    50,
  );
  assert.deepEqual(
    output.issues.filter(({ rule_id }) => rule_id === "line-must-be-covered")
      .map(({ file, line }) => [file, line]),
    [["entry/src/main/ets/Page.ets", 3]],
  );
});

test("module scope excludes coverage evidence from other modules", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony module scope "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "feature/src/main/ets"), { recursive: true });
  await configure(
    root,
    "TN:\nSF:entry/src/main/ets/Page.ets\nDA:1,0\nend_of_record\nSF:feature/src/main/ets/Feature.ets\nDA:1,1\nend_of_record\n",
  );

  const result = check(root, ["--scope", "module", "--module", "feature"]);

  assert.equal(result.status, 0, result.stderr);
  const output = await report(root);
  assert.deepEqual(output.scope, {
    mode: "module",
    module: "feature",
    files: ["feature/src/main/ets/Feature.ets"],
  });
  assert.equal(
    output.metrics.find(({ id }) => id === "line_coverage").value,
    100,
  );
  assert.deepEqual(output.metrics.map(({ id }) => id), ["line_coverage"]);
  assert.equal(output.coverage.files.length, 1);
  assert.equal(output.coverage.files[0].path, "feature/src/main/ets/Feature.ets");
});

test("full scope excludes source and coverage outside configured Harmony modules", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony module ownership "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "tools"), { recursive: true });
  await writeFile(path.join(root, "entry/src/main/ets/Page.ets"), "const page = 1\n");
  await writeFile(path.join(root, "tools/helper.ts"), "try {} catch (error) {}\n");
  await configure(
    root,
    "TN:\nSF:entry/src/main/ets/Page.ets\nDA:1,1\nend_of_record\nSF:tools/helper.ts\nDA:1,0\nend_of_record\n",
  );

  const result = check(root, ["--scope", "full"]);

  assert.equal(result.status, 0, result.stderr);
  const output = await report(root);
  assert.deepEqual(output.coverage.files.map(({ path: file }) => file), [
    "entry/src/main/ets/Page.ets",
  ]);
  assert.equal(output.issues.some(({ file }) => file === "tools/helper.ts"), false);
});
