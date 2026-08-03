<h1 align="center">spec-superflow</h1>

<p align="center">
  <strong>A self-contained AI coding workflow plugin fusing OpenSpec planning + Superpowers execution discipline</strong>
</p>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://github.com/MageByte-Zero/spec-superflow/stargazers"><img src="https://img.shields.io/github/stars/MageByte-Zero/spec-superflow" alt="GitHub Stars"></a>
  <a href="https://www.npmjs.com/package/spec-superflow"><img src="https://img.shields.io/npm/v/spec-superflow" alt="npm version"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> |
  <a href="#installation">Install</a> |
  <a href="#why">Why</a> |
  <a href="#core-skills">Skills</a> |
  <a href="#workflow">Workflow</a> |
  <a href="../README.md">中文</a> |
  <a href="showcase.html">Showcase</a> |
  <a href="#faq">FAQ</a>
</p>

---

## Quick Start

Once installed, just tell your agent:

```
use workflow-start to begin
```

For the first use in an existing repository, initialize its development baseline:

```text
/spec-superflow:project-init
```

The agent inspects your current artifacts, performs **content-level detection** (comparing proposal scope vs. contract intent lock, not just file timestamps), determines your workflow stage, and routes to the correct next skill.

- New change → `use workflow-start to begin`
- Resume work → `continue the workflow`
- Unsure → `check what state we're in`

## Installation

### Claude Code (Marketplace)

Claude Code's primary installation path is the plugin marketplace:

```bash
/plugin marketplace add MageByte-Zero/spec-superflow
/plugin install spec-superflow@spec-superflow
/plugin update spec-superflow@spec-superflow   # upgrade
```

### Cursor (Skills directories / GitHub import)

```bash
npx spec-superflow@latest install-cursor

# Or run the installer directly:
curl -fsSL https://raw.githubusercontent.com/MageByte-Zero/spec-superflow/main/scripts/install-cursor.mjs | node -
```

Cursor discovers `.cursor/skills/`, `.agents/skills/`, `~/.cursor/skills/`, and compatible Claude/Codex skill directories. You can also import a GitHub repo from Customize → Rules → Remote Rule (Github).

### OpenAI Codex CLI / App

Codex uses the Plugin Directory / marketplace model. This repo ships `.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json`.

```bash
codex
/plugins

# Or add the community marketplace and install:
codex plugin marketplace add hashgraph-online/awesome-codex-plugins
codex plugin add spec-superflow@spec-superflow
```

In the Codex app, open **Plugins** and install or enable `spec-superflow`. If installed from the CLI, restart the app and enable it in the Plugins panel.

### GitHub Copilot CLI

```bash
copilot plugin marketplace add MageByte-Zero/spec-superflow
copilot plugin install spec-superflow@spec-superflow
```

### VS Code GitHub Copilot (Agent Plugin)

Run **Chat: Install Plugin From Source** from the VS Code Command Palette and
enter this repository's Git URL. Keep the built-in **Agent** selected, type
`/workflow-init`, and click the Plugin suggestion or press **Tab** to commit it
as a structured Slash Command. The bootstrap installs the matching global `ssf` CLI from the
Plugin itself. After it reports `READY`, select **Spec Superflow** from the
agent picker and start the requirement. Switching to another agent stops
applying its agent-specific instructions. The Plugin bundles its Agent, Skills
with their artifact templates, Commands, scripts, CLI source, and bootstrap MCP. Normal workflow
requests use the installed CLI directly. The plugin is installed once per user
profile and works across repositories.
Target repositories keep their own Copilot instructions and repository
skills; they do not need copies of the central `agents/`, `skills/`, `scripts/`,
or `skills/*/references/` directories. See
[vscode-agent-plugin.md](vscode-agent-plugin.md) for the complete ownership and
runtime model.

### Gemini CLI

```bash
gemini extensions install https://github.com/MageByte-Zero/spec-superflow
gemini extensions update spec-superflow   # upgrade
```

### OpenCode

```bash
cd /absolute/path/to/spec-superflow
opencode plugin "$(pwd)" -g
```

This registers the central repository path globally without copying workflow
files into target projects. Restart OpenCode, run `/workflow-init`, and select
the **spec-superflow** Agent after setup reports `workflow=READY`. The primary
Agent directly owns normal planning, implementation, tests, and repairs and
runs the global `ssf` CLI directly. Full workflows use one hidden read-only
Reviewer only at the two Planning semantic gates and final Code Review, with
a body-free CLI-owned candidate plus current paths. Reviewer uses ordinary
project-read and terminal tools to inspect artifacts, the fixed-base Git diff,
and every untracked file itself. It does not mutate files or Git or run
structural, state, workflow, or test commands; those remain primary-Agent
responsibilities.

To update, run `git pull` in the central repository, restart OpenCode, and run
`/workflow-init` again. See
[.opencode/INSTALL.md](../.opencode/INSTALL.md) for complete instructions.

### WorkBuddy / Trae

| Platform | Method | Status |
|----------|--------|--------|
| **WorkBuddy** | `npx spec-superflow@latest install-workbuddy` | Installer provided |
| **Trae IDE / TRAE Work** | `.trae/skills/`, `~/.trae/skills/`, or zip/.skill upload | Manual/import |

> Full installation guide: [INSTALL.md](../INSTALL.md)

### CLI Toolchain

```bash
npm install -g spec-superflow
```

| Command | Purpose |
|---------|---------|
| `ssf list` | List all changes and status |
| `ssf validate <dir>` | Validate artifact completeness |
| `ssf doctor` | Source-checkout maintenance check (versions, hooks, skills, docs) |
| `ssf version <semver>` | Sync version across all manifests |
| `ssf state <sub> <dir>` | Manage `.spec-superflow.yaml` state file |
| `ssf check-update` | Check for a spec-superflow update |
| `ssf infer-workflow <dir>` | Infer hotfix, tweak, or full workflow mode |
| `ssf guard check ...` | Validate a workflow state transition |
| `ssf review candidate\|record\|check ...` | Build, record, and check current independent-review evidence |
| `ssf task-brief ...` | Extract one Task or AC execution brief |
| `ssf review-package ...` | Generate a bounded review package |
| `ssf inject <dir>` | Generate multi-platform phase-guard artifacts |
| `ssf audit <dir>` | Generate decision-point audit report |
| `ssf memories init` / `list` / `check` | Create a Claude-style shared-memory index, list topics, or validate types, limits, and links |
| `ssf project check` | Validate project baseline structure, paths, and symbol references |
| `ssf install-cursor` | Deploy to `.cursor/` directory |
| `ssf install-workbuddy` | Deploy to WorkBuddy marketplace and enable skills |

### Version

- Current: `v0.15.0`
- Self-contained — no OpenSpec or Superpowers runtime required
- Upstream: [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec), [obra/superpowers](https://github.com/obra/superpowers)
- Changelog: [CHANGELOG.md](../CHANGELOG.md)

---

## Why

AI coding sessions fail in one of two ways:

- **The AI starts coding before you've decided what to build.** You say "add authorization" and it touches 40 files before you realize — RBAC or ABAC?

- **The plan is solid, but execution drifts.** The proposal, specs, and design are written, but nobody enforces testing, nobody gates reviews, and by merge time the behavior doesn't match.

**spec-superflow builds a hard wall between these two failure points:** intent exploration → formal artifacts (Schema-validated) → execution contract bridge → TDD + SDD + Review Gate enforcement → verified closure → delta spec sync to prevent spec rot.

| Principle | Meaning |
|---|---|
| Spec First | No stable planning artifacts → implementation blocked |
| Guarded Handoff | `execution-contract.md` is the only bridge to implementation |
| Strong Guardrails | Contract violations intercepted and rolled back |
| Schema Validated | Planning artifacts validated by embedded engine |
| Execute Disciplined | TDD Iron Law + SDD subagents + Review Gates |
| Self-Contained | No external runtime dependencies |

### When to Use

**✅ Recommended:** Large features, multi-person collaboration, long-term maintenance, brownfield projects needing TDD + review gates.

**❌ Skip:** One-off scripts, pure Q&A conversations.

> **v0.6.0+ auto mode detection:** hotfix (≤2 files, skips planning) and tweak (≤4 files, config/docs only, skips planning + bridging) make lightweight changes efficient too.

---

## Core Skills

| # | Skill | Stage | Purpose |
|---|-------|-------|---------|
| 1 | `project-init` | Project setup | Generate Copilot instructions and an actionable project development baseline |
| 2 | `memory-manager` | Shared auto memory | Claude-style capture and recall of team feedback, code-invisible project context, and external references |
| 3 | `workflow-start` | Entry | Content-level state detection, 8-state routing, blocks illegal transitions |
| 4 | `need-explorer` | Exploring | One question at a time, approach comparison, recommendation |
| 5 | `spec-writer` | Specifying | Generate proposal/specs/design/tasks with Schema engine validation |
| 6 | `contract-builder` | Bridging | Parse 4 artifacts → compress into execution-contract.md |
| 7 | `build-executor` | Executing | TDD Iron Law + SDD subagent-driven + Review Gates |
| 8 | `bug-investigator` | Debugging | 4-phase root cause analysis; 3+ failures → escalate |
| 9 | `code-reviewer` | Review | Structured review with 3-level severity classification |
| 10 | `release-archivist` | Closing | Verification-before-completion + archive + risk summary |
| 11 | `spec-merger` | Syncing | Delta spec → main spec merge with conflict detection |
| 12 | `grill-me` | Decision clarification | After evidence is exhausted, Primary asks one user-owned decision at a time with a recommendation and trade-off |

---

## Workflow

```text
You: "add authorization to the API"
       │
       ▼
   workflow-start     ← Single entry. Content-level detection, routes to correct skill
       │
       ▼
   exploring          need-explorer: "RBAC or ABAC? What granularity?"
       ▼
   specifying         spec-writer generates 4 artifacts + Schema validation
       ▼
   bridging           contract-builder auto-extracts → execution-contract.md
       │
  ◇ User Approval ◇   ← The only human gate
       │
       ▼
   executing          build-executor: TDD → SDD → Review Gate
       │
       ├──[bug]──→ debugging  → bug-investigator
       ▼
   closing            release-archivist: verify + archive
       ▼
   syncing            spec-merger (delta specs → main specs)
```

**Hard constraints:** No `execution-contract.md` or no approval → implementation blocked. Requirements change mid-execution → forced rollback. Bug encountered → must enter debugging state, no ad-hoc fixes.

### Fast Paths (hotfix / tweak)

- **hotfix** — ≤2 files, no new modules → minimal contract → inline execution
- **tweak** — ≤4 files, config/docs only → skip planning + bridging, direct edit

---

## FAQ

<details>
<summary><strong>How is this different from OpenSpec or Superpowers?</strong></summary>

spec-superflow is a source-level fusion, not side-by-side installation. It absorbs OpenSpec's Schema/validation/parsing engine and Superpowers' TDD/SDD/debugging/review discipline, while adding a unique contract-builder bridge layer and 8-state routing. Self-contained — no upstream runtimes needed.

</details>

<details>
<summary><strong>Can I use this alongside existing OpenSpec or Superpowers?</strong></summary>

Not recommended in the same session. Projects with existing OpenSpec artifacts can be adopted directly — `contract-builder` reads your existing proposal/specs/design/tasks to generate the execution contract.

</details>

<details>
<summary><strong>How does the execution contract detect staleness?</strong></summary>

Content-level detection, not timestamps: proposal scope changed, approved spec behavior changed, design constraints changed, or task batches changed → contract marked stale → route back to `contract-builder`.

</details>

<details>
<summary><strong>How does full SDD execution work?</strong></summary>

The visible Primary implements the approved Batches directly with TDD. It does
not dispatch another implementer or add semantic review after every AC/Batch.
After code, tests, and evidence are frozen, the fixed hidden read-only Reviewer
performs the final semantic review; `Request Changes` returns to Primary for a
bounded repair and one complete same-context re-review of the new candidate.

</details>

---

**Star the repo — find it when you need it.**
