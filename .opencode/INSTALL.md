# Use Spec Superflow in OpenCode

Install the central repository once. OpenCode then loads its primary Agent,
Skills, Commands, bootstrap MCP, hidden setup subagent, and one hidden read-only
Reviewer in every project without copying workflow files.

## 1. Install

Clone or update the repository, then register its absolute path:

```bash
cd /absolute/path/to/spec-superflow
opencode plugin "$(pwd)" -g
```

PowerShell:

```powershell
Set-Location C:\absolute\path\to\spec-superflow
opencode plugin (Get-Location).Path -g
```

Restart OpenCode after the first installation.

## 2. Initialize or Update the Runtime

1. Open any project in OpenCode.
2. Run `/workflow-init`.
3. Confirm CLI installation or upgrade when prompted.
4. Continue after the command reports `workflow=READY`.

The command runs only in the hidden setup subagent and only prepares the
matching `ssf` CLI through the two bootstrap MCP tools. It does not inspect the
project, load workflow Skills, configure the optional VS Code MCP, or create a
Change.

## 3. Start Development

Select the **spec-superflow** Agent and describe the requirement. The primary
Agent directly owns normal requirement workflow, planning, implementation,
tests, and repairs. It loads `workflow-start` and runs the global `ssf`
directly. During a normal requirement, it directly invokes the global `ssf`;
normal requirements never call bootstrap MCP tools.

For a full workflow, one hidden read-only Reviewer runs only at the two
Planning semantic gates and final Code Review. The primary Agent supplies the
body-free CLI-owned candidate JSON plus paths to original intent, current stage
artifacts, project standards, and necessary repository/test/runtime evidence.
The Reviewer uses ordinary project-read and terminal tools to resolve those
inputs. For final review it independently runs read-only Git status/diff/log/
show commands and reads every changed and untracked file; it does not receive
copied source or diff bodies, run tests/workflow commands, mutate files or Git,
or call another Agent. Mechanical schema/state/test checks stay with the
primary Agent. A delivery package check stays there too only when the current Specs
explicitly require a delivery package or
`tasks.md > TDD Test Plan` explicitly requires a delivery package.

## 4. Update

```bash
cd /absolute/path/to/spec-superflow
git pull
```

Restart OpenCode, then run `/workflow-init` to align the CLI version. The
Plugin does not need to be copied or reinstalled unless the repository path
changes.

## 5. Verify

```bash
opencode agent list
opencode debug skill
opencode mcp list
```

Expected:

- `spec-superflow` is the only primary Spec Superflow Agent.
- `spec-superflow-setup` and `spec-superflow-reviewer` are hidden subagents.
- Spec Superflow Skills such as `workflow-start` are listed.
- The `spec-superflow` MCP is connected and exposes only CLI status/install
  tools to OpenCode.

If the repository moves, run the install command again with its new absolute
path.
