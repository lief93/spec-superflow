import { access, readFile, readdir, writeFile } from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const IGNORED_DIRECTORIES = new Set([
  ".git",
  ".idea",
  ".hvigor",
  "build",
  "node_modules",
  "oh_modules",
]);

async function exists(target, mode = constants.F_OK) {
  try {
    await access(target, mode);
    return true;
  } catch {
    return false;
  }
}

async function discoverModules(root) {
  const modules = [];

  async function visit(directory, relative = "") {
    if (relative && await exists(path.join(directory, "src/main/ets"))) {
      modules.push(relative.split(path.sep).join("/"));
      return;
    }

    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory() || IGNORED_DIRECTORIES.has(entry.name)) continue;
      const nextRelative = relative ? path.join(relative, entry.name) : entry.name;
      await visit(path.join(directory, entry.name), nextRelative);
    }
  }

  await visit(root);
  return modules.sort();
}

async function findWrapper(root) {
  const candidates = process.platform === "win32"
    ? ["hvigorw.bat", "hvigorw.cmd", "hvigorw"]
    : ["hvigorw"];

  for (const name of candidates) {
    const target = path.join(root, name);
    if (await exists(target, process.platform === "win32" ? constants.F_OK : constants.X_OK)) {
      return { name, target };
    }
  }
  return undefined;
}

function unresolved() {
  return { status: "unresolved", required: true, argv: [] };
}

function verified(argv) {
  return { status: "verified", required: true, timeoutMs: 120_000, argv };
}

function defaultQualityGates() {
  return [
    {
      id: "functionality-minimum",
      source: "score",
      key: "functionality_suitability",
      operator: ">=",
      threshold: 90,
      required: true,
      remediation: "Link every acceptance criterion to passing executable behavior tests.",
    },
    {
      id: "reliability-minimum",
      source: "score",
      key: "reliability",
      operator: ">=",
      threshold: 90,
      required: true,
      remediation: "Resolve blocker and critical reliability findings before delivery.",
    },
    {
      id: "maintainability-minimum",
      source: "score",
      key: "maintainability",
      operator: ">=",
      threshold: 80,
      required: true,
      remediation: "Reduce code smells, duplication, excessive complexity, and high CRAP functions.",
    },
    {
      id: "test-quality-minimum",
      source: "score",
      key: "test_quality",
      operator: ">=",
      threshold: 80,
      required: true,
      remediation: "Cover changed behavior branches and add tests that kill surviving mutants.",
    },
    {
      id: "overall-minimum",
      source: "score",
      key: "overall",
      operator: ">=",
      threshold: 85,
      required: true,
      remediation: "Resolve the failed category gates and their linked issues, then rerun the check.",
    },
  ];
}

function discoverCommands(root, modules, wrapper) {
  const commands = {
    build: unresolved(),
    unitTest: unresolved(),
    lint: unresolved(),
    uiTest: { ...unresolved(), required: false },
  };
  if (!wrapper || modules.length === 0) return commands;

  const probe = spawnSync(wrapper.target, ["--help"], {
    cwd: root,
    encoding: "utf8",
    timeout: 15_000,
  });
  if (probe.status !== 0 || probe.error) return commands;

  const output = `${probe.stdout}\n${probe.stderr}`;
  const executable = `./${wrapper.name}`;
  if (/\bassembleHap\b/.test(output)) {
    commands.build = verified([executable, "assembleHap"]);
  }
  if (/\btest\b/.test(output) && modules.length === 1) {
    commands.unitTest = verified([
      executable,
      "test",
      "-p",
      `module=${modules[0]}`,
      "-p",
      "coverage=true",
    ]);
    commands.unitTest.hypiumResultPath =
      `${modules[0]}/.test/default/intermediates/test/coverage_data/test_result.txt`;
  }
  if (/\bcodeLinter\b/.test(output)) {
    commands.lint = verified([executable, "codeLinter"]);
  }
  return commands;
}

export async function initializeProject(root, { force = false } = {}) {
  if (!await exists(root)) throw new Error(`project does not exist: ${root}`);
  const configPath = path.join(root, "harmony-quality.config.json");
  if (!force && await exists(configPath)) {
    return {
      config: JSON.parse(await readFile(configPath, "utf8")),
      path: configPath,
      created: false,
    };
  }

  const modules = await discoverModules(root);
  if (modules.length === 0) {
    throw new Error("no Harmony modules containing src/main/ets were found");
  }

  const wrapper = await findWrapper(root);
  const commands = discoverCommands(root, modules, wrapper);
  const config = {
    schemaVersion: 1,
    project: { root: ".", modules },
    commands,
    evidence: {
      tests: commands.unitTest.status === "verified" && modules.length === 1
        ? [{
            id: "unit",
            format: "hypium-text",
            path: commands.unitTest.hypiumResultPath,
          }]
        : [],
      ...(commands.unitTest.status === "verified" && modules.length === 1
        ? {
            coverage: {
              format: "harmony-coverage-json",
              path: `${modules[0]}/.test/default/outputs/test/reports/coverageReport.json`,
            },
          }
        : {}),
    },
    analysis: {
      maxFunctionLines: 60,
      maxComplexity: 15,
      maxNesting: 4,
      duplicateWindow: 6,
      architectureRules: [],
    },
    mutation: { enabled: false },
    qualityGates: defaultQualityGates(),
    scope: { default: "changed" },
    reports: { directory: ".harmony-quality/reports" },
  };
  await writeFile(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
  return { config, path: configPath, created: true };
}
