import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = path.resolve("bin/harmony-quality.mjs");

test("init discovers Harmony modules and verified Hvigor tasks", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony quality init "));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await writeFile(
    path.join(root, "build-profile.json5"),
    `{
      // JSON5 is common in Harmony projects.
      "modules": [{ "name": "entry", "srcPath": "./entry", }],
    }`,
  );

  const wrapper = path.join(root, "hvigorw");
  await writeFile(
    wrapper,
    "#!/bin/sh\nprintf '%s\\n' assembleHap test codeLinter\n",
  );
  await chmod(wrapper, 0o755);

  const result = spawnSync(
    process.execPath,
    [cli, "init", "--project", root],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const config = JSON.parse(
    await readFile(path.join(root, "harmony-quality.config.json"), "utf8"),
  );
  assert.deepEqual(config.project.modules, ["entry"]);
  assert.deepEqual(config.commands.build.argv, ["./hvigorw", "assembleHap"]);
  assert.deepEqual(config.commands.unitTest.argv, [
    "./hvigorw",
    "test",
    "-p",
    "module=entry",
    "-p",
    "coverage=true",
  ]);
  assert.equal(
    config.commands.unitTest.hypiumResultPath,
    "entry/.test/default/intermediates/test/coverage_data/test_result.txt",
  );
  assert.deepEqual(config.commands.lint.argv, ["./hvigorw", "codeLinter"]);
  assert.deepEqual(config.evidence.coverage, {
    format: "harmony-coverage-json",
    path: "entry/.test/default/outputs/test/reports/coverageReport.json",
  });
  assert.deepEqual(config.evidence.tests, [{
    id: "unit",
    format: "hypium-text",
    path: "entry/.test/default/intermediates/test/coverage_data/test_result.txt",
  }]);
  assert.deepEqual(
    config.qualityGates.map(({ id, key, threshold }) => [id, key, threshold]),
    [
      ["functionality-minimum", "functionality_suitability", 90],
      ["reliability-minimum", "reliability", 90],
      ["maintainability-minimum", "maintainability", 80],
      ["test-quality-minimum", "test_quality", 80],
      ["overall-minimum", "overall", 85],
    ],
  );
  assert.ok(config.qualityGates.every(({ remediation }) => remediation.length > 0));
  assert.match(result.stdout, /CONFIGURED/);
});

test("init leaves commands unresolved when no project task can be verified", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony-quality-no-wrapper-"));
  await mkdir(path.join(root, "feature/src/main/ets"), { recursive: true });

  const result = spawnSync(
    process.execPath,
    [cli, "init", "--project", root],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const config = JSON.parse(
    await readFile(path.join(root, "harmony-quality.config.json"), "utf8"),
  );
  assert.deepEqual(config.project.modules, ["feature"]);
  assert.equal(config.commands.build.status, "unresolved");
  assert.equal(config.commands.unitTest.status, "unresolved");
  assert.match(result.stdout, /manual configuration required/i);
});

test("repeated init preserves developer-edited configuration", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony-quality-idempotent-"));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  const configPath = path.join(root, "harmony-quality.config.json");
  const manual = { schemaVersion: 1, project: { modules: ["manual-entry"] } };
  await writeFile(configPath, `${JSON.stringify(manual, null, 2)}\n`);

  const result = spawnSync(
    process.execPath,
    [cli, "init", "--project", root],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(await readFile(configPath, "utf8")), manual);
  assert.match(result.stdout, /ALREADY_CONFIGURED/);
});

test("init does not configure a partial unit command for multiple modules", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony-quality-multi-module-"));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  await mkdir(path.join(root, "feature/src/main/ets"), { recursive: true });
  const wrapper = path.join(root, "hvigorw");
  await writeFile(wrapper, "#!/bin/sh\nprintf '%s\\n' assembleHap test codeLinter\n");
  await chmod(wrapper, 0o755);

  const result = spawnSync(
    process.execPath,
    [cli, "init", "--project", root],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const config = JSON.parse(await readFile(
    path.join(root, "harmony-quality.config.json"),
    "utf8",
  ));
  assert.deepEqual(config.project.modules, ["entry", "feature"]);
  assert.equal(config.commands.unitTest.status, "unresolved");
});

test("init rejects a directory without Harmony source modules", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony-quality-empty-"));

  const result = spawnSync(
    process.execPath,
    [cli, "init", "--project", root],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 4);
  assert.match(result.stderr, /no Harmony modules/);
});

test("init force intentionally replaces an existing configuration", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "harmony-quality-force-"));
  await mkdir(path.join(root, "entry/src/main/ets"), { recursive: true });
  const configPath = path.join(root, "harmony-quality.config.json");
  await writeFile(configPath, JSON.stringify({ manual: true }));

  const result = spawnSync(
    process.execPath,
    [cli, "init", "--project", root, "--force"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  const config = JSON.parse(await readFile(configPath, "utf8"));
  assert.equal(config.manual, undefined);
  assert.deepEqual(config.project.modules, ["entry"]);
});
