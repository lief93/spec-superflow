---
name: workflow-init
description: Install and verify the global spec-superflow CLI required by this Plugin.
---

<!-- spec-superflow-cli-version: 0.14.0 -->

# Initialize Spec Superflow

This is a Plugin setup command, not a development request. Follow this command
directly instead of the Agent's `workflow-start` route. Do not inspect the open
workspace, read development Skills, create task artifacts, or start the
development workflow.

Execute only the following checks and installation:

1. Run `node --version`. If Node.js is missing or lower than 22, stop and report
   that Node.js 22 or newer must be installed through the approved company
   software channel.
2. Run `ssf --version`.
3. If the installed CLI reports version `0.14.0`, do not reinstall it.
4. If `ssf` is missing or reports a different version:

   - When the user supplied `package=<path>`, verify that the file exists and
     is named `spec-superflow-0.14.0.tgz`, then run:

     ```bash
     npm install -g "<path>"
     ```

   - Otherwise run:

     ```bash
     npm install -g spec-superflow@0.14.0
     ```

   Use the npm registry already configured on the machine or the explicitly
   supplied local package. Respect the terminal approval shown by the client.
   Do not use `sudo`, change npm registry settings, search for another package,
   or request credentials. If registry installation fails, report `BLOCKED`
   and tell the user to rerun `/workflow-init package=<absolute-tgz-path>`.
5. Run `ssf --version` again. Initialization succeeds only when it reports
   version `0.14.0`.

Report one of these results:

- `READY`: Node.js and spec-superflow CLI versions are compatible.
- `BLOCKED`: include the failed command and the approved installation action
  required from the user or administrator.
