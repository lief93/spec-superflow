import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SKIP_DIRECTORIES = new Set([
  ".git",
  ".harmony-quality",
  ".hvigor",
  ".test",
  "build",
  "node_modules",
  "oh_modules",
]);

function safeProjectPath(root, relativePath) {
  const target = path.resolve(root, relativePath);
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`analysis path escapes project root: ${relativePath}`);
  }
  return target;
}

export async function listSourceFiles(root, scope) {
  const files = [];
  async function visit(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!SKIP_DIRECTORIES.has(entry.name)) await visit(path.join(directory, entry.name));
      } else if (
        entry.isFile() &&
        entry.name !== "BuildProfile.ets" &&
        /\.(?:ets|ts)$/.test(entry.name)
      ) {
        const file = path.relative(root, path.join(directory, entry.name))
          .split(path.sep).join("/");
        const productionSource = /(?:^|\/)src\/main\//.test(file);
        if (productionSource &&
            (scope.mode === "changed" ? scope.lines.has(file) : scope.includes(file, 1))) {
          files.push(file);
        }
      }
    }
  }
  await visit(root);
  return files.sort();
}

function braceDelta(line) {
  return (line.match(/\{/g)?.length ?? 0) - (line.match(/\}/g)?.length ?? 0);
}

function functionName(line) {
  const declaration = line.match(/\bfunction\s+([A-Za-z_$][\w$]*)\s*\(/);
  if (declaration) return declaration[1];
  const method = line.match(/^\s*(?:(?:public|private|protected|static|async)\s+)*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::[^={]+)?\s*\{/);
  if (!method || ["if", "for", "while", "switch", "catch"].includes(method[1])) return undefined;
  return method[1];
}

function complexityOf(text) {
  const decisions = text.match(/\b(?:if|for|while|case|catch)\b|&&|\|\||\?\?/g) ?? [];
  return 1 + decisions.length;
}

function functionsIn(file, text, coverageLines) {
  const lines = text.split(/\r?\n/);
  const functions = [];
  for (let index = 0; index < lines.length; index += 1) {
    const name = functionName(lines[index]);
    if (!name) continue;
    let balance = 0;
    let started = false;
    let maxNesting = 0;
    let end = index;
    for (; end < lines.length; end += 1) {
      balance += braceDelta(lines[end]);
      if (lines[end].includes("{")) started = true;
      if (started) maxNesting = Math.max(maxNesting, Math.max(0, balance - 1));
      if (started && balance <= 0) break;
    }
    const startLine = index + 1;
    const endLine = Math.min(end + 1, lines.length);
    const body = lines.slice(index, end + 1).join("\n");
    const measured = coverageLines.filter(({ line }) => line >= startLine && line <= endLine);
    const covered = measured.filter(({ hits }) => hits > 0).length;
    const coverage = measured.length === 0
      ? null
      : Math.round((covered / measured.length) * 10_000) / 100;
    const complexity = complexityOf(body);
    const crap = coverage === null
      ? null
      : Math.round(
          (complexity ** 2 * (1 - coverage / 100) ** 3 + complexity) * 100,
        ) / 100;
    functions.push({
      file,
      name,
      startLine,
      endLine,
      complexity,
      coverage,
      crap,
      maxNesting,
    });
    index = end;
  }
  return functions;
}

function issue(fields) {
  return {
    issue_id: fields.issueId,
    rule_id: fields.ruleId,
    category: fields.category ?? "maintainability",
    type: fields.type ?? "code-smell",
    severity: fields.severity ?? "major",
    file: fields.file,
    line: fields.line,
    message: fields.message,
    evidence: fields.evidence,
    metric_impact: fields.metricImpact ?? ["code_smell_count"],
    remediation: fields.remediation,
    source: fields.source ?? "harmony-quality",
  };
}

function analyzeFunctions(functions, config) {
  const issues = [];
  for (const fn of functions) {
    const evidence = [`function:${fn.file}:${fn.name}:${fn.startLine}`];
    if (fn.endLine - fn.startLine + 1 > (config.maxFunctionLines ?? 60)) {
      issues.push(issue({
        issueId: `function-${fn.file}-${fn.startLine}-too-long`,
        ruleId: "function-length",
        file: fn.file,
        line: fn.startLine,
        message: `${fn.name} has ${fn.endLine - fn.startLine + 1} lines.`,
        evidence,
        remediation: "Split the function along behavior or responsibility boundaries.",
      }));
    }
    if (fn.complexity > (config.maxComplexity ?? 15)) {
      issues.push(issue({
        issueId: `function-${fn.file}-${fn.startLine}-complexity`,
        ruleId: "cyclomatic-complexity",
        file: fn.file,
        line: fn.startLine,
        message: `${fn.name} has cyclomatic complexity ${fn.complexity}.`,
        evidence,
        metricImpact: ["max_complexity", "max_crap"],
        remediation: "Reduce independent control paths or extract cohesive behavior.",
      }));
    }
    if (fn.maxNesting > (config.maxNesting ?? 4)) {
      issues.push(issue({
        issueId: `function-${fn.file}-${fn.startLine}-nesting`,
        ruleId: "maximum-nesting",
        file: fn.file,
        line: fn.startLine,
        message: `${fn.name} reaches nesting level ${fn.maxNesting}.`,
        evidence,
        remediation: "Use guard clauses or extract nested behavior.",
      }));
    }
  }
  return issues;
}

function analyzeText(file, text, architectureRules) {
  const issues = [];
  const lines = text.split(/\r?\n/);
  lines.forEach((line, index) => {
    const importMatch = line.match(/\bfrom\s+['"]([^'"]+)['"]|\bimport\s+['"]([^'"]+)['"]/);
    const imported = importMatch?.[1] ?? importMatch?.[2];
    for (const rule of architectureRules) {
      if (
        file.startsWith(rule.from) && imported &&
        rule.forbiddenImports.some((fragment) => imported.includes(fragment))
      ) {
        issues.push(issue({
          issueId: `architecture-${rule.id}-${file}-${index + 1}`,
          ruleId: rule.id,
          file,
          line: index + 1,
          message: `Import ${imported} violates ${rule.id}.`,
          evidence: [`source:${file}:${index + 1}`],
          remediation: "Depend on the allowed abstraction or move the dependency to its owning layer.",
          source: "architecture-rule",
        }));
      }
    }
  });

  const emptyCatch = /catch\s*\([^)]*\)\s*\{\s*\}/g;
  for (const match of text.matchAll(emptyCatch)) {
    const line = text.slice(0, match.index).split(/\r?\n/).length;
    issues.push(issue({
      issueId: `empty-catch-${file}-${line}`,
      ruleId: "empty-catch",
      category: "reliability",
      type: "potential-bug",
      severity: "critical",
      file,
      line,
      message: "Caught error is silently discarded.",
      evidence: [`source:${file}:${line}`],
      metricImpact: ["reliability_issue_count"],
      remediation: "Handle, translate, or explicitly document and report the error.",
    }));
  }
  return issues;
}

function duplicateAnalysis(documents, windowSize) {
  if (!windowSize || windowSize < 2) return { percent: 0, issues: [] };
  const sequences = new Map();
  let normalizedLineCount = 0;
  for (const document of documents) {
    const lines = document.text.split(/\r?\n/)
      .map((text, index) => ({ text: text.trim().replace(/\s+/g, " "), line: index + 1 }))
      .filter(({ text }) => text && !text.startsWith("//"));
    normalizedLineCount += lines.length;
    for (let index = 0; index <= lines.length - windowSize; index += 1) {
      const key = lines.slice(index, index + windowSize).map(({ text }) => text).join("\n");
      const occurrences = sequences.get(key) ?? [];
      occurrences.push({ file: document.file, line: lines[index].line });
      sequences.set(key, occurrences);
    }
  }
  const duplicateWindows = [...sequences.values()]
    .filter((items) => new Set(items.map(({ file }) => file)).size > 1)
    .map((items) => items.sort((left, right) =>
      `${left.file}:${String(left.line).padStart(10, "0")}`
        .localeCompare(`${right.file}:${String(right.line).padStart(10, "0")}`)))
    .sort((left, right) => `${left[0].file}:${left[0].line}`.localeCompare(`${right[0].file}:${right[0].line}`));
  const duplicateGroups = [];
  for (const occurrences of duplicateWindows) {
    const continuation = duplicateGroups.findLast((group) =>
      group.occurrences.length === occurrences.length &&
      occurrences.every((occurrence, index) =>
        occurrence.file === group.occurrences[index].file &&
        occurrence.line === group.occurrences[index].line + group.length - windowSize + 1));
    if (continuation) {
      continuation.length += 1;
    } else {
      duplicateGroups.push({ occurrences, length: windowSize });
    }
  }
  const duplicateLines = new Set();
  for (const group of duplicateGroups) {
    for (const occurrence of group.occurrences) {
      for (let offset = 0; offset < group.length; offset += 1) {
        duplicateLines.add(`${occurrence.file}:${occurrence.line + offset}`);
      }
    }
  }
  const percent = normalizedLineCount === 0
    ? 0
    : Math.min(100, Math.round((duplicateLines.size / normalizedLineCount) * 10_000) / 100);
  const issues = duplicateGroups.map((group, index) => issue({
    issueId: `duplicate-block-${index + 1}`,
    ruleId: "duplicate-code-block",
    file: group.occurrences[0].file,
    line: group.occurrences[0].line,
    message: `Duplicated ${group.length}-line block appears at ${group.occurrences.map(({ file, line }) => `${file}:${line}`).join(", ")}.`,
    evidence: group.occurrences.map(({ file, line }) => `source:${file}:${line}`),
    metricImpact: ["duplication_percent", "code_smell_count"],
    remediation: "Extract the shared behavior when the duplicated code represents the same concept.",
  }));
  return { percent, issues };
}

async function linterIssues(root, linter, scope) {
  if (!linter) return [];
  if (linter.format !== "arkts-json") throw new Error(`unsupported linter format: ${linter.format}`);
  const document = JSON.parse(await readFile(safeProjectPath(root, linter.path), "utf8"));
  return (document.issues ?? []).map((item, index) => issue({
    issueId: `linter-${item.ruleId}-${item.file}-${item.line ?? index + 1}`,
    ruleId: item.ruleId,
    category: item.type === "bug" ? "reliability" : "maintainability",
    type: item.type ?? "code-smell",
    severity: item.severity ?? "major",
    file: item.file,
    line: item.line ?? null,
    message: item.message,
    evidence: [`linter:${item.ruleId}:${item.file}:${item.line ?? index + 1}`],
    metricImpact: item.type === "bug" ? ["reliability_issue_count"] : ["code_smell_count"],
    remediation: item.remediation ?? "Follow the ArkTS linter rule guidance.",
    source: "arkts-linter",
  })).filter((item) =>
    scope.mode !== "changed" || scope.includes(item.file, item.line ?? 1));
}

export async function analyzeProject(root, config, scope, coverage) {
  if (!config.analysis && !config.evidence?.linter) {
    return { functions: [], metrics: [], issues: [], evidence: [] };
  }
  const analysis = config.analysis ?? {};
  const files = await listSourceFiles(root, scope);
  const documents = await Promise.all(files.map(async (file) => ({
    file,
    text: await readFile(path.join(root, file), "utf8"),
  })));
  const coverageByFile = new Map(coverage.files.map((item) => [item.path, item.lines]));
  const functions = documents.flatMap(({ file, text }) =>
    functionsIn(file, text, coverageByFile.get(file) ?? []))
    .filter((fn) => scope.mode !== "changed" ||
      Array.from({ length: fn.endLine - fn.startLine + 1 }, (_, offset) => fn.startLine + offset)
        .some((line) => scope.includes(fn.file, line)));
  const duplicate = duplicateAnalysis(documents, analysis.duplicateWindow ?? 6);
  const issues = [
    ...documents.flatMap(({ file, text }) =>
      analyzeText(file, text, analysis.architectureRules ?? [])),
    ...analyzeFunctions(functions, analysis),
    ...duplicate.issues,
    ...await linterIssues(root, config.evidence?.linter, scope),
  ].filter((item) =>
    scope.mode !== "changed" || !item.file || scope.includes(item.file, item.line ?? 1))
    .sort((left, right) => left.issue_id.localeCompare(right.issue_id));
  const metrics = [
    {
      id: "code_smell_count",
      value: issues.filter(({ type }) => type === "code-smell").length,
      unit: "count",
      evidence: issues.filter(({ type }) => type === "code-smell").map(({ issue_id }) => `issue:${issue_id}`),
    },
    {
      id: "duplication_percent",
      value: duplicate.percent,
      unit: "percent",
      evidence: duplicate.issues.map(({ issue_id }) => `issue:${issue_id}`),
    },
    {
      id: "max_complexity",
      value: Math.max(0, ...functions.map(({ complexity }) => complexity)),
      unit: "count",
      evidence: functions.map(({ file, name, startLine }) => `function:${file}:${name}:${startLine}`),
    },
    {
      id: "reliability_issue_count",
      value: issues.filter(({ category }) => category === "reliability").length,
      unit: "count",
      evidence: issues.filter(({ category }) => category === "reliability")
        .map(({ issue_id }) => `issue:${issue_id}`),
    },
  ];
  const measuredCrap = functions.filter(({ crap }) => crap !== null);
  if (measuredCrap.length > 0) {
    metrics.push({
      id: "max_crap",
      value: Math.max(...measuredCrap.map(({ crap }) => crap)),
      unit: "score",
      evidence: measuredCrap.map(({ file, name, startLine }) =>
        `function:${file}:${name}:${startLine}`),
    });
  }
  metrics.sort((left, right) => left.id.localeCompare(right.id));
  const evidence = [
    ...functions.map((fn) => ({
      id: `function:${fn.file}:${fn.name}:${fn.startLine}`,
      kind: "function-quality",
      ...fn,
    })),
    ...issues.map(({ issue_id }) => ({ id: `issue:${issue_id}`, kind: "issue" })),
  ];
  const existingEvidence = new Set(evidence.map(({ id }) => id));
  for (const id of issues.flatMap((item) => item.evidence)) {
    if (!existingEvidence.has(id)) {
      evidence.push({ id, kind: id.startsWith("linter:") ? "linter" : "source" });
      existingEvidence.add(id);
    }
  }
  return { functions, metrics, issues, evidence };
}
