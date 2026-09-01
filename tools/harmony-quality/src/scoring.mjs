function round(value) {
  return Math.round(value * 100) / 100;
}

function clamp(value) {
  return Math.max(0, Math.min(100, round(value)));
}

function metricInputs(metrics, ids) {
  return ids.map((id) => metrics.get(id)).filter(Boolean).map((metric) => ({
    id: `metric:${metric.id}`,
    value: metric.value,
    evidence: metric.evidence,
  }));
}

function score(id, value, weight, inputs, explanation) {
  return {
    id,
    value: clamp(value),
    weight,
    inputs,
    evidence: [...new Set(inputs.flatMap((input) => input.evidence ?? []))].sort(),
    explanation,
  };
}

export function calculateScores(config, metricsList, issues) {
  const metrics = new Map(metricsList.map((metric) => [metric.id, metric]));
  const scores = [];

  const functionalityInputs = metricInputs(metrics, [
    "acceptance_coverage",
    "test_pass_rate",
  ]);
  if (functionalityInputs.length > 0) {
    scores.push(score(
      "functionality_suitability",
      functionalityInputs.reduce((sum, input) => sum + input.value, 0) /
        functionalityInputs.length,
      0.35,
      functionalityInputs,
      "Arithmetic mean of available acceptance coverage and executable test pass rate.",
    ));
  }

  if (config.analysis || config.evidence?.linter) {
    const reliabilityMetric = metrics.get("reliability_issue_count");
    const reliabilityIssues = issues.filter(({ category }) => category === "reliability");
    const penalties = { blocker: 40, critical: 25, major: 10, minor: 3, info: 0 };
    const penalty = reliabilityIssues.reduce(
      (sum, item) => sum + (penalties[item.severity] ?? penalties.major),
      0,
    );
    const inputs = reliabilityMetric ? [{
      id: `metric:${reliabilityMetric.id}`,
      value: reliabilityMetric.value,
      evidence: reliabilityMetric.evidence,
    }] : [];
    scores.push(score(
      "reliability",
      100 - penalty,
      0.25,
      inputs,
      "Starts at 100 and subtracts deterministic severity weights for reliability issues.",
    ));

    const maintainabilityInputs = metricInputs(metrics, [
      "code_smell_count",
      "duplication_percent",
      "max_complexity",
      "max_crap",
    ]);
    const value = 100 -
      (metrics.get("code_smell_count")?.value ?? 0) * 5 -
      (metrics.get("duplication_percent")?.value ?? 0) -
      Math.max(0, (metrics.get("max_complexity")?.value ?? 0) - 5) * 3 -
      Math.max(0, (metrics.get("max_crap")?.value ?? 0) - 10);
    scores.push(score(
      "maintainability",
      value,
      0.2,
      maintainabilityInputs,
      "Starts at 100 and subtracts code-smell, duplication, excess-complexity, and excess-CRAP penalties.",
    ));
  }

  const testQualityInputs = metricInputs(metrics, [
    "branch_coverage",
    "function_coverage",
    "line_coverage",
    "mutation_score",
  ]);
  if (testQualityInputs.length > 0) {
    scores.push(score(
      "test_quality",
      testQualityInputs.reduce((sum, input) => sum + input.value, 0) /
        testQualityInputs.length,
      0.2,
      testQualityInputs,
      "Arithmetic mean of available line, branch, function, and mutation coverage percentages.",
    ));
  }

  if (scores.length > 0) {
    const totalWeight = scores.reduce((sum, item) => sum + item.weight, 0);
    const value = scores.reduce((sum, item) => sum + item.value * item.weight, 0) /
      totalWeight;
    scores.push(score(
      "overall",
      value,
      1,
      scores.map((item) => ({
        id: `score:${item.id}`,
        value: item.value,
        evidence: item.evidence,
      })),
      "Weighted mean of available deterministic category scores, renormalized when a category has no evidence.",
    ));
  }

  return scores.sort((left, right) => left.id.localeCompare(right.id));
}
