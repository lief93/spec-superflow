import assert from "node:assert/strict";
import test from "node:test";
import { calculateScores } from "../src/scoring.mjs";

function metric(id, value) {
  return { id, value, evidence: [`evidence:${id}`] };
}

test("category and overall scores match independently worked non-perfect values", () => {
  const metrics = [
    metric("acceptance_coverage", 80),
    metric("test_pass_rate", 60),
    metric("branch_coverage", 60),
    metric("function_coverage", 100),
    metric("line_coverage", 80),
    metric("mutation_score", 50),
    metric("reliability_issue_count", 2),
    metric("code_smell_count", 2),
    metric("duplication_percent", 5),
    metric("max_complexity", 8),
    metric("max_crap", 20),
  ];
  const issues = [
    { category: "reliability", severity: "critical" },
    { category: "reliability", severity: "major" },
  ];

  const scores = calculateScores({ analysis: {} }, metrics, issues);

  assert.deepEqual(
    scores.map(({ id, value }) => [id, value]),
    [
      ["functionality_suitability", 70],
      ["maintainability", 66],
      ["overall", 68.45],
      ["reliability", 65],
      ["test_quality", 72.5],
    ],
  );
});

test("severity penalties clamp reliability at zero", () => {
  const issues = Array.from({ length: 3 }, () => ({
    category: "reliability",
    severity: "blocker",
  }));

  const scores = calculateScores(
    { analysis: {} },
    [metric("reliability_issue_count", 3)],
    issues,
  );

  assert.equal(scores.find(({ id }) => id === "reliability").value, 0);
  assert.equal(scores.find(({ id }) => id === "maintainability").value, 100);
  assert.equal(scores.find(({ id }) => id === "overall").value, 44.44);
});
