import path from "node:path";
import { realpath } from "node:fs/promises";
import { checkProject } from "./check.mjs";
import { initializeProject } from "./init.mjs";

const INTERNAL_IO_CODES = new Set(["EACCES", "EIO", "ENOSPC", "ENOTDIR", "EPERM", "EROFS"]);

function readOption(args, name) {
  const index = args.indexOf(name);
  return index === -1 ? undefined : args[index + 1];
}

export async function run(args) {
  const [command] = args;

  if (command !== "init" && command !== "check") {
    process.stderr.write("Usage: harmony-quality <init|check> --project <path>\n");
    return 4;
  }

  const projectOption = readOption(args, "--project");
  if (!projectOption) {
    process.stderr.write("CONFIG_ERROR: --project is required\n");
    return 4;
  }

  try {
    const projectRoot = await realpath(path.resolve(projectOption));
    if (command === "check") {
      const result = await checkProject(
        projectRoot,
        {
          mode: readOption(args, "--scope"),
          module: readOption(args, "--module"),
          base: readOption(args, "--base"),
        },
      );
      process.stdout.write(`${result.report.status}: ${result.reportPath}\n`);
      return result.exitCode;
    }

    const result = await initializeProject(projectRoot, {
      force: args.includes("--force"),
    });
    if (!result.created) {
      process.stdout.write(`ALREADY_CONFIGURED: ${result.path}\n`);
      return 0;
    }
    const unresolved = Object.values(result.config.commands).some(
      ({ status }) => status === "unresolved",
    );
    process.stdout.write(
      unresolved
        ? `CONFIGURED: ${result.path}; manual configuration required\n`
        : `CONFIGURED: ${result.path}\n`,
    );
    return 0;
  } catch (error) {
    if (INTERNAL_IO_CODES.has(error.code)) {
      process.stderr.write(`INTERNAL_ERROR: ${error.message}\n`);
      return 5;
    }
    process.stderr.write(`CONFIG_ERROR: ${error.message}\n`);
    return 4;
  }
}
