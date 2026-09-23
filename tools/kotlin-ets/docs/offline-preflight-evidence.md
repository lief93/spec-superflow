# Offline project preflight and evidence return

Use this entry on the network that contains the real project. It does not upload
files, edit the project, install an application, infer a module, or search for a
replacement dependency. Gradle always receives `--offline`.

## Exact command

```bash
node tools/kotlin-ets/offline-preflight.mjs \
  --project /absolute/path/to/project \
  --module :app \
  --variant debug \
  --mode page \
  --entry com.example.feature.ExampleScreen \
  --evidence /absolute/path/to/fresh/kotlin-ets-preflight
```

For a non-Android JVM module, replace `--variant debug` with the exact local
Kotlin task, for example `--compile-task compileKotlin`. Use `--mode language`
for ordinary Kotlin; page mode requires a fully qualified `--entry`.

These values are required and have no guessed defaults:

- the project root containing `gradlew`;
- the absolute Gradle module path;
- exactly one Android variant or local Kotlin compile task;
- `page` or `language` mode;
- the page entry for page mode; and
- a fresh evidence directory outside the project tree.

All wrapper distributions, plugins, dependencies, Android SDK artifacts, and
producer outputs must already be available locally. The command fails closed if
offline Gradle resolution, compiler compatibility, plugin handling, resource
collection, or adapter discovery cannot be proven. Explicit dependency source
files may be supplied with `--dependency-sources-file`. Repeat `--adapter-dir`
for project adapter module roots; each root must use the existing SPI contract.

## Result

The command prints one JSON result containing `status`, `evidence`, `share`,
`diagnosis`, and `manifest`. A completed preflight exits successfully even when
the target is blocked, because a blocked migration is a valid diagnostic result.
Collection or compiler setup failures exit unsuccessfully.

`share/summary.json` is the machine-readable summary. It records:

- source counts, the selected compile task, resource inputs, and compiler
  compatibility;
- classpath categories and compiler plugin exclusions/retentions;
- loaded adapter providers;
- all six Core Profile coverage groups, plus combined Compose and
  business/dependency coverage;
- unsupported language nodes, project adapter/dependency gaps, and every
  unsupported call with its 1-based source line and column;
- each source default used at a call site;
- every approved degradation and the blocking failure; and
- whether a target was generated.

`share/diagnosis.md` is the single human-readable diagnosis. Unknown calls and
defaults are never converted into invented values. A source default is listed
explicitly; an approved UI projection appears as a degradation; a blocking
failure produces no target.

## Evidence boundary

The evidence directory has two boundaries:

- `raw/` stays on the project network. It contains the unredacted input
  manifest, exact source/classpath lists, Gradle and compiler logs, generated
  ETS when available, and the raw Core Profile report.
- `share/` is path-redacted and ready for review. It contains `summary.json`,
  `core-profile.json`, `compiler-environment.json`, `adapter-modules.json`, the
  single `diagnosis.md`, and `evidence-manifest.json`.

`evidence-manifest.json` lists every included payload file with a SHA-256 hash,
self-identifies without a recursive hash, and lists every excluded raw file with
the reason it remains local. Infrastructure paths are replaced by tokens such as
`$PROJECT`, `$EVIDENCE`, `$TOOL`, `$HOME`, and `$GRADLE_HOME`.
Project-relative filenames, API symbols, and diagnostic text are retained
because they are needed to fix the migration; review those fields for business
sensitivity before transfer.

After review, package only the share boundary:

```bash
tar -czf kotlin-ets-offline-preflight.tar.gz \
  -C /absolute/path/to/fresh/kotlin-ets-preflight/share .
```

Do not include `raw/` in the return package unless it has undergone a separate
project-specific review.
