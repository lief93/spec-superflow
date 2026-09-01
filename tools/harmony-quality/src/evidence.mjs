import { readFile } from "node:fs/promises";
import { realpathSync } from "node:fs";
import path from "node:path";
import { parseHypiumDocument } from "./hypium-result.mjs";

function percent(hit, total) {
  if (total === 0) return 100;
  return Math.round((hit / total) * 10_000) / 100;
}

function projectPath(root, relativePath) {
  const target = path.resolve(root, relativePath);
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`evidence path escapes project root: ${relativePath}`);
  }
  return target;
}

async function readJson(root, relativePath) {
  return JSON.parse(await readFile(projectPath(root, relativePath), "utf8"));
}

function normalizeFrame(root, frame) {
  const target = path.isAbsolute(frame.file)
    ? path.resolve(frame.file)
    : path.resolve(root, frame.file);
  const relative = path.relative(root, target);
  return {
    ...frame,
    file: relative.startsWith("..") || path.isAbsolute(relative)
      ? frame.file
      : relative.split(path.sep).join("/"),
    ...(relative.startsWith("..") || path.isAbsolute(relative) ? { external: true } : {}),
  };
}

function normalizeTests(root, sources) {
  const cases = [];
  for (const source of sources) {
    const items = source.format === "test-json"
      ? source.document.tests ?? []
      : source.format === "hypium-text"
        ? source.document.cases
        : undefined;
    if (!items) throw new Error(`unsupported test evidence format: ${source.format}`);
    for (const item of items) {
      if (!item.id || !["passed", "failed", "skipped"].includes(item.status)) {
        throw new Error(`invalid test case in ${source.path}`);
      }
      cases.push({
        id: `${source.id}:${item.id}`,
        name: item.name ?? item.id,
        status: item.status,
        durationMs: item.durationMs ?? 0,
        source: source.id,
        ...(item.stack?.length > 0
          ? { stack: item.stack.map((frame) => normalizeFrame(root, frame)) }
          : {}),
      });
    }
  }
  cases.sort((left, right) => left.id.localeCompare(right.id));

  const summary = {
    total: cases.length,
    passed: cases.filter(({ status }) => status === "passed").length,
    failed: cases.filter(({ status }) => status === "failed").length,
    skipped: cases.filter(({ status }) => status === "skipped").length,
    durationMs: cases.reduce((sum, item) => sum + item.durationMs, 0),
  };
  return { cases, summary };
}

function failedTestIssues(tests) {
  return tests.cases
    .filter(({ status }) => status === "failed")
    .map((testCase) => {
      const stack = testCase.stack ?? [];
      const frame = stack.find(({ file, external }) =>
        !external && !/(?:^|\/)(?:node_modules|oh_modules|\.ohpm)(?:\/|$)/.test(file));
      return {
        issue_id: `test-${testCase.id.replaceAll(/[^a-zA-Z0-9]+/g, "-")}-failed`,
        rule_id: "test-case-must-pass",
        category: "functionality",
        type: "test-failure",
        severity: "blocker",
        file: frame?.file ?? null,
        line: frame?.line ?? null,
        column: frame?.column ?? null,
        message: `${testCase.name} failed.`,
        evidence: [`test:${testCase.id}`],
        metric_impact: ["test_pass_rate"],
        remediation: frame
          ? "Open the first project stack frame, fix the failed behavior, and rerun the test."
          : "Inspect the test evidence, fix the failed behavior, and rerun the test.",
        source: "test-evidence",
        ...(stack.length > 0 ? { stack } : {}),
      };
    });
}

function evaluateAcceptance(document, tests) {
  const byId = new Map(tests.cases.map((item) => [item.id, item]));
  const criteria = (document.criteria ?? [])
    .map((criterion) => {
      const linked = (criterion.tests ?? []).map((id) => byId.get(id));
      let status = "passed";
      if (linked.length === 0 || linked.some((item) => !item)) status = "missing-test";
      else if (linked.some((item) => item.status === "failed")) status = "failed";
      else if (linked.some((item) => item.status === "skipped")) status = "not-executed";
      return {
        id: criterion.id,
        ...(criterion.given === undefined ? {} : { given: criterion.given }),
        ...(criterion.when === undefined ? {} : { when: criterion.when }),
        ...(criterion.then === undefined ? {} : { then: criterion.then }),
        status,
        tests: criterion.tests ?? [],
      };
    })
    .sort((left, right) => left.id.localeCompare(right.id));

  const issues = criteria
    .filter(({ status }) => status !== "passed")
    .map((criterion) => ({
      issue_id: `acceptance-${criterion.id}-${criterion.status}`,
      rule_id: criterion.status === "missing-test"
        ? "acceptance-criterion-must-have-executable-test"
        : "acceptance-criterion-must-pass",
      category: "functionality",
      type: "test-gap",
      severity: "blocker",
      file: null,
      line: null,
      message: `${criterion.id} is ${criterion.status}`,
      evidence: [`acceptance:${criterion.id}`],
      metric_impact: ["acceptance_coverage"],
      remediation: "Add or repair an executable test linked to this acceptance criterion.",
      source: "acceptance-map",
    }));
  return { criteria, issues };
}

function parseLcov(root, text) {
  const files = [];
  let current;
  for (const line of text.split(/\r?\n/)) {
    if (line.startsWith("SF:")) {
      const sourcePath = line.slice(3);
      current = {
        path: (path.isAbsolute(sourcePath) ? path.relative(root, sourcePath) : sourcePath)
          .split(path.sep).join("/"),
        lines: [],
        branches: [],
        functions: [],
      };
      files.push(current);
    } else if (current && line.startsWith("DA:")) {
      const [lineNumber, hits] = line.slice(3).split(",").map(Number);
      current.lines.push({ line: lineNumber, hits });
    } else if (current && line.startsWith("BRDA:")) {
      const [lineNumber, block, branch, taken] = line.slice(5).split(",");
      current.branches.push({
        line: Number(lineNumber),
        block: Number(block),
        branch: Number(branch),
        hits: taken === "-" ? 0 : Number(taken),
      });
    } else if (current && line.startsWith("FNDA:")) {
      const separator = line.indexOf(",", 5);
      current.functions.push({
        name: line.slice(separator + 1),
        hits: Number(line.slice(5, separator)),
      });
    }
  }
  files.sort((left, right) => left.path.localeCompare(right.path));
  return files;
}

function coveragePath(root, sourcePath) {
  const unresolvedTarget = path.isAbsolute(sourcePath)
    ? path.resolve(sourcePath)
    : path.resolve(root, sourcePath);
  let target;
  try {
    target = realpathSync(unresolvedTarget);
  } catch (error) {
    const unresolvedRelative = path.relative(root, unresolvedTarget);
    if (unresolvedRelative.startsWith("..") || path.isAbsolute(unresolvedRelative)) {
      throw new Error(`coverage source path escapes project root: ${sourcePath}`);
    }
    throw error;
  }
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`coverage source path escapes project root: ${sourcePath}`);
  }
  return relative.split(path.sep).join("/");
}

function harmonyBranches(functions) {
  const branches = [];
  let branchIndex = 0;
  for (const fn of functions) {
    for (const branch of fn.branches ?? []) {
      const line = branch.startLoc?.line;
      if (!Number.isInteger(line)) continue;
      const group = branch.group ?? [];
      if (branch.ignored === 0 || branch.ignored === 4) {
        branches.push({
          line,
          block: 0,
          branch: branchIndex,
          hits: branch.trueCount ?? 0,
        });
        branchIndex += 1;
      }
      if ((branch.ignored === 0 || branch.ignored === 3) && group.length === 0) {
        branches.push({
          line,
          block: 0,
          branch: branchIndex,
          hits: branch.falseCount ?? 0,
        });
        branchIndex += 1;
      }
    }
  }
  return branches;
}

function parseHarmonyCoverage(root, document) {
  if (!Array.isArray(document.files)) {
    throw new Error("invalid Harmony coverage report: files must be an array");
  }
  return document.files.map((file) => {
    if (typeof file.path !== "string") {
      throw new Error("invalid Harmony coverage report: file path is required");
    }
    const executed = file.summary?.lines?.executedLineCount;
    if (!Array.isArray(executed)) {
      throw new Error(`invalid Harmony coverage report: missing executed lines for ${file.path}`);
    }
    const functions = (file.functions ?? [])
      .filter(({ ignored }) => ignored === 0)
      .map(({ name, count }) => ({ name, hits: count ?? 0 }));
    return {
      path: coveragePath(root, file.path),
      lines: executed
        .map((hits, line) => ({ line, hits }))
        .filter(({ hits }) => Number.isFinite(hits) && hits >= 0),
      branches: harmonyBranches(file.functions ?? []),
      functions,
    };
  }).sort((left, right) => left.path.localeCompare(right.path));
}

function evaluateCoverage(files) {
  const allLines = files.flatMap(({ path: file, lines }) =>
    lines.map((line) => ({ file, ...line })));
  const allBranches = files.flatMap(({ path: file, branches }) =>
    branches.map((branch) => ({ file, ...branch })));
  const allFunctions = files.flatMap(({ path: file, functions }) =>
    functions.map((fn) => ({ file, ...fn })));
  const metrics = [];
  if (allBranches.length > 0) {
    metrics.push({
      id: "branch_coverage",
      value: percent(allBranches.filter(({ hits }) => hits > 0).length, allBranches.length),
      unit: "percent",
      evidence: files.map(({ path: file }) => `coverage:${file}`),
    });
  }
  if (allFunctions.length > 0) {
    metrics.push({
      id: "function_coverage",
      value: percent(allFunctions.filter(({ hits }) => hits > 0).length, allFunctions.length),
      unit: "percent",
      evidence: files.map(({ path: file }) => `coverage:${file}`),
    });
  }
  if (allLines.length > 0) {
    metrics.push({
      id: "line_coverage",
      value: percent(allLines.filter(({ hits }) => hits > 0).length, allLines.length),
      unit: "percent",
      evidence: files.map(({ path: file }) => `coverage:${file}`),
    });
  }
  const issues = allLines
    .filter(({ hits }) => hits === 0)
    .map(({ file, line }) => ({
      issue_id: `coverage-${file.replaceAll(/[^a-zA-Z0-9]+/g, "-")}-${line}`,
      rule_id: "line-must-be-covered",
      category: "test-quality",
      type: "coverage-gap",
      severity: "major",
      file,
      line,
      message: "Executable line is not covered.",
      evidence: [`coverage:${file}:${line}`],
      metric_impact: ["line_coverage"],
      remediation: "Add a behavior test that executes this line.",
      source: "lcov",
    }));
  return { files, metrics, issues };
}

export async function collectEvidence(root, config, scope) {
  const testSources = [];
  for (const source of config.evidence?.tests ?? []) {
    const text = await readFile(projectPath(root, source.path), "utf8");
    testSources.push({
      ...source,
      document: source.format === "hypium-text"
        ? parseHypiumDocument(text)
        : JSON.parse(text),
    });
  }
  const tests = normalizeTests(root, testSources);
  const testIssues = failedTestIssues(tests);

  const acceptanceDocument = config.evidence?.acceptance
    ? await readJson(root, config.evidence.acceptance.path)
    : { criteria: [] };
  const acceptance = evaluateAcceptance(acceptanceDocument, tests);

  let coverage = { files: [], metrics: [], issues: [] };
  if (config.evidence?.coverage) {
    const coverageText = await readFile(
      projectPath(root, config.evidence.coverage.path),
      "utf8",
    );
    const parsed = config.evidence.coverage.format === "lcov"
      ? parseLcov(root, coverageText)
      : config.evidence.coverage.format === "harmony-coverage-json"
        ? parseHarmonyCoverage(root, JSON.parse(coverageText))
        : undefined;
    if (!parsed) {
      throw new Error(`unsupported coverage format: ${config.evidence.coverage.format}`);
    }
    const scoped = parsed
      .map((file) => ({
        ...file,
        lines: file.lines.filter(({ line }) => scope.includes(file.path, line)),
        branches: file.branches.filter(({ line }) => scope.includes(file.path, line)),
        functions: scope.mode === "changed"
          ? []
          : file.functions.filter(() => scope.includes(file.path)),
      }))
      .filter((file) =>
        file.lines.length > 0 || file.branches.length > 0 || file.functions.length > 0);
    coverage = evaluateCoverage(scoped);
  }

  const executableTests = tests.summary.passed + tests.summary.failed;
  const metrics = [];
  if (config.evidence?.acceptance) {
    metrics.push({
      id: "acceptance_coverage",
      value: percent(
        acceptance.criteria.filter(({ status }) => status === "passed").length,
        acceptance.criteria.length,
      ),
      unit: "percent",
      evidence: acceptance.criteria.map(({ id }) => `acceptance:${id}`),
    });
  }
  metrics.push(...coverage.metrics);
  if (testSources.length > 0 && executableTests > 0) {
    metrics.push({
      id: "test_pass_rate",
      value: percent(tests.summary.passed, executableTests),
      unit: "percent",
      evidence: tests.cases.map(({ id }) => `test:${id}`),
    });
  }
  metrics.sort((left, right) => left.id.localeCompare(right.id));

  const evidence = [
    ...tests.cases.map((item) => ({
      id: `test:${item.id}`,
      kind: "test",
      outcome: item.status,
      durationMs: item.durationMs,
      ...(item.stack ? { stack: item.stack } : {}),
    })),
    ...acceptance.criteria.map((item) => ({
      id: `acceptance:${item.id}`,
      kind: "acceptance",
      outcome: item.status,
      tests: item.tests,
    })),
    ...coverage.files.map((item) => ({
      id: `coverage:${item.path}`,
      kind: "coverage",
      path: item.path,
      lines: item.lines,
      branches: item.branches,
      functions: item.functions,
    })),
    ...coverage.files.flatMap((item) => item.lines.map((line) => ({
      id: `coverage:${item.path}:${line.line}`,
      kind: "coverage-line",
      path: item.path,
      line: line.line,
      hits: line.hits,
    }))),
  ];

  return {
    tests,
    acceptance: { criteria: acceptance.criteria },
    coverage: { files: coverage.files },
    metrics,
    issues: [...testIssues, ...acceptance.issues, ...coverage.issues],
    evidence,
    failed: acceptance.issues.length > 0 || tests.summary.failed > 0,
  };
}
