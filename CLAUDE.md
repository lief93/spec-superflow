# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`spec-superflow` is a self-contained Claude Code plugin that fuses OpenSpec-style planning with Superpowers-style execution discipline. It is distributed as a set of skills in `skills/` plus a small TypeScript validation/parser engine in `src/`. The plugin supports multiple clients, but this repository is primarily developed and tested as a Claude Code plugin.

Current version: `0.8.4`.

## Commands

Requires **Node >= 22**.

```bash
# Install dependencies
npm ci

# Compile TypeScript (src/ -> dist/)
npm run build

# Run all tests (tests import from dist/, so build first)
npm test

# Run a single test by name pattern
node --test --experimental-strip-types --test-name-pattern="parseDeltaSpec" tests/e2e.test.ts

# Validate planning artifacts in a change directory
npm run validate -- docs/examples/add-dark-mode
# or directly via the CLI
node scripts/spec-superflow.mjs validate docs/examples/add-dark-mode

# Run health checks
node scripts/spec-superflow.mjs doctor

# List available CLI commands
node scripts/spec-superflow.mjs --help
```

There is no lint script — the project keeps zero runtime dependencies and relies on `tsc --strict` for type checking.

## Architecture

The repository has two layers: an embedded TypeScript engine and a skill-based workflow layer.

### Engine (`src/`)

Compiles to `dist/` with `tsc` (ES2022, NodeNext, strict). Tests import from `dist/index.js`, so always build before testing.

- `schema/` — Type definitions: `Requirement`, `Scenario`, `Delta`, `Change`, `Spec`.
- `parsing/` — Regex-based parsers: `parseDeltaSpec` extracts ADDED/MODIFIED/REMOVED/RENAMED blocks; `parseChangeMarkdown` extracts `## Why`, `## What Changes`, and inline delta sections from proposals.
- `validation/` — `Validator` enforces artifact rules, runs three-dimensional implementation verification (Completeness / Correctness / Coherence), detects sync conflicts, and tokenizes English and Chinese text. `constants.ts` holds thresholds such as minimum Why length and max deltas per change.
- `index.ts` — Public API surface.

### Workflow (`skills/`)

Nine skills that operate as a state machine. Each skill is a directory containing `SKILL.md` (loaded by Claude Code as instructions) and, where needed, sub-prompts for subagents.

| Skill | Phase | Purpose |
|-------|-------|---------|
| `workflow-start` | Entry | Content-level state detection; routes to the correct skill and blocks illegal transitions |
| `need-explorer` | Exploring | One-question-at-a-time elicitation with 2–3 approach comparisons |
| `spec-writer` | Specifying | Generates planning artifacts and validates them against schema rules |
| `contract-builder` | Bridging | Parses planning artifacts and compresses them into `execution-contract.md` |
| `build-executor` | Executing | TDD + SDD subagent execution + Review Gates |
| `bug-investigator` | Debugging | 4-phase root-cause analysis; escalates after repeated failures |
| `code-reviewer` | Review | Structured review with Critical / Important / Minor severity |
| `release-archivist` | Closing | Verification-before-completion, archiving, risk summary |
| `spec-merger` | Syncing | Merges delta specs into main specs with conflict detection |

### State Machine

Seven primary states plus a debugging side-path from `executing`:

```text
exploring → specifying → bridging → approved-for-build → executing → closing
                ↑           ↑            |          ↑     |
                |           |            v          |     |
                |           |        debugging ─────┘     |
                |           |                             |
                └───────────┴─────────────────────────────┘
                  scope change → re-specify    contract drift → re-bridge
```

`workflow-start` is the single entry point. It determines state by reading artifact content, not just file existence.

### Validation Rules

`src/validation/validator.ts` enforces:

- **spec.md**: every requirement must contain `SHALL` or `MUST` and at least one `#### Scenario:` block.
- **Delta spec**: ADDED/MODIFIED sections must have requirement text and scenarios; cross-section conflicts (e.g., the same requirement in both MODIFIED and REMOVED) are blocked.
- **proposal.md**: `## Why` must be ≥ 50 characters; `## What Changes` cannot be empty.
- **Implementation verification**: compares a diff against specs and design decisions across Completeness, Correctness, and Coherence.

`Validator` returns a `ValidationReport`: `{ valid, issues: [{ level, path, message }], summary }`. Strict mode treats warnings as errors.

### Fast Paths and Guardrails (v0.6.0)

- **hotfix** mode — ≤2 files, no new modules, no schema changes; skips full exploration and specification.
- **tweak** mode — ≤4 files, only config/docs changes; skips exploration, specification, and bridging.
- `scripts/guard/guard.mjs` checks five dimensions before allowing a change to proceed.
- `rules/phase-guard.md` / `.claude/always/phase-guard.md` provide per-session drift prevention.
- `docs/decision-points.md` documents the seven standard decision points.

### Helper Scripts (`scripts/`)

- `spec-superflow.mjs` — CLI entrypoint for `ssf` / `spec-superflow` commands.
- `lib/` — CLI subcommand modules (`cmd-validate.mjs`, `cmd-doctor.mjs`, `cmd-state.mjs`, etc.), config loader, hash utilities, and state loader.
- `validate-artifacts` — Reads a change directory, validates `proposal.md` + all `specs/*/spec.md`, and prints a report.
- `task-brief` — Extracts a single task's markdown from an implementation plan.
- `review-package` — Generates a review diff from `BASE..HEAD`.

### Hooks

- `hooks/session-start` — Detects the current client and injects `workflow-start/SKILL.md` as session context.
- `hooks/hooks.json` — Claude Code hook config (triggers on Startup / Clear / Compact).
- `hooks/hooks-cursor.json` — Cursor equivalent.

### Key Files

- `templates/*.md` — Templates for the five artifacts (`proposal`, `spec`, `design`, `tasks`, `execution-contract`).
- `changes/<change-name>/` — In-flight change directories containing planning artifacts, delta specs, and the execution contract.
- `docs/examples/` — Two complete change sets (`add-dark-mode`, `refactor-auth-boundary`) used as real test data.
- `docs/state-machine.md` — Formal state-machine documentation.
- `docs/artifact-contract.md` — Artifact roles and mapping from planning to execution.
- `docs/decision-points.md` — Standard decision-point protocol.
- `spec-superflow.config.json` — Optional configuration (absence uses built-in defaults).

## Hard Constraints

- No `execution-contract.md` or no user approval → implementation is **blocked**.
- Requirements change mid-execution → forced rewind to `specifying` or `bridging`.
- Bug encountered → must enter `debugging` state; no ad-hoc fixes.
- Contract scope drift detected (proposal intent lock ≠ contract intent) → re-bridge.

## Design Decisions

- **`dist/` is committed** — the plugin is consumed via skills and scripts, not as an npm package. Tracking `dist/` lets validation scripts work immediately after cloning.
- **Tests import from `dist/`, not `src/`** — always run `npm run build` before `npm test`.
- **Content-level stale detection** — `workflow-start` compares proposal scope against the contract intent lock, not file timestamps.
- **Self-contained** — does not require OpenSpec or Superpowers to be installed. Absorbed concepts are reimplemented here.
- **Zero runtime dependencies** — only `typescript` is a devDependency.
- **Regex-based parsing** — no Zod or runtime validation libraries.
- **Multi-platform, single source** — the same skills are packaged for Claude Code, Cursor, Codex, Copilot CLI, Gemini CLI, OpenCode, and Trae via platform-specific manifests.

## CI/CD

`.github/workflows/ci.yml`:

- **Push / PR to `main`**: `npm ci` → `npm run build` → `npm test` on Node 22.
- **Tag push `v*`**: build + test → `gh release create` → `npm publish --provenance --access public`.
- Release requires the `NPM_TOKEN` secret and `id-token: write` permission for provenance.

## Testing

Tests use Node's native test runner with `--experimental-strip-types` so `.ts` test files run directly. They import the compiled engine from `dist/index.js`, so `npm run build` must run before `npm test`. Test data lives in `docs/examples/` — real planning artifacts from `add-dark-mode` and `refactor-auth-boundary`.

## Release Checklist

Before publishing, see `docs/release-checklist.md`. Key items:

- Keep `README.md`, `INSTALL.md`, `CHANGELOG.md`, and all plugin manifest versions in sync. Use `ssf version <semver>` to sync manifests.
- Verify all examples are complete (`README.md`, `proposal.md`, `specs/`, `design.md`, `tasks.md`, `execution-contract.md`).
- Run `node scripts/spec-superflow.mjs doctor` and resolve any failures.
- Remove stray `TODO` or `TBD` markers.
- Confirm `package.json` version matches `.claude-plugin/plugin.json`.
