# VS Code Spec Superflow Agent Plugin

The complete Spec Superflow repository is the Plugin. Installing it from a Git
source clones the agents, skills, commands, templates, scripts, and bundled MCP
bridge as one unit. No separate Spec Superflow package or global CLI is needed.

## Repository layout

```text
spec-superflow-plugin/
  .plugin/plugin.json
  plugin.json
  agents/
  skills/
  commands/
  servers/spec-superflow-mcp.mjs
  scripts/
  templates/
  .mcp.json
  package.json
  .github/plugin/marketplace.json   # optional
```

VS Code checks `.plugin/plugin.json`, root `plugin.json`,
`.github/plugin/plugin.json`, and `.claude-plugin/plugin.json`, in that order.
This repository uses the OpenPlugin manifest so MCP configuration can reference
bundled files through `${PLUGIN_ROOT}`.

The manifest must use a kebab-case `name`, a semantic `version`, an `author`
object, and valid relative component paths. Each skill must be stored at
`skills/<name>/SKILL.md`; its directory and frontmatter names must match and use
kebab-case without a namespace prefix. Agents use `*.agent.md`. Commands are
Markdown prompt files in `commands/`.

## Bundled runtime

`.mcp.json` starts `servers/spec-superflow-mcp.mjs` from `${PLUGIN_ROOT}`. The
bundled MCP bridge provides:

- `spec_superflow_health`, which verifies the installed Plugin runtime.
- `spec_superflow_run`, which executes the Plugin's deterministic workflow
  scripts with the open repository as their working directory.

The selected Agent maps logical `ssf <args>` instructions from the Skills to the
MCP tool. Workflow artifacts are written to the open repository, while runtime
code remains in the Plugin.

`/workflow-init` only calls the health tool. It does not install, download, or
update another package.

## Build a Plugin repository

1. Copy the complete Spec Superflow repository, not only `.github/`.
2. Keep `agents/`, `skills/`, `commands/`, `servers/`, `scripts/`, `templates/`,
   and committed runtime output such as `dist/`.
3. Add or verify `.plugin/plugin.json` and `.mcp.json`.
4. Commit the repository to an accessible Git source.
5. Run **Chat: Install Plugin From Source** and enter that Git URL.

The `.github/` directory is optional. Its marketplace manifest is needed only
for marketplace distribution. Its Copilot Instructions govern maintenance of
the Plugin repository itself; they do not replace the Plugin manifest.

For local development, register the checkout directly:

```jsonc
"chat.pluginLocations": {
  "/absolute/path/to/spec-superflow-plugin": true
}
```

After installation, select **Spec Superflow**, run `/workflow-init`, and verify
that `MCP: List Servers` shows `spec-superflow`. Project-specific Instructions,
Skills, task artifacts, memory, source code, and tests remain in each target
repository.

See the [VS Code Agent plugins documentation](https://code.visualstudio.com/docs/agent-customization/agent-plugins)
and [GitHub Copilot CLI plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference).
