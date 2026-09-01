const EXPLANATIONS = {
  acceptance_coverage: "Percentage of acceptance criteria whose linked executable tests all passed.",
  branch_coverage: "Percentage of instrumented branches executed in the selected scope.",
  code_smell_count: "Number of normalized maintainability findings in the selected scope.",
  duplication_percent: "Percentage of normalized source lines participating in cross-file duplicate windows.",
  function_coverage: "Percentage of instrumented functions executed in the selected scope.",
  line_coverage: "Percentage of instrumented executable lines executed in the selected scope.",
  max_complexity: "Highest lexical cyclomatic complexity among functions in the selected scope.",
  max_crap: "Highest CRAP score among functions that have function-level line coverage evidence.",
  mutation_score: "Killed mutants divided by killed plus survived valid mutants.",
  reliability_issue_count: "Number of normalized potential-bug and reliability findings in the selected scope.",
  test_pass_rate: "Passed executable tests divided by passed plus failed executable tests; skipped tests are excluded.",
};

export function explainMetrics(metrics) {
  return metrics.map((metric) => ({
    ...metric,
    explanation: EXPLANATIONS[metric.id] ??
      `Deterministic ${metric.id.replaceAll("_", " ")} value for the selected scope.`,
  }));
}
