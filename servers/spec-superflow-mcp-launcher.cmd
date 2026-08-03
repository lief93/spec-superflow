#!/bin/sh
:; if command -v node >/dev/null 2>&1; then exec node "$@"; fi; if [ -n "${SHELL:-}" ] && [ -x "$SHELL" ]; then exec "$SHELL" -lic 'exec node "$@" >&3' spec-superflow-mcp-launcher "$@" 3>&1 1>&2; fi; plugin_app="VS Code"; if [ "${SPEC_SUPERFLOW_PLUGIN_HOST:-vscode}" = "opencode" ]; then plugin_app="OpenCode"; fi; echo "Node.js 22 or newer was not found. Install Node.js and restart $plugin_app." >&2; exit 127
@echo off
set "SPEC_SUPERFLOW_PLUGIN_APP=VS Code"
if /I "%SPEC_SUPERFLOW_PLUGIN_HOST%"=="opencode" set "SPEC_SUPERFLOW_PLUGIN_APP=OpenCode"
where node >nul 2>&1
if errorlevel 1 (
  >&2 echo Node.js 22 or newer was not found. Install Node.js and restart %SPEC_SUPERFLOW_PLUGIN_APP%.
  exit /b 127
)
node %*
exit /b %errorlevel%
