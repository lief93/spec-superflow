import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { listSourceFiles } from "./static-analysis.mjs";
import { prepareHypiumResult, readHypiumResult } from "./hypium-result.mjs";

const COPY_EXCLUDES = new Set([
  ".git",
  ".harmony-quality",
  ".hvigor",
  ".test",
  "build",
]);

const OPERATORS = [
  { id: "strict-equality-negation", pattern: /===/g, replacement: "!==" },
  { id: "strict-inequality-negation", pattern: /!==/g, replacement: "===" },
  { id: "logical-and-to-or", pattern: /&&/g, replacement: "||" },
  { id: "logical-or-to-and", pattern: /\|\|/g, replacement: "&&" },
  { id: "boolean-true-to-false", pattern: /\btrue\b/g, replacement: "false" },
  { id: "boolean-false-to-true", pattern: /\bfalse\b/g, replacement: "true" },
];

function mutationCandidates(file, text, limit) {
  const candidates = [];
  for (const operator of OPERATORS) {
    for (const match of text.matchAll(operator.pattern)) {
      candidates.push({
        file,
        operator: operator.id,
        index: match.index,
        line: text.slice(0, match.index).split(/\r?\n/).length,
        original: match[0],
        replacement: operator.replacement,
      });
      if (candidates.length >= limit) return candidates;
    }
  }
  return candidates;
}

async function sourceHash(root, files) {
  const hash = createHash("sha256");
  for (const file of files) {
    hash.update(file);
    hash.update("\0");
    hash.update(await readFile(path.join(root, file)));
    hash.update("\0");
  }
  return hash.digest("hex");
}

function execute(root, command, mutantId) {
  if (!Array.isArray(command.argv) || command.argv.length === 0) {
    return { status: "infrastructure-error", reason: "invalid-command" };
  }
  const [executable, ...args] = command.argv;
  prepareHypiumResult(root, command);
  const result = spawnSync(executable, args, {
    cwd: root,
    encoding: "utf8",
    timeout: command.timeoutMs ?? 120_000,
    maxBuffer: 10 * 1024 * 1024,
    env: { ...process.env, HARMONY_QUALITY_MUTANT_ID: mutantId ?? "baseline" },
  });
  if (result.error) {
    return {
      status: result.error.code === "ETIMEDOUT" ? "timeout" : "infrastructure-error",
      reason: result.error.code ?? "spawn-error",
      stdout: result.stdout ?? "",
      stderr: result.stderr ?? "",
    };
  }
  if (result.status === 0) {
    const hypium = readHypiumResult(root, command);
    if (hypium?.outcome === "infrastructure-error") {
      return { status: "infrastructure-error", reason: hypium.reason, exitCode: 0 };
    }
    if (hypium?.outcome === "test-failure") {
      return {
        status: mutantId ? "killed" : "baseline-failure",
        reason: hypium.reason,
        exitCode: 0,
      };
    }
    return { status: mutantId ? "survived" : "pass", exitCode: 0 };
  }
  if ((command.compileExitCodes ?? []).includes(result.status)) {
    return { status: "compile-error", exitCode: result.status };
  }
  return { status: mutantId ? "killed" : "baseline-failure", exitCode: result.status };
}

function emptyMutation(enabled = false) {
  return {
    enabled,
    sourceHashUnchanged: true,
    summary: { total: 0, killed: 0, survived: 0, timeout: 0, compileError: 0, score: null },
    mutants: [],
    metrics: [],
    issues: [],
    evidence: [],
    blocked: false,
  };
}

function mutationIssue(mutant) {
  return {
    issue_id: `mutation-${mutant.id}-survived`,
    rule_id: "mutant-must-be-killed",
    category: "test-quality",
    type: "survived-mutant",
    severity: "major",
    file: mutant.file,
    line: mutant.line,
    message: `${mutant.operator} survived the configured mutation test command.`,
    evidence: [`mutation:${mutant.id}`],
    metric_impact: ["mutation_score"],
    remediation: "Add or strengthen a behavior test that distinguishes the mutated behavior.",
    source: "mutation-runner",
  };
}

async function inIsolatedWorkspace(root, action) {
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), "harmony-quality-mutant-"));
  const workspace = path.join(tempRoot, "project");
  try {
    await cp(root, workspace, {
      recursive: true,
      verbatimSymlinks: true,
      filter: (source) => {
        if (source === root) return true;
        const relative = path.relative(root, source);
        return !relative.split(path.sep).some((part) => COPY_EXCLUDES.has(part));
      },
    });
    return await action(workspace);
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
}

export async function runMutation(root, config, scope) {
  if (!config.mutation?.enabled) return emptyMutation(false);
  const command = config.mutation.command ?? {};
  const files = await listSourceFiles(root, scope);
  const beforeHash = await sourceHash(root, files);
  const baseline = await inIsolatedWorkspace(root, (workspace) => execute(workspace, command));
  if (baseline.status !== "pass") {
    return {
      ...emptyMutation(true),
      blocked: true,
      baseline,
      issues: [{
        issue_id: "mutation-baseline-unavailable",
        rule_id: "mutation-baseline-must-pass",
        category: "test-quality",
        type: "infrastructure",
        severity: "blocker",
        file: null,
        line: null,
        message: `Mutation baseline ended with ${baseline.status}.`,
        evidence: ["mutation:baseline"],
        metric_impact: [],
        remediation: "Make the configured mutation test command pass on unmodified source.",
        source: "mutation-runner",
      }],
      evidence: [{ id: "mutation:baseline", kind: "mutation-baseline", outcome: baseline.status }],
    };
  }

  const maxMutants = Math.max(0, config.mutation.maxMutants ?? 20);
  const candidates = [];
  for (const file of files) {
    const text = await readFile(path.join(root, file), "utf8");
    candidates.push(...mutationCandidates(file, text, maxMutants - candidates.length));
    if (candidates.length >= maxMutants) break;
  }

  const mutants = [];
  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index];
    const id = `M-${String(index + 1).padStart(3, "0")}`;
    const mutant = await inIsolatedWorkspace(root, async (workspace) => {
      const target = path.join(workspace, candidate.file);
      const original = await readFile(target, "utf8");
      const mutated = original.slice(0, candidate.index) + candidate.replacement +
        original.slice(candidate.index + candidate.original.length);
      await writeFile(target, mutated, "utf8");
      const outcome = execute(workspace, command, id);
      return {
        id,
        file: candidate.file,
        line: candidate.line,
        operator: candidate.operator,
        status: outcome.status,
        exitCode: outcome.exitCode ?? null,
      };
    });
    mutants.push(mutant);
  }

  const afterHash = await sourceHash(root, files);
  const killed = mutants.filter(({ status }) => status === "killed").length;
  const survived = mutants.filter(({ status }) => status === "survived").length;
  const denominator = killed + survived;
  const score = denominator === 0 ? null : Math.round((killed / denominator) * 10_000) / 100;
  const summary = {
    total: mutants.length,
    killed,
    survived,
    timeout: mutants.filter(({ status }) => status === "timeout").length,
    compileError: mutants.filter(({ status }) => status === "compile-error").length,
    score,
  };
  const issues = mutants.filter(({ status }) => status === "survived").map(mutationIssue);
  const infrastructure = mutants.some(({ status }) => status === "infrastructure-error");
  return {
    enabled: true,
    sourceHashUnchanged: beforeHash === afterHash,
    summary,
    mutants,
    metrics: score === null ? [] : [{
      id: "mutation_score",
      value: score,
      unit: "percent",
      evidence: mutants.map(({ id }) => `mutation:${id}`),
    }],
    issues,
    evidence: mutants.map((mutant) => ({
      id: `mutation:${mutant.id}`,
      kind: "mutation",
      outcome: mutant.status,
      file: mutant.file,
      line: mutant.line,
      operator: mutant.operator,
    })),
    blocked: infrastructure || summary.timeout > 0 || beforeHash !== afterHash,
  };
}
