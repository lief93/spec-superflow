import path from "node:path";

const SCORE_LABELS = {
  functionality_suitability: "Functionality Suitability",
  reliability: "Reliability",
  maintainability: "Maintainability",
  test_quality: "Test Quality",
  overall: "Overall",
};

function cell(value) {
  return String(value ?? "-").replaceAll("|", "\\|").replaceAll("\n", " ");
}

function locationLabel({ file, line, column }) {
  return `${file}${line ? `:${line}` : ""}${column ? `:${column}` : ""}`;
}

function locationLink(location, { root } = {}) {
  const label = locationLabel(location);
  if (!root || location.external) return cell(label);
  const target = path.isAbsolute(location.file)
    ? path.resolve(location.file)
    : path.resolve(root, location.file);
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return cell(label);
  const encoded = encodeURI(target).replaceAll("#", "%23").replaceAll("?", "%3F");
  return `[${cell(label)}](vscode://file/${encoded}:${location.line ?? 1}:${location.column ?? 1})`;
}

function scoreGate(report, scoreId) {
  return report.gates.find(({ source, key }) => source === "score" && key === scoreId);
}

function repairFrames(stack) {
  const projectFrames = stack.filter(({ file, external }) =>
    !external && !/(?:^|\/)(?:node_modules|oh_modules|\.ohpm)(?:\/|$)/.test(file));
  return projectFrames.length > 0 ? projectFrames : stack;
}

export function renderMarkdown(report, context = {}) {
  const lines = [
    "# Harmony Quality Report",
    "",
    `**Status:** ${report.status}`,
    `**Scope:** ${report.scope.mode}`,
    "",
    "## Scores",
    "",
    "| Category | Score | Target | Result | Explanation |",
    "| --- | ---: | --- | --- | --- |",
  ];
  if (report.scores.length === 0) lines.push("| No calculated scores | - | - | NOT_GATED | No supporting metrics were configured. |");
  for (const score of report.scores) {
    const gate = scoreGate(report, score.id);
    lines.push(
      `| ${SCORE_LABELS[score.id] ?? score.id} | ${score.value} | ${gate ? `${gate.operator} ${gate.threshold}` : "-"} | ${gate?.status ?? "NOT_GATED"} | ${cell(score.explanation)} |`,
    );
  }

  lines.push(
    "",
    "## Metrics",
    "",
    "| Metric | Value | Unit | Explanation | Evidence |",
    "| --- | ---: | --- | --- | --- |",
  );
  if (report.metrics.length === 0) lines.push("| No metrics | - | - | No evidence-backed metrics were calculated. | - |");
  for (const metric of report.metrics) {
    lines.push(
      `| ${metric.id} | ${metric.value} | ${metric.unit} | ${metric.explanation} | ${metric.evidence.join(", ") || "-"} |`,
    );
  }

  lines.push(
    "",
    "## Quality Gates",
    "",
    "| Gate | Status | Condition | Remediation | Evidence |",
    "| --- | --- | --- | --- | --- |",
  );
  if (report.gates.length === 0) lines.push("| No configured gates | PASS | - | - | - |");
  for (const gate of report.gates) {
    lines.push(
      `| ${gate.id} | ${gate.status} | ${gate.actual ?? "missing"} ${gate.operator} ${gate.threshold} | ${cell(gate.remediation)} | ${gate.evidence.join(", ") || "-"} |`,
    );
  }

  const requiredChanges = report.gates.filter(({ status }) =>
    status === "FAIL" || status === "BLOCKED");
  if (requiredChanges.length > 0) {
    lines.push("", "## Required Changes", "");
    for (const gate of requiredChanges) {
      lines.push(
        `- **${gate.id}**: current \`${gate.actual ?? "missing"}\`, target \`${gate.operator} ${gate.threshold}\`. ${gate.remediation ?? "Inspect the linked evidence and resolve the failing condition."}`,
      );
    }
  }

  lines.push(
    "",
    "## Issues",
    "",
    "| Severity | Rule | Location | Message | Remediation | Evidence |",
    "| --- | --- | --- | --- | --- | --- |",
  );
  if (report.issues.length === 0) lines.push("| - | - | - | No issues | - | - |");
  for (const issue of report.issues) {
    const location = issue.file ? locationLink(issue, context) : "-";
    lines.push(
      `| ${issue.severity} | ${issue.rule_id} | ${location} | ${cell(issue.message)} | ${cell(issue.remediation)} | ${issue.evidence.join(", ")} |`,
    );
  }

  const stackIssues = report.issues.filter(({ stack }) => stack?.length > 0);
  if (stackIssues.length > 0) {
    lines.push("", "## Failure Stacks", "");
    for (const issue of stackIssues) {
      lines.push(`### ${issue.message}`, "");
      for (const frame of repairFrames(issue.stack)) {
        lines.push(`- ${frame.function ? `\`${frame.function}\` at ` : ""}${locationLink(frame, context)}`);
      }
      lines.push("");
    }
  }
  lines.push("");
  return `${lines.join("\n")}\n`;
}
