// ssf quality <init|check> — run the bundled Harmony Quality CLI
import { run as runHarmonyQuality } from '../../tools/harmony-quality/src/cli.mjs';

export async function run(args) {
  process.exitCode = await runHarmonyQuality(args);
}
