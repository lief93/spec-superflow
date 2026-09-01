import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { collectEvidence } from "./evidence.mjs";
import { resolveScope } from "./scope.mjs";
import { analyzeProject } from "./static-analysis.mjs";
import { runMutation } from "./mutation.mjs";
import { calculateScores } from "./scoring.mjs";
import { evaluateGates } from "./gates.mjs";
import { renderMarkdown } from "./report.mjs";
import { explainMetrics } from "./metrics.mjs";
import { prepareHypiumResult, readHypiumResult } from "./hypium-result.mjs";

const EXIT_CODES = { PASS: 0, FAIL: 2, BLOCKED: 3 };
const COMMAND_ORDER = ["build", "lint", "unitTest", "uiTest"];

function commandFailure(id, command, result) {
  if (result.error) {
    return {
      outcome: "infrastructure-error",
      reason: result.error.code === "ENOENT"
        ? "executable-not-found"
        : result.error.code === "ETIMEDOUT"
          ? "timeout"
          : "spawn-error",
    };
  }
  if (result.status === 0) return { outcome: "pass" };
  const infrastructureReason = command.infrastructureExitCodes?.[String(result.status)];
  if (infrastructureReason) {
    return { outcome: "infrastructure-error", reason: infrastructureReason };
  }
  return {
    outcome: id === "unitTest" || id === "uiTest"
      ? "test-failure"
      : "command-failure",
    reason: "non-zero-exit",
  };
}

function runCommand(root, id, command) {
  if (command.status !== "verified") {
    return command.required
      ? { id, outcome: "infrastructure-error", reason: "command-unresolved" }
      : { id, outcome: "skipped", reason: "command-optional" };
  }
  if (!Array.isArray(command.argv) || command.argv.length === 0) {
    return { id, outcome: "infrastructure-error", reason: "invalid-command" };
  }

  const [executable, ...args] = command.argv;
  prepareHypiumResult(root, command);
  const result = spawnSync(executable, args, {
    cwd: root,
    encoding: "utf8",
    timeout: command.timeoutMs ?? 120_000,
    maxBuffer: 10 * 1024 * 1024,
  });
  const processOutcome = commandFailure(id, command, result);
  const hypium = processOutcome.outcome === "pass" && (id === "unitTest" || id === "uiTest")
    ? readHypiumResult(root, command)
    : undefined;
  return {
    id,
    ...processOutcome,
    ...hypium,
    ...(hypium?.summary ? { hypium: hypium.summary } : {}),
    exitCode: result.status,
    signal: result.signal,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

function issueForCommand(command) {
  const blocked = command.outcome === "infrastructure-error";
  return {
    issue_id: `command-${command.id}-${command.reason}`,
    rule_id: "configured-command-must-complete",
    category: command.id === "lint" ? "maintainability" : "reliability",
    type: blocked ? "infrastructure" : command.outcome,
    severity: "blocker",
    file: null,
    line: null,
    message: `${command.id} ended with ${command.outcome}`,
    evidence: [`command:${command.id}`],
    metric_impact: blocked ? [] : ["command_success_rate"],
    remediation: blocked
      ? "Correct the configured executable or runtime, then rerun the check."
      : "Fix the reported command failure, then rerun the check.",
    source: "command-runner",
  };
}

function overallStatus(commands) {
  if (commands.some(({ outcome }) => outcome === "infrastructure-error")) {
    return "BLOCKED";
  }
  if (commands.some(({ outcome }) => outcome.endsWith("failure"))) return "FAIL";
  return "PASS";
}

function reportDirectory(root, configured) {
  const target = path.resolve(root, configured ?? ".harmony-quality/reports");
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`report directory escapes project root: ${configured}`);
  }
  return target;
}

export async function checkProject(root, options = {}) {
  const configPath = path.join(root, "harmony-quality.config.json");
  const config = JSON.parse(await readFile(configPath, "utf8"));
  const scope = await resolveScope(root, config, options);

  const commands = Object.entries(config.commands ?? {})
    .sort(([left], [right]) => {
      const leftIndex = COMMAND_ORDER.indexOf(left);
      const rightIndex = COMMAND_ORDER.indexOf(right);
      if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right);
      if (leftIndex === -1) return 1;
      if (rightIndex === -1) return -1;
      return leftIndex - rightIndex;
    })
    .map(([id, command]) => runCommand(root, id, command));
  const commandStatus = overallStatus(commands);
  const collected = commandStatus === "BLOCKED"
    ? {
        tests: { cases: [], summary: { total: 0, passed: 0, failed: 0, skipped: 0, durationMs: 0 } },
        acceptance: { criteria: [] },
        coverage: { files: [] },
        metrics: [],
        issues: [],
        evidence: [],
        failed: false,
      }
    : await collectEvidence(root, config, scope);
  const evidenceStatus = commandStatus === "BLOCKED"
    ? "BLOCKED"
    : commandStatus === "FAIL" || collected.failed
      ? "FAIL"
      : "PASS";
  const analysis = commandStatus === "BLOCKED"
    ? { functions: [], metrics: [], issues: [], evidence: [] }
    : await analyzeProject(root, config, scope, collected.coverage);
  const mutation = commandStatus === "BLOCKED"
    ? { ...await runMutation(root, { mutation: { enabled: false } }, scope), blocked: false }
    : await runMutation(root, config, scope);
  const issues = commands
    .filter(({ outcome }) => outcome !== "pass" && outcome !== "skipped")
    .map(issueForCommand)
    .concat(collected.issues, analysis.issues, mutation.issues);
  const metrics = explainMetrics(
    [...collected.metrics, ...analysis.metrics, ...mutation.metrics]
      .sort((left, right) => left.id.localeCompare(right.id)),
  );
  const scores = calculateScores(config, metrics, issues);
  const gates = evaluateGates(config, metrics, scores, issues);
  const status = evidenceStatus === "BLOCKED" || mutation.blocked ||
      gates.some(({ status: gateStatus }) => gateStatus === "BLOCKED")
    ? "BLOCKED"
    : evidenceStatus === "FAIL" || gates.some(({ status: gateStatus }) => gateStatus === "FAIL")
      ? "FAIL"
      : "PASS";
  const report = {
    schemaVersion: 1,
    status,
    scope: {
      ...scope.public,
      ...(scope.mode === "module"
        ? { files: collected.coverage.files.map(({ path: file }) => file).sort() }
        : {}),
    },
    commands,
    tests: collected.tests,
    acceptance: collected.acceptance,
    coverage: collected.coverage,
    functions: analysis.functions,
    mutation: {
      enabled: mutation.enabled,
      sourceHashUnchanged: mutation.sourceHashUnchanged,
      summary: mutation.summary,
      mutants: mutation.mutants,
    },
    metrics,
    scores,
    gates,
    issues,
    evidence: [
      ...commands.map(({ id, outcome, exitCode }) => ({
        id: `command:${id}`,
        kind: "command",
        outcome,
        exitCode: exitCode ?? null,
      })),
      ...collected.evidence,
      ...analysis.evidence,
      ...mutation.evidence,
    ],
  };

  const outputDirectory = reportDirectory(root, config.reports?.directory);
  await mkdir(outputDirectory, { recursive: true });
  const reportPath = path.join(outputDirectory, "quality-report.json");
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  const markdownPath = path.join(outputDirectory, "quality-report.md");
  await writeFile(markdownPath, renderMarkdown(report, { root }), "utf8");
  return { report, reportPath, markdownPath, exitCode: EXIT_CODES[status] };
}
