# VS Code Spec Superflow VSIX

The recommended offline distribution is one VSIX containing the complete Agent
Plugin, CLI source, two bootstrap Language Model Tools, and a replaceable
one-shot Example MCP bridge. Target repositories do not copy those shared
resources or install a second Spec Superflow package.

## Repository layout

```text
spec-superflow-<version>.vsix
  extension/package.json            # Language Model Tools + chatPlugins
  extension/extension.cjs           # fixed one-shot bridge
  extension/agent-plugin/
    plugin.json
    agents/
    commands/
    skills/
    scripts/
    servers/
    package.json
```

The extension manifest contributes `chatPlugins` at `./agent-plugin`, so the
Agent Plugin and bootstrap tools are discovered from the same installation.
The staged Agent Plugin intentionally has no `.mcp.json`: this path works when
an organization disables the native VS Code MCP Host but still permits
Extension Language Model Tools. Do not enable a second Git-installed copy of
the same Agent Plugin, or duplicate Spec Agents can appear.

## Runtime model

The extension exposes two setup tools:

- `spec_superflow_cli_status`: a read-only check of Node, npm, the CLI under
  `npm prefix -g`, its PATH resolution, and the Plugin version.
- `spec_superflow_install_cli`: after user confirmation, installs or updates
  the global CLI from the VSIX-bundled Agent Plugin only.

`/workflow-init` uses only these tools and the native confirmation tool. It
does not execute workflow commands, configure business MCPs, accept another
package path, or use a registry URL.

After bootstrap, Skills execute `ssf state`, `ssf validate`, `ssf guard`, and
other CLI commands directly. The bootstrap uses the CLI under `npm prefix -g`
as the installed version authority and returns ready only when bare `ssf`
resolves to that same executable. It restores the existing global CLI when an
upgrade fails.

Node.js and npm are prerequisites. Installation is local to the VSIX-bundled
Plugin source; no second repository, registry, or archive is required.

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

## Replaceable Example MCP bridge

The VSIX also contributes `spec_superflow_example_mcp_read`. The bundled
`example-mcp-reader` Skill passes only the user's item URL or key. On first
use, the extension collects the example URL through visible VS Code input and
stores the Token in VS Code SecretStorage. Neither value is a tool argument or
Chat value.

For each call, the extension starts `servers/example-item-mcp.mjs`, performs
one fixed allowlisted MCP call, and closes the process. The upstream example
returns deterministic local data and makes no network request. A company fork
can replace the Server and fixed tool mapping with its Jira stdio MCP without
changing the Skill-to-tool boundary. This Example MCP is independent of
`/workflow-init` and never changes CLI readiness.

## Install and use

1. Run **Extensions: Install from VSIX...** in the Command Palette.
2. Select the offline `spec-superflow-<version>.vsix` file and reload VS Code.
3. Confirm that **Spec Superflow** appears exactly once. Do not also install
   the same Agent Plugin from Git.
4. Keep the built-in **Agent** selected, type `/workflow-init`, and select the
   Plugin-provided suggestion. Click it or press **Tab** so VS Code commits it
   as a structured Slash Command; do not send the candidate as plain text. The
   command remains in the built-in **Agent** and the same Chat. It declares only
   the two extension bootstrap tools and native question tool, and instructs the
   model not to inspect the workspace, use a terminal, access memory, or load the
   development state machine.
5. Approve CLI installation when needed.
6. After setup reports `READY`, select **Spec Superflow** and describe a
   requirement. Normal workflows use the installed CLI and do not install or
   upgrade it.

`/workflow-init` initializes, verifies, or updates the runtime. It does not
inspect the open repository, ask for requirement details, create a Change, or
start or resume development.

Run the setup command while the built-in **Agent** is selected. It remains in
the current Agent and Chat, so `/workflow-init` can be run again without a
handoff or a new Chat. Select **Spec Superflow** only after setup reports
`READY`.

Run `/workflow-init` before starting a requirement. Run it again after updating
the Plugin so the CLI version is synchronized before normal workflow use.

The Example MCP is invoked later by its Skill and is not part of setup.

## Target repository ownership

The Plugin is installed once and can be selected in multiple repositories.
Each target repository keeps only its own source, tests, project Skills, task
artifacts, memory, and project guidance. `project-init` writes:

```text
.github/instructions/spec-superflow.instructions.md
docs/project/project-guidelines.md
```

It leaves an existing `.github/copilot-instructions.md` unchanged. Do not copy
the central `agents/`, `skills/`, `scripts/`, or `skills/*/references/` directories into
each target repository.

## Update and verify

Install the newer offline VSIX over the existing extension, reload VS Code,
then run `/workflow-init`. It detects an older CLI and requests confirmation
before upgrading it from the new bundled Plugin source.

Verify in a real VS Code Chat runtime:

| Check | Expected |
|---|---|
| Plugin | Spec Superflow is installed and selectable |
| Command | `/workflow-init` is discoverable |
| Bootstrap tools | `specSuperflowCliStatus` and `specSuperflowInstallCli` are available |
| Missing CLI | Confirmation, local install, exact version, then `READY` |
| Existing version | No reinstall |
| Example MCP | Skill invokes `spec_superflow_example_mcp_read`; one process starts and exits |
| Credentials | Native visible prompts; Token absent from Chat and tool result |
| Requirement entry | Uses the CLI prepared by `/workflow-init` |
| Project init | Dedicated instructions are generated; root instructions are unchanged |

Protocol tests prove server behavior but do not replace this installed Plugin
and Chat verification.

Format references: [VS Code Agent plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins).
