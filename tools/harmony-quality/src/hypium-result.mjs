import { readFileSync, rmSync } from "node:fs";
import path from "node:path";

function resultPath(root, relativePath) {
  const target = path.resolve(root, relativePath);
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Hypium result path escapes project root: ${relativePath}`);
  }
  return target;
}

export function prepareHypiumResult(root, command) {
  if (!command.hypiumResultPath) return;
  rmSync(resultPath(root, command.hypiumResultPath), { force: true });
}

function parseSummary(text) {
  const summaries = [...text.matchAll(
    /Tests run:\s*(\d+),\s*Failure:\s*(\d+),\s*Error:\s*(\d+),\s*Pass:\s*(\d+),\s*Ignore:\s*(\d+)/g,
  )];
  if (summaries.length === 0) return undefined;
  const [, total, failures, errors, passed, ignored] = summaries.at(-1);
  return {
    total: Number(total),
    failures: Number(failures),
    errors: Number(errors),
    passed: Number(passed),
    ignored: Number(ignored),
  };
}

function parseStackFrame(line) {
  const withFunction = line.match(/^\s*at\s+(.+?)\s+\((.+):(\d+):(\d+)\)\s*$/);
  if (withFunction) {
    return {
      file: withFunction[2].replaceAll("\\", "/"),
      line: Number(withFunction[3]),
      column: Number(withFunction[4]),
      function: withFunction[1],
    };
  }
  const withoutFunction = line.match(/^\s*at\s+(.+):(\d+):(\d+)\s*$/);
  if (!withoutFunction) return undefined;
  return {
    file: withoutFunction[1].replaceAll("\\", "/"),
    line: Number(withoutFunction[2]),
    column: Number(withoutFunction[3]),
  };
}

export function parseHypiumDocument(text) {
  const summary = parseSummary(text);
  if (!summary) throw new Error("invalid Hypium result: summary is missing");

  const cases = [];
  let suite;
  let testName;
  let stack = [];
  for (const line of text.split(/\r?\n/)) {
    if (line.startsWith("class=")) suite = line.slice(6);
    else if (line.startsWith("test=")) {
      testName = line.slice(5);
      stack = [];
    } else if (testName) {
      const frame = parseStackFrame(line);
      if (frame) stack.push(frame);
    }
    if (line.startsWith("result=")) {
      if (!suite || !testName) throw new Error("invalid Hypium result: case identity is missing");
      const raw = line.slice(7);
      const status = raw === "Success"
        ? "passed"
        : raw === "Ignore"
          ? "skipped"
          : raw === "Failure" || raw === "Error"
            ? "failed"
            : undefined;
      if (!status) throw new Error(`invalid Hypium case result: ${raw}`);
      cases.push({
        id: `${suite}/${testName}`,
        name: `${suite}/${testName}`,
        status,
        durationMs: 0,
        ...(stack.length > 0 ? { stack } : {}),
      });
      testName = undefined;
      stack = [];
    }
  }

  const countsMatch = cases.length === summary.total &&
    cases.filter(({ status }) => status === "passed").length === summary.passed &&
    cases.filter(({ status }) => status === "failed").length === summary.failures + summary.errors &&
    cases.filter(({ status }) => status === "skipped").length === summary.ignored;
  if (!countsMatch) {
    throw new Error("Hypium result summary does not match parsed cases");
  }
  return { cases, summary };
}

export function readHypiumResult(root, command) {
  if (!command.hypiumResultPath) return undefined;
  let text;
  try {
    text = readFileSync(resultPath(root, command.hypiumResultPath), "utf8");
  } catch (error) {
    if (error.code === "ENOENT") {
      return { outcome: "infrastructure-error", reason: "hypium-result-missing" };
    }
    throw error;
  }

  const summary = parseSummary(text);
  if (!summary) {
    return { outcome: "infrastructure-error", reason: "hypium-result-invalid" };
  }
  return summary.failures > 0 || summary.errors > 0
    ? { outcome: "test-failure", reason: "hypium-test-failure", summary }
    : { outcome: "pass", summary };
}
