# Release Checklist

Use this checklist before publishing a new version of `spec-superflow`.

## Repository Shape

- `README.md` is current
- `docs/README_en.md` is current
- `INSTALL.md` matches the supported installation story
- `CHANGELOG.md` contains the new release entry
- `LICENSE` is present
- `.claude-plugin/plugin.json` has the intended version
- `.claude-plugin/marketplace.json` version matches `plugin.json`
- `.cursor-plugin/plugin.json` version matches `plugin.json`
- `gemini-extension.json` version matches `plugin.json`
- All 7 manifests can be synced via `ssf version <semver>`

## Workflow Integrity

- skill descriptions still match their actual responsibilities
- `workflow-start` still acts as the primary entry point
- `contract-builder` still requires explicit approval before execution
- planning artifacts and execution contract roles remain distinct
- self-contained ownership is preserved

## Templates And Docs

- templates reflect the current workflow expectations
- `docs/artifact-contract.md` matches the templates and skills
- `docs/state-machine.md` matches the actual workflow routing model
- examples still demonstrate the documented workflow

## Example Quality

For each example in `docs/examples/`:

- `README.md` explains the scenario
- `proposal.md` defines intent and scope
- `specs/` define testable behavior
- `design.md` defines technical shape and constraints
- `tasks.md` defines execution order
- `execution-contract.md` defines approved build rules

## CLI And Config

- `node scripts/spec-superflow.mjs doctor` — all checks pass
- `node scripts/spec-superflow.mjs version <version> --dry-run` — all manifests in sync
- `node scripts/spec-superflow.mjs --help` — all subcommands listed
- `spec-superflow.config.json` absence still works (backward compatible defaults)
- `package.json` `bin` field points to correct entry script

## Publishing Checks

- there are no stray `TODO` or `TBD` markers
- links and referenced paths are still valid
- no local-only junk files are included
- `.gitignore` still excludes editor and OS artifacts

## Recommended Final Pass

Do one last read of:

- `README.md`
- `docs/README_en.md`
- `INSTALL.md`
- `skills/workflow-start/SKILL.md`
- `skills/contract-builder/SKILL.md`

If those five files feel coherent together, the release is usually in good shape.
