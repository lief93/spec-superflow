# VS Code Spec Superflow Agent Plugin

The complete Spec Superflow repository is installed as one Agent Plugin. It
contains the Agent, Skills, Commands, templates, CLI source, and a small
bootstrap MCP server. Target repositories do not need a copy of those central
resources or a separate Spec Superflow download.

## Repository layout

```text
spec-superflow-plugin/
  .plugin/plugin.json
  plugin.json
  agents/
  skills/
  commands/
  servers/spec-superflow-mcp-launcher.cmd
  servers/spec-superflow-mcp.mjs
  scripts/
  templates/
  .mcp.json
  package.json
  .github/plugin/marketplace.json   # optional distribution metadata
```

VS Code checks `.plugin/plugin.json`, root `plugin.json`,
`.github/plugin/plugin.json`, and `.claude-plugin/plugin.json`, in that order.
This repository uses the OpenPlugin manifest so `.mcp.json` can start a bundled
server through `${PLUGIN_ROOT}`.

The manifest uses a kebab-case `name`, semantic `version`, `author` object, and
valid relative component paths. Skills live at
`skills/<name>/SKILL.md`, Agents use `*.agent.md`, and Commands are Markdown
prompt files under `commands/`. The `/workflow-init` prompt declares its
`name`, target `agent`, and restricted `tools`; `allowed-tools` is not a VS Code
prompt-file field.

## Runtime model

The bootstrap MCP server exposes four setup tools:

- `spec_superflow_cli_status`: a read-only check of Node, npm, the installed
  `ssf` path/version, and the Plugin version.
- `spec_superflow_install_cli`: after user confirmation, installs or updates
  the global CLI from the current `${PLUGIN_ROOT}` only.
- `spec_superflow_optional_mcp_status`: checks whether the bundled optional MCP
  definition is registered without reading URL or Token values.
- `spec_superflow_install_optional_mcp`: after user opt-in, registers the
  bundled stdio Server through the VS Code CLI.

It does not execute workflow commands, accept another package path, use a
registry URL, or accept URL or Token values as tool arguments.

After bootstrap, Skills execute `ssf state`, `ssf validate`, `ssf guard`, and
other CLI commands directly. The bootstrap verifies `ssf --version` against the
Plugin version and restores an existing usable CLI when an upgrade fails.

Node.js and npm are prerequisites. Installation is local to the installed
Plugin source; no second Spec repository or archive is required.

## Full workflow reviews

Only a `full` workflow uses the fixed hidden read-only Reviewer. The visible
Primary directly owns planning, implementation, tests, and finding repair. The
first semantic checkpoint reviews authoritative user intent, Proposal and
Specs after CLI structural validation. After approval, Primary asks the user
to confirm or adjust goals, scope, behaviors, and non-goals before detailed
Planning begins.

All three checkpoints use the same fixed identity, `Spec Superflow Reviewer`.
Each stage starts its initial review in a fresh isolated context. If that review
returns a first `Request Changes`, Primary repairs the stage exactly once and
resumes the same Reviewer context for one complete re-review of the new
candidate. A second `Request Changes` is `BLOCKED`; there is no third review or
workflow-state progression. Earlier findings or verdicts are not evidence for
the current candidate, and a later stage starts its own fresh context.

The second checkpoint reviews Design and Tasks together with all approved
upstream Planning. After approval, Primary defaults to a concise summary of
the major choices, affected areas, Batch shape, tests, findings, and risks,
while also providing the complete `design.md` and `tasks.md` paths. The user
chooses the desired reading depth and explicitly confirms or adjusts the
implementation direction.

A first blocking finding returns to Primary for one bounded repair, then to the
same stage Reviewer context after validation. The Reviewer rereads the complete
current candidate instead of reusing an earlier verdict. A question is raised
only after repository evidence is exhausted; a genuine
user-owned decision is asked by Primary one at a time with a recommendation.
Semantic drift repeats the affected review and user confirmation. Changing
only a real Tasks execution checkbox does not.

These instructions and protocol tests do not prove the actual Agent picker,
fresh Reviewer context, behaviorally read-only tool use, or Primary mediation.
Real VS Code 1.123 acceptance remains `PENDING`.

### Final review and combined runtime acceptance

After implementation, exact full completes every mechanical gate, every
applicable runtime check, required evidence rows, and PR summary before one
final independent Code Review. A package check runs only when the current Specs
explicitly require a delivery package or `tasks.md > TDD Test Plan`
explicitly requires a delivery package. Reviewer reads the frozen code candidate and exact test/risk context,
judges whether tests prove the requirements and failure paths rather than
mirroring the implementation, and does not run tests. On `Request Changes`,
Primary repairs only the located targets once; the repaired candidate and every affected
result are refrozen before the single same-context re-review. A second `Request Changes`
is `BLOCKED`. After current `Approved`, only workflow-state progression is allowed.

Final invocation contains only the Change directory and `final` stage. Reviewer
runs the read-only `ssf review candidate` command to discover the current
artifacts, evidence paths, changed files, and resolved `HEAD` base itself; no
Primary-authored candidate, path index, evidence summary, result schema, tracked
diff, untracked source text, or whole artifact/source/test/evidence body is
passed. Reviewer takes the resolved review base from the candidate,
runs read-only `git status`, fixed-base `git diff`, `git log`, and necessary
`git show`, then reads every changed-file entry and every untracked file itself.
Candidate computation writes no Review Markdown, bundle, or extra report JSON.
A user-global instruction is environment state, not part of Plugin delivery.

When a combined isolated VS Code 1.123 acceptance is executed, it should prove
these runtime properties together:

1. The Agent picker exposes only `Spec Superflow` as the user-invocable
   workflow Agent.
2. Primary invokes exactly `Spec Superflow Reviewer`; no separate Dev Agent is
   registered or invoked.
3. Primary-only, cross-stage, and prior-invocation canaries do not leak into a
   fresh Reviewer context.
4. Reviewer uses ordinary project-read and terminal tools to run the required
   read-only Git commands and read an untracked canary; candidate identity,
   porcelain status, cached diff, file bytes, and staged state remain unchanged.
   It does not run tests or any workflow command except read-only
   `ssf review candidate`, mutate Git, or invoke another Agent.
5. Reviewer output returns to Primary before Primary repairs the located target
   or asks the user; no direct Reviewer-to-user path qualifies.

Automation for this Chat acceptance is `Unavailable`. Its status stays
`PENDING` until one real isolated run records the raw trace, screenshots,
package identity, canary observations, Git/file-read trace, before/after
candidate and worktree hashes, mediation trace, and environment restoration. Static prompt,
frontmatter, unit, or protocol tests cannot convert these runtime assertions
to PASS. A truthful `PENDING` result is a disclosed runtime boundary, not a
source-only validation failure.

## Optional MCP with URL and Token

A local stdio MCP server can be bundled with the Plugin. `stdio` describes how
VS Code communicates with the process; it does not require the server to be a
separate installation. The Plugin starts bundled JavaScript through
`${PLUGIN_ROOT}/servers/spec-superflow-mcp-launcher.cmd`. On macOS and Linux,
the launcher falls back to the user's login shell when a GUI-launched VS Code
does not inherit the Node.js path. On Windows, Node.js must be on the system
`PATH`.

Business MCP is optional. A user who declines it still receives:

```text
workflow=READY, optionalMcp=SKIPPED
```

The CLI, Skills, planning, tests, and review workflow continue normally.

Credential configuration has a different scope:

| Configuration | Top-level server key | Interactive `inputs` |
|---|---|---|
| Agent Plugin `.mcp.json` | `mcpServers` | Starts the bundled bootstrap server; credentials are not defined here |
| User or workspace `mcp.json` | `servers` | Supported; VS Code prompts once and stores the value securely |

When the user opts in during `/workflow-init`,
`spec_superflow_install_optional_mcp` runs VS Code's `--add-mcp` command with
the bundled definition. It does not receive credentials. Registration returns:

```text
workflow=READY, optionalMcp=REGISTERED
```

To start it, run **MCP: List Servers**, select
**spec-superflow-optional-example**, and choose **Start Server**. VS Code then
prompts for the service URL and Token and keeps both values visible so users
can verify them. Neither value is written to the MCP configuration file or
passed through Chat. VS Code stores the entered values in its secure credentials
store. A later `/workflow-init` verifies the running Server and returns
`optionalMcp=READY`.

The registered definition uses the bundled
launcher and `servers/token-example-mcp.mjs`. The equivalent generated
configuration is documented under `examples/mcp/token-auth/`. Do not commit
Token values or service-specific URLs to the Plugin repository.

## Install and use

1. Run **Chat: Install Plugin From Source** in the VS Code Command Palette.
2. Enter the Git source for this complete repository.
3. Enable **Spec Superflow** in the Agent Plugins view.
4. Keep the built-in **Agent** selected, type `/workflow-init`, and select the
   Plugin-provided suggestion. Click it or press **Tab** so VS Code commits it
   as a structured Slash Command; do not send the candidate as plain text. The
   command automatically uses the hidden **Spec Superflow Setup** Agent, whose
   tool list contains only the bootstrap MCP and native question tool. It does
   not load the development state machine from the **Spec Superflow** Agent.
5. Approve CLI installation when needed.
6. Choose whether to configure the optional credentialed MCP. Skipping it
   returns `workflow=READY, optionalMcp=SKIPPED`.
7. When enabled, wait for `optionalMcp=REGISTERED`, then run
   **MCP: List Servers** and start **spec-superflow-optional-example**.
8. Complete the visible native VS Code URL and Token prompts. Run
   `/workflow-init` again to verify `optionalMcp=READY`.
9. After setup reports `workflow=READY`, select **Spec Superflow** and describe a
   requirement. Normal workflows use the installed CLI and do not install or
   upgrade it.

`/workflow-init` initializes, verifies, or updates the runtime. It does not
inspect the open repository, ask for requirement details, create a Change, or
start or resume development.

Run the setup command while the built-in **Agent** is selected. The command
switches to its hidden setup-only Agent for that request. Select
**Spec Superflow** only after setup reports `workflow=READY`.

Run `/workflow-init` before starting a requirement. Run it again after updating
the Plugin so the CLI version is synchronized before normal workflow use.

For local Plugin development:

```jsonc
"chat.pluginLocations": {
  "/absolute/path/to/spec-superflow-plugin": true
}
```

## Target repository ownership

The Plugin is installed once and can be selected in multiple repositories.
Each target repository keeps only its own source, tests, project Skills, task
artifacts, memory, and project guidance. `project-init` writes:

```text
.github/instructions/spec-superflow.instructions.md
docs/project/project-guidelines.md
```

It leaves an existing `.github/copilot-instructions.md` unchanged. Do not copy
the central `agents/`, `skills/`, `scripts/`, or `templates/` directories into
each target repository.

## Update and verify

Update the Plugin source and keep all manifests, `package.json`, and
`/workflow-init` on the same version. Run `/workflow-init` after the update; it
detects an older CLI and requests confirmation before upgrading it.

Verify in a real VS Code Chat runtime:

| Check | Expected |
|---|---|
| Plugin | Spec Superflow is installed and selectable |
| Command | `/workflow-init` is discoverable |
| Bootstrap MCP | `spec-superflow` starts and lists the four setup tools |
| Missing CLI | Confirmation, local install, exact version, then `READY` |
| Existing version | No reinstall |
| Optional MCP skipped | `workflow=READY, optionalMcp=SKIPPED` |
| Optional MCP registered | `workflow=READY, optionalMcp=REGISTERED` |
| Optional MCP started | VS Code prompts for visible URL and Token values; bundled Server starts |
| Optional MCP verified | A later `/workflow-init` reports `workflow=READY, optionalMcp=READY` |
| Requirement entry | Uses the CLI prepared by `/workflow-init` |
| Project init | Dedicated instructions are generated; root instructions are unchanged |

Protocol tests prove server behavior but do not replace this installed Plugin
and Chat verification.

Format references: [VS Code Agent plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins)
and [MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).
