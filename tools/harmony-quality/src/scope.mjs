import { readFile } from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";

const SOURCE_EXTENSION = /\.(?:ets|ts)$/;

function git(root, args) {
  const result = spawnSync("git", args, { cwd: root, encoding: "utf8" });
  if (result.status !== 0 || result.error) {
    throw new Error(`cannot resolve changed scope: ${result.stderr || result.error?.message}`);
  }
  return result.stdout;
}

async function changedLines(root, base) {
  const byFile = new Map();
  let currentFile;
  const diff = git(root, ["diff", "--unified=0", "--no-color", base, "--"]);
  for (const line of diff.split(/\r?\n/)) {
    if (line.startsWith("+++ b/")) {
      currentFile = line.slice(6);
      if (!SOURCE_EXTENSION.test(currentFile)) currentFile = undefined;
    } else if (currentFile && line.startsWith("@@")) {
      const match = line.match(/\+(\d+)(?:,(\d+))?/);
      if (!match) continue;
      const start = Number(match[1]);
      const count = match[2] === undefined ? 1 : Number(match[2]);
      const lines = byFile.get(currentFile) ?? new Set();
      for (let offset = 0; offset < count; offset += 1) lines.add(start + offset);
      byFile.set(currentFile, lines);
    }
  }

  const untracked = git(root, [
    "ls-files",
    "--others",
    "--exclude-standard",
    "--",
    "*.ets",
    "*.ts",
  ]);
  for (const file of untracked.split(/\r?\n/).filter(Boolean)) {
    if (!SOURCE_EXTENSION.test(file)) continue;
    const text = await readFile(path.join(root, file), "utf8");
    const count = text === "" ? 0 : text.split(/\r?\n/).length;
    byFile.set(file, new Set(Array.from({ length: count }, (_, index) => index + 1)));
  }
  return byFile;
}

export async function resolveScope(root, config, options) {
  const mode = options.mode ?? config.scope?.default ?? "changed";
  const modules = (config.project?.modules ?? []).map((module) =>
    module.replaceAll("\\", "/").replace(/\/$/, ""));
  const ownedByModule = (file) => modules.some((module) =>
    file === module || file.startsWith(`${module}/`));
  if (mode === "full") {
    return { mode, public: { mode }, includes: (file) => ownedByModule(file) };
  }
  if (mode === "module") {
    const module = options.module ?? config.scope?.module;
    if (!module || !config.project?.modules?.includes(module)) {
      throw new Error("module scope requires a configured --module");
    }
    const prefix = `${module.replaceAll("\\", "/")}/`;
    return {
      mode,
      module,
      public: { mode, module },
      includes: (file) => file === module || file.startsWith(prefix),
    };
  }
  if (mode === "changed") {
    const base = options.base ?? config.scope?.base ?? "HEAD";
    const lines = await changedLines(root, base);
    for (const file of lines.keys()) {
      if (!ownedByModule(file)) lines.delete(file);
    }
    return {
      mode,
      base,
      lines,
      public: { mode, base, files: [...lines.keys()].sort() },
      includes: (file, line) => lines.get(file)?.has(line) ?? false,
    };
  }
  throw new Error(`unsupported scope: ${mode}`);
}
