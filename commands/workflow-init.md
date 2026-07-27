---
name: workflow-init
description: Prepare the Spec Superflow CLI and optionally configure the bundled credentialed MCP.
agent: Spec Superflow
tools:
  - 'spec-superflow/*'
  - 'spec-superflow-optional-example/*'
  - 'vscode/askQuestions'
---

<!-- spec-superflow-plugin-version: 0.14.0 -->

# Initialize Spec Superflow

This is a Plugin setup command, not a development request. Follow this command
directly instead of the Agent's `workflow-start` route. Do not inspect the open
workspace, read development Skills, create task artifacts, or start the
development workflow.

Do not announce project initialization, workspace inspection, or artifact
creation. The first action is #tool:spec-superflow/spec_superflow_cli_status.
Treat its JSON as
authoritative: a completed tool call is not a successful setup. Continue only
when `ready` is `true` and the CLI version exactly matches the Plugin version.
When `requiredAction` is `request-install-confirmation`, request confirmation
before any other action.

This command has a closed tool sequence. Do not read the workspace, any file,
or any Skill, even when the workspace is empty. Do not route to project-init
or workflow-start. After the CLI is verified, the next and only tool call is
#tool:spec-superflow/spec_superflow_optional_mcp_status.

1. Call #tool:spec-superflow/spec_superflow_cli_status.
2. If the tool is unavailable because `node` cannot start it, report `BLOCKED`
   with Node.js as the missing prerequisite.
3. If npm is unavailable, report `BLOCKED` with npm as the missing prerequisite.
4. The status tool executes `ssf --version`. If it reports `ready: true` and
   both Plugin and CLI versions are exactly `0.14.0`, continue.
5. If the CLI is missing or has another version, use
   #tool:vscode/askQuestions to ask whether the user wants to install or update
   the global `ssf` command from this Plugin's bundled source. Call
   #tool:spec-superflow/spec_superflow_install_cli only after an explicit `Yes`.
6. If the user declines, or the tool call is cancelled, unavailable, or
   unsuccessful,
   immediately report `CANCELLED` or `BLOCKED` and stop. Do not use terminal,
   file, alternate installation, or development tools.
7. After a successful install, call
   #tool:spec-superflow/spec_superflow_cli_status again. The workflow runtime
   is ready only when it reports `ready: true` and version `0.14.0`.
8. On installation, permission, PATH, rollback, or version errors, report
   `BLOCKED` with the tool's recovery guidance. Never claim `READY` from npm's
   exit code alone.
9. After the CLI is verified, call
   #tool:spec-superflow/spec_superflow_optional_mcp_status.
   Business MCP is optional and must never block the Spec workflow.
10. If the optional MCP is already registered and
    #tool:spec-superflow-optional-example/spec_superflow_token_example_status
    is available, call it. Report `workflow=READY, optionalMcp=READY` only when
    it returns `configured: true`. If the credential tool is unavailable,
    report `workflow=READY, optionalMcp=REGISTERED` and explain how to start it
    as described in step 14.
11. If the optional MCP is not registered, use #tool:vscode/askQuestions to ask whether the
    user wants to configure it. This question is mandatory for the current
    invocation: an unconfigured status is not a decline. You must not report
    `optionalMcp=SKIPPED` unless #tool:vscode/askQuestions returns an explicit
    `No` answer. If the user declines, report
    `workflow=READY, optionalMcp=SKIPPED` and stop.
    If the user declines optional MCP, it does not block workflow
    initialization.
12. If the user opts in, call
    #tool:spec-superflow/spec_superflow_install_optional_mcp without arguments.
    Do not pass the service URL or Token as a tool argument and do not ask the
    user to paste either value into Chat.
13. A newly registered MCP is not guaranteed to become callable in the current
    Chat. Do not use #tool:vscode/askQuestions for the URL or Token. Report
    `workflow=READY, optionalMcp=REGISTERED`; the Spec workflow is ready.
14. Tell the user to run **MCP: List Servers**, select
    **spec-superflow-optional-example**, and choose **Start Server**. VS Code
    then collects the URL and Token through visible native input prompts so the
    user can verify both values. Neither value is written to the MCP
    configuration file or passed through Chat; VS Code stores the entered
    values in its secure credentials store. A later `/workflow-init` can call
    #tool:spec-superflow-optional-example/spec_superflow_token_example_status
    and report `optionalMcp=READY` without revealing either value.
15. If optional MCP registration or credential verification fails, report
    `workflow=READY, optionalMcp=BLOCKED` with the recovery guidance. The CLI
    workflow remains available.

Do not provide a URL, registry, package name, archive, or alternate path to the
CLI or optional MCP install tools. Do not modify the open workspace. Do not
start or resume a development request after this command.
