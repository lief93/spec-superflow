function compare(actual, operator, threshold) {
  if (operator === ">=") return actual >= threshold;
  if (operator === ">") return actual > threshold;
  if (operator === "<=") return actual <= threshold;
  if (operator === "<") return actual < threshold;
  if (operator === "==") return actual === threshold;
  if (operator === "!=") return actual !== threshold;
  throw new Error(`unsupported quality gate operator: ${operator}`);
}

function issueMatches(issue, filter = {}) {
  return Object.entries(filter).every(([key, expected]) => {
    const values = Array.isArray(expected) ? expected : [expected];
    return values.includes(issue[key]);
  });
}

export function evaluateGates(config, metricsList, scoresList, issues) {
  const metrics = new Map(metricsList.map((metric) => [metric.id, metric]));
  const scores = new Map(scoresList.map((item) => [item.id, item]));
  return (config.qualityGates ?? []).map((gate) => {
    let actual;
    let evidence = [];
    if (gate.source === "metric") {
      const metric = metrics.get(gate.key);
      actual = metric?.value;
      evidence = metric?.evidence ?? [];
    } else if (gate.source === "score") {
      const score = scores.get(gate.key);
      actual = score?.value;
      evidence = score?.evidence ?? [];
    } else if (gate.source === "issue-count") {
      const matched = issues.filter((item) => issueMatches(item, gate.filter));
      actual = matched.length;
      evidence = matched.map(({ issue_id }) => `issue:${issue_id}`);
    } else {
      throw new Error(`unsupported quality gate source: ${gate.source}`);
    }

    const base = {
      id: gate.id,
      status: "PASS",
      source: gate.source,
      key: gate.key,
      operator: gate.operator,
      threshold: gate.threshold,
      actual: actual ?? null,
      evidence: [...evidence].sort(),
      ...(gate.remediation ? { remediation: gate.remediation } : {}),
    };
    if (actual === undefined) {
      return { ...base, status: gate.required === false ? "SKIPPED" : "BLOCKED" };
    }
    return { ...base, status: compare(actual, gate.operator, gate.threshold) ? "PASS" : "FAIL" };
  });
}
